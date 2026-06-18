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
    threshold = 38
    soft_threshold = 72
    protected_mask, protection_meta = _foreground_protection_mask(image, bg)
    background_mask = _edge_connected_background_mask(image, bg, soft_threshold, protected_mask=protected_mask)
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
    protected_restore_meta = restore_protected_foreground(source, target, protected_mask)
    repair_meta = repair_internal_alpha_holes(source, target)
    isolation_meta = isolate_subject_foreground(target)
    low_alpha_meta = remove_low_alpha_artifacts(target)
    return {
        "method": "edge_connected_corner_color_protected_alpha_subject_isolation",
        "background_color": bg,
        "foreground_protection": protection_meta,
        "removed_pixels": removed,
        "softened_pixels": softened,
        "edge_connected_pixels": int(sum(background_mask)),
        "protected_restore": protected_restore_meta,
        "hole_repair": repair_meta,
        "subject_isolation": isolation_meta,
        "low_alpha_cleanup": low_alpha_meta,
        "image_size": list(image.size),
    }


def restore_protected_foreground(source: Path, target: Path, protected_mask: bytearray, alpha_threshold: int = 16) -> dict[str, Any]:
    source_image = Image.open(source).convert("RGBA")
    image = Image.open(target).convert("RGBA")
    source_pixels = list(source_image.getdata())
    pixels = list(image.getdata())
    restored = 0
    for index, protected in enumerate(protected_mask):
        if not protected:
            continue
        red, green, blue, source_alpha = source_pixels[index]
        if source_alpha <= alpha_threshold:
            continue
        old_alpha = pixels[index][3]
        if old_alpha >= source_alpha:
            continue
        pixels[index] = (red, green, blue, source_alpha)
        restored += 1
    if restored:
        image.putdata(pixels)
        image.save(target)
    return {
        "method": "restore_protected_foreground",
        "restored_pixels": restored,
        "alpha_threshold": alpha_threshold,
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


def isolate_subject_foreground(target: Path, alpha_threshold: int = 16) -> dict[str, Any]:
    image = Image.open(target).convert("RGBA")
    width, height = image.size
    alpha_values = list(image.getchannel("A").getdata())
    components = _alpha_components(alpha_values, width, height, alpha_threshold)
    if len(components) <= 1:
        return {
            "method": "dominant_center_component",
            "components": len(components),
            "removed_components": 0,
            "removed_pixels": 0,
            "kept_components": len(components),
        }

    primary = _select_subject_component(components, width, height)
    keep_components = [
        component
        for component in components
        if component is primary or _is_related_subject_component(component, primary, width, height)
    ]
    keep_indices = bytearray(width * height)
    for component in keep_components:
        for index in component["indices"]:
            keep_indices[index] = 1

    pixels = list(image.getdata())
    removed_pixels = 0
    removed_components = 0
    kept_ids = {id(component) for component in keep_components}
    for component in components:
        if id(component) in kept_ids:
            continue
        removed_components += 1
        removed_pixels += int(component["area"])
        for index in component["indices"]:
            red, green, blue, _alpha = pixels[index]
            pixels[index] = (red, green, blue, 0)

    if removed_pixels:
        image.putdata(pixels)
        image.save(target)

    return {
        "method": "dominant_center_component",
        "components": len(components),
        "kept_components": len(keep_components),
        "removed_components": removed_components,
        "removed_pixels": removed_pixels,
        "primary_bbox": list(primary["bbox"]),
        "primary_area": int(primary["area"]),
        "alpha_threshold": alpha_threshold,
    }


def remove_low_alpha_artifacts(target: Path, alpha_threshold: int = 48) -> dict[str, Any]:
    image = Image.open(target).convert("RGBA")
    pixels = list(image.getdata())
    removed = 0
    cleaned: list[tuple[int, int, int, int]] = []
    for red, green, blue, alpha in pixels:
        if 0 < alpha <= alpha_threshold:
            cleaned.append((red, green, blue, 0))
            removed += 1
        else:
            cleaned.append((red, green, blue, alpha))
    if removed:
        image.putdata(cleaned)
        image.save(target)
    return {
        "method": "drop_low_alpha_artifacts",
        "removed_pixels": removed,
        "alpha_threshold": alpha_threshold,
    }


def _alpha_components(alpha_values: list[int], width: int, height: int, threshold: int) -> list[dict[str, Any]]:
    visited = bytearray(width * height)
    components: list[dict[str, Any]] = []
    for start, alpha in enumerate(alpha_values):
        if alpha <= threshold or visited[start]:
            continue
        queue: deque[int] = deque([start])
        visited[start] = 1
        indices: list[int] = []
        left = width
        top = height
        right = 0
        bottom = 0
        alpha_sum = 0
        while queue:
            index = queue.popleft()
            indices.append(index)
            alpha_sum += alpha_values[index]
            x = index % width
            y = index // width
            left = min(left, x)
            right = max(right, x)
            top = min(top, y)
            bottom = max(bottom, y)
            for next_index in (index - 1, index + 1, index - width, index + width):
                if next_index < 0 or next_index >= width * height:
                    continue
                if visited[next_index] or alpha_values[next_index] <= threshold:
                    continue
                next_x = next_index % width
                if abs(next_x - x) > 1:
                    continue
                visited[next_index] = 1
                queue.append(next_index)

        area = len(indices)
        bbox = (left, top, right + 1, bottom + 1)
        components.append(
            {
                "indices": indices,
                "area": area,
                "bbox": bbox,
                "avg_alpha": alpha_sum / max(1, area),
                "touches_left": left <= 1,
                "touches_top": top <= 1,
                "touches_right": right >= width - 2,
                "touches_bottom": bottom >= height - 2,
            }
        )
    return components


def _select_subject_component(components: list[dict[str, Any]], width: int, height: int) -> dict[str, Any]:
    center_x = width / 2
    center_y = height * 0.56

    def score(component: dict[str, Any]) -> float:
        left, top, right, bottom = component["bbox"]
        comp_center_x = (left + right) / 2
        comp_center_y = (top + bottom) / 2
        distance = abs(comp_center_x - center_x) / max(1, width) + abs(comp_center_y - center_y) / max(1, height)
        value = float(component["area"]) * max(0.32, 1.0 - distance * 0.9)
        if component["touches_left"] or component["touches_right"]:
            value *= 0.38
        if component["touches_top"]:
            value *= 0.48
        return value

    return max(components, key=score)


def _is_related_subject_component(
    component: dict[str, Any],
    primary: dict[str, Any],
    width: int,
    height: int,
) -> bool:
    if component["touches_left"] or component["touches_right"] or component["touches_top"]:
        return False
    primary_area = max(1, int(primary["area"]))
    area = int(component["area"])
    if area < max(8, int(primary_area * 0.001)):
        return False
    if area > primary_area * 0.25:
        return False

    left, top, right, bottom = component["bbox"]
    p_left, p_top, p_right, p_bottom = primary["bbox"]
    margin = max(24, min(width, height) // 10)
    expanded = (
        max(0, p_left - margin),
        max(0, p_top - margin),
        min(width, p_right + margin),
        min(height, p_bottom + margin),
    )
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    return expanded[0] <= center_x <= expanded[2] and expanded[1] <= center_y <= expanded[3]


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
        crop = image.crop(box).convert("RGBA")
        points.extend((red, green, blue) for red, green, blue, alpha in crop.getdata() if alpha > 16)
    if not points:
        return (255, 255, 255)
    bucket_size = 16
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for red, green, blue in points:
        key = (red // bucket_size, green // bucket_size, blue // bucket_size)
        buckets.setdefault(key, []).append((red, green, blue))
    bucket = max(buckets.values(), key=len)
    red = sum(pixel[0] for pixel in bucket) // len(bucket)
    green = sum(pixel[1] for pixel in bucket) // len(bucket)
    blue = sum(pixel[2] for pixel in bucket) // len(bucket)
    return (red, green, blue)


def _edge_connected_background_mask(
    image: Image.Image,
    background_color: tuple[int, int, int],
    threshold: int,
    protected_mask: bytearray | None = None,
) -> bytearray:
    rgb_pixels = list(image.convert("RGB").getdata())
    width, height = image.size

    def candidate(index: int) -> bool:
        if protected_mask is not None and protected_mask[index]:
            return False
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


def _foreground_protection_mask(image: Image.Image, background_color: tuple[int, int, int]) -> tuple[bytearray, dict[str, Any]]:
    width, height = image.size
    bg_luma = _luma(*background_color)
    seed = Image.new("L", image.size, 0)
    seed_pixels = seed.load()
    source_pixels = image.load()
    seed_count = 0
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = source_pixels[x, y]
            if alpha <= 24:
                continue
            distance = abs(red - background_color[0]) + abs(green - background_color[1]) + abs(blue - background_color[2])
            max_channel = max(red, green, blue)
            min_channel = min(red, green, blue)
            saturation = max_channel - min_channel
            luma = _luma(red, green, blue)
            skin_color = _is_skin_color(red, green, blue)
            is_seed = False
            if distance >= 84 and (saturation >= 12 or luma <= 96 or skin_color or (bg_luma < 100 and luma >= bg_luma + 70)):
                is_seed = True
            elif distance >= 56 and saturation >= 18:
                is_seed = True
            elif skin_color:
                is_seed = True
            elif luma <= 72:
                is_seed = True
            elif bg_luma >= 168 and luma <= bg_luma - 72:
                is_seed = True
            elif bg_luma < 100 and luma >= bg_luma + 70:
                is_seed = True
            if not is_seed:
                continue
            seed_pixels[x, y] = 255
            seed_count += 1

    radius = max(3, min(10, min(width, height) // 96))
    filter_size = radius * 2 + 1
    protected = seed.filter(ImageFilter.MaxFilter(filter_size))
    protected_data = protected.getdata()
    mask = bytearray(1 if value else 0 for value in protected_data)
    return mask, {
        "method": "foreground_seed_expand",
        "seed_pixels": seed_count,
        "protected_pixels": int(sum(mask)),
        "expand_radius": radius,
    }


def _luma(red: int, green: int, blue: int) -> float:
    return 0.299 * red + 0.587 * green + 0.114 * blue


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
