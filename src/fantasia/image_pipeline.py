from __future__ import annotations

import shutil
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter


@dataclass(frozen=True)
class ProcessedImageSet:
    source_image: Path
    no_bg_image: Path
    face_image: Path
    bordered_image: Path
    metadata: dict[str, Any]


def process_subject_image(
    source: Path,
    work_dir: Path,
    *,
    source_image_name: str,
    border_color: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> ProcessedImageSet:
    work_dir.mkdir(parents=True, exist_ok=True)
    source_image = work_dir / source_image_name
    no_bg_image = work_dir / "no_bg_image.png"
    face_image = work_dir / "face_image.png"
    bordered_image = work_dir / "add_border_image.png"

    _copy_normalized_png(source, source_image)
    removal_meta = remove_background(source_image, no_bg_image)
    face_meta = crop_face(no_bg_image, face_image)
    border_meta = add_alpha_border(no_bg_image, bordered_image, color=border_color)

    return ProcessedImageSet(
        source_image=source_image,
        no_bg_image=no_bg_image,
        face_image=face_image,
        bordered_image=bordered_image,
        metadata={
            "background_removal": removal_meta,
            "face_detection": face_meta,
            "border": border_meta,
        },
    )


def remove_background(source: Path, target: Path) -> dict[str, Any]:
    image = Image.open(source).convert("RGBA")
    bg = _corner_background_color(image)
    threshold = 48
    soft_threshold = 88
    background_mask = _edge_connected_background_mask(image, bg, soft_threshold)
    pixels = []
    removed = 0
    softened = 0
    for index, (red, green, blue, alpha) in enumerate(image.getdata()):
        if not background_mask[index]:
            pixels.append((red, green, blue, alpha))
            continue
        distance = abs(red - bg[0]) + abs(green - bg[1]) + abs(blue - bg[2])
        if distance <= threshold:
            pixels.append((red, green, blue, 0))
            removed += 1
        elif distance <= soft_threshold:
            fade = int(alpha * ((distance - threshold) / max(soft_threshold - threshold, 1)))
            pixels.append((red, green, blue, max(0, min(alpha, fade))))
            softened += 1
        else:
            pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    image.save(target)
    repair_meta = repair_internal_alpha_holes(source, target)
    return {
        "method": "edge_connected_corner_color_alpha",
        "background_color": bg,
        "removed_pixels": removed,
        "softened_pixels": softened,
        "edge_connected_pixels": int(sum(background_mask)),
        "hole_repair": repair_meta,
        "image_size": list(image.size),
    }


def repair_internal_alpha_holes(source: Path, target: Path, alpha_threshold: int = 16) -> dict[str, Any]:
    source_image = Image.open(source).convert("RGBA")
    image = Image.open(target).convert("RGBA")
    width, height = image.size
    alpha = image.getchannel("A")
    transparent = bytearray(1 if value <= alpha_threshold else 0 for value in alpha.getdata())
    exterior = _edge_connected_binary_mask(transparent, width, height)
    source_pixels = list(source_image.getdata())
    pixels = list(image.getdata())
    restored = 0
    for index, is_transparent in enumerate(transparent):
        if not is_transparent or exterior[index]:
            continue
        red, green, blue, source_alpha = source_pixels[index]
        pixels[index] = (red, green, blue, max(source_alpha, 255))
        restored += 1
    if restored:
        image.putdata(pixels)
        image.save(target)
    return {
        "method": "restore_internal_alpha_holes",
        "restored_pixels": restored,
        "alpha_threshold": alpha_threshold,
    }


def crop_face(source: Path, target: Path) -> dict[str, Any]:
    image = Image.open(source).convert("RGBA")
    bbox = _alpha_bbox(image)
    if not bbox:
        bbox = (0, 0, image.width, image.height)
        method = "center_fallback"
        crop_box = _square_crop_around(
            image,
            image.width // 2,
            image.height // 2,
            min(image.width, image.height),
        )
    else:
        crop_box, method = _face_crop_box(image, bbox)

    cropped = image.crop(crop_box)
    cropped.save(target)
    return {
        "method": method,
        "foreground_bbox": list(bbox),
        "crop_box": list(crop_box),
    }


def _face_crop_box(image: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[tuple[int, int, int, int], str]:
    skin_box = _skin_face_bbox(image, bbox)
    if skin_box:
        left, top, right, bottom = skin_box
        width = max(1, right - left)
        height = max(1, bottom - top)
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        fg_left, fg_top, fg_right, fg_bottom = bbox
        fg_width = max(1, fg_right - fg_left)
        fg_height = max(1, fg_bottom - fg_top)
        size = int(max(128, width * 1.6, height * 1.9, min(fg_width, fg_height) * 0.24))
        size = int(min(size, image.width, image.height, max(128, fg_width * 0.56), max(128, fg_height * 0.26)))
        center_y -= int(size * 0.04)
        return _square_crop_around(image, center_x, center_y, size), "skin_face_component"

    return _head_heuristic_crop_box(image, bbox), "foreground_head_heuristic"


def _head_heuristic_crop_box(image: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    fg_width = max(1, right - left)
    fg_height = max(1, bottom - top)
    head_bottom = min(bottom, top + int(fg_height * 0.32))
    head_region = image.crop((left, top, right, head_bottom))
    head_bbox = _alpha_bbox(head_region)
    if head_bbox:
        h_left, h_top, h_right, h_bottom = head_bbox
        center_x = left + (h_left + h_right) // 2
    else:
        center_x = left + fg_width // 2
    center_y = top + int(fg_height * 0.14)
    size = int(max(128, min(fg_width * 0.72, fg_height * 0.30)))
    size = min(size, image.width, image.height)
    return _square_crop_around(image, center_x, center_y, size)


def _square_crop_around(image: Image.Image, center_x: int, center_y: int, size: int) -> tuple[int, int, int, int]:
    size = max(1, min(int(size), image.width, image.height))
    crop_left = max(0, int(center_x) - size // 2)
    crop_top = max(0, int(center_y) - size // 2)
    crop_right = min(image.width, crop_left + size)
    crop_bottom = min(image.height, crop_top + size)
    crop_left = max(0, crop_right - size)
    crop_top = max(0, crop_bottom - size)
    return crop_left, crop_top, crop_right, crop_bottom


def _skin_face_bbox(image: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = bbox
    fg_width = max(1, right - left)
    fg_height = max(1, bottom - top)
    y_limit = min(bottom, top + int(fg_height * 0.30))
    pixels = image.load()
    visited: set[tuple[int, int]] = set()
    candidates: list[tuple[int, int, int, int, int]] = []

    def is_skin_xy(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        if alpha <= 32:
            return False
        return _is_skin_color(red, green, blue)

    for y in range(top, y_limit):
        for x in range(left, right):
            if (x, y) in visited or not is_skin_xy(x, y):
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited.add((x, y))
            comp_left = comp_right = x
            comp_top = comp_bottom = y
            area = 0
            while queue:
                px, py = queue.popleft()
                area += 1
                comp_left = min(comp_left, px)
                comp_right = max(comp_right, px)
                comp_top = min(comp_top, py)
                comp_bottom = max(comp_bottom, py)
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if nx < left or nx >= right or ny < top or ny >= y_limit:
                        continue
                    if (nx, ny) in visited or not is_skin_xy(nx, ny):
                        continue
                    visited.add((nx, ny))
                    queue.append((nx, ny))
            comp_width = comp_right - comp_left + 1
            comp_height = comp_bottom - comp_top + 1
            if area < 32 or comp_width < 4 or comp_height < 4:
                continue
            if comp_width > comp_height * 2.8:
                continue
            candidates.append((comp_left, comp_top, comp_right + 1, comp_bottom + 1, area))

    if not candidates:
        return None

    fg_center_x = left + fg_width / 2

    def score(item: tuple[int, int, int, int, int]) -> float:
        comp_left, comp_top, comp_right, comp_bottom, area = item
        comp_center_x = (comp_left + comp_right) / 2
        top_penalty = (comp_top - top) * 2.2
        center_penalty = abs(comp_center_x - fg_center_x) * 0.18
        return area ** 0.5 - top_penalty - center_penalty

    best = max(candidates, key=score)
    return best[:4]


def _is_skin_color(red: int, green: int, blue: int) -> bool:
    max_channel = max(red, green, blue)
    min_channel = min(red, green, blue)
    if red < 90 or green < 45 or blue < 25:
        return False
    if max_channel - min_channel < 18:
        return False
    if red < green - 8 or red < blue:
        return False
    y = 0.299 * red + 0.587 * green + 0.114 * blue
    cb = 128 - 0.168736 * red - 0.331264 * green + 0.5 * blue
    cr = 128 + 0.5 * red - 0.418688 * green - 0.081312 * blue
    return 70 <= y <= 255 and 75 <= cb <= 145 and 130 <= cr <= 190


def add_alpha_border(
    source: Path,
    target: Path,
    *,
    color: tuple[int, int, int, int],
    width: int = 5,
) -> dict[str, Any]:
    image = Image.open(source).convert("RGBA")
    alpha = image.getchannel("A")
    expanded = alpha
    for _ in range(max(1, width)):
        expanded = expanded.filter(ImageFilter.MaxFilter(3))
    outline_alpha = ImageChops.subtract(expanded, alpha)
    outline = Image.new("RGBA", image.size, color)
    outline.putalpha(outline_alpha)
    result = Image.alpha_composite(outline, image)
    result.save(target)
    return {"method": "alpha_outline", "width": width, "color": list(color)}


def _copy_normalized_png(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    try:
        image = Image.open(source).convert("RGBA")
    except Exception:
        shutil.copy2(source, target)
        return
    image.save(target)


def _corner_background_color(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    sample = max(4, min(width, height, 24) // 2)
    points: list[tuple[int, int, int]] = []
    boxes = (
        (0, 0, sample, sample),
        (width - sample, 0, width, sample),
        (0, height - sample, sample, height),
        (width - sample, height - sample, width, height),
    )
    for box in boxes:
        crop = image.crop(box).convert("RGB")
        points.extend(crop.getdata())
    if not points:
        return (255, 255, 255)
    red = sum(pixel[0] for pixel in points) // len(points)
    green = sum(pixel[1] for pixel in points) // len(points)
    blue = sum(pixel[2] for pixel in points) // len(points)
    return (red, green, blue)


def _edge_connected_background_mask(
    image: Image.Image,
    background_color: tuple[int, int, int],
    threshold: int,
) -> bytearray:
    rgb_pixels = list(image.convert("RGB").getdata())
    width, height = image.size

    def candidate(index: int) -> bool:
        red, green, blue = rgb_pixels[index]
        return abs(red - background_color[0]) + abs(green - background_color[1]) + abs(blue - background_color[2]) <= threshold

    mask = bytearray(width * height)
    queue: deque[int] = deque()

    def add(index: int) -> None:
        if mask[index] or not candidate(index):
            return
        mask[index] = 1
        queue.append(index)

    for x in range(width):
        add(x)
        add((height - 1) * width + x)
    for y in range(height):
        add(y * width)
        add(y * width + width - 1)

    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        if x > 0:
            add(index - 1)
        if x + 1 < width:
            add(index + 1)
        if y > 0:
            add(index - width)
        if y + 1 < height:
            add(index + width)
    return mask


def _edge_connected_binary_mask(mask_source: bytearray, width: int, height: int) -> bytearray:
    mask = bytearray(width * height)
    queue: deque[int] = deque()

    def add(index: int) -> None:
        if mask[index] or not mask_source[index]:
            return
        mask[index] = 1
        queue.append(index)

    for x in range(width):
        add(x)
        add((height - 1) * width + x)
    for y in range(height):
        add(y * width)
        add(y * width + width - 1)

    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        if x > 0:
            add(index - 1)
        if x + 1 < width:
            add(index + 1)
        if y > 0:
            add(index - width)
        if y + 1 < height:
            add(index + width)
    return mask


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    alpha = image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > 16 else 0)
    return mask.getbbox()
