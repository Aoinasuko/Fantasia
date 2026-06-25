from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
import time
import traceback
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from PIL import Image, ImageGrab, ImageTk

from .assets import check_runtime_assets, format_asset_report
from .cloud_models import cached_cloud_model_ids, fetch_cloud_model_ids
from .config import load_config
from .crashlog import install_crash_logging, install_tk_crash_logging
from .craft import craft_items
from .device import detect_device, device_report
from .game import (
    ACTOR_SUBNODE_ID_FLAG,
    ACTOR_SUBNODE_LOCATION_FLAG,
    CURRENT_SUBNODE_FLAG,
    DEFAULT_GUILD_NAME,
    DEFAULT_WORLD_CRIME_RISK,
    DEFAULT_WORLD_ENEMY_STRENGTH,
    INITIAL_WORLD_TIME_HOURS,
    PLAYER_INVENTORY_MAX_SLOTS,
    SUBNODE_GRAPH_KEY,
    GameEngine,
)
from .generation_log import append_task_event, format_generation_log_detail, list_generation_logs
from .i18n import ELEMENT_IDS, tr_enum, tr_enum_format
from .imagegen import DEFAULT_NEGATIVE_PROMPTS, QUALITY_PRESETS, MockSdxlBackend, create_image_backend
from .items import (
    add_item_stack,
    can_add_item_stack,
    inventory_slot_count,
    item_label as format_item_label,
    item_rarity_color,
    item_tooltip_text,
    item_value as get_item_value,
    normalise_item,
    sell_value as get_sell_value,
    starter_items,
    transfer_item_stack,
    use_inventory_item,
)
from .item_generate_loottabel import generate_loot_table_items
from .json_store import JsonStore
from .llm import FixtureLlmBackend, create_llm_backend
from .model_catalog import (
    download_model,
    local_llm_model_options,
    model_label,
    option_from_label,
    option_to_local_llm,
    sdxl_model_options,
)
from .paths import ASSETS_DIR, CONFIG_PATH, CRASHLOG_DIR, LOG_DIR, MODEL_GRAPHIC_DIR, MODEL_TEXT_DIR, OUTPUT_DIR, PORTABLE_ROOT, ROOT, RUNTIME_DIR
from .prompt_templates import PromptTemplateStore, resolve_prompt_template_dir
from .save_store import SaveStore
from .text_encoding import check_project_encoding, configure_stdio_encoding, format_encoding_report
from .ui_font import configure_ui_fonts
from .character import Character
from .world_model import GameStateData, LocationData, WorldData


MAX_EXPLORATION_CHOICES = 5
GAME_BOTTOM_ROW_HEIGHT = 360
GAME_STATUS_PANEL_HEIGHT = 300
GAME_LOG_PANEL_HEIGHT = 176
CHARACTER_STAT_BASE = 8
CHARACTER_BONUS_POINTS = 12
CHARACTER_STAT_MAX = CHARACTER_STAT_BASE + CHARACTER_BONUS_POINTS
APP_GRADIENT_TOP = "#000000"
APP_GRADIENT_BOTTOM = "#07152d"
APP_DEEP_BG = "#061126"
APP_PANEL_BG = "#050914"
APP_PANEL_ACTIVE_BG = "#10182a"
APP_BUTTON_BORDER = "#f2f2f2"
UI_BUTTON_ICON_DIR = ASSETS_DIR / "ui" / "buttons"
UI_TOOL_ICON_DISPLAY_SIZE = 56
UI_TOOL_BUTTON_SIZE = 64
UI_NPC_ROSTER_MIN_HEIGHT = 240
UI_PLAYER_SLOT_HEIGHT = 78
UI_COMPANION_SLOT_HEIGHT = UI_PLAYER_SLOT_HEIGHT * 2
UI_PARTY_COMPANION_LIMIT = 2
BUILTIN_FONT_PATH = "assets/fonts/JF-Dot-MPlus10.ttf"
BUILTIN_FONT_NAME = "JF-Dot-MPlus10"
CRAFT_INTENT_IDS = ("auto", "mix", "synthesis", "smithing", "alchemy", "cooking")
CRAFT_INTENT_UI_KEYS = {
    "auto": "craft_intent_auto",
    "mix": "craft_intent_mix",
    "synthesis": "craft_intent_synthesis",
    "smithing": "craft_intent_smithing",
    "alchemy": "craft_intent_alchemy",
    "cooking": "craft_intent_cooking",
}


class GradientCanvas(tk.Canvas):
    def __init__(self, parent: tk.Widget, top: str = APP_GRADIENT_TOP, bottom: str = APP_GRADIENT_BOTTOM, **kwargs) -> None:
        super().__init__(parent, bd=0, highlightthickness=0, bg=bottom, **kwargs)
        self._gradient_top = top
        self._gradient_bottom = bottom
        self._gradient_size: tuple[int, int] = (0, 0)
        self.bind("<Configure>", self._draw_gradient, add="+")

    def _draw_gradient(self, event=None) -> None:
        width = max(1, int(event.width if event is not None else self.winfo_width()))
        height = max(1, int(event.height if event is not None else self.winfo_height()))
        if self._gradient_size == (width, height):
            return
        self._gradient_size = (width, height)
        self.delete("app_gradient")
        top = self._rgb(self._gradient_top)
        bottom = self._rgb(self._gradient_bottom)
        step = 2
        denominator = max(1, height - 1)
        for y in range(0, height, step):
            ratio = y / denominator
            color = "#%02x%02x%02x" % tuple(
                int(top[index] + (bottom[index] - top[index]) * ratio)
                for index in range(3)
            )
            self.create_rectangle(0, y, width, min(height, y + step), fill=color, outline=color, tags="app_gradient")
        self.tag_lower("app_gradient")

    def _rgb(self, value: str) -> tuple[int, int, int]:
        red, green, blue = self.winfo_rgb(value)
        return red // 256, green // 256, blue // 256

    def tkraise(self, aboveThis: tk.Widget | str | None = None) -> None:
        if aboveThis is None:
            self.tk.call("raise", self._w)
            return
        target = aboveThis._w if isinstance(aboveThis, tk.Widget) else aboveThis
        self.tk.call("raise", self._w, target)


class ModalDialog(tk.Frame):
    def __init__(self, owner: "FantasiaApp", title: str = "", width: int = 820, height: int = 560) -> None:
        self._overlay = tk.Frame(owner.screen_container, bg="#303030")
        self._overlay_bg_image: ImageTk.PhotoImage | None = self._make_overlay_background(owner)
        self._overlay.grid(row=0, column=0, sticky="nsew")
        self._overlay.tkraise()
        if self._overlay_bg_image is not None:
            tk.Label(self._overlay, image=self._overlay_bg_image, bd=0, highlightthickness=0).place(relx=0, rely=0, relwidth=1, relheight=1)
        super().__init__(
            self._overlay,
            bg=APP_DEEP_BG,
            highlightbackground="#f2f2f2",
            highlightcolor="#f2f2f2",
            highlightthickness=2,
        )
        self._title = title
        self._close_callback = None
        self._destroying = False
        self.place(relx=0.5, rely=0.5, anchor="center", width=width, height=height)
        self.bind("<Escape>", lambda _event: self._handle_close(), add="+")
        self._overlay.bind("<Button-1>", lambda _event: "break", add="+")
        self.focus_set()
        self.grab_set()

    def _make_overlay_background(self, owner: "FantasiaApp") -> ImageTk.PhotoImage | None:
        try:
            owner.update_idletasks()
            width = max(owner.winfo_width(), 1)
            height = max(owner.winfo_height(), 1)
            left = owner.winfo_rootx()
            top = owner.winfo_rooty()
            snapshot = ImageGrab.grab((left, top, left + width, top + height)).convert("RGBA")
            mask = Image.new("RGBA", snapshot.size, (48, 48, 48, 150))
            dimmed = Image.alpha_composite(snapshot, mask)
            return ImageTk.PhotoImage(dimmed)
        except Exception:
            return None

    def title(self, value: str) -> None:
        self._title = value

    def geometry(self, value: str) -> None:
        size = str(value).split("+", 1)[0]
        if "x" not in size:
            return
        width, height = size.split("x", 1)
        try:
            self.place_configure(width=int(width), height=int(height))
        except ValueError:
            return

    def transient(self, _owner=None) -> None:
        return

    def resizable(self, _width=None, _height=None) -> None:
        return

    def protocol(self, name: str, callback=None) -> None:
        if name == "WM_DELETE_WINDOW":
            self._close_callback = callback

    def _handle_close(self) -> None:
        if self._close_callback is not None:
            self._close_callback()
            return
        self.destroy()

    def destroy(self) -> None:
        if self._destroying:
            return
        self._destroying = True
        try:
            if self.grab_current() is self:
                self.grab_release()
        except tk.TclError:
            pass
        overlay = self._overlay
        try:
            super().destroy()
        finally:
            try:
                if overlay.winfo_exists():
                    overlay.destroy()
            except tk.TclError:
                pass


class FantasiaApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        install_tk_crash_logging(self)
        self.config_data = load_config()
        self.device_info = detect_device()
        self._apply_startup_device_config()
        self.ui_fonts = configure_ui_fonts(self, self.config_data)
        self.save_store = SaveStore()
        width, height = self.config_data.window_size
        self.title("Fantasia")
        self.window_icon_image: ImageTk.PhotoImage | None = None
        self._apply_window_icon()
        self.geometry(f"{width}x{height}")
        self.minsize(960, 640)

        self.engine = GameEngine(
            create_llm_backend(self.config_data),
            create_image_backend(self.config_data),
            JsonStore(),
            self.save_store,
            PromptTemplateStore(resolve_prompt_template_dir(self.config_data.prompt_template_path)),
            allow_any_action_concept=self.config_data.allow_any_action_concept,
            reveal_world_map_on_generation=self.config_data.reveal_world_map_on_generation,
            debug_free_location_travel=self.config_data.debug_free_location_travel,
            debug_disable_movement_time_passage=self.config_data.debug_disable_movement_time_passage,
            debug_disable_dungeon_random_encounters=self.config_data.debug_disable_dungeon_random_encounters,
        )
        self.preview_image: ImageTk.PhotoImage | None = None
        self.stage_source_image: Image.Image | None = None
        self.stage_image: ImageTk.PhotoImage | None = None
        self.stage_image_refs: list[ImageTk.PhotoImage] = []
        self.roster_image_refs: list[ImageTk.PhotoImage] = []
        self.roster_hitboxes: dict[int, list[tuple[int, int, int, int, dict[str, object]]]] = {}
        self.character_preview_image: ImageTk.PhotoImage | None = None
        self.image_cache: dict[str, Image.Image] = {}
        self.tool_icon_images: dict[str, ImageTk.PhotoImage] = {}
        self.choice_buttons: list[tk.Button] = []
        self.task_buttons: list[tk.Widget] = []
        self.screens: dict[str, tk.Frame] = {}
        self.generation_log_entries = []
        self.task_sequence_id = 0
        self.current_task_id = 0
        self.current_task_name = ""
        self.current_task_started_at = 0.0
        self.current_task_cancel_requested = False
        self.current_task_auto_status = True
        self.current_task_log_animation_enabled = True
        self.visual_task_sequence_id = 0
        self.visual_task_id = 0
        self.visual_task_name = ""
        self.visual_task_started_at = 0.0
        self.task_tick_after_id: str | None = None
        self.world_generation_progress_after_id: str | None = None
        self.world_generation_progress_queue: queue.Queue[dict[str, object]] = queue.Queue()
        self.world_generation_progress_state: dict[str, object] = {"phase_rank": -1, "percent": 0, "items": {}}
        self.visual_task_after_id: str | None = None
        self.typewriter_after_id: str | None = None
        self.typewriter_target_text = ""
        self.typewriter_index = 0
        self.log_typewriter_base_text = ""
        self.task_log_animation_base_text = ""
        self.task_log_animation_last_text = ""
        self.task_log_animation_frame = 0
        self.current_screen_name = "title"
        self.settings_back_screen = "title"
        self.generation_logs_back_screen = "title"
        self.battle_choice_menu = ""
        self.character_skill_entries: list[dict[str, object]] = []
        self.character_trait_entries: list[dict[str, object]] = []
        self.character_entry_tooltip: tk.Toplevel | None = None
        self.character_entry_tooltip_label: tk.Label | None = None
        self.game_button_help_tooltip: tk.Toplevel | None = None
        self.game_button_help_label: tk.Label | None = None
        self.screen_tutorial_dialog_open = False
        self.game_tutorial_page_index = 0

        self._build_menu()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._maybe_open_first_run_notice)

    def _apply_window_icon(self) -> None:
        for icon_path in (ROOT / "docs" / "icon.png", ASSETS_DIR / "icon.png"):
            if not icon_path.exists():
                continue
            try:
                image = Image.open(icon_path).convert("RGBA")
                self.window_icon_image = ImageTk.PhotoImage(image)
                self.iconphoto(True, self.window_icon_image)
                return
            except Exception:
                self.window_icon_image = None

    def _build_menu(self) -> None:
        self.config(menu="")

    def _build_ui(self) -> None:
        self.configure(bg=APP_GRADIENT_BOTTOM)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        language = self.config_data.language
        self.status_var = tk.StringVar(value=tr_enum("app_status", "no_world_loaded", language))
        self.mode_name_var = tk.StringVar(value=tr_enum("mode", "exploration", language))
        self.choices_title_var = tk.StringVar(value=tr_enum("mode_choices_title", "exploration", language))
        self.action_label_var = tk.StringVar(value=tr_enum("mode_action_label", "exploration", language))
        self.task_status_var = tk.StringVar(value="")
        self.llm_backend_var = tk.StringVar(value=self.config_data.llm_backend)
        self.llm_backend_label_var = tk.StringVar(value=_llm_backend_label(self.config_data.llm_backend, language))
        self.llm_context_size_var = tk.StringVar(value=str(self.config_data.llm_context_size))
        self.llm_temperature_var = tk.StringVar(value=_llm_temperature_text(self.config_data))
        self.llm_repeat_suppression_var = tk.BooleanVar(value=_llm_repeat_suppression_enabled(self.config_data))
        self.local_model_var = tk.StringVar(value=_selected_model_label(self.config_data))
        self.cloud_openai_model_var = tk.StringVar(value=_cloud_model_text(self.config_data.cloud_llm, "openai"))
        self.cloud_xai_model_var = tk.StringVar(value=_cloud_model_text(self.config_data.cloud_llm, "xai"))
        self.cloud_gemini_model_var = tk.StringVar(value=_cloud_model_text(self.config_data.cloud_llm, "gemini"))
        self.cloud_openai_key_var = tk.StringVar(value=_cloud_key_value(self.config_data, "openai"))
        self.cloud_xai_key_var = tk.StringVar(value=_cloud_key_value(self.config_data, "xai"))
        self.cloud_gemini_key_var = tk.StringVar(value=_cloud_key_value(self.config_data, "gemini"))
        image_config = self.config_data.image_backend
        sdxl_config = self.config_data.sdxl
        negative_prompts = image_config.get("negative_prompts") if isinstance(image_config.get("negative_prompts"), dict) else {}
        self.image_quality_var = tk.StringVar(value=str(image_config.get("quality_preset", "balanced")))
        self.image_sampler_var = tk.StringVar(value=str(image_config.get("sampling_method", "dpm++2m")))
        self.image_scheduler_var = tk.StringVar(value=str(image_config.get("scheduler", "karras")))
        self.sdxl_model_var = tk.StringVar(value=_selected_sdxl_model_label(self.config_data))
        self.image_lora_prompt_var = tk.StringVar(value=str(image_config.get("lora_prompt", "")))
        self.image_vae_path_var = tk.StringVar(value=str(sdxl_config.get("vae_path", "")))
        self.image_taesd_path_var = tk.StringVar(value=str(sdxl_config.get("taesd_path", "")))
        self.image_lora_dir_var = tk.StringVar(value=str(sdxl_config.get("lora_model_dir", "")))
        self.image_negative_background_var = tk.StringVar(value=str(negative_prompts.get("background", DEFAULT_NEGATIVE_PROMPTS["background"])))
        self.image_negative_character_var = tk.StringVar(value=str(negative_prompts.get("character", DEFAULT_NEGATIVE_PROMPTS["character"])))
        self.image_negative_monster_var = tk.StringVar(value=str(negative_prompts.get("monster", DEFAULT_NEGATIVE_PROMPTS["monster"])))
        self.image_negative_cg_var = tk.StringVar(value=str(negative_prompts.get("cg", DEFAULT_NEGATIVE_PROMPTS["cg"])))
        self.ui_font_var = tk.StringVar(value=_font_label_from_config(self.config_data, self))
        self.ui_font_path_var = tk.StringVar(value=str(self.config_data.font_path))
        self.ui_font_size_var = tk.StringVar(value=str(self.config_data.font_size))
        self.ui_text_speed_var = tk.StringVar(value=str(self.config_data.ui_setting.get("text_speed", 0.02)))
        self.ui_language_var = tk.StringVar(value=_language_label(self.config_data.language))
        self.ui_generate_images_var = tk.BooleanVar(value=_image_generation_enabled_config(self.config_data))
        self.ui_show_button_help_var = tk.BooleanVar(value=bool(self.config_data.ui_setting.get("show_game_button_help", True)))
        self.debug_allow_any_action_var = tk.BooleanVar(value=self.config_data.allow_any_action_concept)
        self.debug_reveal_world_map_on_generation_var = tk.BooleanVar(value=self.config_data.reveal_world_map_on_generation)
        self.debug_free_location_travel_var = tk.BooleanVar(value=self.config_data.debug_free_location_travel)
        self.debug_disable_movement_time_passage_var = tk.BooleanVar(value=self.config_data.debug_disable_movement_time_passage)
        self.debug_disable_dungeon_random_encounters_var = tk.BooleanVar(value=self.config_data.debug_disable_dungeon_random_encounters)
        self.world_name_var = tk.StringVar(value="Misty Frontier")
        self.player_var = tk.StringVar(value="Nana")
        self.character_gender_var = tk.StringVar(value="female")
        self.character_age_var = tk.StringVar(value="20")
        self.character_category_var = tk.StringVar(value="young woman")
        self.character_str_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_dex_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_con_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_int_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_wis_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_cha_var = tk.StringVar(value=str(CHARACTER_STAT_BASE))
        self.character_gold_var = tk.StringVar(value="100")
        self.character_ability_points_var = tk.StringVar(value=f"BP:{CHARACTER_BONUS_POINTS}")
        self.premise_var = tk.StringVar(value="Misty frontier, old magic, exploration")
        self.world_crime_risk_var = tk.StringVar(value=_world_crime_risk_label(DEFAULT_WORLD_CRIME_RISK, language))
        self.world_enemy_strength_var = tk.StringVar(value=_world_enemy_strength_label(DEFAULT_WORLD_ENEMY_STRENGTH, language))
        self.world_generation_progress_var = tk.DoubleVar(value=0)
        self.action_var = tk.StringVar(value=tr_enum("initial_choice", "look_around", language))
        self.layer_background_var = tk.BooleanVar(value=True)
        self.layer_characters_var = tk.BooleanVar(value=True)
        self.layer_monsters_var = tk.BooleanVar(value=True)
        self.save_slots = []
        self.world_slots = []
        self.character_setup_back_screen = "world_create"
        self.last_character_preview_path = ""
        self.last_character_preview_name = ""

        self.screen_container = tk.Frame(self, bg=APP_GRADIENT_BOTTOM)
        self.screen_container.grid(row=0, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self._build_title_screen()
        self._build_world_create_screen()
        self._build_character_setup_screen_v2()
        self._build_world_select_screen()
        self._build_continue_select_screen()
        self._build_settings_screen()
        self._build_generation_log_screen()
        self._build_game_screen_v2()
        self._show_screen("title")

    def _apply_startup_device_config(self) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        raw["device_info"] = self.device_info.to_config()
        setup = raw.setdefault("setup", {})
        setup.setdefault("completed", False)
        setup.setdefault("auto_select_backend", True)
        setup.setdefault("backend_locked", False)
        if bool(setup.get("auto_select_backend", True)) and not bool(setup.get("backend_locked", False)):
            local_model_setting = raw.setdefault("ai_setting", {}).setdefault("local_model_setting", {})
            local_model_setting["llm_backend"] = self.device_info.recommended_llm_backend
            sdxl = local_model_setting.setdefault("sdxl", {})
            server_parameters = raw.setdefault("ai_setting", {}).setdefault("server_parameters", {})
            if self.device_info.recommended_llm_backend == "llama_cpp_completion_cuda":
                sdxl["sd_server_path"] = "bin/stable-diffusion.cpp-cuda/sd-server.exe"
                sdxl["sd_cli_path"] = "bin/stable-diffusion.cpp-cuda/sd-cli.exe"
                server_parameters["stable_diffusion_cpp"] = "--backend cuda0 --vae-tiling"
            else:
                sdxl["sd_server_path"] = "bin/stable-diffusion.cpp/sd-server.exe"
                sdxl["sd_cli_path"] = "bin/stable-diffusion.cpp/sd-cli.exe"
                server_parameters["stable_diffusion_cpp"] = "--vae-tiling"
        if raw != self.config_data.raw:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()

    def _maybe_open_first_run_notice(self) -> None:
        setup = self.config_data.raw.get("setup", {})
        if isinstance(setup, dict) and setup.get("completed"):
            return
        self._open_first_run_notice()

    def _create_screen(self, name: str) -> GradientCanvas:
        frame = GradientCanvas(self.screen_container)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.screens[name] = frame
        return frame

    def _show_screen(self, name: str) -> None:
        if name == "world_select":
            self._refresh_world_select_screen()
        if name == "continue_select":
            self._refresh_continue_select_screen()
        if name == "settings":
            self._refresh_settings_screen()
        if name == "generation_logs":
            self._refresh_generation_log_screen()
        if name == "character_setup":
            self._refresh_character_setup_screen()
        self.screens[name].tkraise()
        self.current_screen_name = name
        if name in {"world_create", "character_setup"}:
            self.after(150, lambda screen_name=name: self._maybe_open_screen_tutorial(screen_name))
        if name == "game":
            self._refresh_status_panel()
            self._render_stage()
            self._schedule_visual_updates()

    def _open_settings_screen(self) -> None:
        if self.current_screen_name != "settings":
            self.settings_back_screen = self.current_screen_name
        self._show_screen("settings")

    def _back_from_settings_screen(self) -> None:
        self._show_screen(self.settings_back_screen or "title")

    def _open_generation_logs_screen(self) -> None:
        self.generation_logs_back_screen = "settings"
        self._show_screen("generation_logs")

    def _back_from_generation_logs_screen(self) -> None:
        self._show_screen(self.generation_logs_back_screen or "settings")

    def _rebuild_settings_screen(self) -> None:
        existing = self.screens.get("settings")
        if existing is not None:
            existing.destroy()
        self._build_settings_screen()
        if self.current_screen_name == "settings":
            self._show_screen("settings")

    def _build_title_screen(self) -> None:
        screen = self._create_screen("title")
        panel = tk.Frame(screen, bg=APP_PANEL_BG, padx=28, pady=10, highlightbackground=APP_BUTTON_BORDER, highlightthickness=2)
        panel.grid(row=0, column=0)
        panel.columnconfigure(0, weight=1)

        tk.Label(panel, text="Fantasia", bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(14)).grid(row=0, column=0, sticky="ew")
        tk.Label(panel, text=_ui_text(self.config_data, "title_subtitle"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(2)).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._title_menu_button(panel, _ui_text(self.config_data, "title_new_world"), lambda: self._show_screen("world_create"), 2)
        self._title_menu_button(panel, _ui_text(self.config_data, "title_world_select"), lambda: self._show_screen("world_select"), 3)
        self._title_menu_button(panel, _ui_text(self.config_data, "title_continue_latest"), lambda: self._show_screen("continue_select"), 4)
        self._title_menu_button(panel, _ui_text(self.config_data, "title_settings"), self._open_settings_screen, 5)
        self._title_menu_button(panel, _ui_text(self.config_data, "title_exit"), self._on_close, 6, pady=(12, 14), ipady=12)

    def _build_world_create_screen(self) -> None:
        screen = self._create_screen("world_create")
        panel = tk.Frame(screen, bg="#111722", padx=28, pady=24, highlightbackground="#2b3142", highlightthickness=1)
        panel.grid(row=0, column=0, sticky="nsew", padx=80, pady=70)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(5, weight=1)

        self._screen_heading(panel, _ui_text(self.config_data, "world_generation_title"), _ui_text(self.config_data, "world_generation_subtitle"), 0)
        tk.Label(panel, text=_ui_text(self.config_data, "world_name"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", pady=(18, 4))
        ttk.Entry(panel, textvariable=self.world_name_var).grid(row=3, column=0, sticky="ew")
        tk.Label(panel, text=_ui_text(self.config_data, "world_premise"), bg="#111722", fg="#b8c0d5").grid(row=4, column=0, sticky="w", pady=(18, 4))
        self.premise_text = tk.Text(
            panel,
            height=8,
            wrap="word",
            bg="#0d1017",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            padx=10,
            pady=8,
            font=self.ui_fonts.normal(-3),
        )
        self.premise_text.grid(row=5, column=0, sticky="nsew")
        self.premise_text.insert("1.0", self.premise_var.get())
        self.premise_text.bind("<KeyRelease>", lambda _event: self.premise_var.set(self.premise_text.get("1.0", "end").strip()))

        tk.Label(panel, text=_ui_text(self.config_data, "world_crime_risk"), bg="#111722", fg="#b8c0d5").grid(row=6, column=0, sticky="w", pady=(14, 4))
        ttk.Combobox(
            panel,
            textvariable=self.world_crime_risk_var,
            values=_world_crime_risk_options(self.config_data.language),
            state="readonly",
        ).grid(row=7, column=0, sticky="ew")

        tk.Label(panel, text=_ui_text(self.config_data, "world_enemy_strength"), bg="#111722", fg="#b8c0d5").grid(row=8, column=0, sticky="w", pady=(14, 4))
        ttk.Combobox(
            panel,
            textvariable=self.world_enemy_strength_var,
            values=_world_enemy_strength_options(self.config_data.language),
            state="readonly",
        ).grid(row=9, column=0, sticky="ew")

        actions = tk.Frame(panel, bg="#111722")
        actions.grid(row=10, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        self._screen_button(actions, _ui_text(self.config_data, "common_back"), lambda: self._show_screen("title"), 0, column=0, sticky="w")
        tk.Label(actions, textvariable=self.task_status_var, bg="#111722", fg="#b8c0d5").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.create_world_btn = self._screen_button(actions, _ui_text(self.config_data, "world_generate"), self._start_world_creation, 0, column=2)
        self.task_buttons.append(self.create_world_btn)
        self.world_generation_progress = ttk.Progressbar(
            panel,
            mode="determinate",
            maximum=100,
            variable=self.world_generation_progress_var,
        )
        self.world_generation_progress.grid(row=11, column=0, sticky="ew", pady=(10, 0))

    def _build_character_setup_screen(self) -> None:
        screen = self._create_screen("character_setup")
        screen.rowconfigure(1, weight=1)

        header = self._screen_topbar(screen, "Character Setup")
        self._screen_button(header, "Back", self._back_from_character_setup, 0, column=1, sticky="e")

        panel = tk.Frame(screen, bg="#111722", padx=16, pady=14)
        panel.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(3, weight=1)

        self.character_world_summary_text = tk.Text(
            panel,
            height=5,
            wrap="word",
            bg="#0d1017",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            padx=10,
            pady=8,
            font=self.ui_fonts.normal(-4),
        )
        self.character_world_summary_text.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.character_world_summary_text.configure(state="disabled")

        basics = tk.Frame(panel, bg="#111722")
        basics.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(8):
            basics.columnconfigure(column, weight=1)
        self._labeled_entry(basics, "Name", self.player_var, 0, 0)
        self._labeled_combo(basics, "Gender", self.character_gender_var, ("female", "male", "other"), 0, 2)
        self._labeled_entry(basics, "Age", self.character_age_var, 0, 4, width=8)
        self._labeled_combo(
            basics,
            "Look Type",
            self.character_category_var,
            (
                "young woman",
                "young man",
                "teenage girl",
                "teenage boy",
                "middle-aged woman",
                "middle-aged man",
                "old woman",
                "old man",
            ),
            0,
            6,
        )

        stats = tk.Frame(panel, bg="#111722")
        stats.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for column in range(12):
            stats.columnconfigure(column, weight=1)
        for index, (label, var) in enumerate(
            (
                ("STR", self.character_str_var),
                ("DEX", self.character_dex_var),
                ("CON", self.character_con_var),
                ("INT", self.character_int_var),
                ("WIS", self.character_wis_var),
                ("CHA", self.character_cha_var),
            )
        ):
            self._labeled_entry(stats, label, var, 0, index * 2, width=6)

        left = tk.Frame(panel, bg="#111722")
        right = tk.Frame(panel, bg="#111722")
        left.grid(row=3, column=0, sticky="nsew", pady=(12, 0), padx=(0, 7))
        right.grid(row=3, column=1, sticky="nsew", pady=(12, 0), padx=(7, 0))
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)
        left.rowconfigure(5, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        self.character_backstory_text = self._editable_text(left, "Backstory", 0, height=5)
        self.character_look_text = self._editable_text(left, "Appearance", 2, height=5)
        self.character_personality_text = self._editable_text(left, "Personality", 4, height=5)
        self.character_traits_text = self._editable_text(right, "Traits / Constitution", 0, height=8)
        self.character_skills_text = self._editable_text(right, "Skills", 2, height=8)
        self.character_backstory_text.insert("1.0", "ある辺境の村で育った駆け出しの冒険者。")
        self.character_look_text.insert("1.0", "short hair, clear eyes, leather armor, practical travel cloak")
        self.character_personality_text.insert("1.0", "慎重だが、困っている人を見捨てられない。")
        self.character_traits_text.insert("1.0", "冷静 | 危機でも判断力を失いにくい\n旅慣れ | 野外行動に慣れている")
        self.character_skills_text.insert("1.0", "一閃 | physical | 武器で素早く斬り込む基本技 | 5 | 2 | str | damage_hp_single\n応急処置 | light | 簡単な治療で体勢を立て直す | 3 | 1 | wis | heal_single")

        actions = tk.Frame(panel, bg="#111722")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        actions.columnconfigure(1, weight=1)
        self._screen_button(actions, "Back", self._back_from_character_setup, 0, column=0, sticky="w")
        tk.Label(actions, textvariable=self.task_status_var, bg="#111722", fg="#b8c0d5").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.start_game_btn = self._screen_button(actions, "Start Game", self._start_game_with_character, 0, column=2, sticky="e")
        self.task_buttons.append(self.start_game_btn)

    def _build_world_select_screen(self) -> None:
        screen = self._create_screen("world_select")
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(0, weight=1)

        panel = self._selection_screen_panel(screen)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        top = tk.Frame(panel, bg=APP_PANEL_BG)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        top.columnconfigure(0, weight=1)
        tk.Label(top, text=_ui_text(self.config_data, "world_select_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, sticky="ew")
        self._grid_settings_button(top, _ui_text(self.config_data, "common_back"), lambda: self._show_screen("title"), row=0, column=1, sticky="e", ipadx=14, ipady=7)

        self.world_listbox = self._selection_listbox(panel)
        self.world_listbox.grid(row=1, column=0, sticky="nsew", pady=(0, 8))

        actions = tk.Frame(panel, bg=APP_PANEL_BG)
        actions.grid(row=2, column=0, sticky="ew")
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        self._grid_settings_button(actions, _ui_text(self.config_data, "export_selected_world"), self._export_selected_world_dialog, row=0, column=0, sticky="ew", padx=(0, 6), ipadx=8, ipady=8)
        self._grid_settings_button(actions, _ui_text(self.config_data, "import_world"), self._import_world_dialog, row=0, column=1, sticky="ew", padx=6, ipadx=8, ipady=8)
        self._grid_settings_button(actions, _ui_text(self.config_data, "start_selected_world"), self._start_selected_world, row=0, column=2, sticky="ew", padx=(6, 0), ipadx=8, ipady=8)

    def _build_continue_select_screen(self) -> None:
        screen = self._create_screen("continue_select")
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(0, weight=1)

        panel = self._selection_screen_panel(screen)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        top = tk.Frame(panel, bg=APP_PANEL_BG)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        top.columnconfigure(0, weight=1)
        tk.Label(top, text=_ui_text(self.config_data, "continue_select_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, sticky="ew")
        self._grid_settings_button(top, _ui_text(self.config_data, "common_back"), lambda: self._show_screen("title"), row=0, column=1, sticky="e", ipadx=14, ipady=7)

        self.continue_save_listbox = self._selection_listbox(panel)
        self.continue_save_listbox.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.continue_save_listbox.bind("<Double-Button-1>", lambda _event: self._load_selected_continue_save())

        actions = tk.Frame(panel, bg=APP_PANEL_BG)
        actions.grid(row=2, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self._grid_settings_button(actions, _ui_text(self.config_data, "continue_selected_character"), self._load_selected_continue_save, row=0, column=1, sticky="e", ipadx=26, ipady=8)

    def _title_menu_button(self, parent: tk.Widget, text: str, command, row: int, *, pady=(4, 4), ipady: int = 7) -> tk.Button:
        button = self._instant_button(parent, text, command)
        button.configure(font=self.ui_fonts.bold(1))
        button.grid(row=row, column=0, sticky="ew", padx=0, pady=pady, ipady=ipady)
        return button

    def _selection_screen_panel(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(
            parent,
            bg=APP_PANEL_BG,
            padx=14,
            pady=12,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=12)
        return panel

    def _selection_listbox(self, parent: tk.Widget) -> tk.Listbox:
        return tk.Listbox(
            parent,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            selectbackground=APP_PANEL_ACTIVE_BG,
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            exportselection=False,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
            activestyle="none",
            font=self.ui_fonts.normal(-2),
        )

    def _build_settings_screen_legacy(self) -> None:
        screen = self._create_screen("settings")
        screen.rowconfigure(0, weight=1)

        panel = tk.Frame(screen, bg="#111722", padx=14, pady=14)
        panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(panel)
        notebook.grid(row=0, column=0, sticky="nsew")

        overview_tab = tk.Frame(notebook, bg="#111722", padx=12, pady=12)
        llm_tab = tk.Frame(notebook, bg="#111722", padx=12, pady=12)
        image_tab = tk.Frame(notebook, bg="#111722", padx=12, pady=12)
        ui_tab = tk.Frame(notebook, bg="#111722", padx=12, pady=12)
        storage_tab = tk.Frame(notebook, bg="#111722", padx=12, pady=12)
        notebook.add(overview_tab, text=_ui_text(self.config_data, "settings_tab_overview"))
        notebook.add(llm_tab, text=_ui_text(self.config_data, "settings_tab_llm"))
        notebook.add(image_tab, text=_ui_text(self.config_data, "settings_tab_images"))
        notebook.add(ui_tab, text=_ui_text(self.config_data, "settings_tab_ui"))
        notebook.add(storage_tab, text=_ui_text(self.config_data, "settings_tab_storage"))

        overview_tab.columnconfigure(0, weight=1)
        overview_tab.rowconfigure(0, weight=1)
        self.settings_text = tk.Text(overview_tab, wrap="word", bg="#0d1017", fg="#e6edf7", insertbackground="#e6edf7", relief="flat", padx=12, pady=10, font=self.ui_fonts.normal(-4))
        self.settings_text.grid(row=0, column=0, sticky="nsew")
        self.settings_text.configure(state="disabled")

        llm_tab.columnconfigure(0, weight=1)
        backend_controls = tk.Frame(llm_tab, bg="#111722")
        backend_controls.grid(row=0, column=0, sticky="ew")
        backend_controls.columnconfigure(1, weight=1)
        tk.Label(backend_controls, text=_ui_text(self.config_data, "settings_llm_backend"), bg="#111722", fg="#b8c0d5").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.llm_backend_combo = ttk.Combobox(
            backend_controls,
            textvariable=self.llm_backend_var,
            values=_llm_backend_options(),
            state="readonly",
        )
        self.llm_backend_combo.grid(row=0, column=1, sticky="ew")
        self._screen_button(backend_controls, _ui_text(self.config_data, "settings_apply_llm"), self._apply_llm_backend_setting, 0, column=2, sticky="e")
        tk.Label(backend_controls, text=_ui_text(self.config_data, "settings_context_tokens"), bg="#111722", fg="#b8c0d5").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(backend_controls, textvariable=self.llm_context_size_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))
        self._screen_button(backend_controls, _ui_text(self.config_data, "settings_detect_device"), self._detect_device_from_settings, 1, column=2, sticky="e")
        tk.Label(backend_controls, text=_ui_text(self.config_data, "settings_local_model"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.local_model_combo = ttk.Combobox(
            backend_controls,
            textvariable=self.local_model_var,
            values=_local_model_labels(self.config_data, self.config_data.language),
            state="readonly",
        )
        self.local_model_combo.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        self._screen_button(backend_controls, _ui_text(self.config_data, "settings_download_model"), self._download_selected_local_model, 2, column=2, sticky="e")

        cloud_controls = tk.LabelFrame(llm_tab, text=_ui_text(self.config_data, "settings_cloud_llm"), bg="#111722", fg="#f4d27a", padx=10, pady=8)
        cloud_controls.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        cloud_controls.columnconfigure(1, weight=1)
        cloud_controls.columnconfigure(3, weight=1)
        self.cloud_model_combos: dict[str, ttk.Combobox] = {}
        self._cloud_setting_row(cloud_controls, 0, "openai", "OpenAI", self.cloud_openai_model_var, self.cloud_openai_key_var, _cloud_model_options("openai", self.config_data))
        self._cloud_setting_row(cloud_controls, 1, "xai", "xAI", self.cloud_xai_model_var, self.cloud_xai_key_var, _cloud_model_options("xai", self.config_data))
        self._cloud_setting_row(cloud_controls, 2, "gemini", "Gemini", self.cloud_gemini_model_var, self.cloud_gemini_key_var, _cloud_model_options("gemini", self.config_data))
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("openai"), 3, column=0, sticky="ew")
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("xai"), 3, column=1, sticky="ew")
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("gemini"), 3, column=2, sticky="ew")

        self.device_info_text = tk.Text(llm_tab, wrap="word", height=6, bg="#0d1017", fg="#d8d4cf", insertbackground="#e6edf7", relief="flat", padx=10, pady=8, font=self.ui_fonts.normal(-4))
        self.device_info_text.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.device_info_text.insert("1.0", device_report(self.device_info, self.config_data.language))
        self.device_info_text.configure(state="disabled")

        llm_info = tk.Text(llm_tab, wrap="word", height=5, bg="#0d1017", fg="#d8d4cf", insertbackground="#e6edf7", relief="flat", padx=10, pady=8, font=self.ui_fonts.normal(-4))
        llm_info.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        llm_info.insert("1.0", _ui_text(self.config_data, "settings_llm_info"))
        llm_info.configure(state="disabled")

        image_tab.columnconfigure(0, weight=1)
        image_controls = tk.Frame(image_tab, bg="#111722")
        image_controls.grid(row=0, column=0, sticky="ew")
        image_controls.columnconfigure(1, weight=1)
        image_controls.columnconfigure(3, weight=1)
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_sdxl_model"), bg="#111722", fg="#b8c0d5").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.sdxl_model_combo = ttk.Combobox(
            image_controls,
            textvariable=self.sdxl_model_var,
            values=_sdxl_model_labels(self.config_data, self.config_data.language),
            state="readonly",
        )
        self.sdxl_model_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3, padx=(0, 10))
        self._screen_button(image_controls, _ui_text(self.config_data, "settings_download_sdxl_model"), self._download_selected_sdxl_model, 0, column=3, sticky="e")
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_quality"), bg="#111722", fg="#b8c0d5").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.image_quality_combo = ttk.Combobox(
            image_controls,
            textvariable=self.image_quality_var,
            values=_quality_preset_options(self.config_data.image_backend),
            state="readonly",
        )
        self.image_quality_combo.grid(row=1, column=1, sticky="ew", pady=3, padx=(0, 10))
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_sampler"), bg="#111722", fg="#b8c0d5").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=3)
        self.image_sampler_combo = ttk.Combobox(
            image_controls,
            textvariable=self.image_sampler_var,
            values=_sampler_options(),
            state="normal",
        )
        self.image_sampler_combo.grid(row=1, column=3, sticky="ew", pady=3)
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_scheduler"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        self.image_scheduler_combo = ttk.Combobox(
            image_controls,
            textvariable=self.image_scheduler_var,
            values=_scheduler_options(),
            state="normal",
        )
        self.image_scheduler_combo.grid(row=2, column=1, sticky="ew", pady=3, padx=(0, 10))
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_lora_prompt"), bg="#111722", fg="#b8c0d5").grid(row=2, column=2, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(image_controls, textvariable=self.image_lora_prompt_var).grid(row=2, column=3, sticky="ew", pady=3)
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_vae"), bg="#111722", fg="#b8c0d5").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(image_controls, textvariable=self.image_vae_path_var).grid(row=3, column=1, sticky="ew", pady=3, padx=(0, 10))
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_taesd"), bg="#111722", fg="#b8c0d5").grid(row=3, column=2, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(image_controls, textvariable=self.image_taesd_path_var).grid(row=3, column=3, sticky="ew", pady=3)
        tk.Label(image_controls, text=_ui_text(self.config_data, "settings_lora_dir"), bg="#111722", fg="#b8c0d5").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(image_controls, textvariable=self.image_lora_dir_var).grid(row=4, column=1, columnspan=3, sticky="ew", pady=3)

        negative_controls = tk.Frame(image_tab, bg="#111722")
        negative_controls.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        negative_controls.columnconfigure(1, weight=1)
        tk.Label(negative_controls, text=_ui_text(self.config_data, "settings_negative_background"), bg="#111722", fg="#b8c0d5").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(negative_controls, textvariable=self.image_negative_background_var).grid(row=0, column=1, sticky="ew", pady=3)
        tk.Label(negative_controls, text=_ui_text(self.config_data, "settings_negative_character"), bg="#111722", fg="#b8c0d5").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(negative_controls, textvariable=self.image_negative_character_var).grid(row=1, column=1, sticky="ew", pady=3)
        tk.Label(negative_controls, text=_ui_text(self.config_data, "settings_negative_monster"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(negative_controls, textvariable=self.image_negative_monster_var).grid(row=2, column=1, sticky="ew", pady=3)
        image_actions = tk.Frame(image_tab, bg="#111722")
        image_actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        image_actions.columnconfigure(0, weight=1)
        self._screen_button(image_actions, _ui_text(self.config_data, "settings_apply_image"), self._apply_image_generation_setting, 0, column=1, sticky="e")

        ui_tab.columnconfigure(0, weight=1)
        ui_controls = tk.Frame(ui_tab, bg="#111722")
        ui_controls.grid(row=0, column=0, sticky="ew")
        ui_controls.columnconfigure(1, weight=1)
        ui_controls.columnconfigure(3, weight=1)
        tk.Label(ui_controls, text=_ui_text(self.config_data, "settings_language"), bg="#111722", fg="#b8c0d5").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Combobox(ui_controls, textvariable=self.ui_language_var, values=_language_options(), state="readonly", width=16).grid(row=0, column=1, sticky="w", pady=3, padx=(0, 10))
        tk.Label(ui_controls, text=_ui_text(self.config_data, "settings_font_path"), bg="#111722", fg="#b8c0d5").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(ui_controls, textvariable=self.ui_font_path_var).grid(row=1, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Label(ui_controls, text=_ui_text(self.config_data, "settings_font_size"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(ui_controls, textvariable=self.ui_font_size_var, width=8).grid(row=2, column=1, sticky="w", pady=3, padx=(0, 10))
        tk.Label(ui_controls, text=_ui_text(self.config_data, "settings_text_speed"), bg="#111722", fg="#b8c0d5").grid(row=2, column=2, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(ui_controls, textvariable=self.ui_text_speed_var, width=8).grid(row=2, column=3, sticky="w", pady=3)
        self._screen_button(ui_controls, _ui_text(self.config_data, "settings_apply_ui"), self._apply_ui_setting, 3, column=3, sticky="e")

        self._build_layer_controls(ui_tab, 1)

        storage_tab.columnconfigure(0, weight=1)
        storage_text = tk.Text(storage_tab, wrap="word", height=9, bg="#0d1017", fg="#d8d4cf", insertbackground="#e6edf7", relief="flat", padx=10, pady=8, font=self.ui_fonts.normal(-4))
        storage_text.grid(row=0, column=0, sticky="ew")
        storage_text.insert(
            "1.0",
            _ui_text(self.config_data, "settings_storage_info").format(
                config=CONFIG_PATH,
                appdata=self.save_store.data_dir,
                runtime=RUNTIME_DIR,
                output=OUTPUT_DIR,
            ),
        )
        storage_text.configure(state="disabled")
        storage_actions = tk.Frame(storage_tab, bg="#111722")
        storage_actions.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        storage_actions.columnconfigure(5, weight=1)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_refresh"), self._refresh_settings_screen, 0, column=0)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_check_assets"), self._check_assets_dialog, 0, column=1)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_import_world"), self._import_world_dialog, 0, column=2)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_export_current"), self._export_world_dialog, 0, column=3)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_back"), self._back_from_settings_screen, 0, column=6, sticky="e")

    def _build_settings_screen(self) -> None:
        screen = self._create_screen("settings")
        screen.configure(bg=APP_GRADIENT_BOTTOM)
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(0, weight=1)

        panel = tk.Frame(screen, bg=APP_PANEL_BG, padx=12, pady=12, highlightbackground="#f2f2f2", highlightthickness=2)
        panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        nav = tk.Frame(panel, bg=APP_PANEL_BG)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        nav.columnconfigure(3, weight=1)
        self.settings_category_buttons: dict[str, tk.Button] = {}
        categories = (
            ("llm", _ui_text(self.config_data, "settings_category_llm")),
            ("images", _ui_text(self.config_data, "settings_category_images")),
            ("ui", _ui_text(self.config_data, "settings_category_ui")),
            ("debug", _ui_text(self.config_data, "settings_category_debug")),
        )
        for column, (category, label) in enumerate(categories):
            button = self._grid_settings_button(
                nav,
                label,
                lambda name=category: self._show_settings_category(name),
                row=0,
                column=column if category != "debug" else 4,
                sticky="w" if category != "debug" else "e",
                padx=(0, 10) if category != "debug" else (10, 0),
                ipady=8,
                ipadx=14,
            )
            self.settings_category_buttons[category] = button

        self.settings_content_frame = tk.Frame(panel, bg=APP_PANEL_BG)
        self.settings_content_frame.grid(row=1, column=0, sticky="nsew")
        self.settings_content_frame.columnconfigure(0, weight=1)
        self.settings_content_frame.rowconfigure(0, weight=1)
        self.settings_category_frames: dict[str, tk.Frame] = {}
        self._build_settings_llm_category()
        self._build_settings_image_category()
        self._build_settings_ui_category()
        self._build_settings_debug_category()
        self._show_settings_category("llm")

    def _settings_category_frame(self, category: str) -> tk.Frame:
        frame = tk.Frame(self.settings_content_frame, bg=APP_PANEL_BG)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(20, weight=1)
        self.settings_category_frames[category] = frame
        return frame

    def _show_settings_category(self, category: str) -> None:
        frame = self.settings_category_frames.get(category)
        if frame is None:
            return
        frame.tkraise()
        for name, button in getattr(self, "settings_category_buttons", {}).items():
            button.configure(bg=APP_PANEL_ACTIVE_BG if name == category else APP_PANEL_BG)
        if category == "llm":
            self._refresh_llm_backend_fields()

    def _settings_action_row(self, parent: tk.Widget, row: int, apply_command) -> tk.Frame:
        actions = tk.Frame(parent, bg=APP_PANEL_BG)
        actions.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        self._grid_settings_button(actions, _ui_text(self.config_data, "settings_apply"), apply_command, row=0, column=1, sticky="e", padx=(0, 8), ipadx=18, ipady=8)
        self._grid_settings_button(actions, _ui_text(self.config_data, "settings_close"), self._back_from_settings_screen, row=0, column=2, sticky="e", ipadx=18, ipady=8)
        return actions

    def _settings_button(self, parent: tk.Widget, text: str, command, fg: str = "#f2f2f2") -> tk.Button:
        border = tk.Frame(parent, bg=APP_BUTTON_BORDER)
        border.columnconfigure(0, weight=1)
        border.rowconfigure(0, weight=1)
        button = tk.Button(
            border,
            text=text,
            command=command,
            bg=APP_PANEL_BG,
            fg=fg,
            activebackground=APP_PANEL_ACTIVE_BG,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self.ui_fonts.bold(-3),
            padx=8,
            pady=4,
        )
        button.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        button._border_frame = border  # type: ignore[attr-defined]
        return button

    def _grid_settings_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        row: int,
        column: int = 0,
        sticky: str = "ew",
        padx=0,
        pady=0,
        ipadx=0,
        ipady=0,
    ) -> tk.Button:
        button = self._settings_button(parent, text, command)
        button.grid_configure(ipadx=ipadx, ipady=ipady)
        button._border_frame.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)  # type: ignore[attr-defined]
        return button

    def _settings_checkbutton(self, parent: tk.Widget, variable: tk.Variable) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            variable=variable,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            activebackground=APP_PANEL_BG,
            activeforeground="#ffffff",
            selectcolor=APP_PANEL_BG,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
            bd=0,
        )

    def _build_settings_llm_category(self) -> None:
        frame = self._settings_category_frame("llm")
        frame.columnconfigure(1, weight=1)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_llm_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))

        tk.Label(frame, text=_ui_text(self.config_data, "settings_llm_backend"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.llm_backend_combo = ttk.Combobox(
            frame,
            textvariable=self.llm_backend_label_var,
            values=_llm_backend_label_options(self.config_data.language),
            state="readonly",
        )
        self.llm_backend_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        self.llm_backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_llm_backend_label_changed())

        self.llm_backend_detail_frame = tk.Frame(frame, bg=APP_PANEL_BG)
        self.llm_backend_detail_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.llm_backend_detail_frame.columnconfigure(1, weight=1)

        tk.Frame(frame, bg="#f2f2f2", height=2).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 10))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_context_tokens"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=4, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.llm_context_size_var, width=14).grid(row=4, column=1, sticky="w", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_context_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=5, column=0, columnspan=4, sticky="w", pady=(0, 8))

        tk.Label(frame, text=_ui_text(self.config_data, "settings_repeat_suppression"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=6, column=0, sticky="w", padx=(0, 8), pady=3)
        self._settings_checkbutton(frame, self.llm_repeat_suppression_var).grid(row=6, column=1, sticky="w", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_repeat_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=7, column=0, columnspan=4, sticky="w", pady=(0, 8))

        tk.Label(frame, text=_ui_text(self.config_data, "settings_temperature"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=8, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.llm_temperature_var, width=14).grid(row=8, column=1, sticky="w", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_temperature_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=9, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self._settings_action_row(frame, 21, self._apply_llm_backend_setting)
        self._refresh_llm_backend_fields()

    def _on_llm_backend_label_changed(self) -> None:
        backend = _llm_backend_from_label(self.llm_backend_label_var.get(), self.config_data.language)
        self.llm_backend_var.set(backend)
        self._refresh_llm_backend_fields()

    def _refresh_llm_backend_fields(self) -> None:
        if not hasattr(self, "llm_backend_detail_frame"):
            return
        for child in self.llm_backend_detail_frame.winfo_children():
            child.destroy()
        backend = _llm_backend_from_label(self.llm_backend_label_var.get(), self.config_data.language)
        self.llm_backend_var.set(backend)
        row = 0
        if backend.startswith("cloud_"):
            provider = backend.removeprefix("cloud_")
            model_var = self._cloud_model_var(provider)
            key_var = self._cloud_key_var(provider)
            tk.Label(self.llm_backend_detail_frame, text=_ui_text(self.config_data, "settings_api_key"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(self.llm_backend_detail_frame, textvariable=key_var, show="*").grid(row=row, column=1, sticky="ew", pady=4, padx=(0, 8))
            self._grid_settings_button(self.llm_backend_detail_frame, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda p=provider: self._fetch_cloud_models(p), row=row, column=2, sticky="e", pady=4)
            row += 1
            tk.Label(self.llm_backend_detail_frame, text=_ui_text(self.config_data, "settings_model"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            combo = ttk.Combobox(self.llm_backend_detail_frame, textvariable=model_var, values=_cloud_model_options(provider, self.config_data), state="normal")
            combo.grid(row=row, column=1, sticky="ew", pady=4)
            if not hasattr(self, "cloud_model_combos"):
                self.cloud_model_combos = {}
            self.cloud_model_combos[provider] = combo
            return

        tk.Label(self.llm_backend_detail_frame, text=_ui_text(self.config_data, "settings_model"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        self.local_model_combo = ttk.Combobox(
            self.llm_backend_detail_frame,
            textvariable=self.local_model_var,
            values=_local_model_labels(self.config_data, self.config_data.language),
            state="readonly",
        )
        self.local_model_combo.grid(row=row, column=1, sticky="ew", pady=4, padx=(0, 8))
        self._grid_settings_button(self.llm_backend_detail_frame, _ui_text(self.config_data, "settings_download_model"), self._download_selected_local_model, row=row, column=2, sticky="e", pady=4)
        row += 1
        tk.Label(self.llm_backend_detail_frame, textvariable=self.task_status_var, bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        row += 1
        tk.Label(self.llm_backend_detail_frame, text=_ui_text(self.config_data, "settings_local_model_folder_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", justify="left", wraplength=760, font=self.ui_fonts.normal(-4)).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._grid_settings_button(self.llm_backend_detail_frame, _ui_text(self.config_data, "settings_open_text_model_folder"), self._open_text_model_folder, row=row, column=2, sticky="e", pady=(4, 0))

    def _build_settings_image_category(self) -> None:
        frame = self._settings_category_frame("images")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_image_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))

        tk.Label(frame, text=_ui_text(self.config_data, "settings_model"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.sdxl_model_combo = ttk.Combobox(frame, textvariable=self.sdxl_model_var, values=_sdxl_model_labels(self.config_data, self.config_data.language), state="readonly")
        self.sdxl_model_combo.grid(row=1, column=1, sticky="ew", pady=3, padx=(0, 24))
        self._grid_settings_button(frame, _ui_text(self.config_data, "settings_download_sdxl_model"), self._download_selected_sdxl_model, row=1, column=3, sticky="e", pady=3, ipadx=18, ipady=6)
        tk.Label(frame, textvariable=self.task_status_var, bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_graphic_model_folder_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", justify="left", wraplength=780, font=self.ui_fonts.normal(-4)).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._grid_settings_button(frame, _ui_text(self.config_data, "settings_open_graphic_model_folder"), self._open_graphic_model_folder, row=3, column=3, sticky="e", pady=(0, 8), ipadx=18, ipady=6)

        tk.Frame(frame, bg=APP_BUTTON_BORDER, height=2).grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 12))

        tk.Label(frame, text=_ui_text(self.config_data, "settings_quality"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=5, column=0, sticky="w", padx=(0, 8), pady=3)
        self.image_quality_combo = ttk.Combobox(frame, textvariable=self.image_quality_var, values=_quality_preset_options(self.config_data.image_backend), state="readonly")
        self.image_quality_combo.grid(row=5, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_sampler"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=6, column=0, sticky="w", padx=(0, 8), pady=3)
        self.image_sampler_combo = ttk.Combobox(frame, textvariable=self.image_sampler_var, values=_sampler_options(), state="normal")
        self.image_sampler_combo.grid(row=6, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_scheduler"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=7, column=0, sticky="w", padx=(0, 8), pady=3)
        self.image_scheduler_combo = ttk.Combobox(frame, textvariable=self.image_scheduler_var, values=_scheduler_options(), state="normal")
        self.image_scheduler_combo.grid(row=7, column=1, sticky="ew", pady=3, padx=(0, 24))

        tk.Frame(frame, bg=APP_BUTTON_BORDER, height=2).grid(row=8, column=0, columnspan=4, sticky="ew", pady=(12, 10))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_negative_prompt"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=9, column=0, columnspan=4, sticky="w", pady=(0, 4))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_negative_background"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.normal(-2)).grid(row=10, column=0, sticky="w", padx=(12, 8), pady=3)
        ttk.Entry(frame, textvariable=self.image_negative_background_var).grid(row=10, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_negative_character"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.normal(-2)).grid(row=11, column=0, sticky="w", padx=(12, 8), pady=3)
        ttk.Entry(frame, textvariable=self.image_negative_character_var).grid(row=11, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_negative_monster"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.normal(-2)).grid(row=12, column=0, sticky="w", padx=(12, 8), pady=3)
        ttk.Entry(frame, textvariable=self.image_negative_monster_var).grid(row=12, column=1, columnspan=3, sticky="ew", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_negative_cg"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.normal(-2)).grid(row=13, column=0, sticky="w", padx=(12, 8), pady=3)
        ttk.Entry(frame, textvariable=self.image_negative_cg_var).grid(row=13, column=1, columnspan=3, sticky="ew", pady=3)
        self._settings_action_row(frame, 21, self._apply_image_generation_setting)

    def _build_settings_ui_category(self) -> None:
        frame = self._settings_category_frame("ui")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_ui_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_language"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Combobox(frame, textvariable=self.ui_language_var, values=_language_options(), state="readonly", width=24).grid(row=1, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_font"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        self.ui_font_combo = ttk.Combobox(
            frame,
            textvariable=self.ui_font_var,
            values=_font_options(self, self.config_data.language),
            state="readonly",
            width=28,
        )
        self.ui_font_combo.grid(row=2, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_font_size"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.ui_font_size_var, width=12).grid(row=3, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_text_speed"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=4, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(frame, textvariable=self.ui_text_speed_var, width=12).grid(row=4, column=1, sticky="ew", pady=3, padx=(0, 24))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_show_button_help"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=5, column=0, sticky="w", padx=(0, 8), pady=3)
        self._settings_checkbutton(frame, self.ui_show_button_help_var).grid(row=5, column=1, sticky="w", pady=3)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_show_button_help_hint"), bg=APP_PANEL_BG, fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-4)).grid(row=6, column=0, columnspan=4, sticky="w", pady=(0, 8))
        tk.Frame(frame, bg=APP_BUTTON_BORDER, height=2).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(12, 12))
        tk.Label(frame, text=_ui_text(self.config_data, "settings_generate_images"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=8, column=0, sticky="w", padx=(0, 8), pady=3)
        self._settings_checkbutton(frame, self.ui_generate_images_var).grid(row=8, column=1, sticky="w", pady=3)
        self._settings_action_row(frame, 21, self._apply_ui_setting)

    def _build_settings_debug_category(self) -> None:
        frame = self._settings_category_frame("debug")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)
        frame.rowconfigure(14, weight=1)
        tk.Label(frame, text=_ui_text(self.config_data, "settings_debug_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.device_info_text = tk.Text(
            frame,
            wrap="word",
            height=6,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=0,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
            padx=14,
            pady=10,
            font=self.ui_fonts.normal(-2),
        )
        self.device_info_text.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.device_info_text.configure(state="disabled")

        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_allow_any_action_concept"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self._settings_checkbutton(frame, self.debug_allow_any_action_var).grid(row=2, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_allow_any_action_concept_hint"),
            bg=APP_PANEL_BG,
            fg="#b8c0d5",
            anchor="w",
            justify="left",
            font=self.ui_fonts.normal(-4),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 12))

        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_reveal_world_map_on_generation"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self._settings_checkbutton(frame, self.debug_reveal_world_map_on_generation_var).grid(row=4, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_reveal_world_map_on_generation_hint"),
            bg=APP_PANEL_BG,
            fg="#b8c0d5",
            anchor="w",
            justify="left",
            font=self.ui_fonts.normal(-4),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 12))

        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_free_location_travel"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=6, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self._settings_checkbutton(frame, self.debug_free_location_travel_var).grid(row=6, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_free_location_travel_hint"),
            bg=APP_PANEL_BG,
            fg="#b8c0d5",
            anchor="w",
            justify="left",
            font=self.ui_fonts.normal(-4),
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 12))

        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_disable_movement_time_passage"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=8, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self._settings_checkbutton(frame, self.debug_disable_movement_time_passage_var).grid(row=8, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_disable_movement_time_passage_hint"),
            bg=APP_PANEL_BG,
            fg="#b8c0d5",
            anchor="w",
            justify="left",
            font=self.ui_fonts.normal(-4),
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 12))

        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_disable_dungeon_random_encounters"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=10, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        self._settings_checkbutton(frame, self.debug_disable_dungeon_random_encounters_var).grid(row=10, column=1, sticky="w", pady=(2, 0))
        tk.Label(
            frame,
            text=_ui_text(self.config_data, "settings_debug_disable_dungeon_random_encounters_hint"),
            bg=APP_PANEL_BG,
            fg="#b8c0d5",
            anchor="w",
            justify="left",
            font=self.ui_fonts.normal(-4),
        ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 12))

        actions = tk.Frame(frame, bg=APP_PANEL_BG)
        actions.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(0, 0))
        actions.columnconfigure(1, weight=1)
        self._grid_settings_button(actions, _ui_text(self.config_data, "settings_check_generation_logs"), self._open_generation_logs_screen, row=0, column=0, sticky="w", ipadx=52, ipady=8)

        self._settings_action_row(frame, 21, self._apply_debug_setting)
        self._replace_text(self.device_info_text, _debug_device_summary(self.device_info, self.config_data.language))

    def _open_text_model_folder(self) -> None:
        MODEL_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(MODEL_TEXT_DIR)
        except OSError as exc:
            self._show_error(exc)

    def _open_graphic_model_folder(self) -> None:
        MODEL_GRAPHIC_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(MODEL_GRAPHIC_DIR)
        except OSError as exc:
            self._show_error(exc)

    def _build_generation_log_screen(self) -> None:
        screen = self._create_screen("generation_logs")
        screen.columnconfigure(0, weight=1)
        screen.rowconfigure(0, weight=1)

        panel = tk.Frame(screen, bg=APP_PANEL_BG, padx=14, pady=14, highlightbackground=APP_BUTTON_BORDER, highlightthickness=2)
        panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        panel.columnconfigure(0, weight=1, minsize=300)
        panel.columnconfigure(1, weight=2)
        panel.rowconfigure(2, weight=1)

        tk.Label(panel, text=_ui_text(self.config_data, "generation_logs_title"), bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(4)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._grid_settings_button(panel, _ui_text(self.config_data, "common_back"), self._back_from_generation_logs_screen, row=0, column=1, sticky="e", ipadx=18, ipady=8)

        tk.Label(panel, text=_ui_text(self.config_data, "generation_logs_entries"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=1, column=0, sticky="w", pady=(0, 4))
        tk.Label(panel, text=_ui_text(self.config_data, "generation_logs_detail"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(0, 4))

        self.generation_log_listbox = tk.Listbox(
            panel,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            selectbackground=APP_PANEL_ACTIVE_BG,
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            exportselection=False,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
            font=self.ui_fonts.normal(-3),
        )
        self.generation_log_listbox.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        self.generation_log_listbox.bind("<<ListboxSelect>>", lambda _event: self._show_selected_generation_log())

        self.generation_log_text = tk.Text(
            panel,
            wrap="word",
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            highlightthickness=2,
            font=self.ui_fonts.normal(-4),
        )
        self.generation_log_text.grid(row=2, column=1, sticky="nsew", padx=(6, 0))
        self.generation_log_text.configure(state="disabled")

    def _build_game_screen(self) -> None:
        screen = self._create_screen("game")
        screen.rowconfigure(1, weight=1)

        header = tk.Frame(screen, bg="#151925", padx=12, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        tk.Label(header, text="Fantasia", bg="#151925", fg="#f4d27a", font=self.ui_fonts.bold(4)).grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.mode_badge = tk.Label(
            header,
            textvariable=self.mode_name_var,
            bg="#2b3142",
            fg="#f2f5fb",
            padx=10,
            pady=3,
            font=self.ui_fonts.bold(-5),
        )
        self.mode_badge.grid(row=0, column=1, sticky="w", padx=(0, 10))
        tk.Label(
            header,
            textvariable=self.status_var,
            bg="#151925",
            fg="#e6edf7",
            anchor="w",
            font=self.ui_fonts.bold(-4),
        ).grid(row=0, column=2, sticky="ew", padx=(6, 12))
        self._screen_button(header, "Title", lambda: self._show_screen("title"), 0, column=3)
        self._screen_button(header, "Worlds", lambda: self._show_screen("world_select"), 0, column=4)
        self._screen_button(header, "Settings", lambda: self._show_screen("settings"), 0, column=5)

        body = tk.Frame(screen, bg="#0d1017", padx=10, pady=10)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=5)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        stage_frame = tk.Frame(body, bg="#080a10", highlightbackground="#2b3142", highlightthickness=1)
        stage_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        stage_frame.rowconfigure(0, weight=1)
        stage_frame.columnconfigure(0, weight=1)

        self.stage_canvas = tk.Canvas(stage_frame, bg="#080a10", highlightthickness=0)
        self.stage_canvas.grid(row=0, column=0, sticky="nsew")
        self.stage_canvas.bind("<Configure>", lambda _event: self._render_stage())

        side = tk.Frame(body, bg="#111722", highlightbackground="#2b3142", highlightthickness=1)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(6, weight=1)

        self.mode_info_text = self._make_panel_text(side, "Mode", 0, height=5)
        self.world_info_text = self._make_panel_text(side, "World", 1, height=4)
        self.party_text = self._make_panel_text(side, "Cast", 2, height=5)
        self.quest_text = self._make_panel_text(side, "Quests", 3, height=5)
        tools = tk.Frame(side, bg="#111722", padx=8, pady=8)
        tools.grid(row=4, column=0, sticky="ew")
        tools.columnconfigure(0, weight=1)
        tools.columnconfigure(1, weight=1)
        tk.Label(tools, text="Tools", bg="#111722", fg="#f4d27a", anchor="w", font=self.ui_fonts.bold(-4)).grid(row=0, column=0, columnspan=2, sticky="ew")
        self.image_btn = self._instant_button(tools, "Scene", self._generate_image)
        self.image_btn.grid(row=1, column=0, sticky="ew", pady=(6, 4), padx=(0, 4))
        self.character_image_btn = self._instant_button(tools, "Character", self._generate_character_image)
        self.character_image_btn.grid(row=1, column=1, sticky="ew", pady=(6, 4), padx=(4, 0))
        self.monster_image_btn = self._instant_button(tools, "Monster", self._generate_monster_image)
        self.monster_image_btn.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.save_btn = self._instant_button(tools, "Save", self._save_game)
        self.save_btn.grid(row=2, column=1, sticky="ew", padx=(4, 0))
        self.cancel_task_btn = self._instant_button(tools, "Cancel", self._cancel_current_task)
        self.cancel_task_btn.configure(state="disabled")
        self.cancel_task_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.task_status_label = tk.Label(
            tools,
            textvariable=self.task_status_var,
            bg="#111722",
            fg="#b8c0d5",
            anchor="w",
            font=self.ui_fonts.normal(-5),
        )
        self.task_status_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.task_progress = ttk.Progressbar(tools, mode="indeterminate")
        self.task_progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        self.task_buttons.extend([self.image_btn, self.character_image_btn, self.monster_image_btn, self.save_btn])
        self._build_layer_controls(side, 5)
        self.log_text = self._make_panel_text(side, "Log", 6, height=10, expand=True)
        self._replace_text(self.log_text, "Start or load a world from the title screen.\n")

        bottom = tk.Frame(screen, bg="#111722", padx=10, pady=8)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        tk.Label(
            bottom,
            textvariable=self.choices_title_var,
            bg="#111722",
            fg="#f4d27a",
            font=self.ui_fonts.bold(-4),
        ).grid(row=0, column=0, sticky="w")
        self.choice_frame = tk.Frame(bottom, bg="#111722")
        self.choice_frame.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.choice_frame.columnconfigure(0, weight=1)
        self.choice_frame.columnconfigure(1, weight=1)

        action_bar = tk.Frame(bottom, bg="#111722")
        action_bar.grid(row=2, column=0, sticky="ew")
        action_bar.columnconfigure(1, weight=1)
        tk.Label(action_bar, textvariable=self.action_label_var, bg="#111722", fg="#b8c0d5").grid(row=0, column=0, padx=(0, 8))
        self.action_entry = ttk.Entry(action_bar, textvariable=self.action_var)
        self.action_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.action_entry.bind("<Return>", lambda _event: self._send_action())

        self.action_btn = self._instant_button(action_bar, "Send", self._send_action)
        self.action_btn.grid(row=0, column=2)
        self.task_buttons.append(self.action_btn)
        self._refresh_choices()
        self._refresh_status_panel()
        self._render_stage()

    def _build_character_setup_screen_v2(self) -> None:
        screen = self._create_screen("character_setup")
        screen.configure(bg=APP_GRADIENT_BOTTOM)
        screen.columnconfigure(0, weight=3)
        screen.columnconfigure(1, weight=4)
        screen.columnconfigure(2, weight=3)
        screen.rowconfigure(0, weight=1)

        left = tk.Frame(screen, bg=APP_DEEP_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(18, 16), pady=(18, 28))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.character_preview_canvas = tk.Canvas(
            left,
            bg=APP_PANEL_BG,
            highlightbackground="#d8d4cf",
            highlightcolor="#d8d4cf",
            highlightthickness=1,
            relief="flat",
        )
        self.character_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.character_preview_canvas.bind("<Configure>", lambda _event: self._render_character_preview())
        self.character_preview_generate_btn = self._instant_button(left, _ui_text(self.config_data, "character_preview_generate"), self._generate_character_preview_image)
        self.character_preview_generate_btn.grid(row=1, column=0, sticky="ew", pady=(10, 0), ipady=9)
        tk.Label(
            left,
            textvariable=self.task_status_var,
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            font=self.ui_fonts.normal(-4),
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.task_buttons.append(self.character_preview_generate_btn)

        center = tk.Frame(screen, bg=APP_DEEP_BG)
        center.grid(row=0, column=1, sticky="nsew", padx=(16, 16), pady=(18, 28))
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)
        center.rowconfigure(2, weight=1)

        name_row = tk.Frame(center, bg=APP_DEEP_BG)
        name_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        name_row.columnconfigure(0, weight=1)
        self.character_name_entry = tk.Entry(
            name_row,
            textvariable=self.player_var,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightbackground="#d8d4cf",
            highlightthickness=1,
            font=self.ui_fonts.normal(0),
        )
        self.character_name_entry.grid(row=0, column=0, sticky="ew", ipady=8)
        self.character_gender_label_var = tk.StringVar(value=_gender_button_label(self.character_gender_var.get()))
        self.character_gender_btn = self._instant_button(
            name_row,
            self.character_gender_label_var.get(),
            self._cycle_character_gender,
        )
        self.character_gender_btn.grid(row=0, column=1, sticky="ew", padx=(14, 0), ipady=7)

        self.character_backstory_text = self._instant_labeled_text(center, _ui_text(self.config_data, "character_backstory"), 1, height=9)
        self.character_look_text = self._instant_labeled_text(center, _ui_text(self.config_data, "character_appearance"), 2, height=9)

        age_panel = self._instant_panel(center, 3, 0, sticky="ew", pady=(0, 0))
        age_panel.columnconfigure(1, weight=1)
        tk.Label(age_panel, text=_ui_text(self.config_data, "character_age"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=0, column=0, padx=(20, 8), pady=12)
        tk.Label(age_panel, textvariable=self.character_age_var, bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=0, column=1, sticky="w")
        self._instant_button(age_panel, "-", lambda: self._adjust_character_number(self.character_age_var, -1, 1, 120)).grid(row=0, column=2, padx=(8, 4), pady=8, ipadx=10, ipady=6)
        self._instant_button(age_panel, "+", lambda: self._adjust_character_number(self.character_age_var, 1, 1, 120)).grid(row=0, column=3, padx=(4, 20), pady=8, ipadx=10, ipady=6)

        right = tk.Frame(screen, bg=APP_DEEP_BG)
        right.grid(row=0, column=2, sticky="nsew", padx=(16, 18), pady=(12, 28))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        right.rowconfigure(3, weight=1)

        ability_panel = self._instant_panel(right, 0, 0, sticky="ew", pady=(0, 12))
        tk.Label(
            ability_panel,
            textvariable=self.character_ability_points_var,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            font=self.ui_fonts.bold(-1),
        ).grid(row=0, column=0, sticky="ew", pady=15)

        stats_panel = self._instant_panel(right, 1, 0, sticky="nsew", pady=(0, 12))
        stats_panel.columnconfigure(1, weight=1)
        stat_rows = (
            (_ui_text(self.config_data, "character_strength"), self.character_str_var, 0),
            (_ui_text(self.config_data, "character_dexterity"), self.character_dex_var, 1),
            (_ui_text(self.config_data, "character_constitution"), self.character_con_var, 2),
            (_ui_text(self.config_data, "character_intelligence"), self.character_int_var, 3),
            (_ui_text(self.config_data, "character_wisdom"), self.character_wis_var, 4),
            (_ui_text(self.config_data, "character_charisma"), self.character_cha_var, 5),
        )
        for label, variable, row in stat_rows:
            self._character_stat_row(stats_panel, label, variable, row)

        skills_panel = self._instant_panel(right, 2, 0, sticky="nsew", pady=(0, 12))
        skills_panel.columnconfigure(0, weight=1)
        skills_panel.rowconfigure(1, weight=1)
        tk.Label(skills_panel, text=_ui_text(self.config_data, "character_skills"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", pady=(10, 6))
        self.character_skills_frame = tk.Frame(skills_panel, bg=APP_PANEL_BG)
        self.character_skills_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        self.character_skills_frame.columnconfigure(0, weight=1)

        traits_panel = self._instant_panel(right, 3, 0, sticky="nsew", pady=(0, 12))
        traits_panel.columnconfigure(0, weight=1)
        traits_panel.rowconfigure(1, weight=1)
        tk.Label(traits_panel, text=_ui_text(self.config_data, "character_traits"), bg=APP_PANEL_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", pady=(10, 6))
        self.character_traits_frame = tk.Frame(traits_panel, bg=APP_PANEL_BG)
        self.character_traits_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 14))
        self.character_traits_frame.columnconfigure(0, weight=1)

        start_panel = self._instant_panel(right, 4, 0, sticky="ew")
        start_panel.columnconfigure(0, weight=1)
        self.start_game_btn = self._instant_button(start_panel, _ui_text(self.config_data, "character_start_game"), self._start_game_with_character, fg="#f2f2f2")
        self.start_game_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8), ipady=4)
        self.task_buttons.append(self.start_game_btn)

        self.character_backstory_text.insert("1.0", "辺境の村で育った駆け出しの冒険者。慎重だが、困っている人を見捨てられない。")
        self.character_look_text.insert("1.0", "short hair, clear eyes, leather armor, practical travel cloak")
        self.character_personality_text = tk.Text(screen, height=1)
        self.character_personality_text.insert("1.0", "")
        self._set_character_entries(
            "skills",
                _parse_character_skills(
                "一閃 | physical | 武器で素早く斬り込む基本技 | 5 | 2 | str | damage_hp_single\n"
                "応急処置 | light | 簡単な治療で体勢を立て直す | 3 | 1 | wis | heal_single"
            ),
        )
        self._set_character_entries(
            "traits",
            _parse_character_traits(
                "冷静 | 危機でも判断力を失いにくい\n"
                "旅慣れ | 野外行動に慣れている"
            ),
        )
        self.character_world_summary_text = tk.Text(screen, height=1)
        self.character_world_summary_text.configure(state="disabled")
        for variable in (
            self.character_str_var,
            self.character_dex_var,
            self.character_con_var,
            self.character_int_var,
            self.character_wis_var,
            self.character_cha_var,
            self.character_age_var,
            self.player_var,
            self.character_gender_var,
            self.character_category_var,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_character_setup_points())
        self._refresh_character_setup_points()

    def _build_game_screen_v2(self) -> None:
        screen = self._create_screen("game")
        screen.configure(bg=APP_GRADIENT_BOTTOM)
        screen.columnconfigure(0, weight=5, uniform="game_main")
        screen.columnconfigure(1, weight=3, uniform="game_main")
        screen.columnconfigure(2, weight=3, uniform="game_main")
        screen.rowconfigure(0, weight=5)
        screen.rowconfigure(1, weight=4)
        screen.rowconfigure(2, weight=0, minsize=76)

        stage_frame = tk.Frame(screen, bg=APP_PANEL_BG, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        stage_frame.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=(10, 6))
        stage_frame.rowconfigure(0, weight=1)
        stage_frame.columnconfigure(0, weight=1)
        self.stage_canvas = tk.Canvas(stage_frame, bg=APP_PANEL_BG, highlightthickness=0)
        self.stage_canvas.grid(row=0, column=0, sticky="nsew")
        self.stage_canvas.bind("<Configure>", lambda _event: self._render_stage())

        choice_area = tk.Frame(screen, bg=APP_DEEP_BG)
        choice_area.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=(16, 10))
        choice_area.columnconfigure(0, weight=1)
        choice_area.rowconfigure(0, weight=1)
        self.choice_frame = tk.Frame(choice_area, bg=APP_DEEP_BG)
        self.choice_frame.grid(row=0, column=0, sticky="new")
        self.choice_frame.columnconfigure(0, weight=1)

        right_roster = tk.Frame(screen, bg=APP_DEEP_BG)
        right_roster.grid(row=0, column=2, rowspan=3, sticky="nsew", padx=(14, 14), pady=(14, 14))
        right_roster.columnconfigure(0, weight=1)
        right_roster.rowconfigure(0, weight=1, minsize=UI_NPC_ROSTER_MIN_HEIGHT)
        right_roster.rowconfigure(1, weight=0, minsize=UI_PLAYER_SLOT_HEIGHT)
        right_roster.rowconfigure(2, weight=0, minsize=UI_COMPANION_SLOT_HEIGHT)
        right_roster.rowconfigure(3, weight=0, minsize=GAME_STATUS_PANEL_HEIGHT)
        self.npc_roster_canvas = tk.Canvas(right_roster, bg=APP_PANEL_BG, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        self.npc_roster_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
        self.npc_roster_canvas.bind("<Configure>", lambda _event: self._render_actor_rosters())
        self.npc_roster_canvas.bind("<Button-1>", self._on_roster_click)
        self.player_roster_canvas = tk.Canvas(right_roster, bg=APP_PANEL_BG, height=UI_PLAYER_SLOT_HEIGHT, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        self.player_roster_canvas.grid(row=1, column=0, sticky="nsew", pady=(14, 4))
        self.player_roster_canvas.bind("<Configure>", lambda _event: self._render_actor_rosters())
        self.player_roster_canvas.bind("<Button-1>", self._on_roster_click)
        self.companion_roster_canvas = tk.Canvas(right_roster, bg=APP_PANEL_BG, height=UI_COMPANION_SLOT_HEIGHT, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        self.companion_roster_canvas.grid(row=2, column=0, sticky="nsew", pady=(4, 8))
        self.companion_roster_canvas.bind("<Configure>", lambda _event: self._render_actor_rosters())
        self.companion_roster_canvas.bind("<Button-1>", self._on_roster_click)
        self.info_canvas = tk.Canvas(right_roster, bg=APP_PANEL_BG, height=GAME_STATUS_PANEL_HEIGHT, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        self.info_canvas.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.info_canvas.bind("<Configure>", lambda _event: self._render_player_info_panel())
        self.player_roster_canvases = [self.player_roster_canvas, self.companion_roster_canvas]

        log_panel = tk.Frame(screen, bg=APP_PANEL_BG, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=2)
        log_panel.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(14, 14), pady=(6, 6))
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(0, weight=1)
        self.log_text = self._instant_text(
            log_panel,
            0,
            0,
            height=8,
            padx=12,
            pady=(12, 4),
        )
        self._replace_text(self.log_text, _ui_text(self.config_data, "game_initial_log"))

        action_bar = tk.Frame(log_panel, bg=APP_PANEL_BG)
        action_bar.grid(row=1, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        self.action_entry = tk.Entry(
            action_bar,
            textvariable=self.action_var,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            font=self.ui_fonts.normal(-1),
        )
        self.action_entry.grid(row=0, column=0, sticky="ew", ipady=10, padx=(10, 8), pady=(4, 10))
        self.action_entry.bind("<Return>", lambda _event: self._send_action())
        send_border = tk.Frame(action_bar, bg=APP_BUTTON_BORDER)
        send_border.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=(4, 10))
        send_border.columnconfigure(0, weight=1)
        send_border.rowconfigure(0, weight=1)
        self.action_btn = self._instant_button(send_border, _ui_text(self.config_data, "game_send"), self._send_action)
        self.action_btn.configure(relief="flat", bd=0)
        self.action_btn.grid(row=0, column=0, sticky="nsew", ipadx=18, padx=2, pady=2)
        self.task_buttons.append(self.action_btn)

        tool_bar = tk.Frame(screen, bg=APP_DEEP_BG)
        tool_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(14, 14), pady=(4, 10))
        tool_bar.columnconfigure(0, weight=0)
        tool_bar.columnconfigure(1, weight=1)
        tool_bar.columnconfigure(2, weight=0)

        left_tools = tk.Frame(tool_bar, bg=APP_DEEP_BG)
        left_tools.grid(row=0, column=0, sticky="w")
        right_tools = tk.Frame(tool_bar, bg=APP_DEEP_BG)
        right_tools.grid(row=0, column=2, sticky="e")

        self.inventory_btn = self._tool_icon_button(left_tools, "inv", _ui_text(self.config_data, "game_inventory"), self._open_player_inventory)
        self.craft_btn = self._tool_icon_button(left_tools, "craft", _ui_text(self.config_data, "game_craft"), self._open_craft_window)
        self.loot_btn = self._tool_icon_button(left_tools, "loot", _ui_text(self.config_data, "game_loot"), self._open_loot_inventory)
        self.world_map_btn = self._tool_icon_button(left_tools, "worldmap", _ui_text(self.config_data, "game_world_map"), self._open_world_map_window)
        self.quest_status_btn = self._tool_icon_button(left_tools, "quest", _ui_text(self.config_data, "game_quest_status"), self._open_active_quest_window)
        self.subnode_map_btn = self._tool_icon_button(left_tools, "worldmap", _ui_text(self.config_data, "game_subnode_map"), self._open_subnode_map_window)
        for column, button in enumerate((self.inventory_btn, self.craft_btn, self.loot_btn, self.world_map_btn, self.quest_status_btn, self.subnode_map_btn)):
            button.grid(row=0, column=column, padx=(0, 10), pady=0)

        self.cg_btn = self._tool_icon_button(right_tools, "cg", _ui_text(self.config_data, "game_cg"), self._generate_cg_image)
        self.tutorial_btn = self._tool_icon_button(right_tools, "tutorial", _ui_text(self.config_data, "game_tutorial"), self._open_game_tutorial)
        self.save_btn = self._tool_icon_button(right_tools, "save", _ui_text(self.config_data, "game_save"), self._save_game)
        self.setting_btn = self._tool_icon_button(right_tools, "setting", _ui_text(self.config_data, "game_setting"), self._open_game_submenu)
        for column, button in enumerate((self.cg_btn, self.tutorial_btn, self.save_btn, self.setting_btn)):
            button.grid(row=0, column=column, padx=(10, 0), pady=0)
        self.task_buttons.extend([self.inventory_btn, self.craft_btn, self.loot_btn, self.world_map_btn, self.quest_status_btn, self.subnode_map_btn, self.cg_btn, self.tutorial_btn, self.save_btn, self.setting_btn])
        for button, title_key, help_key in (
            (self.inventory_btn, "game_inventory", "game_inventory_help"),
            (self.craft_btn, "game_craft", "game_craft_help"),
            (self.loot_btn, "game_loot", "game_loot_help"),
            (self.world_map_btn, "game_world_map", "game_world_map_help"),
            (self.quest_status_btn, "game_quest_status", "game_quest_status_help"),
            (self.subnode_map_btn, "game_subnode_map", "game_subnode_map_help"),
            (self.cg_btn, "game_cg", "game_cg_help"),
            (self.tutorial_btn, "game_tutorial", "game_tutorial_help"),
            (self.save_btn, "game_save", "game_save_help"),
            (self.setting_btn, "game_setting", "game_setting_help"),
        ):
            self._bind_game_button_help(button, title_key, help_key)

        self._refresh_choices()
        self._refresh_status_panel()
        self._render_stage()

    def _instant_panel(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        rowspan: int = 1,
        columnspan: int = 1,
        sticky: str = "nsew",
        padx=0,
        pady=0,
    ) -> tk.Frame:
        panel = tk.Frame(parent, bg=APP_PANEL_BG, highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=1)
        panel.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky=sticky, padx=padx, pady=pady)
        return panel

    def _instant_button(self, parent: tk.Widget, text: str, command, fg: str = "#f2f2f2") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=APP_PANEL_BG,
            fg=fg,
            activebackground=APP_PANEL_ACTIVE_BG,
            activeforeground="#ffffff",
            relief="solid",
            bd=0,
            highlightthickness=2,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            font=self.ui_fonts.bold(-3),
            padx=8,
            pady=4,
        )

    def _create_modal_dialog(self, title: str, width: int, height: int) -> ModalDialog:
        return ModalDialog(self, title=title, width=width, height=height)

    def _tool_icon_button(self, parent: tk.Widget, icon_name: str, label: str, command) -> tk.Button:
        photo = self._load_tool_icon(icon_name)
        button = tk.Button(
            parent,
            command=command,
            bg=APP_PANEL_BG,
            activebackground=APP_PANEL_ACTIVE_BG,
            relief="solid",
            bd=0,
            highlightthickness=2,
            highlightbackground=APP_BUTTON_BORDER,
            highlightcolor=APP_BUTTON_BORDER,
            width=UI_TOOL_BUTTON_SIZE,
            height=UI_TOOL_BUTTON_SIZE,
            padx=0,
            pady=0,
            takefocus=True,
        )
        if photo is None:
            button.configure(text=label, fg="#f2f2f2", activeforeground="#ffffff", font=self.ui_fonts.bold(-5))
        else:
            button.configure(image=photo)
            button.image = photo
        return button

    def _load_tool_icon(self, icon_name: str) -> ImageTk.PhotoImage | None:
        key = f"{icon_name}:{UI_TOOL_ICON_DISPLAY_SIZE}"
        cached = self.tool_icon_images.get(key)
        if cached is not None:
            return cached
        path = UI_BUTTON_ICON_DIR / f"{icon_name}.png"
        try:
            image = Image.open(path).convert("RGBA")
        except OSError:
            return None
        display = image.resize((UI_TOOL_ICON_DISPLAY_SIZE, UI_TOOL_ICON_DISPLAY_SIZE), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(display)
        self.tool_icon_images[key] = photo
        return photo

    def _bind_game_button_help(self, widget: tk.Widget, title_key: str, help_key: str) -> None:
        widget.bind("<Enter>", lambda event, title=title_key, help_text=help_key: self._show_game_button_help(title, help_text, event), add="+")
        widget.bind("<Motion>", lambda event, title=title_key, help_text=help_key: self._show_game_button_help(title, help_text, event), add="+")
        widget.bind("<Leave>", self._hide_game_button_help, add="+")

    def _game_button_help_enabled(self) -> bool:
        try:
            return bool(self.ui_show_button_help_var.get())
        except tk.TclError:
            return bool(self.config_data.ui_setting.get("show_game_button_help", True))

    def _ensure_game_button_help_tooltip(self) -> tuple[tk.Toplevel, tk.Label]:
        if self.game_button_help_tooltip is None or not self.game_button_help_tooltip.winfo_exists():
            tooltip = tk.Toplevel(self)
            tooltip.withdraw()
            tooltip.overrideredirect(True)
            tooltip.configure(bg=APP_BUTTON_BORDER)
            label = tk.Label(
                tooltip,
                bg=APP_PANEL_BG,
                fg="#f2f2f2",
                justify="left",
                anchor="w",
                bd=0,
                padx=12,
                pady=8,
                wraplength=340,
                font=self.ui_fonts.normal(-3),
            )
            label.pack(padx=2, pady=2)
            self.game_button_help_tooltip = tooltip
            self.game_button_help_label = label
        return self.game_button_help_tooltip, self.game_button_help_label

    def _show_game_button_help(self, title_key: str, help_key: str, event) -> None:
        if not self._game_button_help_enabled():
            self._hide_game_button_help()
            return
        tooltip, label = self._ensure_game_button_help_tooltip()
        label.configure(text=f"{_ui_text(self.config_data, title_key)}\n{_ui_text(self.config_data, help_key)}")
        tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
        tooltip.deiconify()

    def _hide_game_button_help(self, _event=None) -> None:
        if self.game_button_help_tooltip is not None and self.game_button_help_tooltip.winfo_exists():
            self.game_button_help_tooltip.withdraw()

    def _open_game_submenu(self) -> None:
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "game_setting"), 320, 230)
        dialog.title(_ui_text(self.config_data, "game_setting"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.columnconfigure(0, weight=1)

        actions = [
            (_ui_text(self.config_data, "game_submenu_continue"), dialog.destroy),
            (_ui_text(self.config_data, "game_submenu_exit"), lambda: self._exit_current_game(dialog)),
            (_ui_text(self.config_data, "game_submenu_settings"), lambda: self._open_settings_from_game_submenu(dialog)),
        ]
        for row, (text, command) in enumerate(actions):
            button = self._instant_button(dialog, text, command)
            button.grid(row=row, column=0, sticky="ew", padx=18, pady=(18 if row == 0 else 8, 18 if row == len(actions) - 1 else 0), ipadx=36, ipady=8)
        dialog.update_idletasks()

    def _exit_current_game(self, dialog: tk.Toplevel) -> None:
        dialog.destroy()
        self._show_screen("title")

    def _open_settings_from_game_submenu(self, dialog: tk.Toplevel) -> None:
        dialog.destroy()
        self._open_settings_screen()

    def _game_tutorial_pages(self) -> list[tuple[str, str]]:
        return [
            (_ui_text(self.config_data, "tutorial_page_start_title"), _ui_text(self.config_data, "tutorial_page_start_body")),
            (_ui_text(self.config_data, "tutorial_page_maps_title"), _ui_text(self.config_data, "tutorial_page_maps_body")),
            (_ui_text(self.config_data, "tutorial_page_items_title"), _ui_text(self.config_data, "tutorial_page_items_body")),
            (_ui_text(self.config_data, "tutorial_page_quests_title"), _ui_text(self.config_data, "tutorial_page_quests_body")),
            (_ui_text(self.config_data, "tutorial_page_first_goal_title"), _ui_text(self.config_data, "tutorial_page_first_goal_body")),
        ]

    def _open_game_tutorial(self) -> None:
        self._hide_game_button_help()
        pages = self._game_tutorial_pages()
        if not pages:
            return
        self.game_tutorial_page_index = max(0, min(self.game_tutorial_page_index, len(pages) - 1))
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "game_tutorial_title"), 760, 520)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        title_var = tk.StringVar()
        body_var = tk.StringVar()
        page_var = tk.StringVar()

        tk.Label(
            dialog,
            textvariable=title_var,
            bg=APP_DEEP_BG,
            fg="#f4d27a",
            anchor="w",
            font=self.ui_fonts.bold(5),
        ).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 10))
        tk.Label(
            dialog,
            textvariable=body_var,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            justify="left",
            anchor="nw",
            wraplength=660,
            font=self.ui_fonts.normal(0),
            padx=18,
            pady=16,
            highlightbackground=APP_BUTTON_BORDER,
            highlightthickness=1,
        ).grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 14))

        footer = tk.Frame(dialog, bg=APP_DEEP_BG)
        footer.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        footer.columnconfigure(1, weight=1)

        prev_btn = self._instant_button(footer, _ui_text(self.config_data, "game_tutorial_prev"), lambda: show_page(self.game_tutorial_page_index - 1))
        prev_btn.grid(row=0, column=0, sticky="w", ipadx=16, ipady=6)
        tk.Label(footer, textvariable=page_var, bg=APP_DEEP_BG, fg="#d8d4cf", font=self.ui_fonts.normal(-2)).grid(row=0, column=1)
        next_btn = self._instant_button(footer, _ui_text(self.config_data, "game_tutorial_next"), lambda: show_page(self.game_tutorial_page_index + 1))
        next_btn.grid(row=0, column=2, sticky="e", padx=(8, 0), ipadx=16, ipady=6)
        close_btn = self._instant_button(footer, _ui_text(self.config_data, "settings_close"), dialog.destroy)
        close_btn.grid(row=0, column=3, sticky="e", padx=(8, 0), ipadx=16, ipady=6)

        def show_page(index: int) -> None:
            index = max(0, min(index, len(pages) - 1))
            self.game_tutorial_page_index = index
            title, body = pages[index]
            title_var.set(title)
            body_var.set(body)
            page_var.set(_ui_text(self.config_data, "game_tutorial_page").format(page=index + 1, total=len(pages)))
            prev_btn.configure(state="normal" if index > 0 else "disabled")
            next_btn.configure(state="normal" if index < len(pages) - 1 else "disabled")

        show_page(self.game_tutorial_page_index)

    def _maybe_open_screen_tutorial(self, screen_name: str) -> None:
        if self.current_screen_name != screen_name or self.screen_tutorial_dialog_open:
            return
        tutorial_map = {
            "world_create": (
                "world_create_tutorial_shown",
                "world_create_tutorial_title",
                "world_create_tutorial_body",
            ),
            "character_setup": (
                "character_setup_tutorial_shown",
                "character_setup_tutorial_title",
                "character_setup_tutorial_body",
            ),
        }
        tutorial = tutorial_map.get(screen_name)
        if tutorial is None:
            return
        flag, title_key, body_key = tutorial
        if bool(self.config_data.ui_setting.get(flag, False)):
            return
        self._open_screen_tutorial(flag, title_key, body_key)

    def _open_screen_tutorial(self, flag: str, title_key: str, body_key: str) -> None:
        self.screen_tutorial_dialog_open = True
        dialog = self._create_modal_dialog(_ui_text(self.config_data, title_key), 700, 460)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        tk.Label(
            dialog,
            text=_ui_text(self.config_data, title_key),
            bg=APP_DEEP_BG,
            fg="#f4d27a",
            anchor="w",
            font=self.ui_fonts.bold(5),
        ).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 10))
        tk.Label(
            dialog,
            text=_ui_text(self.config_data, body_key),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            justify="left",
            anchor="nw",
            wraplength=620,
            font=self.ui_fonts.normal(-1),
            padx=18,
            pady=16,
            highlightbackground=APP_BUTTON_BORDER,
            highlightthickness=1,
        ).grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 14))
        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        actions.columnconfigure(0, weight=1)

        def close() -> None:
            self.screen_tutorial_dialog_open = False
            self._set_ui_setting_value(flag, True)
            dialog.destroy()

        self._instant_button(actions, _ui_text(self.config_data, "settings_close"), close).grid(row=0, column=1, sticky="e", ipadx=24, ipady=7)
        dialog.protocol("WM_DELETE_WINDOW", close)

    def _instant_text(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        height: int,
        padx=0,
        pady=0,
        fixed_height: int | None = None,
    ) -> tk.Text:
        if fixed_height is not None:
            holder_bg = APP_DEEP_BG
            try:
                holder_bg = str(parent.cget("bg"))
            except tk.TclError:
                pass
            holder = tk.Frame(parent, bg=holder_bg, height=fixed_height)
            holder.grid(row=row, column=column, sticky="ew", padx=padx, pady=pady)
            holder.grid_propagate(False)
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)
            parent = holder
            row = 0
            column = 0
            padx = 0
            pady = 0
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            padx=10,
            pady=8,
            font=self.ui_fonts.normal(-2),
        )
        text.grid(row=row, column=column, sticky="nsew", padx=padx, pady=pady)
        return text

    def _instant_labeled_text(self, parent: tk.Widget, label: str, row: int, height: int) -> tk.Text:
        frame = self._instant_panel(parent, row, 0, sticky="nsew", pady=(0, 20))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        tk.Label(frame, text=label, bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        return self._instant_text(frame, 1, 0, height=height, padx=8, pady=(4, 8))

    def _character_stat_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, row: int) -> None:
        tk.Label(parent, text=label, bg=APP_PANEL_BG, fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=row, column=0, sticky="ew", padx=(72, 8), pady=(8 if row == 0 else 2, 2))
        tk.Label(parent, textvariable=variable, bg=APP_PANEL_BG, fg="#f2f2f2", anchor="center", width=4, font=self.ui_fonts.bold(-2)).grid(row=row, column=1, sticky="ew")
        minimum = CHARACTER_STAT_BASE if self._is_character_stat_var(variable) else 0
        maximum = CHARACTER_STAT_MAX if self._is_character_stat_var(variable) else 999999
        self._instant_button(parent, "-", lambda var=variable, min_value=minimum, max_value=maximum: self._adjust_character_number(var, -1, min_value, max_value)).grid(row=row, column=2, padx=4, pady=2, ipadx=8)
        self._instant_button(parent, "+", lambda var=variable, min_value=minimum, max_value=maximum: self._adjust_character_number(var, 1, min_value, max_value)).grid(row=row, column=3, padx=(4, 64), pady=2, ipadx=8)

    def _adjust_character_number(self, variable: tk.StringVar, delta: int, minimum: int, maximum: int) -> None:
        current = _safe_int(variable.get(), minimum)
        value = max(minimum, min(maximum, current + delta))
        if self._is_character_stat_var(variable):
            other_spent = self._character_stat_spent(exclude=variable)
            max_for_stat = CHARACTER_STAT_BASE + max(0, CHARACTER_BONUS_POINTS - other_spent)
            value = max(CHARACTER_STAT_BASE, min(min(CHARACTER_STAT_MAX, max_for_stat), value))
        variable.set(str(value))
        self._refresh_character_setup_points()

    def _character_stat_variables(self) -> tuple[tk.StringVar, ...]:
        return (
            self.character_str_var,
            self.character_dex_var,
            self.character_con_var,
            self.character_int_var,
            self.character_wis_var,
            self.character_cha_var,
        )

    def _is_character_stat_var(self, variable: tk.StringVar) -> bool:
        return any(variable is stat_var for stat_var in self._character_stat_variables())

    def _character_stat_spent(self, *, exclude: tk.StringVar | None = None) -> int:
        total = 0
        for variable in self._character_stat_variables():
            if exclude is not None and variable is exclude:
                continue
            value = max(CHARACTER_STAT_BASE, _safe_int(variable.get(), CHARACTER_STAT_BASE))
            total += max(0, value - CHARACTER_STAT_BASE)
        return total

    def _refresh_character_setup_points(self) -> None:
        self._refresh_character_gender_button()
        spent = self._character_stat_spent()
        remaining = max(0, CHARACTER_BONUS_POINTS - spent)
        self.character_ability_points_var.set(f"BP:{remaining}")
        if hasattr(self, "character_preview_canvas"):
            self._render_character_preview()

    def _refresh_character_gender_button(self) -> None:
        if not hasattr(self, "character_gender_label_var"):
            return
        label = _gender_button_label(self.character_gender_var.get())
        self.character_gender_label_var.set(label)
        if hasattr(self, "character_gender_btn"):
            self.character_gender_btn.configure(text=label)

    def _cycle_character_gender(self) -> None:
        values = ("female", "male", "other")
        current = self.character_gender_var.get()
        next_value = values[(values.index(current) + 1) % len(values)] if current in values else values[0]
        self.character_gender_var.set(next_value)
        self._refresh_character_gender_button()

    def _reset_character_preset(self) -> None:
        self.player_var.set("Nana")
        self.character_gender_var.set("female")
        self._refresh_character_gender_button()
        self.character_age_var.set("20")
        self.character_category_var.set("young woman")
        for variable in self._character_stat_variables():
            variable.set(str(CHARACTER_STAT_BASE))
        self.character_gold_var.set("100")
        if hasattr(self, "character_backstory_text"):
            self.character_backstory_text.delete("1.0", "end")
            self.character_backstory_text.insert("1.0", "辺境の村で育った駆け出しの冒険者。")
        if hasattr(self, "character_look_text"):
            self.character_look_text.delete("1.0", "end")
            self.character_look_text.insert("1.0", "short hair, clear eyes, leather armor, practical travel cloak")
        if hasattr(self, "character_skills_frame") or hasattr(self, "character_skills_text"):
            self._set_character_entries(
                "skills",
                _parse_character_skills(
                    "一閃 | physical | 武器で素早く斬り込む基本技 | 5 | 2 | str | damage_hp_single\n"
                    "応急処置 | light | 簡単な治療で体勢を立て直す | 3 | 1 | wis | heal_single"
                ),
            )
        if hasattr(self, "character_traits_frame") or hasattr(self, "character_traits_text"):
            self._set_character_entries(
                "traits",
                _parse_character_traits(
                    "冷静 | 危機でも判断力を失いにくい\n"
                    "旅慣れ | 野外行動に慣れている"
                ),
            )
        self._refresh_character_setup_points()

    def _render_character_preview(self) -> None:
        if not hasattr(self, "character_preview_canvas"):
            return
        canvas = self.character_preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_rectangle(0, 0, width, height, fill=APP_PANEL_BG, outline="")
        image = self._character_setup_preview_image()
        if image is not None:
            display = _fit_image(image, max(1, width - 32), max(1, height - 32))
            photo = ImageTk.PhotoImage(display)
            self.character_preview_image = photo
            canvas.create_image(width // 2, height // 2, image=photo, anchor="center")
            return

        name = self.player_var.get().strip() or "No Name"
        canvas.create_text(
            width // 2,
            height // 2,
            text=f"{name}\nPreview image is not generated yet.",
            fill="#6f6f6f",
            anchor="center",
            width=max(120, width - 70),
            font=self.ui_fonts.bold(0),
            justify="center",
        )

    def _character_setup_preview_image(self) -> Image.Image | None:
        character = self.engine.state.world_data.character(self.player_var.get().strip())
        if character:
            image_path = _subject_image_path(
                character.image_paths,
                ("add_border_image", "generated_image", "no_bg_image", "face_image"),
            )
            image = self._load_layer_image(image_path)
            if image is not None:
                return image
        if self.last_character_preview_path and self.last_character_preview_name == self.player_var.get().strip():
            return self._load_layer_image(self.last_character_preview_path)
        return None

    def _generate_character_preview_image(self) -> None:
        if not self._image_generation_enabled(show_status=True):
            return
        if self.engine.state.world_data.world_name == "unknown":
            self._show_error(ValueError(_ui_text(self.config_data, "character_need_world_image")))
            return
        character = self._character_from_setup()

        def task():
            character.flags["is_player"] = True
            character.flags.setdefault("source", "character_setup_preview")
            self.engine.state.world_data.add_character(character)
            return self.engine.generate_character_image(character.name, save_game=False)

        def done(result) -> None:
            self.last_character_preview_path = str(result.path)
            self.last_character_preview_name = self.player_var.get().strip()
            self.image_cache.clear()
            self._render_character_preview()
            self._append_log("\n" + _ui_text(self.config_data, "log_character_preview").format(path=result.path) + "\n")

        self._run_task(_ui_text(self.config_data, "character_generating_preview"), task, done)

    def _open_character_list_editor(self, kind: str) -> None:
        source = getattr(self, "character_skills_text", None) if kind == "skills" else getattr(self, "character_traits_text", None)
        title = _ui_text(self.config_data, "character_skill_settings" if kind == "skills" else "character_trait_settings")
        hint = (
            _ui_text(self.config_data, "character_skill_hint")
            if kind == "skills"
            else _ui_text(self.config_data, "character_trait_hint")
        )
        dialog = self._create_modal_dialog(title, 720, 520)
        dialog.title(title)
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry("720x520")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text=hint,
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        editor = tk.Text(
            dialog,
            wrap="word",
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            padx=10,
            pady=8,
            font=self.ui_fonts.normal(-2),
        )
        editor.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        entries = self.character_skill_entries if kind == "skills" else self.character_trait_entries
        if entries:
            editor.insert("1.0", _format_character_skills(entries) if kind == "skills" else _format_character_traits(entries))
        elif isinstance(source, tk.Text):
            editor.insert("1.0", source.get("1.0", "end-1c"))

        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        if kind == "skills":
            self._instant_button(actions, _ui_text(self.config_data, "common_generate"), lambda: self._generate_character_setup_entries(kind, editor)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_apply"), lambda: self._apply_character_list_editor(kind, editor, dialog)).grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _apply_character_list_editor(self, kind: str, editor: tk.Text, dialog: tk.Toplevel) -> None:
        self._set_character_list_text(kind, editor.get("1.0", "end").strip())
        dialog.destroy()
        self._render_character_preview()

    def _open_character_entry_generator(self, kind: str, entry_index: int | None = None) -> None:
        is_skill = kind == "skills"
        entries = self.character_skill_entries if is_skill else self.character_trait_entries
        current_entry = dict(entries[entry_index]) if entry_index is not None and 0 <= entry_index < len(entries) else {}
        title = _ui_text(self.config_data, "character_skill_settings" if is_skill else "character_trait_settings")
        dialog = self._create_modal_dialog(title, 560, 540)
        dialog.title(title)
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry("560x540")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=0)
        dialog.rowconfigure(1, weight=1)

        top = tk.Frame(dialog, bg=APP_DEEP_BG)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        top.columnconfigure(1, weight=1)
        tk.Label(
            top,
            text=_ui_text(self.config_data, "character_entry_name_skill" if is_skill else "character_entry_name_trait"),
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            font=self.ui_fonts.bold(-3),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        name_var = tk.StringVar(value=str(current_entry.get("name") or ""))
        name_entry = tk.Entry(
            top,
            textvariable=name_var,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightbackground="#d8d4cf",
            highlightthickness=1,
            font=self.ui_fonts.normal(-2),
        )
        name_entry.grid(row=0, column=1, sticky="ew", ipady=8)

        element_var = tk.StringVar()
        if is_skill:
            language = getattr(self.config_data, "language", "ja")
            element_labels = [tr_enum("element", element_id, language, fallback=element_id) for element_id in ELEMENT_IDS]
            current_element = _normalise_element_id(current_entry.get("element"), fallback="fire")
            element_var.set(tr_enum("element", current_element, language, fallback=current_element))
            tk.Label(
                top,
                text=_ui_text(self.config_data, "character_entry_element"),
                bg=APP_DEEP_BG,
                fg="#d8d4cf",
                font=self.ui_fonts.bold(-3),
            ).grid(row=0, column=2, sticky="e", padx=(12, 6))
            element_combo = ttk.Combobox(top, textvariable=element_var, values=element_labels, state="readonly", width=8)
            element_combo.grid(row=0, column=3, sticky="e", ipady=5)

        description_frame = self._instant_panel(dialog, 1, 0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))
        description_frame.columnconfigure(0, weight=1)
        description_frame.rowconfigure(1, weight=1)
        tk.Label(
            description_frame,
            text=_ui_text(self.config_data, "character_entry_description"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        description_text = self._instant_text(description_frame, 1, 0, height=10, padx=8, pady=(4, 8))
        current_description = str(current_entry.get("desc") or "").strip()
        if current_description:
            description_text.insert("1.0", current_description)

        result_frame = self._instant_panel(dialog, 2, 0, sticky="nsew", padx=(12, 8), pady=(0, 12))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)
        tk.Label(
            result_frame,
            text=_ui_text(self.config_data, "character_entry_result"),
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(-3),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        result_text = self._instant_text(result_frame, 1, 0, height=4, padx=8, pady=(2, 8))
        if current_entry:
            result_text.insert("1.0", _character_entry_generated_summary(current_entry, kind, self.config_data))
        result_text.configure(state="disabled")

        action_frame = self._instant_panel(dialog, 2, 1, sticky="nsew", padx=(8, 12), pady=(0, 12))
        action_frame.columnconfigure(0, weight=1)
        action_frame.rowconfigure(0, weight=1)

        def selected_element_id() -> str:
            if not is_skill:
                return ""
            label = element_var.get()
            language = getattr(self.config_data, "language", "ja")
            for element_id in ELEMENT_IDS:
                if label == tr_enum("element", element_id, language, fallback=element_id):
                    return element_id
            return "fire"

        def generate() -> None:
            if is_skill and self.engine.state.world_data.world_name == "unknown":
                self._show_error(ValueError(_ui_text(self.config_data, "character_need_world_details")))
                return
            character = self._character_from_setup()
            seed_name = name_var.get().strip()
            seed_description = description_text.get("1.0", "end").strip()
            element_id = selected_element_id()

            if not is_skill:
                normalized_trait = _character_trait_entries([{"name": seed_name, "desc": seed_description}])
                if not normalized_trait:
                    self._show_error(ValueError(_ui_text(self.config_data, "character_entry_empty_result")))
                    return
                entry = normalized_trait[0]
                self._replace_character_entry_at(kind, entry_index, entry)
                if result_text.winfo_exists():
                    result_text.configure(state="normal")
                    result_text.delete("1.0", "end")
                    result_text.insert("1.0", _character_entry_generated_summary(entry, kind, self.config_data))
                    result_text.configure(state="disabled")
                if generate_btn.winfo_exists():
                    generate_btn.configure(text=_ui_text(self.config_data, "character_close"), command=dialog.destroy)
                self._render_character_preview()
                kind_label = _ui_text(self.config_data, "character_traits").rstrip(":：")
                self._append_log("\n" + _ui_text(self.config_data, "log_character_generated").format(kind=kind_label) + "\n")
                return

            def task():
                return self.engine.generate_character_setup_skills(
                    character,
                    desired_element=element_id,
                    seed_name=seed_name,
                    seed_description=seed_description,
                )

            def done(entries) -> None:
                normalized = _normalise_character_skills(entries)
                if not normalized:
                    raise ValueError(_ui_text(self.config_data, "character_entry_empty_result"))
                candidates: list[dict[str, object]] = []
                for candidate in normalized:
                    entry = dict(candidate)
                    if seed_name:
                        entry["name"] = seed_name
                    if seed_description:
                        entry["desc"] = seed_description
                    entry["element"] = element_id
                    normalized_entry = _normalise_character_skills([entry])
                    if normalized_entry:
                        candidates.append(normalized_entry[0])
                existing_entries = self.character_skill_entries
                entry = _select_generated_character_entry(candidates, existing_entries, kind, entry_index)
                if not entry:
                    raise ValueError(_ui_text(self.config_data, "character_entry_empty_result"))
                self._replace_character_entry_at(kind, entry_index, entry)
                if result_text.winfo_exists():
                    result_text.configure(state="normal")
                    result_text.delete("1.0", "end")
                    result_text.insert("1.0", _character_entry_generated_summary(entry, kind, self.config_data))
                    result_text.configure(state="disabled")
                if generate_btn.winfo_exists():
                    generate_btn.configure(text=_ui_text(self.config_data, "character_close"), command=dialog.destroy)
                self._render_character_preview()
                kind_label = _ui_text(self.config_data, "character_skills").rstrip(":：")
                self._append_log("\n" + _ui_text(self.config_data, "log_character_generated").format(kind=kind_label) + "\n")

            kind_label = _ui_text(self.config_data, "character_skills").rstrip(":：")
            self._run_task(_ui_text(self.config_data, "character_generating_entries").format(kind=kind_label), task, done)

        generate_btn = self._instant_button(
            action_frame,
            _ui_text(self.config_data, "common_generate" if is_skill else "character_apply"),
            generate,
        )
        generate_btn.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        name_entry.focus_set()

    def _generate_character_setup_entries(self, kind: str, target_text: tk.Text | None = None) -> None:
        if kind != "skills":
            entries = _character_trait_entries(self.character_trait_entries)
            text = _format_character_traits(entries)
            if target_text is not None and target_text.winfo_exists():
                target_text.delete("1.0", "end")
                target_text.insert("1.0", text)
            else:
                self._set_character_entries(kind, entries)
            return
        if self.engine.state.world_data.world_name == "unknown":
            self._show_error(ValueError(_ui_text(self.config_data, "character_need_world_details")))
            return
        character = self._character_from_setup()

        def task():
            return self.engine.generate_character_setup_skills(character)

        def done(entries) -> None:
            normalized = _normalise_character_skills(entries)
            text = _format_character_skills(normalized)
            if target_text is not None and target_text.winfo_exists():
                target_text.delete("1.0", "end")
                target_text.insert("1.0", text)
            else:
                self._set_character_entries(kind, normalized)
            self._append_log("\n" + _ui_text(self.config_data, "log_character_generated").format(kind=kind_label) + "\n")

        kind_label = _ui_text(self.config_data, "character_skills" if kind == "skills" else "character_traits").rstrip(":：")
        self._run_task(_ui_text(self.config_data, "character_generating_entries").format(kind=kind_label), task, done)

    def _set_character_list_text(self, kind: str, text: str) -> None:
        entries = _parse_character_skills(text) if kind == "skills" else _parse_character_traits(text)
        self._set_character_entries(kind, entries)

    def _set_character_entries(self, kind: str, entries: list[dict[str, object]]) -> None:
        entries = _normalise_character_skills(entries) if kind == "skills" else _character_trait_entries(entries)
        if kind == "skills":
            self.character_skill_entries = entries
        else:
            self.character_trait_entries = entries
        frame_name = "character_skills_frame" if kind == "skills" else "character_traits_frame"
        if hasattr(self, frame_name):
            self._render_character_entry_buttons(kind)
            return
        text_name = "character_skills_text" if kind == "skills" else "character_traits_text"
        if not hasattr(self, text_name):
            return
        widget = getattr(self, text_name)
        if not widget.winfo_exists():
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", _format_character_entry_names(entries))
        widget.configure(state="disabled")

    def _render_character_entry_buttons(self, kind: str) -> None:
        frame_name = "character_skills_frame" if kind == "skills" else "character_traits_frame"
        if not hasattr(self, frame_name):
            return
        frame = getattr(self, frame_name)
        if not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        entries = self.character_skill_entries if kind == "skills" else self.character_trait_entries
        for index, entry in enumerate(entries):
            name = str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
            if not name:
                name = _ui_text(self.config_data, "character_entry_name_skill" if kind == "skills" else "character_entry_name_trait")
            button = self._instant_button(frame, name, lambda item_index=index, item_kind=kind: self._open_character_entry_from_button(item_kind, item_index))
            button.grid(row=index, column=0, sticky="ew", pady=(0 if index == 0 else 10, 0), ipady=8)
            self._bind_character_entry_button_tooltip(button, kind, index)

    def _open_character_entry_from_button(self, kind: str, index: int) -> None:
        self._hide_character_entry_tooltip()
        self._open_character_entry_generator(kind, index)

    def _upsert_character_entry(self, kind: str, entry: dict[str, object]) -> None:
        entries = list(self.character_skill_entries if kind == "skills" else self.character_trait_entries)
        name = str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
        key = name.casefold()
        replaced = False
        for index, existing in enumerate(entries):
            existing_name = str(existing.get("name") or existing.get("skill") or existing.get("trait") or "").strip()
            if existing_name.casefold() == key:
                entries[index] = entry
                replaced = True
                break
        if not replaced:
            entries.append(entry)
        self._set_character_entries(kind, entries)

    def _replace_character_entry_at(self, kind: str, index: int | None, entry: dict[str, object]) -> None:
        if index is None:
            self._upsert_character_entry(kind, entry)
            return
        entries = list(self.character_skill_entries if kind == "skills" else self.character_trait_entries)
        if index < 0 or index >= len(entries):
            self._upsert_character_entry(kind, entry)
            return
        entries[index] = entry
        self._set_character_entries(kind, entries)

    def _bind_character_entry_button_tooltip(self, button: tk.Button, kind: str, index: int) -> None:
        button.bind("<Enter>", lambda event, item_kind=kind, item_index=index: self._show_character_entry_button_tooltip(item_kind, item_index, event))
        button.bind("<Motion>", lambda event, item_kind=kind, item_index=index: self._show_character_entry_button_tooltip(item_kind, item_index, event))
        button.bind("<Leave>", self._hide_character_entry_tooltip)

    def _bind_character_entry_tooltip(self, widget: tk.Text, kind: str) -> None:
        widget.bind("<Motion>", lambda event, item_kind=kind, target=widget: self._show_character_entry_tooltip(item_kind, target, event))
        widget.bind("<Leave>", self._hide_character_entry_tooltip)

    def _ensure_character_entry_tooltip(self) -> tuple[tk.Toplevel, tk.Label]:
        if self.character_entry_tooltip is None or not self.character_entry_tooltip.winfo_exists():
            tooltip = tk.Toplevel(self)
            tooltip.withdraw()
            tooltip.overrideredirect(True)
            tooltip.configure(bg="#d8d4cf")
            label = tk.Label(
                tooltip,
                bg=APP_PANEL_BG,
                fg="#f2f2f2",
                justify="left",
                anchor="w",
                bd=1,
                relief="solid",
                padx=8,
                pady=6,
                font=self.ui_fonts.normal(-3),
            )
            label.pack()
            self.character_entry_tooltip = tooltip
            self.character_entry_tooltip_label = label
        return self.character_entry_tooltip, self.character_entry_tooltip_label

    def _show_character_entry_tooltip(self, kind: str, widget: tk.Text, event) -> None:
        entries = self.character_skill_entries if kind == "skills" else self.character_trait_entries
        if not entries:
            self._hide_character_entry_tooltip()
            return
        try:
            line = int(str(widget.index(f"@{event.x},{event.y}")).split(".", 1)[0]) - 1
        except (tk.TclError, ValueError):
            self._hide_character_entry_tooltip()
            return
        if line < 0 or line >= len(entries):
            self._hide_character_entry_tooltip()
            return
        tooltip, label = self._ensure_character_entry_tooltip()
        label.configure(text=_character_entry_tooltip_text(entries[line], kind, self.config_data))
        tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
        tooltip.deiconify()

    def _show_character_entry_button_tooltip(self, kind: str, index: int, event) -> None:
        entries = self.character_skill_entries if kind == "skills" else self.character_trait_entries
        if index < 0 or index >= len(entries):
            self._hide_character_entry_tooltip()
            return
        tooltip, label = self._ensure_character_entry_tooltip()
        label.configure(text=_character_entry_tooltip_text(entries[index], kind, self.config_data))
        tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
        tooltip.deiconify()

    def _hide_character_entry_tooltip(self, _event=None) -> None:
        if self.character_entry_tooltip is not None and self.character_entry_tooltip.winfo_exists():
            self.character_entry_tooltip.withdraw()

    def _player_status_text(self) -> str:
        state = self.engine.state
        player = self._player_character_dict()
        gold = int(player.get("gold") or state.gold or 0)
        time_label = self.engine.current_time_label()
        combat_stats = self.engine.player_combat_stats()
        atk = int(combat_stats.get("attack") or 0)
        atk_bonus = int(combat_stats.get("attack_bonus") or 0)
        defense = int(combat_stats.get("defense") or 0)
        defense_bonus = int(combat_stats.get("defense_bonus") or 0)
        location = self._display_location_name()
        quest = state.active_quest or "-"
        quest_remaining = self.engine.active_quest_remaining_time_label() if state.active_quest else "-"
        hunger, max_hunger = self.engine.player_hunger_status()
        language = self.config_data.language
        info_labels = (
            {
                "attack": "攻撃力",
                "defense": "防御力",
                "gold": "所持金",
                "time": "日時",
                "location": "現在地",
                "quest": "クエスト",
                "hunger": "空腹度",
            }
            if language == "ja"
            else {
                "attack": "Attack",
                "defense": "Defense",
                "gold": "Gold",
                "time": "Time",
                "location": "Location",
                "quest": "Quest",
                "hunger": "Hunger",
            }
        )
        label = lambda key: info_labels.get(key, tr_enum("status_field", key, language))
        return "\n".join(
            [
                f"{label('attack')}: {atk}({atk_bonus:+d})",
                f"{label('defense')}: {defense}({defense_bonus:+d})",
                f"{label('gold')}: {gold}",
                f"{label('time')}: {time_label}",
                f"{label('location')}: {location}",
                f"{label('quest')}: {quest}",
                f"{'残り時間' if language == 'ja' else 'Quest time'}: {quest_remaining}",
                f"{label('hunger')}: {hunger}/{max_hunger}",
            ]
        )

    def _render_player_info_panel(self) -> None:
        if not hasattr(self, "info_canvas"):
            return
        canvas = self.info_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_rectangle(0, 0, width, height, fill=APP_PANEL_BG, outline="")
        lines = self._player_status_text().splitlines()
        x = 14
        y = 14
        line_height = max(26, self.ui_fonts.size + 8)
        font = self.ui_fonts.bold(4 if height >= 220 else 0)
        for line in lines:
            item_id = canvas.create_text(
                x,
                y,
                text=line,
                fill="#f2f2f2",
                anchor="nw",
                font=font,
                width=max(120, width - x * 2),
            )
            bbox = canvas.bbox(item_id)
            if bbox:
                y = max(y + line_height, bbox[3] + 4)
            else:
                y += line_height

    def _player_character_dict(self) -> dict[str, object]:
        player = self.engine.player_character()
        if player:
            return player.to_dict()
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            return self.engine.state.party[0]
        return {}

    def _render_actor_rosters(self) -> None:
        if not hasattr(self, "npc_roster_canvas"):
            return
        self.roster_image_refs = []
        self._draw_roster_canvas(self.npc_roster_canvas, self._npc_roster_items(), "NPC / ENEMY")
        player_items = self._player_roster_items()
        self._draw_roster_canvas(self.player_roster_canvas, player_items[:1], "PLAYER")
        self._draw_roster_canvas(self.companion_roster_canvas, player_items[1:1 + UI_PARTY_COMPANION_LIMIT], "ALLY")

    def _ellipsize_canvas_text(self, text: str, font_spec: object, max_width: int) -> str:
        value = " ".join(str(text or "").split())
        if not value:
            return ""
        try:
            if isinstance(font_spec, str):
                font_obj = tkfont.nametofont(font_spec)
            else:
                font_obj = tkfont.Font(root=self, font=font_spec)
            if font_obj.measure(value) <= max_width:
                return value
            ellipsis = "..."
            while value and font_obj.measure(value + ellipsis) > max_width:
                value = value[:-1]
            return (value + ellipsis) if value else ellipsis
        except tk.TclError:
            return _short_display(value, 24)

    def _draw_roster_canvas(self, canvas: tk.Canvas, items: list[dict[str, object]], title: str) -> None:
        canvas.delete("all")
        self.roster_hitboxes[id(canvas)] = []
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_rectangle(0, 0, width, height, fill=APP_PANEL_BG, outline="")
        language = self.config_data.language
        is_party_panel = title in {"PLAYER", "ALLY"}
        if not items:
            if title == "ALLY":
                empty_text = tr_enum(
                    "roster",
                    "no_companion",
                    language,
                    fallback="No companion" if str(language).lower().startswith("en") else "同行者なし",
                )
            else:
                empty_text = tr_enum("roster", "no_player" if title == "PLAYER" else "no_npc", language)
            canvas.create_text(
                width // 2,
                height // 2,
                text=empty_text,
                fill="#575757",
                font=self.ui_fonts.bold(-2),
            )
            return
        visible_limit = UI_PARTY_COMPANION_LIMIT if title == "ALLY" else 1 if title == "PLAYER" else 3
        visible_items = items[:visible_limit]
        row_count = max(1, min(len(visible_items), visible_limit))
        if title == "PLAYER":
            row_height = height
        elif title == "ALLY":
            row_height = max(76, min(128, height // UI_PARTY_COMPANION_LIMIT))
        else:
            row_height = max(76, min(128, height // row_count))
        for index, item in enumerate(visible_items):
            top = index * row_height
            bottom = min(height, top + row_height)
            self.roster_hitboxes[id(canvas)].append((0, top, width, bottom, item))
            canvas.create_rectangle(0, top, width, bottom, fill=APP_PANEL_BG, outline="#d8d4cf")
            image = item.get("image")
            image_box = min(
                max(56, int(width * (0.42 if is_party_panel else 0.28))),
                max(56, row_height - 12),
                132 if is_party_panel else 96,
            )
            if isinstance(image, Image.Image):
                display = _cover_image(image, image_box, image_box)
                photo = ImageTk.PhotoImage(display)
                self.roster_image_refs.append(photo)
                canvas.create_image(8, top + max(6, (row_height - image_box) // 2), image=photo, anchor="nw")
            elif is_party_panel:
                canvas.create_rectangle(8, top + max(6, (row_height - image_box) // 2), 8 + image_box, top + max(6, (row_height - image_box) // 2) + image_box, outline="#575757")
                canvas.create_text(8 + image_box // 2, top + row_height // 2, text=tr_enum("roster", "face", language), fill="#575757", font=self.ui_fonts.bold(-5))
            text_x = image_box + 24 if width > 240 else 74
            name = str(item.get("name") or tr_enum("roster", "unknown", language))
            subtitle = str(item.get("subtitle") or "")
            hp = str(item.get("hp") or "")
            sp = str(item.get("sp") or "")
            compact_party = is_party_panel and row_height <= 88
            if is_party_panel:
                hp_y = top + (10 if compact_party else 14)
                sp_y = top + (27 if compact_party else 34)
                name_y = top + (44 if compact_party else (58 if sp else 38))
                subtitle_y = top + (62 if compact_party else name_y + 24)
                name_y = min(name_y, max(top + 12, bottom - 28))
                subtitle_y = min(subtitle_y, max(top + 24, bottom - 12))
            else:
                compact_npc = row_height <= 88
                hp_y = top + (8 if compact_npc else 12)
                sp_y = top + (23 if compact_npc else 29)
                if hp or sp:
                    name_y = top + (39 if compact_npc else 48)
                    subtitle_y = top + (57 if compact_npc else 70)
                else:
                    name_y = top + (18 if compact_npc else 24)
                    subtitle_y = top + (39 if compact_npc else 48)
                name_y = min(max(name_y, top + 8), max(top + 8, bottom - 30))
                subtitle_y = min(max(subtitle_y, name_y + (14 if compact_npc else 16)), max(top + 10, bottom - 18))
            text_width = max(80, width - text_x - 12)
            hp_font = self.ui_fonts.bold(-5 if compact_party else -4)
            sp_font = self.ui_fonts.bold(-5 if compact_party else -4)
            name_font = self.ui_fonts.bold(-3 if compact_party else -2)
            subtitle_font = self.ui_fonts.normal(-6 if compact_party else -5)
            name_text = self._ellipsize_canvas_text(name, name_font, text_width)
            subtitle_text = self._ellipsize_canvas_text(subtitle, subtitle_font, text_width)
            canvas.create_text(width - 8, hp_y, text=hp, fill="#f2f2f2", anchor="ne", font=hp_font)
            if sp:
                canvas.create_text(width - 8, sp_y, text=sp, fill="#a8d8ff", anchor="ne", font=sp_font)
            canvas.create_text(width - 8, name_y, text=name_text, fill="#f2f2f2", anchor="ne", font=name_font)
            if subtitle_text:
                canvas.create_text(width - 8, subtitle_y, text=subtitle_text, fill="#d8d4cf", anchor="ne", font=subtitle_font)

    def _on_roster_click(self, event) -> None:
        canvas = event.widget
        if not isinstance(canvas, tk.Canvas):
            return
        for left, top, right, bottom, item in self.roster_hitboxes.get(id(canvas), []):
            if left <= event.x <= right and top <= event.y <= bottom:
                self._open_actor_status_window(item)
                return

    def _open_actor_status_window(self, item: dict[str, object]) -> None:
        language = self.config_data.language
        name = str(item.get("name") or tr_enum("roster", "unknown", language))
        dialog_title = tr_enum_format("roster", "status_title", language, name=name)
        dialog = self._create_modal_dialog(dialog_title, 680, 620)
        dialog.title(dialog_title)
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry("680x620")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text=name,
            bg=APP_DEEP_BG,
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(1),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        detail = tk.Text(
            dialog,
            wrap="word",
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            padx=12,
            pady=10,
            font=self.ui_fonts.normal(-2),
        )
        detail.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        detail.insert("1.0", self._actor_status_detail_text(item))
        detail.configure(state="disabled")

        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, "閉じる", dialog.destroy).grid(row=0, column=1, sticky="e")

    def _status_item_character(self, item: dict[str, object]) -> Character | None:
        kind = str(item.get("kind") or "")
        if kind == "player":
            return self.engine.player_character()
        uuid = str(item.get("uuid") or item.get("character_uuid") or "").strip()
        name = str(item.get("name") or item.get("character_name") or "").strip()
        return self._world_character_by_uuid_or_non_player_name(uuid, name)

    def _world_character_by_uuid_or_non_player_name(self, uuid: str = "", name: str = "") -> Character | None:
        world = self.engine.state.world_data
        uuid = str(uuid or "").strip()
        if uuid:
            character = world.character(uuid)
            if character:
                return character
        name = str(name or "").strip()
        if not name:
            return None
        for character in world.characters.values():
            if character.name == name and not character.flags.get("is_player"):
                return character
        character = world.character(name)
        if character and not character.flags.get("is_player"):
            return character
        return None

    def _actor_status_detail_text(self, item: dict[str, object]) -> str:
        language = self.config_data.language
        kind = str(item.get("kind") or "")
        name = str(item.get("name") or "")
        uuid = str(item.get("uuid") or "").strip()
        encounter = item.get("encounter") if isinstance(item.get("encounter"), dict) else {}
        if kind in {"player", "character", "companion"}:
            character = self._status_item_character(item)
            if character and kind != "player":
                self.engine._ensure_character_runtime_data(character)
            data = character.to_dict() if character else {}
            if kind == "companion":
                companion_ref = uuid or str(data.get("uuid") or "") or name
                companion = self._companion_character_dict(companion_ref)
                data = {**data, **companion} if data else companion
            if kind == "player":
                player = self._player_character_dict()
                data = {**data, **player} if data else player
                data["inventory"] = self._player_inventory()
                data["equipment"] = self.engine._player_equipment()
                encounter = self.engine.state.flags.get("active_encounter") if isinstance(self.engine.state.flags.get("active_encounter"), dict) else {}
            if not data:
                return f"{name}\n\n{tr_enum('roster', 'no_character_data', language)}"
            data = dict(data)
            encounter_data = encounter if isinstance(encounter, dict) else {}
            data["status_effects"] = self._actor_detail_status_effects(data, kind=kind, encounter=encounter_data)
            return _format_character_status_detail(data, encounter_data, is_player=kind == "player", language=language)

        return f"{name}\n\n{tr_enum('roster', 'no_status_data', language)}"

    def _actor_detail_status_effects(self, data: dict[str, object], *, kind: str, encounter: dict[str, object]) -> list[object]:
        collected: list[object] = []
        seen: set[str] = set()

        def add_all(value: object) -> None:
            if not isinstance(value, list):
                return
            for effect in value:
                if isinstance(effect, dict):
                    effect_id = str(effect.get("effect_id") or effect.get("id") or effect.get("status_id") or "").strip()
                    effect_name = str(effect.get("name") or effect.get("status") or "").strip()
                    effect_text = str(effect.get("description") or effect.get("llm_effect") or effect.get("effect_text") or "").strip()
                    key_source = "|".join(part for part in (effect_id, effect_name, effect_text) if part) or json.dumps(effect, ensure_ascii=False, sort_keys=True, default=str)
                    key = str(key_source).strip().casefold()
                    item: object = dict(effect)
                else:
                    key = str(effect).strip().casefold()
                    item = effect
                if not key or key in seen:
                    continue
                seen.add(key)
                collected.append(item)

        active_encounter = isinstance(encounter, dict) and encounter.get("status") != "ended"
        if kind == "player":
            add_all(getattr(self.engine.state, "status_effects", []))
            if active_encounter:
                add_all(encounter.get("player_status_effects"))
            player = self.engine.player_character()
            if player:
                add_all(player.status_effects)
            if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
                add_all(self.engine.state.party[0].get("status_effects"))
            add_all(data.get("status_effects"))
            return collected

        data_name = str(data.get("name") or "").strip()
        data_uuid = str(data.get("uuid") or "").strip()
        if active_encounter:
            raw_opponents = encounter.get("opponents")
            for entry in raw_opponents if isinstance(raw_opponents, list) else []:
                if not isinstance(entry, dict):
                    continue
                entry_name = str(entry.get("name") or "").strip()
                entry_uuid = str(entry.get("uuid") or "").strip()
                if entry_name == data_name or (data_uuid and entry_uuid == data_uuid):
                    add_all(entry.get("status_effects"))
                    add_all(entry.get("opponent_status_effects"))
                    break
            if str(encounter.get("opponent_name") or "").strip() == data_name or (
                data_uuid and str(encounter.get("opponent_uuid") or "").strip() == data_uuid
            ):
                add_all(encounter.get("opponent_status_effects"))

        character = self._world_character_by_uuid_or_non_player_name(data_uuid, data_name)
        if character:
            add_all(character.status_effects)
        add_all(data.get("status_effects"))
        return collected

    def _npc_roster_items(self) -> list[dict[str, object]]:
        state = self.engine.state
        language = self.config_data.language
        items: list[dict[str, object]] = []
        party_names = {
            str(item.get("name") or item.get("character_name") or "")
            for item in state.party[1:]
            if isinstance(item, dict)
        }
        party_uuids = {
            str(item.get("uuid") or "")
            for item in state.party[1:]
            if isinstance(item, dict)
        }
        party_uuids.update(str(item or "") for item in state.party_uuids[1:])
        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("status") != "ended":
            raw_opponents = active_encounter.get("opponents")
            opponents = [entry for entry in raw_opponents if isinstance(entry, dict)] if isinstance(raw_opponents, list) else []
            if not opponents:
                opponents = [
                    {
                        "name": active_encounter.get("opponent_name"),
                        "uuid": active_encounter.get("opponent_uuid"),
                        "opponent_type": active_encounter.get("opponent_type"),
                        "opponent_hp": active_encounter.get("opponent_hp"),
                        "opponent_max_hp": active_encounter.get("opponent_max_hp"),
                    }
                ]
            for entry in opponents[:3]:
                name = str(entry.get("name") or tr_enum("roster", "unknown", language))
                uuid = str(entry.get("uuid") or "").strip()
                opponent_type = str(entry.get("opponent_type") or active_encounter.get("opponent_type") or "")
                hp = entry.get("opponent_hp")
                max_hp = entry.get("opponent_max_hp")
                image: Image.Image | None = None
                character = self._world_character_by_uuid_or_non_player_name(uuid, name)
                if character:
                    image = self._actor_image_from_paths(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image"))
                    opponent_type = self._character_roster_subtitle(character, fallback=opponent_type or "enemy")
                    hp = character.current_hp if character.current_hp is not None else hp
                    max_hp = character.max_hp if character.max_hp else max_hp
                hp_text = f"HP:{hp}/{max_hp}" if hp is not None and max_hp else (f"HP:{hp}" if hp is not None else "")
                items.append(
                    {
                        "name": name,
                        "uuid": uuid,
                        "subtitle": opponent_type or "enemy",
                        "hp": hp_text,
                        "image": image,
                        "kind": "character",
                        "encounter": active_encounter,
                    }
                )
            return items

        current_location = self._current_location_name()

        def append_character(character: Character) -> None:
            if len(items) >= 3:
                return
            if character.flags.get("is_player"):
                return
            if character.name in party_names or str(character.uuid) in party_uuids:
                return
            if any(str(item.get("uuid") or "") == str(character.uuid or "") for item in items):
                return
            if not self._character_is_present_at(character, current_location):
                return
            self.engine._ensure_character_runtime_data(character)
            items.append(
                {
                    "name": character.name,
                    "uuid": str(character.uuid or ""),
                    "subtitle": self._character_roster_subtitle(character),
                    "hp": "",
                    "image": self._actor_image_from_paths(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")),
                    "kind": "character",
                }
            )

        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            name = str(active_conversation.get("character") or "")
            uuid = str(active_conversation.get("character_uuid") or active_conversation.get("uuid") or "")
            character = self._world_character_by_uuid_or_non_player_name(uuid, name)
            if character:
                append_character(character)

        for character in state.world_data.characters.values():
            append_character(character)
            if len(items) >= 3:
                break
        return items

    def _character_roster_subtitle(self, character: Character, *, fallback: str = "NPC") -> str:
        internal_labels = {
            "rescue_target": "救出対象",
            "blocker": "妨害者",
            "defeat_target": "討伐対象",
            "delivery_target": "配達先",
            "quest_objective": "依頼関係者",
        }
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        for key in ("display_alias", "role_label", "title", "epithet", "occupation"):
            value = str(extra.get(key) or flags.get(key) or "").strip()
            if not value:
                continue
            return internal_labels.get(value, value)
        for value in (character.role, character.category, fallback):
            text = str(value or "").strip()
            if text:
                return internal_labels.get(text, text)
        return fallback

    def _player_roster_items(self) -> list[dict[str, object]]:
        player = self._player_character_dict()
        if not player:
            return []
        items = [self._character_roster_item(player, kind="player")]
        for companion in self._companion_character_dicts():
            items.append(self._character_roster_item(companion, kind="companion"))
        return items

    def _companion_character_dicts(self) -> list[dict[str, object]]:
        state = self.engine.state
        result: list[dict[str, object]] = []
        seen: set[str] = set()

        def append_ref(ref: str, party_entry: dict[str, object] | None = None) -> None:
            ref = str(ref or "").strip()
            if not ref:
                return
            character = self._world_character_by_uuid_or_non_player_name(ref, ref)
            if character:
                key = str(character.uuid or character.name)
                if key in seen:
                    return
                seen.add(key)
                data = character.to_dict()
                if party_entry:
                    data.update(party_entry)
                result.append(data)
                return
            if party_entry:
                key = str(party_entry.get("uuid") or party_entry.get("name") or party_entry.get("character_name") or ref)
                if key in seen:
                    return
                seen.add(key)
                result.append(dict(party_entry))

        for uuid in state.party_uuids[1:1 + UI_PARTY_COMPANION_LIMIT]:
            append_ref(str(uuid))
        for raw_entry in state.party[1:1 + UI_PARTY_COMPANION_LIMIT]:
            if not isinstance(raw_entry, dict):
                continue
            party_entry = dict(raw_entry)
            name = str(party_entry.get("name") or party_entry.get("character_name") or "").strip()
            uuid = str(party_entry.get("uuid") or "").strip()
            append_ref(uuid or name, party_entry)
        return result[:UI_PARTY_COMPANION_LIMIT]

    def _companion_character_dict(self, ref: str = "") -> dict[str, object]:
        ref = str(ref or "").strip()
        companions = self._companion_character_dicts()
        if ref:
            for companion in companions:
                if ref in {str(companion.get("uuid") or ""), str(companion.get("name") or ""), str(companion.get("character_name") or "")}:
                    return companion
        return companions[0] if companions else {}

    def _character_roster_item(self, character_data: dict[str, object], *, kind: str) -> dict[str, object]:
        player = character_data
        image_paths = player.get("image_paths")
        name = str(player.get("name") or (self.engine.state.player_name if kind == "player" else ""))
        uuid = str(player.get("uuid") or "")
        if (not isinstance(image_paths, dict) or not _subject_image_path(image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image"))) and name:
            character = self.engine.player_character() if kind == "player" else self._world_character_by_uuid_or_non_player_name(uuid, name)
            if character and character.image_paths:
                image_paths = character.image_paths
        image = self._actor_image_from_paths(image_paths if isinstance(image_paths, dict) else {}, ("face_image", "add_border_image", "no_bg_image", "generated_image"))
        attrs = _character_attributes(player)
        extra = player.get("extra")
        extra_level = extra.get("level") if isinstance(extra, dict) else ""
        level = str(player.get("level") or player.get("lv") or extra_level or "")
        encounter = self.engine.state.flags.get("active_encounter")
        if kind == "player" and isinstance(encounter, dict) and encounter.get("status") != "ended":
            hp = f"{encounter.get('player_hp', '-')}/{encounter.get('player_max_hp', '-')}"
            sp = f"{encounter.get('player_sp', '-')}/{encounter.get('player_max_sp', '-')}"
        else:
            extra_data = extra if isinstance(extra, dict) else {}
            current_hp = player.get("current_hp", extra_data.get("current_hp", "-"))
            max_hp = player.get("max_hp", extra_data.get("max_hp", "-"))
            current_sp = player.get("current_sp", extra_data.get("current_sp", "-"))
            max_sp = player.get("max_sp", extra_data.get("max_sp", "-"))
            hp = str(player.get("hp") or player.get("health") or f"{current_hp}/{max_hp}")
            sp = str(player.get("sp") or f"{current_sp}/{max_sp}")
        subtitle = f"Lv:{level or '1'}"
        return {
            "name": name,
            "uuid": uuid,
            "subtitle": subtitle,
            "hp": f"HP:{hp}",
            "sp": f"SP:{sp}",
            "image": image,
            "attrs": attrs,
            "kind": kind,
        }

    def _actor_image_from_paths(self, image_paths: dict[str, str], keys: tuple[str, ...]) -> Image.Image | None:
        return self._load_layer_image(_subject_image_path(image_paths, keys))

    def _current_location_name(self) -> str:
        state = self.engine.state
        return state.current_location or state.world_data.starting_location or "unknown"

    def _display_location_name(self) -> str:
        location = self._current_location_name()
        active = self.engine.state.flags.get("current_facility")
        if isinstance(active, dict):
            name = str(active.get("name") or "").strip()
            settlement = str(active.get("settlement") or "").strip()
            if name and (not settlement or settlement == location):
                return f"{location} / {name}"
        return location

    def _character_is_present_at(self, character: Character, location: str) -> bool:
        actor_location = character.location or str(character.flags.get("current_location") or "")
        if not actor_location:
            return False
        if actor_location != location:
            return False
        if not self._character_matches_current_subnode(character, location):
            return False
        if not self._character_matches_current_facility(character):
            return False
        return _actor_state_is_present(character.state or str(character.flags.get("state") or "present"))

    def _current_subnode_id(self, location: str) -> str:
        location = str(location or "").strip()
        if not location:
            return ""
        raw = self.engine.state.flags.get(CURRENT_SUBNODE_FLAG)
        if isinstance(raw, dict) and str(raw.get("location") or "") == location:
            node_id = str(raw.get("id") or "").strip()
            if node_id:
                return node_id
        location_data = self.engine.state.world_data.locations.get(location)
        graph = location_data.extra.get("subnode_graph") if location_data else None
        if isinstance(graph, dict):
            node_id = str(graph.get("current") or "").strip()
            if node_id:
                return node_id
        return ""

    def _character_matches_current_subnode(self, character: Character, location: str) -> bool:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        assigned_subnode = str(extra.get(ACTOR_SUBNODE_ID_FLAG) or flags.get(ACTOR_SUBNODE_ID_FLAG) or "").strip()
        if not assigned_subnode:
            assign = getattr(self.engine, "_ensure_character_subnode_assignment_for_location", None)
            if callable(assign):
                assigned_subnode = str(assign(character, location) or "").strip()
            if not assigned_subnode:
                return True
        assigned_location = str(extra.get(ACTOR_SUBNODE_LOCATION_FLAG) or flags.get(ACTOR_SUBNODE_LOCATION_FLAG) or "").strip()
        if assigned_location and location and assigned_location != location:
            return True
        current_subnode = self._current_subnode_id(location)
        return not current_subnode or assigned_subnode == current_subnode

    def _character_matches_current_facility(self, character: Character) -> bool:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        facility_name = str(extra.get("facility") or flags.get("facility_name") or "").strip()
        facility_type = str(extra.get("facility_type") or flags.get("facility_type") or "").strip().casefold()
        if not facility_name and not facility_type:
            return True
        active = self.engine.state.flags.get("current_facility")
        if not isinstance(active, dict):
            return False
        active_name = str(active.get("name") or "").strip()
        active_type = str(active.get("type") or "").strip().casefold()
        if facility_name and active_name and _simple_name_match(facility_name, active_name):
            return True
        return bool(facility_type and active_type and facility_type == active_type and not facility_name)

    def _maybe_open_explicit_subscreen_choice(self, choice: str) -> bool:
        normalized = str(choice or "").strip()
        if not normalized:
            return False
        if normalized in {_ui_text(self.config_data, "game_trade"), "取引", "Trade"} or normalized.casefold() == "trade":
            self._open_trade_inventory(normalized)
            return True
        if normalized in {_ui_text(self.config_data, "choice_quest_board"), "依頼掲示板を確認する", "依頼掲示板を見る", "Open quest board"}:
            self._open_quest_board_window()
            return True
        if normalized in {_ui_text(self.config_data, "choice_move"), "移動する", "Move"}:
            self._open_movement_window()
            return True
        return False

    def _open_pending_home_menu(self) -> None:
        pending = str(self.engine.state.flags.pop("pending_home_menu", "") or "").strip()
        if not pending:
            return
        self.engine.save_game()
        if pending == "storage":
            self._open_home_storage_window()
            return
        if pending == "craft":
            self._open_craft_window()

    def _open_movement_window(self) -> None:
        options = [option for option in self.engine.available_movement_options() if isinstance(option, dict)]
        if not options:
            self._append_log("\n" + _ui_text(self.config_data, "move_window_empty") + "\n")
            return
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "move_window_title"), 720, 520)
        dialog.title(_ui_text(self.config_data, "move_window_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = tk.Frame(dialog, bg=APP_DEEP_BG)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=_ui_text(self.config_data, "move_window_title"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(2)).grid(row=0, column=0, sticky="w")
        self._instant_button(header, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=1, sticky="e")

        body = tk.Frame(dialog, bg=APP_PANEL_BG, highlightbackground=APP_BUTTON_BORDER, highlightthickness=2)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        list_frame = tk.Frame(body, bg=APP_PANEL_BG)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=12)
        list_frame.columnconfigure(0, weight=1)
        detail_var = tk.StringVar(value=_ui_text(self.config_data, "move_window_hint"))
        selected_index = tk.IntVar(value=-1)

        detail_box = tk.Label(
            body,
            textvariable=detail_var,
            bg=APP_DEEP_BG,
            fg="#f2f2f2",
            anchor="nw",
            justify="left",
            wraplength=300,
            font=self.ui_fonts.normal(-1),
            padx=12,
            pady=12,
        )
        detail_box.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)

        def option_label(option: dict[str, object]) -> str:
            prefix_key = "move_window_world" if str(option.get("type") or "") == "world" else "move_window_subnode"
            return f"{_ui_text(self.config_data, prefix_key)}: {option.get('title') or option.get('id')}"

        def option_detail(option: dict[str, object]) -> str:
            parts = [option_label(option)]
            kind = str(option.get("kind") or "").strip()
            if kind:
                parts.append(kind)
            description = str(option.get("description") or "").strip()
            if description:
                parts.append(description)
            if option.get("external"):
                parts.append(_ui_text(self.config_data, "move_window_external"))
            if str(option.get("type") or "") == "world" and not option.get("visited"):
                parts.append(_ui_text(self.config_data, "move_window_unvisited"))
            return "\n".join(parts)

        def select(index: int) -> None:
            selected_index.set(index)
            detail_var.set(option_detail(options[index]))

        for index, option in enumerate(options[:16]):
            self._instant_button(list_frame, option_label(option), lambda i=index: select(i)).grid(row=index, column=0, sticky="ew", pady=(0, 8))

        footer = tk.Frame(dialog, bg=APP_DEEP_BG)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.columnconfigure(0, weight=1)

        def travel() -> None:
            index = selected_index.get()
            if index < 0 or index >= len(options):
                return
            option = options[index]
            destination = str(option.get("id") or "")
            if not destination:
                return
            if str(option.get("type") or "") == "world":
                block_message = self.engine.world_map_travel_precheck_message(destination)
                task_name = _ui_text(self.config_data, "task_world_map_travel")
                callback = lambda dest=destination: self.engine.travel_world_map_to(dest)
            else:
                block_message = self.engine.subnode_travel_precheck_message(destination)
                task_name = _ui_text(self.config_data, "task_subnode_map_travel")
                callback = lambda dest=destination: self.engine.travel_subnode_to(dest)
            if block_message:
                dialog.destroy()
                self._append_log("\n" + block_message + "\n")
                return
            dialog.destroy()
            self._dismiss_active_cg_for_player_input()
            self._run_task(task_name, callback, self._set_log)

        self._instant_button(footer, _ui_text(self.config_data, "move_window_confirm"), travel).grid(row=0, column=1, sticky="e")

    def _open_world_map_window(self) -> None:
        data = self.engine.world_map_data()
        nodes = [node for node in data.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in data.get("edges", []) if isinstance(edge, dict)]
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "world_map_title"), 980, 720)
        dialog.title(_ui_text(self.config_data, "world_map_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = tk.Frame(dialog, bg=APP_DEEP_BG)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=_ui_text(self.config_data, "world_map_title"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(2)).grid(row=0, column=0, sticky="w")
        self._instant_button(header, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=1, sticky="e")

        canvas_frame = tk.Frame(dialog, bg=APP_PANEL_BG, highlightbackground=APP_BUTTON_BORDER, highlightthickness=2)
        canvas_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(canvas_frame, bg="#f7f7f7", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        selected_name = tk.StringVar(value="")
        detail_var = tk.StringVar(value=_ui_text(self.config_data, "world_map_drag_hint"))
        node_lookup = {str(node.get("name") or ""): node for node in nodes}
        rect_items: dict[str, int] = {}
        node_size = 84

        def node_xy(node: dict[str, object]) -> tuple[int, int]:
            return int(node.get("x") or 80), int(node.get("y") or 80)

        if not nodes:
            canvas.create_text(480, 320, text=_ui_text(self.config_data, "world_map_no_locations"), fill="#111111", font=self.ui_fonts.bold(0))
        else:
            max_x = max(int(node.get("x") or 80) for node in nodes) + 220
            max_y = max(int(node.get("y") or 80) for node in nodes) + 180
            canvas.configure(scrollregion=(0, 0, max(max_x, 940), max(max_y, 620)))
            for edge in edges:
                a = node_lookup.get(str(edge.get("from") or ""))
                b = node_lookup.get(str(edge.get("to") or ""))
                if not a or not b:
                    continue
                ax, ay = node_xy(a)
                bx, by = node_xy(b)
                canvas.create_line(ax + node_size // 2, ay + node_size // 2, bx + node_size // 2, by + node_size // 2, fill="#111111", width=5)

            def select_node(node: dict[str, object]) -> None:
                name = str(node.get("name") or "")
                selected_name.set(name)
                for item_name, rect in rect_items.items():
                    canvas.itemconfigure(rect, outline="#101010", width=7 if item_name == name else 4)
                detail_var.set(_world_map_node_detail(node, data.get("current_location"), self.config_data.language))

            def draw_icon(node: dict[str, object], x: int, y: int, tag: str) -> None:
                kind = str(node.get("kind") or "").lower()
                if kind in {"settlement", "town", "village", "city"}:
                    canvas.create_polygon(x + 22, y + 44, x + 42, y + 22, x + 62, y + 44, fill="", outline="#101010", width=5, tags=tag)
                    canvas.create_rectangle(x + 28, y + 44, x + 56, y + 66, fill="", outline="#101010", width=5, tags=tag)
                    canvas.create_rectangle(x + 39, y + 52, x + 48, y + 66, fill="#101010", outline="#101010", tags=tag)
                elif kind in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
                    canvas.create_arc(x + 18, y + 22, x + 66, y + 78, start=0, extent=180, style="arc", outline="#101010", width=7, tags=tag)
                    canvas.create_line(x + 18, y + 50, x + 18, y + 76, x + 66, y + 76, x + 66, y + 50, fill="#101010", width=7, tags=tag)
                    canvas.create_rectangle(x + 34, y + 50, x + 50, y + 76, fill="#101010", outline="#101010", tags=tag)
                else:
                    canvas.create_oval(x + 22, y + 22, x + 62, y + 62, outline="#101010", width=5, tags=tag)
                    canvas.create_line(x + 42, y + 62, x + 42, y + 74, fill="#101010", width=5, tags=tag)

            for index, node in enumerate(nodes):
                name = str(node.get("name") or f"node{index}")
                x, y = node_xy(node)
                tag = f"world_node_{index}"
                rect = canvas.create_rectangle(x, y, x + node_size, y + node_size, fill="#ffffff", outline="#101010", width=4, tags=tag)
                rect_items[name] = rect
                draw_icon(node, x, y, tag)
                if name == str(data.get("current_location") or ""):
                    canvas.create_oval(x + node_size - 18, y + 8, x + node_size - 8, y + 18, fill="#d33030", outline="#d33030", tags=tag)
                canvas.tag_bind(tag, "<Enter>", lambda _event, n=node: detail_var.set(_world_map_node_detail(n, data.get("current_location"), self.config_data.language)))
                canvas.tag_bind(tag, "<Leave>", lambda _event: detail_var.set(_ui_text(self.config_data, "world_map_drag_hint")) if not selected_name.get() else None)
                canvas.tag_bind(tag, "<Button-1>", lambda _event, n=node: select_node(n))

        canvas.bind("<ButtonPress-1>", lambda event: canvas.scan_mark(event.x, event.y), add="+")
        canvas.bind("<B1-Motion>", lambda event: canvas.scan_dragto(event.x, event.y, gain=1), add="+")

        footer = tk.Frame(dialog, bg=APP_DEEP_BG)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=detail_var, bg=APP_DEEP_BG, fg="#f2f2f2", anchor="w", justify="left", font=self.ui_fonts.normal(-2)).grid(row=0, column=0, sticky="ew")

        def travel() -> None:
            destination = selected_name.get()
            if not destination:
                return
            block_message = self.engine.world_map_travel_precheck_message(destination)
            if block_message:
                dialog.destroy()
                self._append_log("\n" + block_message + "\n")
                return
            dialog.destroy()
            self._dismiss_active_cg_for_player_input()
            self._run_task(
                _ui_text(self.config_data, "task_world_map_travel"),
                lambda dest=destination: self.engine.travel_world_map_to(dest),
                self._set_log,
            )

        self._instant_button(footer, _ui_text(self.config_data, "world_map_move"), travel).grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _open_subnode_map_window(self) -> None:
        data = self.engine.subnode_map_data()
        nodes = [node for node in data.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in data.get("edges", []) if isinstance(edge, dict)]
        if not nodes:
            self._show_error(ValueError(_ui_text(self.config_data, "subnode_map_no_locations")))
            return
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "subnode_map_title"), 980, 720)
        dialog.title(_ui_text(self.config_data, "subnode_map_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = tk.Frame(dialog, bg=APP_DEEP_BG)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=_ui_text(self.config_data, "subnode_map_title"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(2)).grid(row=0, column=0, sticky="w")
        self._instant_button(header, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=1, sticky="e")

        canvas_frame = tk.Frame(dialog, bg=APP_PANEL_BG, highlightbackground=APP_BUTTON_BORDER, highlightthickness=2)
        canvas_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(canvas_frame, bg="#f7f7f7", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        selected_id = tk.StringVar(value="")
        detail_var = tk.StringVar(value=_ui_text(self.config_data, "subnode_map_drag_hint"))
        node_lookup = {str(node.get("id") or ""): node for node in nodes}
        rect_items: dict[str, int] = {}
        node_size = 84

        def node_xy(node: dict[str, object]) -> tuple[int, int]:
            return int(node.get("x") or 80), int(node.get("y") or 80)

        max_x = max(int(node.get("x") or 80) for node in nodes) + 220
        max_y = max(int(node.get("y") or 80) for node in nodes) + 180
        canvas.configure(scrollregion=(0, 0, max(max_x, 940), max(max_y, 620)))
        for edge in edges:
            a = node_lookup.get(str(edge.get("from") or ""))
            b = node_lookup.get(str(edge.get("to") or ""))
            if not a or not b:
                continue
            ax, ay = node_xy(a)
            bx, by = node_xy(b)
            dash = (10, 6) if edge.get("external") else None
            canvas.create_line(ax + node_size // 2, ay + node_size // 2, bx + node_size // 2, by + node_size // 2, fill="#111111", width=5, dash=dash)

        def select_node(node: dict[str, object]) -> None:
            node_id = str(node.get("id") or "")
            selected_id.set(node_id)
            for item_id, rect in rect_items.items():
                canvas.itemconfigure(rect, outline="#101010", width=7 if item_id == node_id else 4)
            detail_var.set(_subnode_map_node_detail(node, data, self.config_data.language))

        def draw_icon(node: dict[str, object], x: int, y: int, tag: str) -> None:
            kind = str(node.get("kind") or "").lower()
            if node.get("external"):
                canvas.create_line(x + 20, y + 42, x + 64, y + 42, arrow="last", fill="#101010", width=7, tags=tag)
                canvas.create_rectangle(x + 16, y + 24, x + 68, y + 60, fill="", outline="#101010", width=4, tags=tag)
            elif kind in {"gate", "entrance"}:
                canvas.create_arc(x + 18, y + 18, x + 66, y + 74, start=0, extent=180, style="arc", outline="#101010", width=6, tags=tag)
                canvas.create_line(x + 18, y + 46, x + 18, y + 74, x + 66, y + 74, x + 66, y + 46, fill="#101010", width=6, tags=tag)
            elif kind == "well":
                canvas.create_oval(x + 20, y + 22, x + 64, y + 62, outline="#101010", width=6, tags=tag)
                canvas.create_arc(x + 18, y + 10, x + 66, y + 50, start=0, extent=180, style="arc", outline="#101010", width=4, tags=tag)
            elif kind in {"guild", "blacksmith", "black_market", "apothecary", "food_store", "material_store", "general_store", "magic_store", "facility", "shop"} or str(node.get("facility_name") or ""):
                canvas.create_rectangle(x + 18, y + 30, x + 66, y + 66, fill="", outline="#101010", width=5, tags=tag)
                canvas.create_polygon(x + 16, y + 32, x + 42, y + 16, x + 68, y + 32, fill="", outline="#101010", width=5, tags=tag)
            elif kind in {"depths", "deepest", "passage", "fork", "subarea"}:
                canvas.create_rectangle(x + 18, y + 22, x + 66, y + 66, fill="", outline="#101010", width=5, tags=tag)
                canvas.create_line(x + 26, y + 44, x + 58, y + 44, fill="#101010", width=5, tags=tag)
            else:
                canvas.create_oval(x + 22, y + 22, x + 62, y + 62, outline="#101010", width=5, tags=tag)

        for index, node in enumerate(nodes):
            node_id = str(node.get("id") or f"node{index}")
            x, y = node_xy(node)
            tag = f"subnode_{index}"
            fill = "#ffffff" if not node.get("external") else "#f0f0f0"
            rect = canvas.create_rectangle(x, y, x + node_size, y + node_size, fill=fill, outline="#101010", width=4, tags=tag)
            rect_items[node_id] = rect
            draw_icon(node, x, y, tag)
            if node.get("current"):
                canvas.create_oval(x + node_size - 18, y + 8, x + node_size - 8, y + 18, fill="#d33030", outline="#d33030", tags=tag)
            canvas.tag_bind(tag, "<Enter>", lambda _event, n=node: detail_var.set(_subnode_map_node_detail(n, data, self.config_data.language)))
            canvas.tag_bind(tag, "<Leave>", lambda _event: detail_var.set(_ui_text(self.config_data, "subnode_map_drag_hint")) if not selected_id.get() else None)
            canvas.tag_bind(tag, "<Button-1>", lambda _event, n=node: select_node(n))

        canvas.bind("<ButtonPress-1>", lambda event: canvas.scan_mark(event.x, event.y), add="+")
        canvas.bind("<B1-Motion>", lambda event: canvas.scan_dragto(event.x, event.y, gain=1), add="+")

        footer = tk.Frame(dialog, bg=APP_DEEP_BG)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=detail_var, bg=APP_DEEP_BG, fg="#f2f2f2", anchor="w", justify="left", font=self.ui_fonts.normal(-2)).grid(row=0, column=0, sticky="ew")

        def travel() -> None:
            destination = selected_id.get()
            if not destination:
                return
            block_message = self.engine.subnode_travel_precheck_message(destination)
            if block_message:
                dialog.destroy()
                self._append_log("\n" + block_message + "\n")
                return
            dialog.destroy()
            self._dismiss_active_cg_for_player_input()
            self._run_task(
                _ui_text(self.config_data, "task_subnode_map_travel"),
                lambda dest=destination: self.engine.travel_subnode_to(dest),
                self._set_log,
            )

        self._instant_button(footer, _ui_text(self.config_data, "subnode_map_move"), travel).grid(row=0, column=1, sticky="e", padx=(12, 0))

    def _open_active_quest_window(self) -> None:
        self._hide_game_button_help()
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "quest_status_title"), 760, 520)
        dialog.title(_ui_text(self.config_data, "quest_status_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = tk.Frame(dialog, bg=APP_DEEP_BG)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=_ui_text(self.config_data, "quest_status_title"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(1)).grid(row=0, column=0, sticky="w")
        self._instant_button(header, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=1, sticky="e")

        text = self._instant_text(dialog, 1, 0, height=18, padx=16, pady=(0, 14))
        text.insert("1.0", self._active_quest_status_text())
        text.configure(state="disabled")

    def _active_quest_status_text(self) -> str:
        state = self.engine.state
        active_name = str(state.active_quest or "").strip()
        if not active_name:
            return _ui_text(self.config_data, "quest_status_empty")
        quest = next((item for item in state.world_data.quests if item.name == active_name), None)
        if quest is None:
            return f"{_ui_text(self.config_data, 'quest_status_name')}: {active_name}\n{_ui_text(self.config_data, 'quest_status_missing')}"
        extra = quest.extra if isinstance(quest.extra, dict) else {}
        destination = extra.get("destination") if isinstance(extra.get("destination"), dict) else {}
        pack = extra.get("objective_entities") if isinstance(extra.get("objective_entities"), dict) else {}
        entries = [entry for entry in pack.get("entries", []) if isinstance(entry, dict)] if isinstance(pack, dict) else []
        location = str(destination.get("location") or extra.get("objective_location") or pack.get("location") or "").strip()
        subnode_name = str(destination.get("objective_subnode_name") or extra.get("objective_subnode_name") or "")
        subnode_id = str(destination.get("objective_subnode_id") or extra.get("objective_subnode_id") or pack.get("subnode_id") or "")
        subnode = self._quest_status_subnode_display_name(location, subnode_id, subnode_name) or "-"
        location_display = location if location and not _quest_status_internal_place_id(location) else "-"
        lines = [
            f"{_ui_text(self.config_data, 'quest_status_name')}: {quest.name}",
            f"{_ui_text(self.config_data, 'quest_board_status')}: {quest.status}",
            f"{_ui_text(self.config_data, 'quest_board_danger')}: {extra.get('danger_level') or extra.get('planned_danger_level') or '-'}",
            f"{_ui_text(self.config_data, 'quest_status_destination')}: {location_display}",
            f"{_ui_text(self.config_data, 'quest_status_subnode')}: {subnode}",
        ]
        remaining = self.engine.active_quest_remaining_time_label() if state.active_quest else ""
        if remaining:
            lines.append(f"{_ui_text(self.config_data, 'quest_status_deadline')}: {remaining}")
        objective = str(extra.get("objective") or quest.overview or "").strip()
        if objective:
            lines.extend(["", f"{_ui_text(self.config_data, 'quest_board_objective')}:", objective])
        lines.append("")
        lines.append(f"{_ui_text(self.config_data, 'quest_status_todo')}:")
        if entries:
            for entry in entries:
                lines.append(f"- {self._quest_entry_status_line(entry)}")
        else:
            lines.append(f"- {_ui_text(self.config_data, 'quest_status_no_entries')}")
        return "\n".join(lines)

    def _quest_entry_status_line(self, entry: dict[str, object]) -> str:
        role = str(entry.get("role") or "")
        kind = str(entry.get("kind") or "")
        name = str(entry.get("name") or entry.get("display_alias") or role or kind or "-")
        status = str(entry.get("status") or "waiting")
        location = str(entry.get("location") or "").strip()
        subnode = self._quest_status_subnode_display_name(
            location,
            str(entry.get("subnode_id") or ""),
            str(entry.get("subnode_name") or entry.get("objective_subnode_name") or ""),
        )
        todo_map = {
            "rescue_target": {
                "waiting": "救出対象を見つけて保護する",
                "found": "救出対象を保護する",
                "escorting": "救出対象をギルドまで連れて帰る",
                "delivered": "ギルドで報告する",
            },
            "blocker": {
                "waiting": "妨害者を説得・無力化・討伐して解決する",
                "neutralized": "救出対象を保護する",
                "defeated": "救出対象を保護する",
            },
            "defeat_target": {
                "waiting": "討伐対象を倒す",
                "defeated": "ギルドで報告する",
                "dead": "ギルドで報告する",
            },
            "delivery_item": {
                "carrying": "配達先へ届ける",
                "delivered": "ギルドで報告する",
            },
            "delivery_target": {
                "waiting": "配達先に会う",
                "received": "ギルドで報告する",
                "delivered": "ギルドで報告する",
            },
            "retrieve_item": {
                "waiting": "目的アイテムを採取・回収する",
                "found": "目的アイテムを採取・回収する",
                "retrieved": "ギルドで報告する",
                "delivered": "完了済み",
            },
            "investigation_point": {
                "waiting": "調査地点を調べる",
                "found": "調査地点を調べる",
                "investigated": "ギルドで報告する",
                "delivered": "完了済み",
            },
            "procurement_requirement": {
                "waiting": "指定品を用意してギルドで提出する",
                "submitted": "ギルドで報告する",
                "delivered": "完了済み",
            },
        }
        todo = todo_map.get(role, {}).get(status) or todo_map.get(role, {}).get("waiting") or _ui_text(self.config_data, "quest_status_continue")
        place_location = location if location and not _quest_status_internal_place_id(location) else ""
        place = f" / {place_location}" if place_location else ""
        if subnode:
            place += f" / {subnode}"
        return f"{name}: {todo} ({status}){place}"

    def _quest_status_subnode_display_name(self, location: str, subnode_id: str, fallback_name: str = "") -> str:
        location = str(location or "").strip()
        subnode_id = str(subnode_id or "").strip()
        fallback_name = str(fallback_name or "").strip()
        if fallback_name and not _quest_status_internal_place_id(fallback_name):
            return fallback_name
        if location and subnode_id:
            location_data = self.engine.state.world_data.locations.get(location)
            graph = location_data.extra.get(SUBNODE_GRAPH_KEY) if location_data and isinstance(location_data.extra, dict) else None
            nodes = graph.get("nodes") if isinstance(graph, dict) else None
            node = nodes.get(subnode_id) if isinstance(nodes, dict) else None
            if isinstance(node, dict):
                name = str(node.get("name") or node.get("title") or "").strip()
                if name and not _quest_status_internal_place_id(name):
                    return name
        return ""

    def _open_quest_board_window(self) -> None:
        if not self.engine.is_current_location_guild():
            if self.engine.is_current_location_settlement():
                self._set_log(self.engine.travel_to_facility(DEFAULT_GUILD_NAME))
            if not self.engine.is_current_location_guild():
                self._show_error(ValueError(_ui_text(self.config_data, "quest_board_not_guild")))
                return
        quests = self.engine.available_quest_board_quests()
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "quest_board_title"), 820, 560)
        dialog.title(_ui_text(self.config_data, "quest_board_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry("820x560")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=2)
        dialog.rowconfigure(1, weight=1)

        tk.Label(dialog, text=_ui_text(self.config_data, "quest_board_title"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(0)).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))
        listbox = tk.Listbox(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", selectbackground="#263654", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        listbox.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 10))
        detail = tk.Text(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", relief="solid", bd=1, wrap="word", height=12, font=self.ui_fonts.normal(-2))
        detail.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 10))

        def quest_danger(quest) -> int:
            extra = quest.extra if isinstance(quest.extra, dict) else {}
            reward = extra.get("reward") if isinstance(extra.get("reward"), dict) else {}
            return max(0, _safe_int(str(extra.get("danger_level") or reward.get("danger_level") or 0), 0))

        for quest in quests:
            danger = quest_danger(quest)
            listbox.insert("end", f"{quest.name} / {_ui_text(self.config_data, 'quest_board_danger')} {danger}")
        if not quests:
            listbox.insert("end", _ui_text(self.config_data, "quest_board_empty"))

        tooltip = tk.Toplevel(dialog)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tooltip.configure(bg="#d8d4cf")
        tooltip_label = tk.Label(tooltip, bg=APP_PANEL_BG, fg="#f2f2f2", justify="left", anchor="w", bd=1, relief="solid", padx=8, pady=6, font=self.ui_fonts.normal(-3))
        tooltip_label.pack()

        def selected_quest():
            selection = listbox.curselection()
            if not selection or not quests:
                return None
            index = int(selection[0])
            return quests[index] if 0 <= index < len(quests) else None

        def quest_text(quest) -> str:
            reward = quest.extra.get("reward") if isinstance(quest.extra, dict) else {}
            reward_text = _quest_reward_text(reward)
            lines = [
                quest.name,
                f"{_ui_text(self.config_data, 'quest_board_status')}: {quest.status or 'available'}",
                f"{_ui_text(self.config_data, 'quest_board_danger')}: {quest_danger(quest)}",
                f"{_ui_text(self.config_data, 'quest_board_reward')}: {reward_text or '-'}",
                "",
                quest.overview or "",
            ]
            objective = quest.extra.get("objective") if isinstance(quest.extra, dict) else ""
            if objective:
                lines.extend(["", f"{_ui_text(self.config_data, 'quest_board_objective')}: {objective}"])
            return "\n".join(str(line) for line in lines)

        def update_detail(_event=None) -> None:
            quest = selected_quest()
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            if quest:
                detail.insert("1.0", quest_text(quest))
            elif not quests:
                detail.insert("1.0", _ui_text(self.config_data, "quest_board_empty"))
            detail.configure(state="disabled")

        def show_tooltip(event) -> None:
            if not quests:
                tooltip.withdraw()
                return
            index = listbox.nearest(event.y)
            if index < 0 or index >= len(quests):
                tooltip.withdraw()
                return
            tooltip_label.configure(text=quest_text(quests[index]))
            tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
            tooltip.deiconify()

        def accept() -> None:
            quest = selected_quest()
            if not quest:
                return
            tooltip.withdraw()
            dialog.destroy()
            self._run_task(
                _ui_text(self.config_data, "task_accepting_quest"),
                lambda name=quest.name: self.engine.accept_quest_from_board(name),
                self._set_log,
            )

        listbox.bind("<<ListboxSelect>>", update_detail)
        listbox.bind("<Motion>", show_tooltip)
        listbox.bind("<Leave>", lambda _event: tooltip.withdraw())
        dialog.bind("<Destroy>", lambda _event: tooltip.destroy() if tooltip.winfo_exists() else None, add="+")
        if quests:
            listbox.selection_set(0)
        update_detail()

        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "quest_board_accept"), accept).grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=2, sticky="e")

    def _open_player_inventory(self) -> None:
        self._open_inventory_window(_ui_text(self.config_data, "inventory_title"), _ui_text(self.config_data, "inventory_details"), [], mode="inventory")

    def _open_loot_inventory(self) -> None:
        label, inventory = self.engine.current_loot_inventory()
        self._open_inventory_window(_ui_text(self.config_data, "loot_title"), label, inventory, mode="loot")

    def _open_trade_inventory(self, action: str = "") -> None:
        character = self._trade_target_character(action)
        if character is None:
            self._show_error(ValueError(_ui_text(self.config_data, "trade_no_target")))
            return
        vendor_event = self.engine.prepare_vendor_inventory(character)
        if vendor_event.get("changed"):
            self._append_inventory_event(_ui_text(self.config_data, "trade_stock_changed").format(name=character.name))
            self.engine.save_game()
        self._open_inventory_window(_ui_text(self.config_data, "trade_title"), character.name, character.vender_inventory, mode="shop", target_character=character)

    def _trade_target_character(self, action: str = "") -> Character | None:
        candidates = self._current_trade_candidates()
        action_text = str(action or "")
        if action_text:
            for character in candidates:
                if self._character_action_text_matches(character, action_text):
                    return character
        active = self.engine.state.flags.get("active_conversation")
        if isinstance(active, dict):
            name = str(active.get("character") or "")
            character = self.engine.state.world_data.character(name)
            if character:
                for candidate in candidates:
                    if candidate.name == character.name or str(candidate.uuid) == str(character.uuid):
                        return candidate
        return candidates[0] if len(candidates) == 1 else None

    def _current_trade_candidates(self) -> list[Character]:
        current_location = self._current_location_name()
        can_trade = getattr(self.engine, "_character_can_trade", None)
        candidates: list[Character] = []
        for character in self.engine.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if self._character_is_present_at(character, current_location):
                if callable(can_trade) and not can_trade(character):
                    continue
                candidates.append(character)
        return candidates

    def _character_action_text_matches(self, character: Character, action_text: str) -> bool:
        text = str(action_text or "").strip()
        if not text:
            return False
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        terms = [
            character.name,
            character.role,
            character.category,
            str(extra.get("facility") or flags.get("facility_name") or ""),
            str(extra.get("facility_type") or flags.get("facility_type") or ""),
            str(extra.get("occupation") or ""),
            str(extra.get("archetype") or ""),
            str(extra.get("display_alias") or flags.get("display_alias") or ""),
            str(extra.get("role_label") or flags.get("role_label") or ""),
        ]
        aliases = extra.get("aliases")
        if isinstance(aliases, list):
            terms.extend(str(item) for item in aliases)
        elif aliases:
            terms.append(str(aliases))
        for term in terms:
            value = str(term or "").strip()
            if value and (value in text or _simple_name_match(value, text)):
                return True
        return False

    def _open_craft_window(self) -> None:
        player_inventory = self._player_inventory()
        language = self.config_data.language
        craft_inventory: list[dict[str, object]] = []
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "craft_title"), 900, 620)
        dialog.title(_ui_text(self.config_data, "craft_title"))
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry("900x620")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=0)
        dialog.columnconfigure(2, weight=1)
        dialog.rowconfigure(1, weight=1)

        detail_var = tk.StringVar(value="")
        craft_preview_var = tk.StringVar(value="種別:- / 予想目標値:-")
        craft_intent_var = tk.StringVar(value=_craft_intent_label(self.config_data, "auto"))
        tk.Label(dialog, text=_ui_text(self.config_data, "game_inventory"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        tk.Label(dialog, text=_ui_text(self.config_data, "craft_materials"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=2, sticky="ew", padx=16, pady=(14, 6))
        player_list = tk.Listbox(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", selectbackground="#263654", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        craft_list = tk.Listbox(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", selectbackground="#263654", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        player_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        craft_list.grid(row=1, column=2, sticky="nsew", padx=16, pady=(0, 8))

        controls = tk.Frame(dialog, bg=APP_DEEP_BG)
        controls.grid(row=1, column=1, sticky="ns", pady=(70, 8))
        add_btn = self._instant_button(controls, ">>", lambda: add_material())
        remove_btn = self._instant_button(controls, "<<", lambda: remove_material())
        add_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4), ipadx=14, ipady=8)
        remove_btn.grid(row=1, column=0, sticky="ew", padx=8, pady=4, ipadx=14, ipady=8)

        tk.Label(
            dialog,
            textvariable=detail_var,
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            justify="left",
            wraplength=820,
            font=self.ui_fonts.normal(-3),
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 0))

        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(10, 14))
        actions.columnconfigure(0, weight=1)
        tk.Label(
            actions,
            textvariable=craft_preview_var,
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            font=self.ui_fonts.bold(-3),
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(
            actions,
            text=_ui_text(self.config_data, "craft_intent"),
            bg=APP_DEEP_BG,
            fg="#f2f2f2",
            font=self.ui_fonts.bold(-3),
        ).grid(row=0, column=1, sticky="e", padx=(0, 6))
        craft_intent_combo = ttk.Combobox(
            actions,
            textvariable=craft_intent_var,
            values=_craft_intent_options(self.config_data),
            state="readonly",
            width=14,
        )
        craft_intent_combo.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "craft_create"), lambda: craft_selected()).grid(row=0, column=3, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), lambda: close_dialog()).grid(row=0, column=4, sticky="e")

        def refresh_craft_preview() -> None:
            craft_intent = _craft_intent_id_from_label(self.config_data, craft_intent_var.get())
            preview = self.engine.craft_preview_for_selected_items(craft_inventory, craft_intent)
            craft_preview_var.set(str(preview.get("text") or "種別:- / 予想目標値:-"))

        def refresh() -> None:
            player_list.delete(0, "end")
            craft_list.delete(0, "end")
            for item in player_inventory:
                _insert_item_row(player_list, item, language=language)
            for item in craft_inventory:
                _insert_item_row(craft_list, item, language=language)
            if craft_inventory:
                names = " / ".join(str(normalise_item(item).get("name") or "") for item in craft_inventory[:6])
                detail_var.set(f"{_ui_text(self.config_data, 'craft_materials')}: {names}")
            else:
                detail_var.set(_ui_text(self.config_data, "craft_empty_help"))
            refresh_craft_preview()

        craft_intent_combo.bind("<<ComboboxSelected>>", lambda _event: refresh_craft_preview())

        def selected_index(listbox: tk.Listbox) -> int | None:
            selection = listbox.curselection()
            if not selection:
                return None
            return int(selection[0])

        def selected_uuids_for_item(item: dict[str, object]) -> set[str]:
            name = str(item.get("name") or "")
            selected: set[str] = set()
            for selected_item in craft_inventory:
                if str(selected_item.get("name") or "") != name:
                    continue
                selected.update(str(value) for value in selected_item.get("item_uuids", []) if str(value))
                selected_uuid = str(selected_item.get("item_uuid") or "")
                if selected_uuid:
                    selected.add(selected_uuid)
            return selected

        def material_copy_for_selection(item: dict[str, object]) -> dict[str, object] | None:
            normalised = normalise_item(item)
            available = max(1, _safe_int(normalised.get("quantity", 1), 1))
            uuids = [str(value) for value in normalised.get("item_uuids", []) if str(value)]
            if not uuids:
                uuid = str(normalised.get("item_uuid") or "")
                uuids = [uuid] if uuid else []
            selected_uuids = selected_uuids_for_item(normalised)
            selected_count = len(selected_uuids) if uuids else sum(
                1 for selected_item in craft_inventory if str(selected_item.get("name") or "") == str(normalised.get("name") or "")
            )
            if selected_count >= available:
                return None
            copy_item = deepcopy(normalised)
            item_uuid = next((uuid for uuid in uuids if uuid not in selected_uuids), str(copy_item.get("item_uuid") or ""))
            copy_item["quantity"] = 1
            copy_item["item_uuids"] = [item_uuid] if item_uuid else []
            copy_item["item_uuid"] = item_uuid
            copy_item["_craft_source"] = "player"
            copy_item["_craft_source_uuid"] = item_uuid
            return copy_item

        def add_material() -> None:
            index = selected_index(player_list)
            if index is None or index >= len(player_inventory):
                return
            selected = material_copy_for_selection(player_inventory[index])
            if selected:
                craft_inventory.append(selected)
                refresh()

        def remove_material() -> None:
            index = selected_index(craft_list)
            if index is None or index >= len(craft_inventory):
                return
            craft_inventory.pop(index)
            refresh()

        def craft_selected() -> None:
            if len(craft_inventory) < 2:
                messagebox.showwarning(_ui_text(self.config_data, "craft_title"), _ui_text(self.config_data, "craft_empty_help"))
                return
            ingredients = [deepcopy(item) for item in craft_inventory]
            craft_intent = _craft_intent_id_from_label(self.config_data, craft_intent_var.get())
            dialog.destroy()
            self._run_task(
                _ui_text(self.config_data, "craft_title"),
                lambda ingredients=ingredients, craft_intent=craft_intent: self.engine.resolve_craft_from_selected_items(
                    ingredients,
                    craft_category=craft_intent,
                ),
                self._set_log,
            )
            return
            if len(craft_inventory) < 2:
                result, message = craft_items(craft_inventory, language=language, craft_intent=craft_intent)
                messagebox.showwarning(_ui_text(self.config_data, "craft_title"), message)
                return
            craft_roll = self.engine.roll_craft_check(craft_inventory)
            used_labels = [_item_label(item, language=language) for item in craft_inventory]
            if craft_roll.get("critical_failure"):
                craft_inventory.clear()
                self._append_inventory_event(str(craft_roll.get("line") or ""))
                self._append_inventory_event("> [クラフト] クラフトに失敗しました。素材は失われました。")
                self.engine.state.world_data.extra.setdefault("craft_events", []).append(
                    {
                        "ingredients": used_labels,
                        "roll": craft_roll,
                        "failed": True,
                    }
                )
                self._save_inventory_change()
                refresh()
                return
            result, message = craft_items(craft_inventory, language=language, craft_roll=craft_roll, craft_intent=craft_intent)
            if not result:
                messagebox.showwarning(_ui_text(self.config_data, "craft_title"), message)
                return
            craft_inventory.clear()
            added = add_item_stack(player_inventory, result, source="craft")
            self._append_inventory_event(str(craft_roll.get("line") or ""))
            self._append_inventory_event(f"> [クラフト] {message}")
            self.engine.state.world_data.extra.setdefault("craft_events", []).append(
                {
                    "ingredients": used_labels,
                    "roll": craft_roll,
                    "result": normalise_item(added),
                }
            )
            self._save_inventory_change()
            refresh()

        def close_dialog() -> None:
            dialog.destroy()
            return
            while craft_inventory:
                transfer_item_stack(craft_inventory, player_inventory, 0, 1, source="craft_return")
            self._save_inventory_change()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        refresh()

    def _open_inventory_window(
        self,
        title: str,
        target_name: str,
        target_inventory: list[dict[str, object]],
        *,
        mode: str,
        target_character: Character | None = None,
    ) -> None:
        player_inventory = self._player_inventory()
        language = self.config_data.language
        dialog_height = 600
        dialog = self._create_modal_dialog(title, 900, dialog_height)
        dialog.title(title)
        dialog.configure(bg=APP_DEEP_BG)
        dialog.geometry(f"900x{dialog_height}")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=0)
        dialog.columnconfigure(2, weight=1)
        dialog.rowconfigure(1, weight=1)

        player_gold_var = tk.StringVar()
        target_gold_var = tk.StringVar()
        detail_var = tk.StringVar(value="")

        tk.Label(dialog, text=_ui_text(self.config_data, "player_label"), bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        tk.Label(dialog, text=target_name, bg=APP_DEEP_BG, fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=2, sticky="ew", padx=16, pady=(14, 6))

        player_list = tk.Listbox(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", selectbackground="#263654", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        target_list = tk.Listbox(dialog, bg=APP_PANEL_BG, fg="#f2f2f2", selectbackground="#263654", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        player_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        target_list.grid(row=1, column=2, sticky="nsew", padx=16, pady=(0, 8))

        controls = tk.Frame(dialog, bg=APP_DEEP_BG)
        controls.grid(row=1, column=1, sticky="ns", pady=(36, 8))
        move_left_btn = self._instant_button(controls, "<<", lambda: move_to_player())
        move_left_all_btn = self._instant_button(controls, "all <<", lambda: move_all_to_player())
        move_right_btn = self._instant_button(controls, ">>", lambda: move_to_target())
        move_right_all_btn = self._instant_button(controls, "all >>", lambda: move_all_to_target())
        move_left_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4), ipadx=14, ipady=8)
        move_left_all_btn.grid(row=1, column=0, sticky="ew", padx=8, pady=4, ipadx=14, ipady=8)
        move_right_btn.grid(row=2, column=0, sticky="ew", padx=8, pady=(18, 4), ipadx=14, ipady=8)
        move_right_all_btn.grid(row=3, column=0, sticky="ew", padx=8, pady=4, ipadx=14, ipady=8)
        if mode == "inventory":
            for button in (move_left_btn, move_left_all_btn, move_right_btn, move_right_all_btn):
                button.configure(state="disabled")

        tk.Label(dialog, textvariable=player_gold_var, bg=APP_DEEP_BG, fg="#d8d4cf", anchor="w").grid(row=2, column=0, sticky="ew", padx=16)
        tk.Label(dialog, textvariable=target_gold_var, bg=APP_DEEP_BG, fg="#d8d4cf", anchor="w").grid(row=2, column=2, sticky="ew", padx=16)

        tk.Label(
            dialog,
            textvariable=detail_var,
            bg=APP_DEEP_BG,
            fg="#d8d4cf",
            anchor="w",
            justify="left",
            wraplength=820,
            font=self.ui_fonts.normal(-3),
        ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 0))

        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", padx=16, pady=(10, 14))
        actions.columnconfigure(0, weight=1)
        if mode == "inventory":
            self._instant_button(actions, "装備", lambda: equip_selected_item()).grid(row=0, column=1, sticky="e", padx=(0, 8))
            self._instant_button(actions, "使う", lambda: use_selected_item()).grid(row=0, column=2, sticky="e", padx=(0, 8))
        self._instant_button(actions, "閉じる", dialog.destroy).grid(row=0, column=3, sticky="e")

        tooltip = tk.Toplevel(dialog)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tooltip.configure(bg="#d8d4cf")
        tooltip_label = tk.Label(
            tooltip,
            bg=APP_PANEL_BG,
            fg="#f2f2f2",
            justify="left",
            anchor="w",
            bd=1,
            relief="solid",
            padx=8,
            pady=6,
            font=self.ui_fonts.normal(-3),
        )
        tooltip_label.pack()

        def hide_tooltip(_event=None) -> None:
            tooltip.withdraw()

        def show_tooltip(listbox: tk.Listbox, inventory: list[dict[str, object]], price_mode: str, event) -> None:
            if not inventory:
                hide_tooltip()
                return
            index = listbox.nearest(event.y)
            if index < 0 or index >= len(inventory):
                hide_tooltip()
                return
            item = normalise_item(inventory[index])
            tooltip_label.configure(text=item_tooltip_text(item, price_mode=price_mode, language=language))
            tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
            tooltip.deiconify()

        dialog.bind("<Destroy>", lambda _event: tooltip.destroy() if tooltip.winfo_exists() else None, add="+")

        def current_buy_multiplier() -> float:
            return self.engine.vendor_price_multiplier(target_character) if mode == "shop" else 1.0

        def buy_value(item: dict[str, object]) -> int:
            return max(1, int(round(_item_value(item) * current_buy_multiplier())))

        def refresh() -> None:
            player_list.delete(0, "end")
            target_list.delete(0, "end")
            for item in player_inventory:
                _insert_item_row(player_list, item, price_mode="sell" if mode == "shop" else "", language=language)
            for item in target_inventory:
                _insert_item_row(target_list, item, price_mode="buy" if mode == "shop" else "", language=language)
            slots_text = f"{inventory_slot_count(player_inventory)}/{PLAYER_INVENTORY_MAX_SLOTS}"
            slot_label = "Items" if str(language).lower().startswith("en") else "所持品"
            player_gold_var.set(f"Gold: {self._player_gold()} / {slot_label}: {slots_text}")
            target_gold = target_character.gold if target_character else 0
            target_gold_var.set(f"Gold: {target_gold}" if mode == "shop" else "")
            update_detail()

        def selected_index(listbox: tk.Listbox) -> int | None:
            selection = listbox.curselection()
            if not selection:
                return None
            return int(selection[0])

        def update_detail(_event=None) -> None:
            item = None
            source_side = ""
            index = selected_index(player_list)
            if index is not None and index < len(player_inventory):
                item = normalise_item(player_inventory[index])
                source_side = "player"
            else:
                index = selected_index(target_list)
                if index is not None and index < len(target_inventory):
                    item = normalise_item(target_inventory[index])
                    source_side = "target"
            if not item:
                detail_var.set("")
                return
            source = str(item.get("source") or "")
            if mode == "shop" and index is not None:
                if source_side == "target":
                    price_text = _ui_text(self.config_data, "trade_buy_price").format(price=buy_value(item))
                else:
                    price_text = _ui_text(self.config_data, "trade_sell_price").format(price=get_sell_value(item))
                detail_var.set(f"{_item_label(item, language=language)} / {price_text} / source:{source}".strip())
            else:
                detail_var.set(f"{_item_label(item, language=language)} / source:{source}".strip())

        def transfer_to_player(index: int, quantity: int = 1) -> bool:
            if index < 0 or index >= len(target_inventory):
                return False
            item = normalise_item(target_inventory[index])
            amount = min(max(1, quantity), _safe_int(item.get("quantity", 1), 1))
            price = buy_value(item) * amount
            if not can_add_item_stack(
                player_inventory,
                item,
                max_slots=PLAYER_INVENTORY_MAX_SLOTS,
                source="trade" if mode == "shop" else "loot",
                quantity=amount,
            ):
                slot_label = "Inventory is full" if str(language).lower().startswith("en") else "所持品がいっぱいです"
                messagebox.showwarning(
                    title,
                    f"{slot_label} ({inventory_slot_count(player_inventory)}/{PLAYER_INVENTORY_MAX_SLOTS}).",
                )
                return False
            if mode == "shop":
                if self._player_gold() < price:
                    messagebox.showwarning(_ui_text(self.config_data, "trade_title"), _ui_text(self.config_data, "trade_not_enough_gold"))
                    return False
                self._set_player_gold(self._player_gold() - price)
                if target_character:
                    target_character.gold += price
            moved = transfer_item_stack(
                target_inventory,
                player_inventory,
                index,
                amount,
                source="trade" if mode == "shop" else "loot",
                max_target_slots=PLAYER_INVENTORY_MAX_SLOTS,
            )
            if not moved:
                return False
            label = _item_label(moved, language=language)
            if mode == "shop":
                self._append_inventory_event(f"> [購入] {label} (-{price}G)")
            else:
                self._append_inventory_event(f"> [入手] {label}")
            return True

        def transfer_to_target(index: int, quantity: int = 1) -> bool:
            if index < 0 or index >= len(player_inventory):
                return False
            item = normalise_item(player_inventory[index])
            amount = min(max(1, quantity), _safe_int(item.get("quantity", 1), 1))
            price = get_sell_value(item) * amount
            if item.get("equipped"):
                self.engine._unequip_player_slot(self.engine._equipment_slot_for_item(item), source="inventory_transfer")
            if mode == "shop":
                if target_character and target_character.gold < price:
                    messagebox.showwarning(
                        _ui_text(self.config_data, "trade_title"),
                        _ui_text(self.config_data, "trade_target_not_enough_gold").format(name=target_character.name),
                    )
                    return False
                self._set_player_gold(self._player_gold() + price)
                if target_character:
                    target_character.gold = max(0, target_character.gold - price)
            moved = transfer_item_stack(player_inventory, target_inventory, index, amount, source="trade" if mode == "shop" else "container")
            if not moved:
                return False
            label = _item_label(moved, language=language)
            if mode == "shop":
                self._append_inventory_event(f"> [売却] {label} (+{price}G)")
            else:
                self._append_inventory_event(f"> [移動] {label}")
            return True

        def move_to_player() -> None:
            selection = target_list.curselection()
            if not selection:
                return
            if not transfer_to_player(int(selection[0]), 1):
                return
            self._save_inventory_change()
            refresh()

        def move_to_target() -> None:
            selection = player_list.curselection()
            if not selection or mode == "inventory":
                return
            if not transfer_to_target(int(selection[0]), 1):
                return
            self._save_inventory_change()
            refresh()

        def move_all_to_player() -> None:
            moved_any = False
            index = 0
            while index < len(target_inventory):
                item = normalise_item(target_inventory[index])
                amount = _safe_int(item.get("quantity", 1), 1)
                if mode == "shop":
                    unit_price = max(1, buy_value(item))
                    amount = min(amount, self._player_gold() // unit_price)
                    if amount <= 0:
                        index += 1
                        continue
                if transfer_to_player(index, amount):
                    moved_any = True
                    continue
                index += 1
            if moved_any:
                self._save_inventory_change()
                refresh()

        def move_all_to_target() -> None:
            if mode == "inventory":
                return
            moved_any = False
            index = 0
            while index < len(player_inventory):
                item = normalise_item(player_inventory[index])
                amount = _safe_int(item.get("quantity", 1), 1)
                if mode == "shop" and target_character:
                    unit_price = max(1, get_sell_value(item))
                    amount = min(amount, target_character.gold // unit_price)
                    if amount <= 0:
                        index += 1
                        continue
                if transfer_to_target(index, amount):
                    moved_any = True
                    continue
                index += 1
            if moved_any:
                self._save_inventory_change()
                refresh()

        def equip_selected_item() -> None:
            index = selected_index(player_list)
            if index is None:
                return
            event = self.engine.toggle_player_equipment(index, save_game=False)
            line = str(event.get("line") or "")
            if line:
                self._append_inventory_event(line)
            if event.get("changed"):
                self._save_inventory_change()
                refresh()
            else:
                update_detail()

        def select_item_target(item: dict[str, object]) -> str | None:
            options = self.engine.item_use_target_options(item)
            if len(options) <= 1:
                return "player"
            result = {"target": None}
            dialog = self._create_modal_dialog("対象選択", 420, 360)
            dialog.title("対象選択")
            dialog.grid_columnconfigure(0, weight=1)
            dialog.grid_rowconfigure(1, weight=1)
            tk.Label(
                dialog,
                text=f"{item.get('name') or 'アイテム'} の使用対象",
                bg=APP_DEEP_BG,
                fg="#f2f2f2",
                font=self.ui_fonts.bold(-2),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
            target_list = tk.Listbox(
                dialog,
                bg=APP_PANEL_BG,
                fg="#f2f2f2",
                selectbackground="#263654",
                relief="solid",
                bd=1,
                font=self.ui_fonts.normal(-2),
            )
            target_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
            for option in options:
                target_list.insert("end", str(option.get("label") or option.get("name") or option.get("id") or "target"))
            target_list.selection_set(0)
            actions = tk.Frame(dialog, bg=APP_DEEP_BG)
            actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
            actions.grid_columnconfigure(0, weight=1)

            def choose() -> None:
                selection = target_list.curselection()
                if not selection:
                    return
                result["target"] = str(options[int(selection[0])].get("id") or "player")
                dialog.destroy()

            def cancel() -> None:
                result["target"] = None
                dialog.destroy()

            self._instant_button(actions, "決定", choose).grid(row=0, column=1, sticky="e", padx=(0, 8))
            self._instant_button(actions, "キャンセル", cancel).grid(row=0, column=2, sticky="e")
            target_list.bind("<Double-Button-1>", lambda _event: choose())
            self.wait_window(dialog)
            return result["target"]

        def use_selected_item() -> None:
            index = selected_index(player_list)
            if index is None:
                return
            item = normalise_item(player_inventory[index])
            target_id = select_item_target(item)
            if target_id is None:
                return
            used, message = use_inventory_item(player_inventory, index, language=language)
            if message:
                self._append_inventory_event(f"> [使用] {message}")
            if used:
                self.engine.apply_item_effects_to_target(
                    used,
                    target_id=target_id,
                    source="item",
                    save_game=False,
                )
                if hasattr(self, "log_text"):
                    self._set_log(self.engine.state.log_text(16))
                self._save_inventory_change()
                refresh()

        player_list.bind("<<ListboxSelect>>", update_detail)
        target_list.bind("<<ListboxSelect>>", update_detail)
        player_list.bind("<Motion>", lambda event: show_tooltip(player_list, player_inventory, "sell" if mode == "shop" else "", event))
        target_list.bind("<Motion>", lambda event: show_tooltip(target_list, target_inventory, "buy" if mode == "shop" else "", event))
        player_list.bind("<Leave>", hide_tooltip)
        target_list.bind("<Leave>", hide_tooltip)
        refresh()

    def _player_inventory(self) -> list[dict[str, object]]:
        inventory = self.engine._player_inventory()
        if not isinstance(inventory, list):
            inventory = []
        if not inventory and not self.engine.state.flags.get("starter_inventory_seeded"):
            inventory.extend(starter_items())
            self.engine.state.flags["starter_inventory_seeded"] = True
            self.engine._sync_player_inventory()
        return inventory

    def _player_gold(self) -> int:
        player = self._player_character_dict()
        return int(player.get("gold") or self.engine.state.gold or 0)

    def _set_player_gold(self, value: int) -> None:
        gold = max(0, int(value))
        self.engine.state.gold = gold
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            self.engine.state.party[0]["gold"] = gold
        character = self.engine.player_character()
        if character:
            character.gold = gold

    def _save_inventory_change(self) -> None:
        inventory = self._player_inventory()
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            self.engine.state.party[0]["inventory"] = inventory
        character = self.engine.player_character()
        if character:
            character.inventory = inventory
            character.equipment = self.engine._player_equipment()
        self.engine._sync_player_equipment()
        try:
            self.engine.save_game()
        except Exception:
            pass
        self._refresh_status_panel()

    def _append_inventory_event(self, text: str) -> None:
        self.engine.state.display_log.append(text)
        if hasattr(self, "log_text"):
            self._set_log(self.engine.state.log_text(16))

    def _open_home_storage_window(self) -> None:
        if not self.engine.is_current_player_home():
            messagebox.showinfo("家の保存箱", "現在地はプレイヤーの家ではありません。")
            return
        storage = self.engine.current_home_storage_inventory()
        self._open_inventory_window("家の保存箱", "家の保存箱", storage, mode="container")

    def _screen_heading(self, parent: tk.Widget, title: str, subtitle: str, row: int) -> None:
        tk.Label(parent, text=title, bg="#111722", fg="#f4d27a", anchor="w", font=self.ui_fonts.bold(8)).grid(row=row, column=0, sticky="ew")
        tk.Label(parent, text=subtitle, bg="#111722", fg="#b8c0d5", anchor="w", font=self.ui_fonts.normal(-3)).grid(row=row + 1, column=0, sticky="ew", pady=(2, 0))

    def _screen_topbar(self, parent: tk.Widget, title: str) -> tk.Frame:
        header = tk.Frame(parent, bg="#151925", padx=12, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=title, bg="#151925", fg="#f4d27a", anchor="w", font=self.ui_fonts.bold(2)).grid(row=0, column=0, sticky="ew")
        return header

    def _screen_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        row: int,
        column: int = 0,
        sticky: str = "ew",
    ) -> tk.Widget:
        button = self._instant_button(parent, text, command)
        button.grid(row=row, column=column, sticky=sticky, padx=4, pady=5)
        return button

    def _cloud_setting_row(
        self,
        parent: tk.Widget,
        row: int,
        provider: str,
        provider_label: str,
        model_var: tk.StringVar,
        key_var: tk.StringVar,
        model_values: tuple[str, ...],
    ) -> None:
        tk.Label(parent, text=provider_label, bg="#111722", fg="#b8c0d5").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        combo = ttk.Combobox(parent, textvariable=model_var, values=model_values, state="normal")
        combo.grid(row=row, column=1, sticky="ew", pady=3, padx=(0, 10))
        self.cloud_model_combos[provider] = combo
        tk.Label(parent, text=_ui_text(self.config_data, "settings_api_key"), bg="#111722", fg="#b8c0d5").grid(row=row, column=2, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(parent, textvariable=key_var, show="*").grid(row=row, column=3, sticky="ew", pady=3)

    def _labeled_entry(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        width: int | None = None,
    ) -> None:
        tk.Label(parent, text=label, bg="#111722", fg="#b8c0d5").grid(row=row, column=column, sticky="w", padx=(0, 6))
        ttk.Entry(parent, textvariable=variable, width=width).grid(row=row, column=column + 1, sticky="ew", padx=(0, 10))

    def _labeled_combo(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        row: int,
        column: int,
    ) -> None:
        tk.Label(parent, text=label, bg="#111722", fg="#b8c0d5").grid(row=row, column=column, sticky="w", padx=(0, 6))
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(0, 10),
        )

    def _editable_text(self, parent: tk.Widget, label: str, row: int, height: int) -> tk.Text:
        tk.Label(parent, text=label, bg="#111722", fg="#f4d27a", anchor="w", font=self.ui_fonts.bold(-4)).grid(
            row=row,
            column=0,
            sticky="ew",
        )
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg="#0d1017",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            padx=8,
            pady=6,
            font=self.ui_fonts.normal(-4),
        )
        text.grid(row=row + 1, column=0, sticky="nsew", pady=(4, 8))
        return text

    def _continue_latest(self) -> None:
        try:
            text = self.engine.load_game()
        except Exception as exc:
            self._show_error(exc)
            return
        self._enter_loaded_game(text)
        self._append_log(
            "\n"
            + _ui_text(self.config_data, "log_loaded").format(
                world=self.engine.state.world_name,
                player=self.engine.state.player_name,
            )
            + "\n"
        )

    def _start_world_creation(self) -> None:
        self.premise_var.set(self.premise_text.get("1.0", "end").strip())
        self._new_world()

    def _refresh_world_select_screen(self) -> None:
        if not hasattr(self, "world_listbox"):
            return
        self.world_slots = self.save_store.list_worlds()
        self.world_listbox.delete(0, "end")
        for slot in self.world_slots:
            self.world_listbox.insert("end", slot.label)
        if not self.world_slots:
            self.world_listbox.insert("end", _ui_text(self.config_data, "empty_no_worlds"))
            return
        self.world_listbox.selection_set(0)

    def _refresh_continue_select_screen(self) -> None:
        if not hasattr(self, "continue_save_listbox"):
            return
        self.save_slots = self.save_store.list_saves()
        self.continue_save_listbox.delete(0, "end")
        for slot in self.save_slots:
            self.continue_save_listbox.insert("end", slot.label)
        if not self.save_slots:
            self.continue_save_listbox.insert("end", _ui_text(self.config_data, "empty_no_saved_games"))
            return
        self.continue_save_listbox.selection_set(0)

    def _load_selected_save(self) -> None:
        self._load_selected_continue_save()

    def _load_selected_continue_save(self) -> None:
        if not hasattr(self, "continue_save_listbox"):
            return
        selection = self.continue_save_listbox.curselection()
        if not selection or not self.save_slots:
            self._show_error(ValueError(_ui_text(self.config_data, "error_no_save_selected")))
            return
        slot = self.save_slots[int(selection[0])]
        try:
            text = self.engine.load_game(slot.world_name, slot.player_name)
        except Exception as exc:
            self._show_error(exc)
            return
        self._enter_loaded_game(text)
        self._append_log("\n" + _ui_text(self.config_data, "log_loaded").format(world=slot.world_name, player=slot.player_name) + "\n")

    def _start_selected_world(self) -> None:
        selection = self.world_listbox.curselection()
        if not selection or not self.world_slots:
            self._show_error(ValueError(_ui_text(self.config_data, "error_no_world_selected")))
            return
        slot = self.world_slots[int(selection[0])]
        try:
            world = self.save_store.load_world(slot.world_name)
        except Exception as exc:
            self._show_error(exc)
            return

        opening = world.overview or world.structure_description or f"{world.world_name} begins."
        choices = _initial_world_choices(world, self.config_data.language)
        self.engine.state = GameStateData.new_game("Player", world, opening, choices)
        self.engine._set_world_time_total_hours(INITIAL_WORLD_TIME_HOURS)
        self.engine.state.flags["screen_mode"] = "exploration"
        self.character_setup_back_screen = "world_select"
        self._show_screen("character_setup")
        self._append_log("\n" + _ui_text(self.config_data, "log_prepared_world").format(world=world.world_name) + "\n")

    def _export_selected_world_dialog(self) -> None:
        if not hasattr(self, "world_listbox"):
            return
        selection = self.world_listbox.curselection()
        if not selection or not self.world_slots:
            self._show_error(ValueError(_ui_text(self.config_data, "error_no_world_selected")))
            return
        slot = self.world_slots[int(selection[0])]
        filename = filedialog.asksaveasfilename(
            title=_ui_text(self.config_data, "dialog_export_world"),
            defaultextension=".zip",
            initialfile=f"{_safe_filename(slot.world_name)}.fantasia-world.zip",
            filetypes=[
                (_ui_text(self.config_data, "dialog_file_world_package"), "*.zip"),
                (_ui_text(self.config_data, "dialog_file_world_json"), "*.json"),
                (_ui_text(self.config_data, "dialog_file_all"), "*.*"),
            ],
        )
        if not filename:
            return
        self._run_task(
            _ui_text(self.config_data, "task_exporting_world"),
            lambda: self.save_store.export_world(slot.world_name, Path(filename)),
            lambda path: self._append_log("\n" + _ui_text(self.config_data, "log_exported_world").format(path=path) + "\n"),
        )

    def _enter_loaded_game(self, text: str) -> None:
        self.player_var.set(self.engine.state.player_name)
        self._show_screen("game")
        self._set_log(text, animate=False)
        self._set_current_image_if_available()

    def _set_current_image_if_available(self) -> None:
        state = self.engine.state
        candidates: list[str] = []
        location = state.world_data.locations.get(state.current_location)
        if location and location.image_path:
            candidates.append(location.image_path)
        for item in candidates:
            path = Path(item)
            if path.is_file():
                self._set_image(path)
                return

    def _image_generation_enabled(self, *, show_status: bool = False) -> bool:
        enabled = _image_generation_enabled_config(self.config_data)
        if not enabled and show_status:
            self._set_task_status(_ui_text(self.config_data, "task_image_generation_disabled"))
        return enabled

    def _refresh_settings_screen(self) -> None:
        self.llm_backend_var.set(self.config_data.llm_backend)
        self.llm_context_size_var.set(str(self.config_data.llm_context_size))
        self._load_llm_settings_vars()
        self._load_image_settings_vars()
        self._load_ui_settings_vars()
        self._load_debug_settings_vars()
        if hasattr(self, "settings_text"):
            self._replace_text(self.settings_text, self._settings_text())
        if hasattr(self, "device_info_text"):
            self._replace_text(self.device_info_text, _debug_device_summary(self.device_info, self.config_data.language))

    def _refresh_debug_settings(self) -> None:
        self.device_info = detect_device()
        if hasattr(self, "device_info_text"):
            self._replace_text(self.device_info_text, _debug_device_summary(self.device_info, self.config_data.language))

    def _load_debug_settings_vars(self) -> None:
        self.debug_allow_any_action_var.set(self.config_data.allow_any_action_concept)
        self.debug_reveal_world_map_on_generation_var.set(self.config_data.reveal_world_map_on_generation)
        self.debug_free_location_travel_var.set(self.config_data.debug_free_location_travel)
        self.debug_disable_movement_time_passage_var.set(self.config_data.debug_disable_movement_time_passage)
        self.debug_disable_dungeon_random_encounters_var.set(self.config_data.debug_disable_dungeon_random_encounters)

    def _apply_llm_backend_setting(self) -> None:
        backend = _llm_backend_from_label(self.llm_backend_label_var.get(), self.config_data.language)
        self.llm_backend_var.set(backend)
        if backend not in _llm_backend_options():
            self._show_error(ValueError(_ui_text(self.config_data, "error_unknown_llm_backend").format(backend=backend)))
            return
        try:
            context_size = int(self.llm_context_size_var.get().strip())
            if context_size < 1024:
                raise ValueError(_ui_text(self.config_data, "error_llm_context_min"))
            temperature = float(self.llm_temperature_var.get().strip())
            if temperature < 0:
                raise ValueError(_ui_text(self.config_data, "error_llm_temperature_min"))
        except ValueError as exc:
            self._show_error(exc)
            return
        try:
            self._save_llm_settings(backend, context_size)
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        self._append_log(
            "\n"
            + _ui_text(self.config_data, "log_settings_llm").format(
                backend=backend,
                context_size=context_size,
            )
            + "\n"
        )

    def _load_llm_settings_vars(self) -> None:
        self.llm_backend_var.set(self.config_data.llm_backend)
        self.llm_backend_label_var.set(_llm_backend_label(self.config_data.llm_backend, self.config_data.language))
        self.llm_context_size_var.set(str(self.config_data.llm_context_size))
        self.llm_temperature_var.set(_llm_temperature_text(self.config_data))
        self.llm_repeat_suppression_var.set(_llm_repeat_suppression_enabled(self.config_data))
        self.local_model_var.set(_selected_model_label(self.config_data))
        self.cloud_openai_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "openai"))
        self.cloud_xai_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "xai"))
        self.cloud_gemini_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "gemini"))
        self.cloud_openai_key_var.set(_cloud_key_value(self.config_data, "openai"))
        self.cloud_xai_key_var.set(_cloud_key_value(self.config_data, "xai"))
        self.cloud_gemini_key_var.set(_cloud_key_value(self.config_data, "gemini"))
        if hasattr(self, "local_model_combo"):
            self.local_model_combo.configure(values=_local_model_labels(self.config_data, self.config_data.language))
        if hasattr(self, "llm_backend_combo"):
            self.llm_backend_combo.configure(values=_llm_backend_label_options(self.config_data.language))
        if hasattr(self, "cloud_model_combos"):
            for provider, combo in self.cloud_model_combos.items():
                combo.configure(values=_cloud_model_options(provider, self.config_data))
        self._refresh_llm_backend_fields()

    def _save_llm_settings(self, backend: str, context_size: int, *, complete_setup: bool = False, lock_backend: bool = True) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ai_setting = raw.setdefault("ai_setting", {})
        local_model_setting = ai_setting.setdefault("local_model_setting", {})
        local_llm = dict(local_model_setting.get("local_llm", {}))
        selected_model = option_from_label(self.config_data, self.local_model_var.get())
        if selected_model is not None:
            local_llm = option_to_local_llm(selected_model, local_llm)
        local_model_setting["llm_backend"] = backend
        local_llm["context_size"] = context_size
        local_model_setting["local_llm"] = local_llm
        completion_parameters = ai_setting.setdefault("completion_parameters", {})
        if not isinstance(completion_parameters, dict):
            completion_parameters = {}
            ai_setting["completion_parameters"] = completion_parameters
        default_completion = completion_parameters.setdefault("default", {})
        if not isinstance(default_completion, dict):
            default_completion = {}
            completion_parameters["default"] = default_completion
        default_completion["temperature"] = float(self.llm_temperature_var.get().strip())
        if self.llm_repeat_suppression_var.get():
            default_completion["repeat_penalty"] = 1.15
        else:
            default_completion["repeat_penalty"] = 1.0
        cloud_llm = dict(local_model_setting.get("cloud_llm", {}))
        self._apply_cloud_provider_vars(cloud_llm, ai_setting, "openai", self.cloud_openai_model_var, self.cloud_openai_key_var)
        self._apply_cloud_provider_vars(cloud_llm, ai_setting, "xai", self.cloud_xai_model_var, self.cloud_xai_key_var)
        self._apply_cloud_provider_vars(cloud_llm, ai_setting, "gemini", self.cloud_gemini_model_var, self.cloud_gemini_key_var)
        local_model_setting["cloud_llm"] = cloud_llm
        setup = raw.setdefault("setup", {})
        if complete_setup:
            setup["completed"] = True
        setup["backend_locked"] = bool(lock_backend)
        setup.setdefault("auto_select_backend", True)
        raw["device_info"] = self.device_info.to_config()
        self._write_config_and_reload_engine(raw)

    def _apply_cloud_provider_vars(
        self,
        cloud_llm: dict,
        ai_setting: dict,
        provider: str,
        model_var: tk.StringVar,
        key_var: tk.StringVar,
    ) -> None:
        provider_config = dict(cloud_llm.get(provider, {}))
        model = model_var.get().strip()
        if model:
            provider_config["model"] = model
        cloud_llm[provider] = provider_config
        key = key_var.get().strip()
        env_name = str(provider_config.get("api_key_env") or _cloud_default_env(provider))
        environment_setting = ai_setting.setdefault("environment_setting", {})
        if key:
            environment_setting[env_name] = key
            environment_setting[f"{provider}_api_key"] = key

    def _write_config_and_reload_engine(self, raw: dict) -> None:
        CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config_data = load_config()
        old_state = self.engine.state
        self.engine.stop()
        self.engine = GameEngine(
            create_llm_backend(self.config_data),
            create_image_backend(self.config_data),
            JsonStore(),
            self.save_store,
            PromptTemplateStore(resolve_prompt_template_dir(self.config_data.prompt_template_path)),
            allow_any_action_concept=self.config_data.allow_any_action_concept,
            reveal_world_map_on_generation=self.config_data.reveal_world_map_on_generation,
            debug_free_location_travel=self.config_data.debug_free_location_travel,
            debug_disable_movement_time_passage=self.config_data.debug_disable_movement_time_passage,
            debug_disable_dungeon_random_encounters=self.config_data.debug_disable_dungeon_random_encounters,
        )
        self.engine.state = old_state

    def _detect_device_from_settings(self) -> None:
        self.device_info = detect_device()
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        raw["device_info"] = self.device_info.to_config()
        CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config_data = load_config()
        self.llm_backend_var.set(self.device_info.recommended_llm_backend)
        self._refresh_settings_screen()

    def _fetch_cloud_models(self, provider: str) -> None:
        provider = provider.strip().lower()
        model_var = self._cloud_model_var(provider)
        key_var = self._cloud_key_var(provider)

        def work() -> list[str]:
            return fetch_cloud_model_ids(self.config_data, provider, key_var.get())

        def done(models: list[str]) -> None:
            if not models:
                self._show_error(ValueError(_ui_text(self.config_data, "error_no_cloud_models_fetched").format(provider=provider)))
                return
            raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
            ai_setting = raw.setdefault("ai_setting", {})
            local_model_setting = ai_setting.setdefault("local_model_setting", {})
            cloud_llm = local_model_setting.setdefault("cloud_llm", {})
            model_cache = cloud_llm.setdefault("model_cache", {})
            model_cache[provider] = models
            provider_config = cloud_llm.setdefault(provider, {})
            if model_var.get().strip() not in models:
                model_var.set(models[0])
            provider_config["model"] = model_var.get().strip()
            self._apply_cloud_provider_vars(cloud_llm, ai_setting, provider, model_var, key_var)
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
            self._load_llm_settings_vars()
            messagebox.showinfo(
                _ui_text(self.config_data, "settings_fetch_cloud_models"),
                _ui_text(self.config_data, "dialog_cloud_models_fetched").format(provider=provider, count=len(models)),
            )

        self._run_task(
            _ui_text(self.config_data, "task_fetching_cloud_models").format(provider=provider),
            work,
            done,
        )

    def _cloud_model_var(self, provider: str) -> tk.StringVar:
        if provider == "xai":
            return self.cloud_xai_model_var
        if provider == "gemini":
            return self.cloud_gemini_model_var
        return self.cloud_openai_model_var

    def _cloud_key_var(self, provider: str) -> tk.StringVar:
        if provider == "xai":
            return self.cloud_xai_key_var
        if provider == "gemini":
            return self.cloud_gemini_key_var
        return self.cloud_openai_key_var

    def _download_selected_local_model(self) -> None:
        option = option_from_label(self.config_data, self.local_model_var.get())
        if option is None:
            self._show_error(ValueError(_ui_text(self.config_data, "error_no_model_selected")))
            return

        def progress(received: int, total: int) -> None:
            if total:
                percent = int(received * 100 / total)
                text = _ui_text(self.config_data, "task_downloading_model_progress").format(name=option.display_name, percent=percent)
            else:
                mb = received // (1024 * 1024)
                text = _ui_text(self.config_data, "task_downloading_model_bytes").format(name=option.display_name, mb=mb)
            self.after(0, lambda value=text: self._set_task_status(value))

        def work() -> Path:
            return download_model(option, progress)

        def done(path: Path) -> None:
            self.local_model_var.set(_localized_model_label(option, self.config_data.language))
            self._save_llm_settings(self.llm_backend_var.get().strip(), option.context_size)
            self._refresh_settings_screen()
            messagebox.showinfo(
                _ui_text(self.config_data, "settings_download_model"),
                _ui_text(self.config_data, "dialog_model_downloaded").format(path=path),
            )

        self._run_task(
            _ui_text(self.config_data, "task_downloading_model").format(name=option.display_name),
            work,
            done,
            initial_status=_ui_text(self.config_data, "task_downloading_model_progress").format(name=option.display_name, percent=0),
            auto_status=False,
            log_animation=False,
        )

    def _download_selected_sdxl_model(self) -> None:
        option = option_from_label(self.config_data, self.sdxl_model_var.get())
        if option is None:
            self._show_error(ValueError(_ui_text(self.config_data, "error_no_sdxl_model_selected")))
            return

        def progress(received: int, total: int) -> None:
            if total:
                percent = int(received * 100 / total)
                text = _ui_text(self.config_data, "task_downloading_model_progress").format(name=option.display_name, percent=percent)
            else:
                mb = received // (1024 * 1024)
                text = _ui_text(self.config_data, "task_downloading_model_bytes").format(name=option.display_name, mb=mb)
            self.after(0, lambda value=text: self._set_task_status(value))

        def work() -> Path:
            return download_model(option, progress)

        def done(path: Path) -> None:
            self.sdxl_model_var.set(_localized_model_label(option, self.config_data.language))
            self._apply_image_generation_setting()
            self._refresh_settings_screen()
            messagebox.showinfo(
                _ui_text(self.config_data, "settings_download_sdxl_model"),
                _ui_text(self.config_data, "dialog_model_downloaded").format(path=path),
            )

        self._run_task(
            _ui_text(self.config_data, "task_downloading_model").format(name=option.display_name),
            work,
            done,
            initial_status=_ui_text(self.config_data, "task_downloading_model_progress").format(name=option.display_name, percent=0),
            auto_status=False,
            log_animation=False,
        )

    def _open_first_run_notice(self) -> None:
        dialog = self._create_modal_dialog(_ui_text(self.config_data, "wizard_title"), 560, 220)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        tk.Label(
            dialog,
            text=_ui_text(self.config_data, "wizard_title"),
            bg=APP_DEEP_BG,
            fg="#f4d27a",
            font=self.ui_fonts.bold(4),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 10))
        tk.Label(
            dialog,
            text=_ui_text(self.config_data, "wizard_body"),
            bg=APP_DEEP_BG,
            fg="#f2f2f2",
            anchor="center",
            justify="center",
            wraplength=480,
            font=self.ui_fonts.normal(0),
        ).grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 14))
        actions = tk.Frame(dialog, bg=APP_DEEP_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 20))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "settings_close"), lambda: self._close_first_run_notice(dialog)).grid(row=0, column=1, sticky="e", ipadx=22, ipady=7)
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_first_run_notice(dialog))

    def _close_first_run_notice(self, dialog: ModalDialog) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        setup = raw.setdefault("setup", {})
        setup["completed"] = True
        setup["backend_locked"] = True
        setup.setdefault("auto_select_backend", True)
        CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config_data = load_config()
        dialog.destroy()

    def _set_ui_setting_value(self, key: str, value: object) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ui_setting = raw.setdefault("ui_setting", {})
        ui_setting[key] = value
        try:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
        except Exception as exc:
            self._show_error(exc)

    def _load_image_settings_vars(self) -> None:
        image_config = self.config_data.image_backend
        sdxl_config = self.config_data.sdxl
        negative_prompts = image_config.get("negative_prompts") if isinstance(image_config.get("negative_prompts"), dict) else {}
        self.image_quality_var.set(str(image_config.get("quality_preset", "balanced")))
        self.image_sampler_var.set(str(image_config.get("sampling_method", "dpm++2m")))
        self.image_scheduler_var.set(str(image_config.get("scheduler", "karras")))
        self.sdxl_model_var.set(_selected_sdxl_model_label(self.config_data))
        self.image_lora_prompt_var.set(str(image_config.get("lora_prompt", "")))
        self.image_vae_path_var.set(str(sdxl_config.get("vae_path", "")))
        self.image_taesd_path_var.set(str(sdxl_config.get("taesd_path", "")))
        self.image_lora_dir_var.set(str(sdxl_config.get("lora_model_dir", "")))
        self.image_negative_background_var.set(str(negative_prompts.get("background", DEFAULT_NEGATIVE_PROMPTS["background"])))
        self.image_negative_character_var.set(str(negative_prompts.get("character", DEFAULT_NEGATIVE_PROMPTS["character"])))
        self.image_negative_monster_var.set(str(negative_prompts.get("monster", DEFAULT_NEGATIVE_PROMPTS["monster"])))
        self.image_negative_cg_var.set(str(negative_prompts.get("cg", DEFAULT_NEGATIVE_PROMPTS["cg"])))
        if hasattr(self, "image_quality_combo"):
            self.image_quality_combo.configure(values=_quality_preset_options(image_config))
        if hasattr(self, "sdxl_model_combo"):
            self.sdxl_model_combo.configure(values=_sdxl_model_labels(self.config_data, self.config_data.language))

    def _load_ui_settings_vars(self) -> None:
        self.ui_font_var.set(_font_label_from_config(self.config_data, self))
        self.ui_font_path_var.set(str(self.config_data.font_path))
        self.ui_font_size_var.set(str(self.config_data.font_size))
        self.ui_text_speed_var.set(str(self.config_data.ui_setting.get("text_speed", 0.02)))
        self.ui_language_var.set(_language_label(self.config_data.language))
        self.ui_generate_images_var.set(_image_generation_enabled_config(self.config_data))
        self.ui_show_button_help_var.set(bool(self.config_data.ui_setting.get("show_game_button_help", True)))
        if hasattr(self, "ui_font_combo"):
            self.ui_font_combo.configure(values=_font_options(self, self.config_data.language))

    def _apply_image_generation_setting(self) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ai_setting = raw.setdefault("ai_setting", {})
        local_model_setting = ai_setting.setdefault("local_model_setting", {})
        image_config = local_model_setting.setdefault("image_backend", {})
        sdxl_config = local_model_setting.setdefault("sdxl", {})
        image_config["quality_preset"] = self.image_quality_var.get().strip() or "balanced"
        image_config["sampling_method"] = self.image_sampler_var.get().strip()
        image_config["scheduler"] = self.image_scheduler_var.get().strip()
        image_config.pop("lora_prompt", None)
        selected_sdxl = option_from_label(self.config_data, self.sdxl_model_var.get())
        if selected_sdxl is not None:
            sdxl_config["model_name"] = selected_sdxl.display_name
            sdxl_config["selected_model_id"] = selected_sdxl.model_id
            sdxl_config["checkpoint_path"] = _project_relative_path_text(selected_sdxl.path)
            sdxl_config["download_url"] = selected_sdxl.url
        negative_prompts = dict(image_config.get("negative_prompts", {})) if isinstance(image_config.get("negative_prompts"), dict) else {}
        negative_prompts["background"] = self.image_negative_background_var.get().strip()
        negative_prompts["character"] = self.image_negative_character_var.get().strip()
        negative_prompts["monster"] = self.image_negative_monster_var.get().strip()
        negative_prompts["cg"] = self.image_negative_cg_var.get().strip()
        image_config["negative_prompts"] = negative_prompts
        sdxl_config.pop("vae_path", None)
        sdxl_config.pop("taesd_path", None)
        sdxl_config.pop("lora_model_dir", None)
        try:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
            stop_image = getattr(self.engine.image_backend, "stop", None)
            if callable(stop_image):
                stop_image()
            self.engine.image_backend = create_image_backend(self.config_data)
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        self._append_log("\n" + _ui_text(self.config_data, "log_settings_image") + "\n")

    def _apply_ui_setting(self) -> None:
        try:
            font_size = int(self.ui_font_size_var.get().strip())
            if font_size < 6:
                raise ValueError(_ui_text(self.config_data, "error_font_size_min"))
            text_speed = float(self.ui_text_speed_var.get().strip())
            if text_speed < 0:
                raise ValueError(_ui_text(self.config_data, "error_text_speed_min"))
        except ValueError as exc:
            self._show_error(exc)
            return

        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ui_setting = raw.setdefault("ui_setting", {})
        selected_font_family = _font_family_from_label(self.ui_font_var.get(), self.config_data.language)
        ui_setting["font_path"] = BUILTIN_FONT_PATH
        if selected_font_family:
            ui_setting["font_family"] = selected_font_family
        else:
            ui_setting.pop("font_family", None)
        ui_setting["font_size"] = font_size
        ui_setting["text_speed"] = text_speed
        ui_setting["language"] = _language_code(self.ui_language_var.get())
        ui_setting["generate_images"] = bool(self.ui_generate_images_var.get())
        ui_setting["show_game_button_help"] = bool(self.ui_show_button_help_var.get())
        try:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
            self.ui_fonts = configure_ui_fonts(self, self.config_data)
            if not bool(self.config_data.ui_setting.get("show_game_button_help", True)):
                self._hide_game_button_help()
            if not _image_generation_enabled_config(self.config_data) and self.visual_task_after_id:
                try:
                    self.after_cancel(self.visual_task_after_id)
                except tk.TclError:
                    pass
                self.visual_task_after_id = None
            self._build_menu()
            self._rebuild_settings_screen()
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        self._append_log("\n" + _ui_text(self.config_data, "log_settings_ui") + "\n")

    def _apply_debug_setting(self) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ui_setting = raw.setdefault("ui_setting", {})
        ui_setting["allow_any_action_concept"] = bool(self.debug_allow_any_action_var.get())
        ui_setting["reveal_world_map_on_generation"] = bool(self.debug_reveal_world_map_on_generation_var.get())
        ui_setting["debug_free_location_travel"] = bool(self.debug_free_location_travel_var.get())
        ui_setting["debug_disable_movement_time_passage"] = bool(self.debug_disable_movement_time_passage_var.get())
        ui_setting["debug_disable_dungeon_random_encounters"] = bool(self.debug_disable_dungeon_random_encounters_var.get())
        try:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
            self.engine.allow_any_action_concept = self.config_data.allow_any_action_concept
            self.engine.reveal_world_map_on_generation = self.config_data.reveal_world_map_on_generation
            self.engine.debug_free_location_travel = self.config_data.debug_free_location_travel
            self.engine.debug_disable_movement_time_passage = self.config_data.debug_disable_movement_time_passage
            self.engine.debug_disable_dungeon_random_encounters = self.config_data.debug_disable_dungeon_random_encounters
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        self._append_log("\n" + _ui_text(self.config_data, "log_settings_debug") + "\n")

    def _refresh_generation_log_screen(self) -> None:
        if not hasattr(self, "generation_log_listbox"):
            return
        self.generation_log_entries = list_generation_logs(
            OUTPUT_DIR,
            self.save_store.worlds_dir,
            LOG_DIR,
            CRASHLOG_DIR,
        )
        self.generation_log_listbox.delete(0, "end")
        if not self.generation_log_entries:
            self.generation_log_listbox.insert("end", _ui_text(self.config_data, "empty_no_generation_logs"))
            self._replace_text(self.generation_log_text, _ui_text(self.config_data, "empty_no_generation_logs_detail"))
            return
        for entry in self.generation_log_entries:
            self.generation_log_listbox.insert("end", entry.label)
        self.generation_log_listbox.selection_set(0)
        self._show_selected_generation_log()

    def _show_selected_generation_log(self) -> None:
        if not hasattr(self, "generation_log_listbox"):
            return
        selection = self.generation_log_listbox.curselection()
        if not selection or not self.generation_log_entries:
            return
        index = int(selection[0])
        if index >= len(self.generation_log_entries):
            return
        self._replace_text(
            self.generation_log_text,
            format_generation_log_detail(self.generation_log_entries[index], self.config_data.language),
        )

    def _clear_generation_log_selection(self) -> None:
        if not hasattr(self, "generation_log_listbox"):
            return
        self.generation_log_listbox.selection_clear(0, "end")
        self._replace_text(self.generation_log_text, "")

    def _settings_text(self) -> str:
        local_llm = self.config_data.local_llm
        cloud_llm = self.config_data.cloud_llm
        image_config = self.config_data.image_backend
        sdxl = self.config_data.sdxl
        negative_prompts = image_config.get("negative_prompts") if isinstance(image_config.get("negative_prompts"), dict) else {}
        label = lambda key: _ui_text(self.config_data, key)
        loaded_text = label("settings_yes") if self.ui_fonts.loaded else label("settings_no")
        lines = [
            f"{label('settings_label_config')}: {CONFIG_PATH}",
            f"{label('settings_label_appdata')}: {self.save_store.data_dir}",
            f"{label('settings_label_runtime')}: {RUNTIME_DIR}",
            f"{label('settings_label_output')}: {OUTPUT_DIR}",
            f"{label('settings_label_prompt_templates')}: {resolve_prompt_template_dir(self.config_data.prompt_template_path)}",
            "",
            f"{label('settings_label_font_family')}: {self.ui_fonts.family}",
            f"{label('settings_label_font_size')}: {self.config_data.font_size}",
            f"{label('settings_label_font_path')}: {self.config_data.font_path}",
            f"{label('settings_label_font_file')}: {self.ui_fonts.path}",
            f"{label('settings_label_font_loaded')}: {loaded_text}",
            f"{label('settings_label_language')}: {_language_label(self.config_data.language)}",
            f"{label('settings_generate_images')}: {label('settings_yes') if _image_generation_enabled_config(self.config_data) else label('settings_no')}",
            "",
            f"{label('settings_label_device')}:",
            device_report(self.device_info, self.config_data.language),
            "",
            f"{label('settings_label_llm_backend')}: {self.config_data.llm_backend}",
            f"{label('settings_label_llm_mode')}: {_llm_backend_mode(self.config_data.llm_backend)}",
            f"{label('settings_label_llm_context_tokens')}: {self.config_data.llm_context_size}",
            f"{label('settings_label_local_model')}: {local_llm.get('model_path', '')}",
            f"{label('settings_label_selected_model')}: {_selected_model_label(self.config_data)}",
            f"{label('settings_label_llama_cpu_server')}: {_local_llm_server_path_text(local_llm, 'cpu')}",
            f"{label('settings_label_llama_vulkan_server')}: {_local_llm_server_path_text(local_llm, 'vulkan')}",
            f"{label('settings_label_llama_cuda_server')}: {_local_llm_server_path_text(local_llm, 'cuda')}",
            f"{label('settings_label_log_dir')}: {LOG_DIR}",
            f"{label('settings_label_crashlog_dir')}: {CRASHLOG_DIR}",
            f"{label('settings_label_llama_log_dir')}: {LOG_DIR / 'llama-server'}",
            "",
            f"{label('settings_label_cloud_openai_model')}: {_cloud_model_text(cloud_llm, 'openai')}",
            f"{label('settings_label_cloud_xai_model')}: {_cloud_model_text(cloud_llm, 'xai')}",
            f"{label('settings_label_cloud_gemini_model')}: {_cloud_model_text(cloud_llm, 'gemini')}",
            f"{label('settings_label_openai_key_env')}: {_cloud_key_status(self.config_data, 'openai')}",
            f"{label('settings_label_xai_key_env')}: {_cloud_key_status(self.config_data, 'xai')}",
            f"{label('settings_label_gemini_key_env')}: {_cloud_key_status(self.config_data, 'gemini')}",
            "",
            f"{label('settings_label_image_backend')}: {self.config_data.image_backend_name}",
            f"{label('settings_label_image_quality')}: {image_config.get('quality_preset', 'balanced')}",
            f"{label('settings_label_image_sampler')}: {image_config.get('sampling_method', '')}",
            f"{label('settings_label_image_scheduler')}: {image_config.get('scheduler', '')}",
            f"{label('settings_label_image_server')}: {sdxl.get('sd_server_path', '')}",
            f"{label('settings_label_sdxl_checkpoint')}: {sdxl.get('checkpoint_path', '')}",
            f"{label('settings_negative_background')}: {negative_prompts.get('background', '')}",
            f"{label('settings_negative_character')}: {negative_prompts.get('character', '')}",
            f"{label('settings_negative_monster')}: {negative_prompts.get('monster', '')}",
            f"{label('settings_negative_cg')}: {negative_prompts.get('cg', '')}",
            f"{label('settings_label_sd_server_log_dir')}: {LOG_DIR / 'sd-server'}",
            "",
            f"{label('settings_label_known_worlds')}: {len(self.save_store.list_worlds())}",
            f"{label('settings_label_save_slots')}: {len(self.save_store.list_saves())}",
        ]
        return "\n".join(lines)

    def _check_assets_dialog(self) -> None:
        checks = check_runtime_assets(self.config_data)
        message = format_asset_report(checks, self.config_data.language)
        if all(check.ok for check in checks):
            messagebox.showinfo(_ui_text(self.config_data, "asset_check_title"), message)
        else:
            messagebox.showwarning(_ui_text(self.config_data, "asset_check_title"), message)

    def _new_world(self) -> None:
        self.character_setup_back_screen = "world_create"
        self._reset_world_generation_progress()
        self._run_task(
            _ui_text(self.config_data, "task_creating_world"),
            lambda: self.engine.create_world(
                self.world_name_var.get(),
                self.premise_var.get(),
                crime_risk=_world_crime_risk_from_label(self.world_crime_risk_var.get()),
                enemy_strength=_world_enemy_strength_from_label(self.world_enemy_strength_var.get()),
                save_game=False,
                progress_callback=self._world_generation_progress_callback,
            ),
            self._on_world_created,
            initial_status=_ui_text(self.config_data, "world_generation_progress_start"),
            auto_status=False,
        )

    def _on_world_created(self, text: str) -> None:
        self.world_generation_progress_state = {
            "phase_rank": _world_generation_phase_rank("completed"),
            "percent": 100,
            "items": {},
        }
        self.world_generation_progress_var.set(100)
        self._show_screen("character_setup")
        self._replace_text(self.character_world_summary_text, self._character_world_summary())
        self._append_log("\n" + _ui_text(self.config_data, "log_world_generated") + "\n" + text + "\n")

    def _reset_world_generation_progress(self) -> None:
        self.world_generation_progress_state = {"phase_rank": -1, "percent": 0, "items": {}}
        self._clear_world_generation_progress_queue()
        if hasattr(self, "world_generation_progress_var"):
            self.world_generation_progress_var.set(0)

    def _world_generation_progress_callback(self, payload: dict[str, object]) -> None:
        try:
            self.world_generation_progress_queue.put_nowait(dict(payload))
        except Exception:
            pass

    def _clear_world_generation_progress_queue(self) -> None:
        progress_queue = getattr(self, "world_generation_progress_queue", None)
        if progress_queue is None:
            return
        while True:
            try:
                progress_queue.get_nowait()
            except queue.Empty:
                return

    def _schedule_world_generation_progress_poll(self) -> None:
        if self.world_generation_progress_after_id:
            return
        self.world_generation_progress_after_id = self.after(100, self._poll_world_generation_progress)

    def _poll_world_generation_progress(self) -> None:
        self.world_generation_progress_after_id = None
        self._drain_world_generation_progress_queue()
        if self.current_task_id:
            self._schedule_world_generation_progress_poll()

    def _drain_world_generation_progress_queue(self) -> None:
        progress_queue = getattr(self, "world_generation_progress_queue", None)
        if progress_queue is None:
            return
        while True:
            try:
                payload = progress_queue.get_nowait()
            except queue.Empty:
                return
            self._apply_world_generation_progress(payload)

    def _apply_world_generation_progress(self, payload: dict[str, object]) -> None:
        phase = str(payload.get("phase") or "")
        percent = max(0, min(100, _safe_int(str(payload.get("percent", payload.get("current", 0))), 0)))
        rank = _world_generation_phase_rank(phase)
        state = getattr(self, "world_generation_progress_state", None)
        if not isinstance(state, dict):
            state = {"phase_rank": -1, "percent": 0, "items": {}}
            self.world_generation_progress_state = state
        last_rank = _safe_int(str(state.get("phase_rank", -1)), -1)
        last_percent = _safe_int(str(state.get("percent", 0)), 0)
        if rank < last_rank or (rank == last_rank and percent < last_percent):
            return
        item_total = _safe_int(str(payload.get("item_total", 0)), 0)
        item_current = _safe_int(str(payload.get("item_current", 0)), 0)
        if rank == last_rank and item_total:
            items = state.setdefault("items", {})
            if isinstance(items, dict):
                last_item = _safe_int(str(items.get(phase, -1)), -1)
                if percent == last_percent and item_current < last_item:
                    return
                items[phase] = max(last_item, item_current)
        state["phase_rank"] = rank
        state["percent"] = percent
        self.world_generation_progress_var.set(percent)
        self._set_task_status(_world_generation_progress_text(self.config_data, payload))

    def _refresh_character_setup_screen(self) -> None:
        if not hasattr(self, "character_world_summary_text"):
            return
        self._replace_text(self.character_world_summary_text, self._character_world_summary())
        self._render_character_preview()

    def _back_from_character_setup(self) -> None:
        self._show_screen(self.character_setup_back_screen)

    def _character_world_summary(self) -> str:
        world = self.engine.state.world_data
        if not world or world.world_name == "unknown":
            return _ui_text(self.config_data, "character_world_need")
        lines = [
            f"{_ui_text(self.config_data, 'character_world_label')}: {world.world_name}",
            f"{_ui_text(self.config_data, 'character_world_start')}: {world.starting_location}",
        ]
        if world.overview:
            lines.append(world.overview)
        return "\n".join(lines)

    def _start_game_with_character(self) -> None:
        try:
            if self._character_stat_spent() > CHARACTER_BONUS_POINTS:
                raise ValueError(_ui_text(self.config_data, "character_bp_over"))
            character = self._character_from_setup()
            text = self.engine.apply_player_character(character)
        except Exception as exc:
            self._show_error(exc)
            return
        self._enter_loaded_game(text)
        self._append_log(
            "\n"
            + _ui_text(self.config_data, "log_started_game").format(
                world=self.engine.state.world_name,
                player=character.name,
            )
            + "\n"
        )

    def _character_from_setup(self) -> Character:
        name = self.player_var.get().strip() or "Player"
        character = Character(
            name=name,
            role="Player",
            category=self.character_category_var.get().strip() or "player",
            gender=self.character_gender_var.get().strip(),
            age=self.character_age_var.get().strip(),
            backstory=self.character_backstory_text.get("1.0", "end").strip(),
            personality=self.character_personality_text.get("1.0", "end").strip(),
            look=self.character_look_text.get("1.0", "end").strip(),
        )
        character.gold = _safe_int(self.character_gold_var.get(), 0)
        attributes = {
            "str": _clamp_int(self.character_str_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
            "dex": _clamp_int(self.character_dex_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
            "con": _clamp_int(self.character_con_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
            "int": _clamp_int(self.character_int_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
            "wis": _clamp_int(self.character_wis_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
            "cha": _clamp_int(self.character_cha_var.get(), CHARACTER_STAT_BASE, CHARACTER_STAT_BASE, CHARACTER_STAT_MAX),
        }
        fallback_traits = []
        fallback_skills = []
        if hasattr(self, "character_traits_text") and self.character_traits_text.winfo_exists():
            fallback_traits = _parse_character_traits(self.character_traits_text.get("1.0", "end"))
        if hasattr(self, "character_skills_text") and self.character_skills_text.winfo_exists():
            fallback_skills = _parse_character_skills(self.character_skills_text.get("1.0", "end"))
        character.traits = _character_trait_entries(self.character_trait_entries or fallback_traits)
        character.skills = _normalise_character_skills(self.character_skill_entries or fallback_skills)
        character.extra["ability"] = {"attributes": attributes}
        character.extra["attributes"] = attributes
        character.image_generation_prompt = _prompt_parts_from_look(character.look)
        existing = self.engine.state.world_data.character(name)
        if existing:
            character.image_paths.update(existing.image_paths)
            character.prompts.update(existing.prompts)
            if existing.extra.get("image_pipeline"):
                character.extra["image_pipeline"] = existing.extra.get("image_pipeline")
        if self.last_character_preview_path and self.last_character_preview_name == name:
            character.image_paths.setdefault("add_border_image", self.last_character_preview_path)
            character.image_paths.setdefault("generated_image", self.last_character_preview_path)
        if _subject_image_path(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
            character.flags.pop("portrait_generation_skipped", None)
            character.extra.pop("portrait_generation_skipped", None)
        else:
            character.flags["portrait_generation_skipped"] = True
            character.extra["portrait_generation_skipped"] = True
        return character

    def _generate_image(self) -> None:
        if not self._image_generation_enabled(show_status=True):
            return
        self._run_task(
            _ui_text(self.config_data, "task_generating_scene_image"),
            self.engine.generate_scene_image,
            lambda result: self._set_image(result.path),
        )

    def _generate_cg_image(self) -> None:
        self._hide_game_button_help()
        if not self._image_generation_enabled(show_status=True):
            return
        self._run_task(
            _ui_text(self.config_data, "task_generating_cg_image"),
            self.engine.generate_cg_image,
            lambda result: self._on_cg_image_generated(result.path),
        )

    def _generate_character_image(self) -> None:
        if not self._image_generation_enabled(show_status=True):
            return
        self._run_task(
            _ui_text(self.config_data, "task_generating_character_image"),
            self.engine.generate_character_image,
            lambda result: self._on_layer_image_generated(result.path),
        )

    def _generate_monster_image(self) -> None:
        if not self._image_generation_enabled(show_status=True):
            return
        self._run_task(
            _ui_text(self.config_data, "task_generating_monster_image"),
            self.engine.generate_monster_image,
            lambda result: self._on_layer_image_generated(result.path),
        )

    def _send_action(self) -> None:
        if self.current_task_id:
            return
        action = self.action_var.get()
        self.action_var.set("")
        self._dismiss_active_cg_for_player_input()
        self._run_task(
            _ui_text(self.config_data, "task_resolving_free_action"),
            lambda action=action: self.engine.resolve_action(action),
            self._set_log,
        )

    def _send_choice(self, choice: str) -> None:
        if self.current_task_id:
            return
        if self._maybe_open_explicit_subscreen_choice(choice):
            return
        self._dismiss_active_cg_for_player_input()
        self._run_task(
            _ui_text(self.config_data, "task_resolving_choice"),
            lambda: self.engine.resolve_choice(choice),
            self._set_log,
        )

    def _save_game(self) -> None:
        try:
            path = self.engine.save_game()
        except Exception as exc:
            self._show_error(exc)
            return
        self._append_log("\n" + _ui_text(self.config_data, "log_saved").format(path=path) + "\n")

    def _load_latest(self) -> None:
        try:
            text = self.engine.load_game()
        except Exception as exc:
            self._show_error(exc)
            return
        self.player_var.set(self.engine.state.player_name)
        self._set_log(text, animate=False)
        self._set_current_image_if_available()
        self._append_log(
            "\n"
            + _ui_text(self.config_data, "log_loaded").format(
                world=self.engine.state.world_name,
                player=self.engine.state.player_name,
            )
            + "\n"
        )

    def _import_world_dialog(self) -> None:
        filename = filedialog.askopenfilename(
            title=_ui_text(self.config_data, "dialog_import_world"),
            filetypes=[
                (_ui_text(self.config_data, "dialog_file_fantasia_worlds"), "*.zip *.fantasia-world *.json"),
                (_ui_text(self.config_data, "dialog_file_all"), "*.*"),
            ],
        )
        if not filename:
            return
        self._run_task(
            _ui_text(self.config_data, "task_importing_world"),
            lambda: self.save_store.import_world(Path(filename)),
            self._on_world_imported,
        )

    def _on_world_imported(self, result) -> None:
        self._refresh_world_select_screen()
        self._append_log(
            "\n"
            + _ui_text(self.config_data, "log_imported_world").format(
                world=result.world.world_name,
                path=result.path,
            )
            + "\n"
        )
        messagebox.showinfo(
            _ui_text(self.config_data, "dialog_import_world"),
            _ui_text(self.config_data, "dialog_imported_world").format(name=result.world.world_name),
        )

    def _export_world_dialog(self) -> None:
        world_name = self.engine.state.world_data.world_name or self.engine.state.world_name
        if not world_name or world_name == "unknown":
            self._show_error(ValueError(_ui_text(self.config_data, "dialog_no_current_world")))
            return
        filename = filedialog.asksaveasfilename(
            title=_ui_text(self.config_data, "dialog_export_world"),
            defaultextension=".zip",
            initialfile=f"{_safe_filename(world_name)}.fantasia-world.zip",
            filetypes=[
                (_ui_text(self.config_data, "dialog_file_world_package"), "*.zip"),
                (_ui_text(self.config_data, "dialog_file_world_json"), "*.json"),
                (_ui_text(self.config_data, "dialog_file_all"), "*.*"),
            ],
        )
        if not filename:
            return

        def work() -> Path:
            self.engine.save_game()
            return self.save_store.export_world(world_name, Path(filename))

        self._run_task(
            _ui_text(self.config_data, "task_exporting_world"),
            work,
            lambda path: self._append_log("\n" + _ui_text(self.config_data, "log_exported_world").format(path=path) + "\n"),
        )

    def _make_panel_text(
        self,
        parent: tk.Widget,
        title: str,
        row: int,
        height: int,
        expand: bool = False,
    ) -> tk.Text:
        panel = tk.Frame(parent, bg="#111722", padx=8, pady=8)
        panel.grid(row=row, column=0, sticky="nsew" if expand else "ew")
        panel.columnconfigure(0, weight=1)
        if expand:
            panel.rowconfigure(1, weight=1)

        tk.Label(
            panel,
            text=title,
            bg="#111722",
            fg="#f4d27a",
            anchor="w",
            font=self.ui_fonts.bold(-4),
        ).grid(row=0, column=0, sticky="ew")
        text = tk.Text(
            panel,
            height=height,
            wrap="word",
            bg="#0d1017",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            padx=8,
            pady=6,
            font=self.ui_fonts.normal(-4),
        )
        text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        text.configure(state="disabled")
        return text

    def _build_layer_controls(self, parent: tk.Widget, row: int) -> None:
        panel = tk.Frame(parent, bg="#111722", padx=8, pady=8)
        panel.grid(row=row, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)

        tk.Label(
            panel,
            text=_ui_text(self.config_data, "layers_title"),
            bg="#111722",
            fg="#f4d27a",
            anchor="w",
            font=self.ui_fonts.bold(-4),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(panel, text=_ui_text(self.config_data, "layers_background"), variable=self.layer_background_var, command=self._render_stage).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(panel, text=_ui_text(self.config_data, "layers_characters"), variable=self.layer_characters_var, command=self._render_stage).grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(panel, text=_ui_text(self.config_data, "layers_monsters"), variable=self.layer_monsters_var, command=self._render_stage).grid(row=2, column=0, sticky="w")

    def _replace_text(self, widget: tk.Text, text: str, *, scroll_to_end: bool = False) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        if scroll_to_end:
            self._scroll_text_to_end(widget)
        widget.configure(state="disabled")
        if scroll_to_end:
            self._scroll_text_to_end(widget)

    def _scroll_text_to_end(self, widget: tk.Text) -> None:
        widget.see("end")
        widget.yview_moveto(1.0)

        def scroll_after_layout(target: tk.Text = widget) -> None:
            try:
                if target.winfo_exists():
                    target.see("end")
                    target.yview_moveto(1.0)
            except tk.TclError:
                pass

        self.after_idle(scroll_after_layout)

    def _refresh_status_panel(self) -> None:
        state = self.engine.state
        world = state.world_data
        world_name = world.world_name if world.world_name != "unknown" else state.world_name
        location = self._display_location_name()
        active = state.active_quest or "None"
        mode = self._screen_mode()
        if mode != "battle":
            self.battle_choice_menu = ""
        quest_label = tr_enum("status_field", "quest", self.config_data.language)
        self.status_var.set(f"{world_name} / {location} / {quest_label}: {active}")
        self._refresh_mode_ui(mode)
        if hasattr(self, "mode_info_text"):
            self._replace_text(self.mode_info_text, self._mode_info_text(mode))
        if hasattr(self, "world_info_text"):
            self._replace_text(self.world_info_text, self._world_info_text())
        if hasattr(self, "party_text"):
            self._replace_text(self.party_text, self._party_info_text())
        if hasattr(self, "quest_text"):
            self._replace_text(self.quest_text, self._quest_info_text())
        if hasattr(self, "player_status_text"):
            self._replace_text(self.player_status_text, self._player_status_text())
        if hasattr(self, "info_canvas"):
            self._render_player_info_panel()
        if hasattr(self, "npc_roster_canvas"):
            self._render_actor_rosters()
        if hasattr(self, "subnode_map_btn"):
            try:
                has_subnodes = self.engine.has_current_subnode_map()
            except Exception:
                has_subnodes = False
            if has_subnodes:
                self.subnode_map_btn.grid()
            else:
                self.subnode_map_btn.grid_remove()

    def _screen_mode(self) -> str:
        if self.engine.state.flags.get("game_over"):
            return "game_over"
        active_encounter = self.engine.state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("status") != "ended":
            return "battle"
        active_conversation = self.engine.state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            return "conversation"
        return "exploration"

    def _refresh_mode_ui(self, mode: str) -> None:
        language = self.config_data.language
        name, bg, fg = _mode_display(mode, language)
        self.mode_name_var.set(name)
        self.choices_title_var.set(_mode_choices_title(mode, language))
        self.action_label_var.set(_mode_action_label(mode, language))
        if hasattr(self, "mode_badge"):
            self.mode_badge.configure(bg=bg, fg=fg)

    def _mode_info_text(self, mode: str) -> str:
        if mode == "game_over":
            return self._game_over_mode_text()
        if mode == "battle":
            return self._battle_mode_text()
        if mode == "conversation":
            return self._conversation_mode_text()
        return self._exploration_mode_text()

    def _game_over_mode_text(self) -> str:
        language = self.config_data.language
        label = lambda key: tr_enum("mode_info", key, language)
        info = self.engine.state.flags.get("game_over")
        if not isinstance(info, dict):
            return label("game_over")
        return "\n".join(
            [
                f"{label('state')}: {tr_enum('mode', 'game_over', language)}",
                f"{label('reason')}: {info.get('reason') or '-'}",
                f"{label('location')}: {info.get('location') or self.engine.state.current_location or '-'}",
                f"{label('turn')}: {info.get('turn', '-')}",
            ]
        )

    def _battle_mode_text(self) -> str:
        language = self.config_data.language
        label = lambda key: tr_enum("mode_info", key, language)
        encounter = self.engine.state.flags.get("active_encounter")
        if not isinstance(encounter, dict):
            return label("no_active_encounter")
        player_hp = encounter.get("player_hp", "?")
        player_sp = encounter.get("player_sp", "?")
        opponent_lines: list[str] = []
        for entry in self._battle_target_entries(encounter):
            name = str(entry.get("name") or tr_enum("roster", "unknown", language))
            hp = entry.get("hp", "?")
            max_hp = entry.get("max_hp")
            hp_text = f"{hp}/{max_hp}" if max_hp else str(hp)
            opponent_lines.append(f"{name} HP {hp_text}")
        if not opponent_lines:
            opponent_name = str(encounter.get("opponent_name") or tr_enum("roster", "unknown", language))
            opponent_lines.append(f"{opponent_name} HP {encounter.get('opponent_hp', '?')}")
        lines = [
            f"{label('state')}: {label('battle')}",
            f"{label('opponent')}: " + " / ".join(opponent_lines),
            f"HP: {label('player')} {player_hp}",
            f"SP: {label('player')} {player_sp}",
            f"{label('turn')}: {encounter.get('turn', 0)}",
        ]
        player_status = str(encounter.get("player_status") or "")
        opponent_status = str(encounter.get("opponent_status") or "")
        if player_status or opponent_status:
            lines.append(f"{label('status')}: {player_status or '-'} / {opponent_status or '-'}")
        return "\n".join(lines)

    def _conversation_mode_text(self) -> str:
        language = self.config_data.language
        label = lambda key: tr_enum("mode_info", key, language)
        active = self.engine.state.flags.get("active_conversation")
        if not isinstance(active, dict):
            return label("no_active_conversation")
        name = str(active.get("character") or tr_enum("roster", "unknown", language))
        character = self.engine.state.world_data.character(name)
        lines = [
            f"{label('state')}: {label('conversation')}",
            f"{label('speaker')}: {name}",
            f"{label('location')}: {active.get('location') or self.engine.state.current_location}",
        ]
        topic = str(active.get("topic") or "")
        if topic:
            lines.append(f"{label('topic')}: {topic}")
        if character:
            if character.role or character.category:
                lines.append(f"{label('role')}: {character.role or character.category}")
            relationship = character.extra.get("relationship")
            if relationship:
                lines.append(f"{label('relation')}: {relationship}")
        return "\n".join(lines)

    def _exploration_mode_text(self) -> str:
        language = self.config_data.language
        label = lambda key: tr_enum("mode_info", key, language)
        state = self.engine.state
        world = state.world_data
        lines = [
            f"{label('state')}: {label('exploration')}",
            f"{label('location')}: {state.current_location or world.starting_location}",
        ]
        if state.active_quest:
            lines.append(f"{label('active_quest')}: {state.active_quest}")
        elif world.quests:
            available = [quest.name for quest in world.quests if quest.status in {"available", ""}][:3]
            if available:
                lines.append(f"{label('available')}: " + ", ".join(available))
        if world.current_rumor:
            lines.append(f"{label('rumor')}: {world.current_rumor}")
        field_events = world.extra.get("field_events")
        if isinstance(field_events, list) and field_events:
            last = field_events[-1]
            if isinstance(last, dict):
                event_name = last.get("event") or last.get("discovered_location") or ""
                if event_name:
                    lines.append(f"{label('last_event')}: {event_name}")
        return "\n".join(lines)

    def _world_info_text(self) -> str:
        language = self.config_data.language
        label = lambda key: tr_enum("mode_info", key, language)
        state = self.engine.state
        world = state.world_data
        lines = [
            f"{label('world')}: {world.world_name}",
            f"{label('location')}: {state.current_location or world.starting_location}",
            f"{label('time')}: {self.engine.current_time_label()}",
        ]
        if world.current_rumor:
            lines.append(f"{label('rumor')}: {world.current_rumor}")
        if world.world_situation:
            lines.append(f"{label('situation')}: {world.world_situation}")
        return "\n".join(lines)

    def _party_info_text(self) -> str:
        language = self.config_data.language
        characters = list(self.engine.state.world_data.characters.values())[:8]
        if not characters:
            return tr_enum("mode_info", "no_cast", language)
        lines = []
        for character in characters:
            role = self._character_roster_subtitle(character, fallback="npc")
            lines.append(f"- {character.name} / {role}")
        return "\n".join(lines)

    def _quest_info_text(self) -> str:
        quests = self.engine.state.world_data.quests[:8]
        if not quests:
            return "No quests yet."
        lines = []
        for quest in quests:
            remaining = ""
            if quest.status == "active":
                hours = self.engine._quest_remaining_hours(quest)
                if hours is not None:
                    remaining = f" / {hours}h"
            lines.append(f"- {quest.name} [{quest.status}]{remaining}")
        return "\n".join(lines)

    def _latest_stage_text(self) -> str:
        lines = [line for line in self.engine.state.display_log if line.strip()]
        for line in reversed(lines):
            if line.startswith(">") or line.startswith("["):
                continue
            return line
        return "New でAI RPGを開始します。"

    def _render_stage(self) -> None:
        if not hasattr(self, "stage_canvas"):
            return
        canvas = self.stage_canvas
        canvas.delete("all")
        self.stage_image_refs = []
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_rectangle(0, 0, width, height, fill="#080a10", outline="")

        actor_bottom = max(80, height - 16)

        cg_image = self._active_cg_image()
        if cg_image is not None:
            display = _cover_image(cg_image, width, height)
            self._draw_photo(canvas, display, 0, 0, anchor="nw")
            return

        background = self._current_background_image()
        if self.layer_background_var.get() and background is not None:
            display = _cover_image(background, width, height)
            self._draw_photo(canvas, display, 0, 0, anchor="nw")
        else:
            canvas.create_text(
                width // 2,
                height // 2,
                text="No background",
                fill="#596070",
                font=self.ui_fonts.bold(10),
            )

        if self.layer_characters_var.get():
            for index, character in enumerate(self._stage_character_layers()):
                image = self._load_layer_image(character[1])
                if image is None:
                    continue
                display = _fit_subject_image(image, max(96, int(width * 0.28)), max(120, int(actor_bottom * 0.86)))
                x_positions = [int(width * 0.28), int(width * 0.43), int(width * 0.16)]
                x = x_positions[min(index, len(x_positions) - 1)]
                y = actor_bottom + 8
                self._draw_photo(canvas, display, x, y, anchor="s")
                self._draw_layer_label(canvas, character[0], x, y - display.height - 8)

        if self.layer_monsters_var.get():
            for index, monster in enumerate(self._stage_monster_layers()):
                image = self._load_layer_image(monster[1])
                if image is None:
                    continue
                display = _fit_subject_image(image, max(96, int(width * 0.3)), max(120, int(actor_bottom * 0.82)))
                x_positions = [int(width * 0.72), int(width * 0.86)]
                x = x_positions[min(index, len(x_positions) - 1)]
                y = actor_bottom + 10
                self._draw_photo(canvas, display, x, y, anchor="s")
                self._draw_layer_label(canvas, monster[0], x, y - display.height - 8)

    def _current_background_image(self) -> Image.Image | None:
        state = self.engine.state
        active_path = str(state.flags.get("active_background_image_path") or "")
        if active_path:
            image = self._load_layer_image(active_path)
            if image is not None:
                return image
        location = state.world_data.locations.get(state.current_location)
        if location:
            image = self._load_layer_image(location.image_path)
            if image is not None:
                return image
        return None

    def _active_cg_image(self) -> Image.Image | None:
        path_text = str(self.engine.state.flags.get("active_cg_image_path") or "")
        if not path_text:
            return None
        return self._load_layer_image(path_text)

    def _stage_actor_identity(self, character: Character) -> str:
        return str(character.uuid or character.name or "").strip()

    def _stage_actor_is_monster(self, character: Character) -> bool:
        flags = character.flags if isinstance(character.flags, dict) else {}
        category = str(character.category or "").strip()
        return bool(flags.get("enemy_npc") or flags.get("hostile") or category in {"enemy_npc", "wild_encounter"})

    def _stage_character_layers(self) -> list[tuple[str, str]]:
        state = self.engine.state
        characters: list[Character] = []
        excluded_refs: set[str] = set()
        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("status") != "ended":
            for entry in self._battle_target_entries(active_encounter):
                name = str(entry.get("name") or "").strip()
                uuid = str(entry.get("uuid") or "").strip()
                character = entry.get("character")
                if isinstance(character, Character):
                    name = character.name or name
                    uuid = str(character.uuid or uuid)
                if name:
                    excluded_refs.add(name)
                if uuid:
                    excluded_refs.add(uuid)

        seen_refs: set[str] = set()
        current_location = self._current_location_name()

        def add_stage_character(character: Character | None, *, require_present: bool = True) -> None:
            if character is None or character.flags.get("is_player"):
                return
            identity = self._stage_actor_identity(character)
            if not identity or identity in seen_refs:
                return
            if character.name in excluded_refs or identity in excluded_refs:
                return
            if self._stage_actor_is_monster(character):
                return
            if require_present and not self._character_is_present_at(character, current_location):
                return
            seen_refs.add(identity)
            seen_refs.add(character.name)
            characters.append(character)

        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            conversation_name = str(active_conversation.get("character") or "")
            conversation_uuid = str(active_conversation.get("character_uuid") or active_conversation.get("uuid") or "")
            add_stage_character(self._world_character_by_uuid_or_non_player_name(conversation_uuid, conversation_name), require_present=False)
        for character in state.world_data.characters.values():
            add_stage_character(character)
            if len(characters) >= 3:
                break

        layers: list[tuple[str, str]] = []
        for character in characters:
            image_path = _subject_image_path(character.image_paths, ("no_bg_image", "add_border_image", "generated_image", "face_image"))
            if image_path:
                layers.append((character.name, image_path))
            if len(layers) >= 3:
                break
        return layers

    def _stage_monster_layers(self) -> list[tuple[str, str]]:
        state = self.engine.state
        monsters: list[Character] = []
        seen_refs: set[str] = set()
        current_location = self._current_location_name()

        def add_stage_monster(character: Character | None, *, force: bool = False, require_present: bool = True) -> None:
            if character is None or character.flags.get("is_player"):
                return
            identity = self._stage_actor_identity(character)
            if not identity or identity in seen_refs:
                return
            if not force and not self._stage_actor_is_monster(character):
                return
            if require_present and not self._character_is_present_at(character, current_location):
                return
            seen_refs.add(identity)
            seen_refs.add(character.name)
            monsters.append(character)

        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict):
            for entry in self._battle_target_entries(active_encounter):
                character = entry.get("character")
                if not isinstance(character, Character):
                    character = self._world_character_by_uuid_or_non_player_name(str(entry.get("uuid") or ""), str(entry.get("name") or ""))
                add_stage_monster(character, force=True, require_present=False)
        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            conversation_name = str(active_conversation.get("character") or "")
            conversation_uuid = str(active_conversation.get("character_uuid") or active_conversation.get("uuid") or "")
            add_stage_monster(self._world_character_by_uuid_or_non_player_name(conversation_uuid, conversation_name), require_present=False)
        for character in state.world_data.characters.values():
            add_stage_monster(character)
            if len(monsters) >= 2:
                break

        layers: list[tuple[str, str]] = []
        for monster in monsters:
            image_path = _subject_image_path(monster.image_paths, ("no_bg_image", "add_border_image", "base_image", "generated_image", "face_image"))
            if image_path:
                layers.append((monster.name, image_path))
            if len(layers) >= 2:
                break
        return layers

    def _load_layer_image(self, path_text: str) -> Image.Image | None:
        if not path_text:
            return None
        path = Path(path_text)
        if not path.is_file():
            return None
        key = str(path.resolve())
        cached = self.image_cache.get(key)
        if cached is not None:
            return cached
        try:
            image = Image.open(path).convert("RGBA")
        except OSError:
            return None
        self.image_cache[key] = image
        return image

    def _draw_photo(self, canvas: tk.Canvas, image: Image.Image, x: int, y: int, anchor: str) -> None:
        photo = ImageTk.PhotoImage(image)
        self.stage_image_refs.append(photo)
        self.stage_image = photo
        canvas.create_image(x, y, image=photo, anchor=anchor)

    def _draw_layer_label(self, canvas: tk.Canvas, text: str, x: int, y: int) -> None:
        if not text:
            return
        y = max(22, y)
        canvas.create_text(
            x,
            y,
            text=text,
            fill="#f2f5fb",
            anchor="center",
            font=self.ui_fonts.normal(-5),
        )

    def _run_task(
        self,
        status: str,
        work,
        done,
        *,
        initial_status: str | None = None,
        auto_status: bool = True,
        log_animation: bool = True,
    ) -> None:
        if self.current_task_id:
            return
        self.task_sequence_id += 1
        task_id = self.task_sequence_id
        self.current_task_id = task_id
        self.current_task_name = status
        self.current_task_started_at = time.time()
        self.current_task_cancel_requested = False
        self.current_task_auto_status = auto_status
        self.current_task_log_animation_enabled = log_animation
        self._set_buttons(False)
        if hasattr(self, "cancel_task_btn"):
            self.cancel_task_btn.configure(state="normal")
        if hasattr(self, "task_progress") and self.current_screen_name != "game":
            self.task_progress.start(14)
        if auto_status:
            self._set_task_status(_ui_text(self.config_data, "task_generating_status").format(name=status, elapsed=0))
        else:
            self._set_task_status(initial_status or status)
        if log_animation:
            self._start_task_log_animation(status)
        self._record_task_event("started", status, message=_ui_text(self.config_data, "task_started"))
        self._schedule_task_tick()
        self._schedule_world_generation_progress_poll()

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                trace = traceback.format_exc()
                self.after(0, lambda exc=exc, trace=trace: self._finish_task_error(task_id, status, exc, trace))
            else:
                self.after(0, lambda result=result: self._finish_task_success(task_id, status, result, done))

        threading.Thread(target=runner, daemon=True).start()

    def _run_visual_task(self, status: str, work, done) -> None:
        if self.current_task_id or self.visual_task_id:
            return
        self.visual_task_sequence_id += 1
        task_id = self.visual_task_sequence_id
        self.visual_task_id = task_id
        self.visual_task_name = status
        self.visual_task_started_at = time.time()
        self._record_visual_task_event("started", status, message=_ui_text(self.config_data, "task_started"))

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                trace = traceback.format_exc()
                self.after(0, lambda exc=exc, trace=trace: self._finish_visual_task_error(task_id, status, exc, trace))
            else:
                self.after(0, lambda result=result: self._finish_visual_task_success(task_id, status, result, done))

        threading.Thread(target=runner, daemon=True).start()

    def _finish_visual_task_success(self, task_id: int, status: str, result, done) -> None:
        if task_id != self.visual_task_id:
            return
        try:
            done(result)
        except Exception as exc:
            self._finish_visual_task_error(task_id, status, exc, traceback.format_exc())
            return
        self._record_visual_task_event(
            "completed",
            status,
            message=_task_result_message(result, self.config_data.language) or _ui_text(self.config_data, "task_completed"),
        )
        self._end_visual_task()
        self._schedule_visual_updates()

    def _finish_visual_task_error(self, task_id: int, status: str, exc: Exception, trace: str) -> None:
        if task_id != self.visual_task_id:
            return
        self._record_visual_task_event(
            "failed",
            status,
            message=_ui_text(self.config_data, "task_failed_detail"),
            error=str(exc),
            traceback_text=trace,
        )
        self._end_visual_task()

    def _end_visual_task(self) -> None:
        self.visual_task_id = 0
        self.visual_task_name = ""
        self.visual_task_started_at = 0.0

    def _finish_task_success(self, task_id: int, status: str, result, done) -> None:
        if task_id != self.current_task_id:
            return
        self._drain_world_generation_progress_queue()
        if self.current_task_cancel_requested:
            self._record_task_event("cancelled", status, message=_ui_text(self.config_data, "task_result_ignored_after_cancel"))
            self._end_task(clear_status=True)
            return
        try:
            done(result)
        except Exception as exc:
            self._finish_task_error(task_id, status, exc, traceback.format_exc())
            return
        self._record_task_event(
            "completed",
            status,
            message=_task_result_message(result, self.config_data.language) or _ui_text(self.config_data, "task_completed"),
        )
        self._end_task(clear_status=True)
        self._schedule_visual_updates()

    def _finish_task_error(self, task_id: int, status: str, exc: Exception, trace: str) -> None:
        if task_id != self.current_task_id:
            return
        self._drain_world_generation_progress_queue()
        if self.current_task_cancel_requested:
            self._record_task_event(
                "cancelled",
                status,
                message=_ui_text(self.config_data, "task_was_cancelled"),
                error=str(exc),
                traceback_text=trace,
            )
            self._end_task(clear_status=True)
            return
        self._record_task_event(
            "failed",
            status,
            message=_ui_text(self.config_data, "task_failed_detail"),
            error=str(exc),
            traceback_text=trace,
        )
        self._end_task(clear_status=False)
        self._set_task_status(_ui_text(self.config_data, "task_failed_status"))
        if hasattr(self, "log_text") and self.current_screen_name == "game":
            self._append_log("\n" + _ui_text(self.config_data, "task_generation_failed_log") + "\n")
        messagebox.showerror(_ui_text(self.config_data, "dialog_error_title"), _ui_text(self.config_data, "dialog_generation_failed"))

    def _cancel_current_task(self) -> None:
        if not self.current_task_id:
            return
        status = self.current_task_name or "Task"
        self.current_task_cancel_requested = True
        self._set_task_status(_ui_text(self.config_data, "task_canceling_status").format(name=status))
        if hasattr(self, "cancel_task_btn"):
            self.cancel_task_btn.configure(state="disabled")
        self._record_task_event("cancel_requested", status, message=_ui_text(self.config_data, "task_cancel_requested"))
        try:
            self.engine.cancel_current_task()
        except Exception as exc:
            self._record_task_event(
                "cancel_error",
                status,
                message=_ui_text(self.config_data, "task_cancel_error"),
                error=str(exc),
                traceback_text=traceback.format_exc(),
            )

    def _schedule_task_tick(self) -> None:
        if self.task_tick_after_id:
            try:
                self.after_cancel(self.task_tick_after_id)
            except tk.TclError:
                pass
        self.task_tick_after_id = self.after(1000, self._update_task_tick)

    def _update_task_tick(self) -> None:
        self.task_tick_after_id = None
        if not self.current_task_id or self.current_task_cancel_requested:
            return
        elapsed = max(0, int(time.time() - self.current_task_started_at))
        if self.current_task_auto_status:
            self._set_task_status(_ui_text(self.config_data, "task_generating_status").format(name=self.current_task_name, elapsed=elapsed))
        if self.current_task_log_animation_enabled:
            self._render_task_log_animation()
        self._schedule_task_tick()

    def _end_task(self, clear_status: bool) -> None:
        if self.task_tick_after_id:
            try:
                self.after_cancel(self.task_tick_after_id)
            except tk.TclError:
                pass
        self.task_tick_after_id = None
        if self.world_generation_progress_after_id:
            try:
                self.after_cancel(self.world_generation_progress_after_id)
            except tk.TclError:
                pass
        self.world_generation_progress_after_id = None
        self._drain_world_generation_progress_queue()
        if hasattr(self, "task_progress"):
            self.task_progress.stop()
        if hasattr(self, "cancel_task_btn"):
            self.cancel_task_btn.configure(state="disabled")
        self._clear_task_log_animation()
        self.current_task_id = 0
        self.current_task_name = ""
        self.current_task_started_at = 0.0
        self.current_task_cancel_requested = False
        self.current_task_auto_status = True
        self.current_task_log_animation_enabled = True
        self._set_buttons(True)
        if clear_status:
            self._set_task_status("")

    def _set_task_status(self, text: str) -> None:
        self.task_status_var.set(text)

    def _start_task_log_animation(self, status: str) -> None:
        if self.current_screen_name != "game" or not hasattr(self, "log_text"):
            return
        self._cancel_typewriter()
        self.task_log_animation_base_text = self.log_text.get("1.0", "end-1c")
        self.task_log_animation_last_text = ""
        self.task_log_animation_frame = 0
        self._render_task_log_animation()

    def _render_task_log_animation(self) -> None:
        if self.current_screen_name != "game" or not hasattr(self, "log_text"):
            return
        if not self.current_task_id:
            return
        dots = "・" * (self.task_log_animation_frame % 3 + 1)
        self.task_log_animation_frame += 1
        base = self.task_log_animation_base_text.rstrip()
        line = f"{_ui_text(self.config_data, 'game_generating')}{dots}"
        text = f"{base}\n{line}" if base else line
        self.task_log_animation_last_text = text
        self._replace_text(self.log_text, text, scroll_to_end=True)

    def _clear_task_log_animation(self) -> None:
        if not hasattr(self, "log_text") or not self.task_log_animation_last_text:
            self.task_log_animation_base_text = ""
            self.task_log_animation_last_text = ""
            self.task_log_animation_frame = 0
            return
        try:
            current = self.log_text.get("1.0", "end-1c")
        except tk.TclError:
            current = ""
        if current == self.task_log_animation_last_text:
            self._replace_text(self.log_text, self.task_log_animation_base_text, scroll_to_end=True)
        self.task_log_animation_base_text = ""
        self.task_log_animation_last_text = ""
        self.task_log_animation_frame = 0

    def _record_task_event(
        self,
        status: str,
        name: str,
        message: str = "",
        error: str = "",
        traceback_text: str = "",
    ) -> None:
        append_task_event(
            LOG_DIR,
            {
                "status": status,
                "name": name,
                "message": message,
                "error": error,
                "traceback": traceback_text,
                "world_name": self.engine.state.world_name,
                "player_name": self.engine.state.player_name,
                "elapsed_sec": int(time.time() - self.current_task_started_at) if self.current_task_started_at else 0,
            },
        )
        if hasattr(self, "generation_log_listbox"):
            self._refresh_generation_log_screen()

    def _record_visual_task_event(
        self,
        status: str,
        name: str,
        message: str = "",
        error: str = "",
        traceback_text: str = "",
    ) -> None:
        append_task_event(
            LOG_DIR,
            {
                "status": status,
                "name": name,
                "message": message,
                "error": error,
                "traceback": traceback_text,
                "world_name": self.engine.state.world_name,
                "player_name": self.engine.state.player_name,
                "elapsed_sec": int(time.time() - self.visual_task_started_at) if self.visual_task_started_at else 0,
                "background": True,
            },
        )
        if hasattr(self, "generation_log_listbox"):
            self._refresh_generation_log_screen()

    def _set_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.task_buttons:
            button.configure(state=state)
        self.action_entry.configure(state=state)
        for button in self.choice_buttons:
            button.configure(state=state)

    def _set_log(self, text: str, *, animate: bool = True) -> None:
        if animate:
            self._set_log_text_with_typewriter(text)
        else:
            self._cancel_typewriter()
            self.log_typewriter_base_text = text
            self._replace_text(self.log_text, text, scroll_to_end=True)
        self._refresh_choices()
        self._refresh_status_panel()
        self._render_stage()
        self._schedule_visual_updates()
        if self.engine.state.flags.get("pending_home_menu"):
            self.after(0, self._open_pending_home_menu)
        if self.engine.state.flags.pop("return_to_title", False):
            self.after(0, lambda: self._show_screen("title"))

    def _append_log(self, text: str) -> None:
        self._cancel_typewriter()
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self._scroll_text_to_end(self.log_text)
        self.log_text.configure(state="disabled")
        self._refresh_status_panel()
        self._render_stage()
        self._schedule_visual_updates()

    def _set_log_text_with_typewriter(self, text: str) -> None:
        self._cancel_typewriter()
        speed = float(self.config_data.ui_setting.get("text_speed", 0.02))
        current = self.log_text.get("1.0", "end-1c") if hasattr(self, "log_text") else ""
        prefix_len = max(
            _typewriter_stable_prefix_length(current, text),
            _typewriter_stable_prefix_length(self.log_typewriter_base_text, text),
        )
        self.log_typewriter_base_text = text
        should_type = (
            speed > 0
            and len(text) > prefix_len
            and len(text) - prefix_len <= 3000
        )
        if not should_type:
            self._replace_text(self.log_text, text, scroll_to_end=True)
            return

        self.typewriter_target_text = text
        self.typewriter_index = prefix_len
        self._replace_text(self.log_text, text[:prefix_len], scroll_to_end=True)
        self._advance_typewriter()

    def _advance_typewriter(self) -> None:
        if self.typewriter_index >= len(self.typewriter_target_text):
            self.typewriter_after_id = None
            return
        char = self.typewriter_target_text[self.typewriter_index]
        self.typewriter_index += 1
        self.log_text.configure(state="normal")
        self.log_text.insert("end", char)
        self._scroll_text_to_end(self.log_text)
        self.log_text.configure(state="disabled")
        delay = max(1, int(float(self.config_data.ui_setting.get("text_speed", 0.02)) * 1000))
        self.typewriter_after_id = self.after(delay, self._advance_typewriter)

    def _cancel_typewriter(self) -> None:
        if self.typewriter_after_id:
            try:
                self.after_cancel(self.typewriter_after_id)
            except tk.TclError:
                pass
        self.typewriter_after_id = None
        if self.typewriter_target_text and self.typewriter_index < len(self.typewriter_target_text):
            self._replace_text(self.log_text, self.typewriter_target_text, scroll_to_end=True)
        self.typewriter_target_text = ""
        self.typewriter_index = 0

    def _set_image(self, path: Path) -> None:
        self.image_cache.clear()
        try:
            self.stage_source_image = Image.open(path).convert("RGBA")
        except OSError:
            self.stage_source_image = None
        self._render_stage()

    def _on_layer_image_generated(self, path: Path) -> None:
        self.image_cache.clear()
        self._refresh_status_panel()
        self._render_stage()

    def _on_auto_player_image_generated(self, path: Path, player_key: str, player_name: str) -> None:
        player = self.engine.player_character()
        if player and (not player_key or player_key in {str(player.uuid or ""), player.name}):
            player.flags.pop("portrait_generation_skipped", None)
            player.extra.pop("portrait_generation_skipped", None)
            image_path = str(path)
            player.image_paths.setdefault("add_border_image", image_path)
            player.image_paths.setdefault("generated_image", image_path)
            self.engine.state.flags["player_character"] = player.to_dict()
        self.engine.state.flags["auto_player_image_generation"] = {
            "key": player_key,
            "name": player_name,
            "status": "completed",
            "path": str(path),
        }
        self._on_layer_image_generated(path)

    def _on_scene_image_generated(self, path: Path) -> None:
        self.engine.state.flags.pop("pending_background_location", None)
        self.engine.state.flags.pop("pending_background_context", None)
        self.image_cache.clear()
        self.stage_source_image = None
        self._refresh_status_panel()
        self._render_stage()

    def _on_cg_image_generated(self, path: Path) -> None:
        self.image_cache.clear()
        self.stage_source_image = None
        self._refresh_status_panel()
        self._render_stage()

    def _dismiss_active_cg_for_player_input(self) -> None:
        if self.engine.dismiss_active_cg():
            self.image_cache.clear()
            self.stage_source_image = None
            self._render_stage()

    def _schedule_visual_updates(self) -> None:
        if not self._image_generation_enabled():
            return
        if self.visual_task_after_id:
            try:
                self.after_cancel(self.visual_task_after_id)
            except tk.TclError:
                pass
        self.visual_task_after_id = self.after(160, self._maybe_auto_generate_visuals)

    def _maybe_auto_generate_visuals(self) -> None:
        self.visual_task_after_id = None
        if self.current_task_id or self.visual_task_id or self.current_screen_name != "game":
            return
        state = self.engine.state
        if not self._image_generation_enabled():
            state.flags.pop("pending_cg_request", None)
            state.flags.pop("pending_background_location", None)
            state.flags.pop("pending_background_context", None)
            return
        if state.world_data.world_name == "unknown":
            return
        state.flags.pop("pending_cg_request", None)

        current_location = self._current_location_name()
        pending_background = str(state.flags.get("pending_background_location") or "")
        pending_context = state.flags.get("pending_background_context")
        location_data = state.world_data.locations.get(current_location)
        active_background_path = str(state.flags.get("active_background_image_path") or "")
        active_background_exists = bool(active_background_path and Path(active_background_path).is_file())
        if (
            isinstance(pending_context, dict)
            or pending_background == current_location
            or (not active_background_exists and location_data is not None and not location_data.image_path)
        ):
            self._run_visual_task(
                _ui_text(self.config_data, "task_generating_scene_image"),
                self.engine.generate_scene_image,
                lambda result: self._on_scene_image_generated(result.path),
            )
            return

        encounter = state.flags.get("active_encounter")
        if isinstance(encounter, dict) and encounter.get("status") != "ended":
            missing_character: Character | None = None
            for entry in self._battle_target_entries(encounter):
                character = entry.get("character")
                if isinstance(character, Character) and not _subject_image_path(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
                    missing_character = character
                    break
            if missing_character is not None:
                missing_ref = str(missing_character.uuid or missing_character.name)
                self._run_visual_task(
                    _ui_text(self.config_data, "task_generating_character_image"),
                    lambda ref=missing_ref: self.engine.generate_character_image(ref),
                    lambda result: self._on_layer_image_generated(result.path),
                )
                return

        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            name = str(active_conversation.get("character") or "")
            uuid = str(active_conversation.get("character_uuid") or active_conversation.get("uuid") or "")
            character = state.world_data.character(uuid or name)
            if character and not _subject_image_path(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
                ref = str(character.uuid or uuid or name)
                self._run_visual_task(
                    _ui_text(self.config_data, "task_generating_character_image"),
                    lambda ref=ref: self.engine.generate_character_image(ref),
                    lambda result: self._on_layer_image_generated(result.path),
                )
                return

        player = self.engine.player_character()
        if player and not _subject_image_path(player.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
            if player.flags.get("portrait_generation_skipped") or player.extra.get("portrait_generation_skipped"):
                return
            player_key = str(player.uuid or state.player_uuid or state.player_name or player.name)
            player_image_request = state.flags.get("auto_player_image_generation")
            if (
                isinstance(player_image_request, dict)
                and str(player_image_request.get("key") or "") == player_key
                and str(player_image_request.get("status") or "") in {"pending", "completed"}
            ):
                return
            state.flags["auto_player_image_generation"] = {
                "key": player_key,
                "name": player.name,
                "status": "pending",
            }
            self._run_visual_task(
                _ui_text(self.config_data, "task_generating_player_image"),
                lambda ref=player_key: self.engine.generate_character_image(ref),
                lambda result, ref=player_key, name=player.name: self._on_auto_player_image_generated(result.path, ref, name),
            )

    def _battle_target_entries(self, encounter: dict[str, object]) -> list[dict[str, object]]:
        raw_opponents = encounter.get("opponents")
        entries = [entry for entry in raw_opponents if isinstance(entry, dict)] if isinstance(raw_opponents, list) else []
        if not entries:
            entries = [
                {
                    "name": encounter.get("opponent_name"),
                    "uuid": encounter.get("opponent_uuid"),
                    "status": encounter.get("opponent_status"),
                    "opponent_hp": encounter.get("opponent_hp"),
                    "opponent_max_hp": encounter.get("opponent_max_hp"),
                }
            ]
        result: list[dict[str, object]] = []
        state = self.engine.state
        for entry in entries[:3]:
            name = str(entry.get("name") or "").strip()
            uuid = str(entry.get("uuid") or "").strip()
            character = state.world_data.character(uuid or name)
            hp = entry.get("opponent_hp")
            max_hp = entry.get("opponent_max_hp")
            status = str(entry.get("status") or "").strip().lower()
            if character is not None:
                name = character.name
                hp = character.current_hp
                max_hp = character.max_hp
                if str(character.state or "").strip().lower() in {"dead", "corpse", "killed"}:
                    status = "defeated"
            if not name:
                continue
            if status in {"defeated", "dead", "corpse", "gone"}:
                continue
            if hp is not None and _safe_int(hp, 0) <= 0:
                continue
            result.append({"name": name, "uuid": uuid, "hp": hp, "max_hp": max_hp, "character": character})
        return result

    def _battle_target_names(self, encounter: dict[str, object]) -> list[str]:
        names = [str(entry.get("name") or "").strip() for entry in self._battle_target_entries(encounter)]
        names = [name for name in names if name]
        if names:
            return names[:3]
        fallback = str(encounter.get("opponent_name") or "敵").strip()
        return [fallback or "敵"]

    def _handle_battle_menu_choice(self, choice: str) -> bool:
        return False

    def _battle_menu_choices(self) -> list[str]:
        encounter = self.engine.state.flags.get("active_encounter")
        if not isinstance(encounter, dict) or encounter.get("status") == "ended":
            return [choice for choice in self.engine.state.choices if choice.strip()]
        choices = [choice for choice in self.engine.state.choices if str(choice).strip()]
        return choices or ["攻撃対象選択", "スキル一覧", "逃走する"]

    def _player_battle_skills(self) -> list[dict[str, object]]:
        player = self._player_character_dict()
        raw_skills = player.get("skills")
        skills: list[dict[str, object]] = []
        if isinstance(raw_skills, list):
            for raw in raw_skills:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or raw.get("skill") or "").strip()
                if not name:
                    continue
                effect_types = _skill_effect_type_list(raw.get("type"))
                if not effect_types:
                    continue
                cost = max(1, min(12, _safe_int(raw.get("usesp"), 1)))
                skills.append({**raw, "name": name, "usesp": cost, "type": [{"type": item} for item in effect_types]})
        return skills

    def _battle_free_actions(self, encounter: dict[str, object]) -> list[str]:
        choices = [choice for choice in self.engine.state.choices if choice.strip() and choice not in {"攻撃", "スキル", "行動", "逃走"}]
        blocked = ("攻撃", "スキル:", "skill:")
        actions = [choice for choice in choices if not any(choice.startswith(prefix) for prefix in blocked)]
        if actions:
            return actions[:4]
        opponent = str(encounter.get("opponent_name") or "敵")
        return ["防御する", f"{opponent}の様子を見る", "距離を取る", "交渉を試みる"]

    def _refresh_choices(self) -> None:
        for child in self.choice_frame.winfo_children():
            child.destroy()
        self.choice_buttons = []

        mode = self._screen_mode()
        if mode == "battle":
            choices = self._battle_menu_choices()
        else:
            choices = [choice for choice in self.engine.state.choices if choice.strip()]
            choices = [choice for choice in choices if not _is_invalid_runtime_control_choice_text(choice)]
            if mode == "exploration":
                if self.engine.is_current_location_guild() and not self.engine.state.active_quest:
                    choices = [choice for choice in choices if not _is_direct_quest_accept_choice_text(choice)]
                if self.engine.is_current_location_guild() and not self.engine.state.active_quest:
                    choices.insert(0, _ui_text(self.config_data, "choice_quest_board"))
                if self.engine.has_movement_options():
                    move_choice = _ui_text(self.config_data, "choice_move")
                    if move_choice not in choices:
                        quest_control_choices = {
                            _ui_text(self.config_data, "choice_quest_board"),
                            "依頼掲示板を確認する",
                            "依頼達成を報告する",
                            "現在の依頼を放棄する",
                        }
                        insert_at = 0
                        while insert_at < len(choices) and str(choices[insert_at]).strip() in quest_control_choices:
                            insert_at += 1
                        choices.insert(insert_at, move_choice)
            if mode in {"exploration", "conversation"} and self._trade_target_character() is not None:
                trade_choice = _ui_text(self.config_data, "game_trade")
                if trade_choice not in choices:
                    insert_at = 2 if mode == "exploration" else len(choices)
                    choices.insert(min(insert_at, len(choices)), trade_choice)
            if mode == "exploration":
                choices = self.engine.format_contextual_choices(choices)
                self.engine.state.choices = choices
        if not choices:
            tk.Label(
                self.choice_frame,
                text=_empty_choices_text(mode, self.config_data.language),
                bg=APP_DEEP_BG,
                fg="#596070",
                anchor="center",
                font=self.ui_fonts.bold(-2),
            ).grid(row=0, column=0, sticky="nsew", pady=10)
            return

        for index, choice in enumerate(choices):
            border = tk.Frame(self.choice_frame, bg=APP_BUTTON_BORDER)
            border.grid(row=index, column=0, sticky="ew", pady=(0, 16 if index < len(choices) - 1 else 0))
            border.columnconfigure(0, weight=1)
            button = tk.Button(
                border,
                text=choice,
                command=lambda selected=choice: self._send_choice(selected),
                bg=APP_PANEL_BG,
                fg="#f2f5fb",
                activebackground=APP_PANEL_ACTIVE_BG,
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=10,
                pady=12,
                anchor="center",
                wraplength=260,
                font=self.ui_fonts.bold(-2),
            )
            button.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
            self.choice_buttons.append(button)

    def _show_error(self, exc: Exception) -> None:
        messagebox.showerror(_ui_text(self.config_data, "dialog_error_title"), str(exc))
        self._append_log("\n" + _ui_text(self.config_data, "log_error").format(error=exc) + "\n")

    def _on_close(self) -> None:
        if self.current_task_id:
            self._cancel_current_task()
        self._cancel_typewriter()
        if self.task_tick_after_id:
            try:
                self.after_cancel(self.task_tick_after_id)
            except tk.TclError:
                pass
        if self.visual_task_after_id:
            try:
                self.after_cancel(self.visual_task_after_id)
            except tk.TclError:
                pass
        self.engine.stop()
        self.destroy()


def main() -> None:
    configure_stdio_encoding()
    install_crash_logging()
    if "--check-encoding" in sys.argv:
        run_encoding_check()
        return
    if "--check-assets" in sys.argv:
        run_asset_check()
        return
    if "--save-smoke-test" in sys.argv:
        run_save_smoke_test()
        return
    if "--import-world" in sys.argv:
        run_import_world_cli()
        return
    if "--export-world" in sys.argv:
        run_export_world_cli()
        return
    if "--world-import-export-smoke" in sys.argv:
        run_world_import_export_smoke()
        return
    if "--smoke-test" in sys.argv:
        run_smoke_test()
        return
    app = FantasiaApp()
    app.mainloop()


def run_encoding_check() -> None:
    checks = check_project_encoding(include_generated="--include-generated" in sys.argv)
    print(format_encoding_report(checks))
    if any(not check.ok for check in checks):
        raise SystemExit(1)


def run_smoke_test() -> None:
    config_data = load_config()
    engine = GameEngine(
        create_llm_backend(config_data),
        create_image_backend(config_data),
        JsonStore(),
        SaveStore(),
        PromptTemplateStore(resolve_prompt_template_dir(config_data.prompt_template_path)),
        allow_any_action_concept=config_data.allow_any_action_concept,
        reveal_world_map_on_generation=config_data.reveal_world_map_on_generation,
        debug_free_location_travel=config_data.debug_free_location_travel,
        debug_disable_movement_time_passage=config_data.debug_disable_movement_time_passage,
        debug_disable_dungeon_random_encounters=config_data.debug_disable_dungeon_random_encounters,
    )
    try:
        print(engine.create_world("SmokeTest", "静かな森と古い遺跡"))
        image = engine.generate_scene_image()
        print(f"image={image.path}")
        print(engine.resolve_action("周囲を見る"))
    finally:
        engine.stop()


def run_save_smoke_test() -> None:
    config_data = load_config()
    engine = GameEngine(
        FixtureLlmBackend(),
        MockSdxlBackend(config_data),
        JsonStore(),
        SaveStore(),
        PromptTemplateStore(resolve_prompt_template_dir(config_data.prompt_template_path)),
        allow_any_action_concept=config_data.allow_any_action_concept,
        reveal_world_map_on_generation=config_data.reveal_world_map_on_generation,
        debug_free_location_travel=config_data.debug_free_location_travel,
        debug_disable_movement_time_passage=config_data.debug_disable_movement_time_passage,
        debug_disable_dungeon_random_encounters=config_data.debug_disable_dungeon_random_encounters,
    )
    try:
        print(engine.create_world("SaveSmokeWorld", "霧深い辺境と古い魔法", save_game=False))
        print(
            engine.apply_player_character(
                Character(
                    name="SaveSmoke",
                    role="Player",
                    category="young woman",
                    gender="female",
                    age="20",
                    backstory="A smoke-test adventurer.",
                    look="short hair, leather armor, travel cloak",
                    personality="calm and curious",
                    traits=[{"name": "冷静", "desc": "危機でも判断力を保つ"}],
                    skills=[{"name": "一閃", "desc": "素早い攻撃", "usesp": 5, "power": 2, "ability": "str", "element": "physical", "type": [{"type": "damage_hp_single"}]}],
                    extra={"ability": {"attributes": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}}},
                )
            )
        )
        print(f"choices={engine.state.choices}")
        print(
            "characters="
            + repr(
                [
                    (character.name, len(character.traits), len(character.skills))
                    for character in engine.state.world_data.characters.values()
                ]
            )
        )
        character_image = engine.generate_character_image()
        print(f"character_image={character_image.path}")
        monster_image = engine.generate_monster_image()
        print(f"monster_image={monster_image.path}")
        image = engine.generate_scene_image()
        print(f"image={image.path}")
        print(engine.resolve_choice("宿の主人に話しかける"))
        print(engine.resolve_action("赤い印について聞く"))
        print(engine.resolve_action("会話を終える"))
        print(engine.resolve_action("静かに状況を整理する"))
        print(engine.resolve_action("周辺を探索する"))
        print(engine.resolve_action("硝子森の影を攻撃する"))
        print(engine.resolve_action("降伏する"))
        quest_choice = next((choice for choice in engine.state.choices if choice.startswith("クエスト")), None)
        first_choice = quest_choice or (engine.state.choices[0] if engine.state.choices else "移動する")
        print(engine.resolve_choice(first_choice))
        print(engine.resolve_action("馬丁に話を聞く"))
        save_path = engine.save_game()
        print(f"save={save_path}")
        print(engine.load_game())
        print(f"data_dir={engine.save_store.data_dir}")
    finally:
        engine.stop()


def run_import_world_cli() -> None:
    args = _values_after("--import-world")
    if not args:
        raise SystemExit("Usage: --import-world <world.json|world.zip|world-directory> [--overwrite]")
    save_store = SaveStore()
    result = save_store.import_world(Path(args[0]), overwrite="--overwrite" in sys.argv)
    print(f"source={result.source}")
    print(f"imported_world={result.world.world_name}")
    if result.renamed_from:
        print(f"renamed_from={result.renamed_from}")
    print(f"save={result.path}")
    print(f"data_dir={save_store.data_dir}")


def run_export_world_cli() -> None:
    args = _values_after("--export-world")
    if not args:
        raise SystemExit("Usage: --export-world <world_name> [target.zip|target.json]")
    target = Path(args[1]) if len(args) > 1 else None
    save_store = SaveStore()
    path = save_store.export_world(args[0], target)
    print(f"exported_world={args[0]}")
    print(f"export={path}")


def run_world_import_export_smoke() -> None:
    save_store = SaveStore()
    world = WorldData(
        world_name="ImportExportSmoke",
        overview="Import/export smoke test world.",
        structure_description="A compact world used to verify world package transfer.",
        starting_location="Smoke Gate",
        locations={
            "Smoke Gate": LocationData(
                name="Smoke Gate",
                description="A small gate used to verify world import and export.",
                area="smoke",
            )
        },
        flags={"source": "world_import_export_smoke"},
    )
    save_store.save_world(world)
    export_path = save_store.export_world(world.world_name)
    result = save_store.import_world(export_path)
    print(f"export={export_path}")
    print(f"imported_world={result.world.world_name}")
    if result.renamed_from:
        print(f"renamed_from={result.renamed_from}")
    print(f"save={result.path}")
    print(f"worlds={[(slot.world_name, str(slot.path)) for slot in save_store.list_worlds()[:5]]}")


def run_asset_check() -> None:
    config_data = load_config()
    checks = check_runtime_assets(config_data)
    print(format_asset_report(checks))
    if not all(check.ok or str(check.detail).startswith("download_required:") for check in checks):
        raise SystemExit(1)


def _value_after(flag: str) -> str:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(sys.argv):
        return ""
    value = sys.argv[index + 1]
    return "" if value.startswith("--") else value


def _values_after(flag: str) -> list[str]:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return []
    values: list[str] = []
    for value in sys.argv[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    return values


def _safe_filename(value: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join("_" if ch in bad else ch for ch in value.strip()) or "world"


def _safe_int(value: str, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _clamp_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, _safe_int(str(value), fallback)))


def _gender_button_label(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"female", "woman", "girl", "f", "♀", "女"}:
        return "女"
    if text in {"male", "man", "boy", "m", "♂", "男"}:
        return "男"
    return "・"


def _actor_state_is_present(value: str) -> bool:
    state = str(value or "present").strip().lower()
    if not state:
        state = "present"
    return state not in {"absent", "gone", "left", "hidden", "dead", "ended", "inactive", "removed"}


def _parse_character_traits(text: str) -> list[dict[str, object]]:
    traits: list[dict[str, object]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.replace("｜", "|").replace("：", "|").split("|")]
        if not parts or not parts[0]:
            continue
        trait = {
            "name": parts[0],
            "desc": parts[1] if len(parts) > 1 else "",
        }
        traits.append(trait)
    return _character_trait_entries(traits)


def _parse_character_skills(text: str) -> list[dict[str, object]]:
    skills: list[dict[str, object]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.replace("｜", "|").replace("：", "|").split("|")]
        if not parts or not parts[0]:
            continue
        power = _entry_power(parts[4] if len(parts) > 4 else 1)
        skill = {
            "name": parts[0],
            "element": parts[1] if len(parts) > 1 else "",
            "desc": parts[2] if len(parts) > 2 else "",
            "usesp": max(1, min(12, _safe_int(parts[3], 1) if len(parts) > 3 else 1)),
            "power": power,
            "ability": parts[5].lower() if len(parts) > 5 and parts[5] else "str",
            "type": [{"type": item} for item in _skill_effect_type_list(parts[6] if len(parts) > 6 else "")],
        }
        skills.append(skill)
    return _normalise_character_skills(skills)


def _format_character_traits(traits: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for trait in _character_trait_entries(traits):
        name = str(trait.get("name") or "").strip()
        if not name:
            continue
        desc = str(trait.get("desc") or "").strip()
        lines.append(f"{name} | {desc}".rstrip(" |"))
    return "\n".join(lines)


def _format_character_skills(skills: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for skill in _normalise_character_skills(skills):
        name = str(skill.get("name") or skill.get("skill") or "").strip()
        if not name:
            continue
        category = _normalise_element_id(skill.get("element"))
        description = str(skill.get("desc") or "").strip()
        cost = skill.get("usesp", 1)
        power = _entry_power(skill)
        ability = str(skill.get("ability") or "str")
        effect_types = ",".join(_skill_effect_type_list(skill.get("type")))
        if not effect_types:
            continue
        lines.append(f"{name} | {category} | {description} | {cost} | {power} | {ability} | {effect_types}".rstrip(" |"))
    return "\n".join(lines)


def _format_character_entry_names(entries: list[dict[str, object]]) -> str:
    return "\n".join(
        str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
        for entry in entries
        if str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
    )


def _character_entry_description(entry: dict[str, object], kind: str) -> str:
    return str(entry.get("desc") or "").strip()


def _character_entry_fingerprint(value: object) -> str:
    return "".join(str(value or "").casefold().split())


def _character_entry_is_duplicate(
    entry: dict[str, object],
    existing_entries: list[dict[str, object]],
    kind: str,
    replace_index: int | None,
) -> bool:
    name_key = _character_entry_fingerprint(entry.get("name") or entry.get("skill") or entry.get("trait"))
    description_key = _character_entry_fingerprint(_character_entry_description(entry, kind))
    for index, existing in enumerate(existing_entries):
        if replace_index is not None and index == replace_index:
            continue
        existing_name_key = _character_entry_fingerprint(existing.get("name") or existing.get("skill") or existing.get("trait"))
        if name_key and existing_name_key and name_key == existing_name_key:
            return True
        existing_description_key = _character_entry_fingerprint(_character_entry_description(existing, kind))
        if description_key and existing_description_key and description_key == existing_description_key:
            return True
    return False


def _select_generated_character_entry(
    entries: list[dict[str, object]],
    existing_entries: list[dict[str, object]],
    kind: str,
    replace_index: int | None,
) -> dict[str, object]:
    for entry in entries:
        if not _character_entry_is_duplicate(entry, existing_entries, kind, replace_index):
            return entry
    return {}


def _normalise_element_id(value: object, fallback: str = "physical") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    key = text.casefold()
    aliases = {
        "physical": "physical",
        "phys": "physical",
        "物理": "physical",
        "fire": "fire",
        "flame": "fire",
        "炎": "fire",
        "水": "water",
        "water": "water",
        "ice": "ice",
        "氷": "ice",
        "lightning": "lightning",
        "thunder": "lightning",
        "雷": "lightning",
        "earth": "earth",
        "土": "earth",
        "wind": "wind",
        "風": "wind",
        "grass": "grass",
        "plant": "grass",
        "草": "grass",
        "poison": "poison",
        "毒": "poison",
        "mental": "mental",
        "mind": "mental",
        "精神": "mental",
        "light": "light",
        "holy": "light",
        "光": "light",
        "dark": "dark",
        "darkness": "dark",
        "闇": "dark",
        "none": "none",
        "neutral": "none",
        "無": "none",
    }
    if key in aliases:
        return aliases[key]
    for element_id in ELEMENT_IDS:
        if key == element_id.casefold():
            return element_id
        if key == tr_enum("element", element_id, "ja", fallback=element_id).casefold():
            return element_id
        if key == tr_enum("element", element_id, "en", fallback=element_id).casefold():
            return element_id
    return fallback


def _character_trait_entries(traits: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in traits:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        result.append({"name": name, "desc": str(raw.get("desc") or "").strip()})
    return result


def _skill_effect_type_list(value: object) -> list[str]:
    allowed = {
        "heal_single",
        "heal_party",
        "damage_hp_single",
        "damage_hp_party",
        "damage_sp_single",
        "damage_sp_party",
        "absorption_single",
        "absorption_party",
        "effect_enemy_single",
        "effect_enemy_party",
        "effect_self",
        "effect_ally_single",
        "effect_ally_party",
    }
    items: list[object]
    if isinstance(value, list):
        items = value
    else:
        items = [part.strip() for part in str(value or "").replace("、", ",").split(",")]
    result: list[str] = []
    for item in items:
        effect_type = str(item.get("type") if isinstance(item, dict) else item or "").strip()
        if effect_type in allowed:
            result.append(effect_type)
    return result


def _skill_effect_label(effect_type: str, language: str = "ja") -> str:
    labels_ja = {
        "heal_single": "単体回復",
        "heal_party": "味方全体回復",
        "damage_hp_single": "単体ダメージ",
        "damage_hp_party": "敵全体ダメージ",
        "damage_sp_single": "単体SPダメージ",
        "damage_sp_party": "敵全体SPダメージ",
        "absorption_single": "単体吸収",
        "absorption_party": "敵全体吸収",
        "effect_enemy_single": "敵単体状態変化",
        "effect_enemy_party": "敵全体状態変化",
        "effect_self": "自身状態変化",
        "effect_ally_single": "味方単体状態変化",
        "effect_ally_party": "味方全体状態変化",
    }
    labels_en = {
        "heal_single": "Single Heal",
        "heal_party": "Party Heal",
        "damage_hp_single": "Single Damage",
        "damage_hp_party": "Enemy Party Damage",
        "damage_sp_single": "Single SP Damage",
        "damage_sp_party": "Enemy Party SP Damage",
        "absorption_single": "Single Drain",
        "absorption_party": "Enemy Party Drain",
        "effect_enemy_single": "Enemy Status",
        "effect_enemy_party": "Enemy Party Status",
        "effect_self": "Self Status",
        "effect_ally_single": "Ally Status",
        "effect_ally_party": "Party Status",
    }
    labels = labels_ja if str(language or "ja").startswith("ja") else labels_en
    return labels.get(effect_type, effect_type)


def _skill_effect_label_summary(value: object, config_data) -> str:
    language = getattr(config_data, "language", "ja")
    effect_types = _skill_effect_type_list(value)
    if not effect_types:
        return ""
    ordered: list[str] = []
    counts: dict[str, int] = {}
    for effect_type in effect_types:
        if effect_type not in counts:
            ordered.append(effect_type)
        counts[effect_type] = counts.get(effect_type, 0) + 1
    labels: list[str] = []
    for effect_type in ordered:
        label = _skill_effect_label(effect_type, language)
        count = counts.get(effect_type, 0)
        labels.append(f"{label} x{count}" if count > 1 else label)
    return "、".join(labels) if str(language or "ja").startswith("ja") else ", ".join(labels)


def _normalise_character_skills(skills: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in skills:
        if not isinstance(raw, dict):
            raw = {"name": str(raw)}
        name = str(raw.get("name") or raw.get("skill") or raw.get("title") or "").strip()
        if not name:
            continue
        power = _entry_power(raw)
        effect_types = _skill_effect_type_list(raw.get("type"))
        if not effect_types:
            continue
        skill = {
            "name": name,
            "desc": str(raw.get("desc") or "").strip(),
            "usesp": max(1, min(12, _safe_int(raw.get("usesp"), 1))),
            "power": max(1, min(5, power)),
            "ability": str(raw.get("ability") or "str").strip().lower() or "str",
            "element": _normalise_element_id(raw.get("element")),
            "type": [{"type": item} for item in effect_types],
        }
        result.append(skill)
    return result


def _character_entry_generated_summary(entry: dict[str, object], kind: str, config_data) -> str:
    lines: list[str] = []
    if kind == "skills":
        power = _entry_power(entry)
        sp_cost = entry.get("usesp", "")
        element_id = _normalise_element_id(entry.get("element"))
        lines.append(f"{_ui_text(config_data, 'character_entry_sp_cost')}:{sp_cost}")
        lines.append(f"{_ui_text(config_data, 'character_entry_power')}:{power}")
        lines.append(
            f"{_ui_text(config_data, 'character_entry_element')}:"
            f"{tr_enum('element', element_id, getattr(config_data, 'language', 'ja'), fallback=element_id)}"
        )
        effect_labels = _skill_effect_label_summary(entry.get("type"), config_data)
        if effect_labels:
            lines.append(f"{_ui_text(config_data, 'character_entry_generated_effect')}:{effect_labels}")
    effects = entry.get("type")
    effect = _character_entry_description(entry, kind)
    if effect:
        lines.append(f"{_ui_text(config_data, 'character_entry_description')}:{effect}")
    return "\n".join(lines)


def _entry_power(value: object, fallback: int = 1) -> int:
    if isinstance(value, dict):
        for key in ("power",):
            if value.get(key) not in (None, ""):
                return _entry_power(value.get(key), fallback=fallback)
        return max(1, min(5, fallback))
    text = str(value or "").strip().lower()
    if not text:
        return max(1, min(5, fallback))
    number = _safe_int(text, 0)
    if number:
        return max(1, min(5, number))
    mapping = {
        "very low": 1,
        "low": 1,
        "minor": 1,
        "small": 1,
        "medium": 3,
        "normal": 3,
        "high": 4,
        "major": 4,
        "very high": 5,
        "ultimate": 5,
        "legendary": 5,
        "weak": 1,
        "strong": 4,
    }
    for key, mapped in mapping.items():
        if key in text:
            return mapped
    if any(word in text for word in ("弱", "低", "小", "軽")):
        return 1
    if any(word in text for word in ("中", "標準", "普通")):
        return 3
    if any(word in text for word in ("強", "高", "大", "奥義", "必殺", "伝説")):
        return 5
    return max(1, min(5, fallback))


def _character_entry_tooltip_text(entry: dict[str, object], kind: str, config_data) -> str:
    name = str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
    lines = [name]
    if kind == "skills":
        power = _entry_power(entry)
        lines.append(f"{_ui_text(config_data, 'character_entry_power')}: {power}/5")
        sp_cost = entry.get("usesp", "")
        element_id = _normalise_element_id(entry.get("element"))
        if sp_cost not in (None, ""):
            lines.append(f"{_ui_text(config_data, 'character_entry_sp_cost')}: {sp_cost}")
        if element_id:
            lines.append(
                f"{_ui_text(config_data, 'character_entry_element')}: "
                f"{tr_enum('element', element_id, getattr(config_data, 'language', 'ja'), fallback=element_id)}"
            )
    description = _character_entry_description(entry, kind)
    if description:
        lines.extend(["", description])
    effects = entry.get("type")
    if effects:
        effect_labels = _skill_effect_label_summary(effects, config_data) if kind == "skills" else _compact_tooltip_value(effects)
        lines.extend(["", _ui_text(config_data, "character_entry_generated_effect"), effect_labels])
    return "\n".join(str(line) for line in lines if str(line) != "")


def _compact_tooltip_value(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {_compact_tooltip_value(item)}" for item in value[:5])
    if isinstance(value, dict):
        parts = []
        for key in ("name", "effect", "description", "value", "duration"):
            if value.get(key) not in (None, ""):
                parts.append(str(value.get(key)))
        return " / ".join(parts) if parts else json.dumps(value, ensure_ascii=False)
    return str(value)


def _quest_reward_text(reward) -> str:
    if not reward:
        return ""
    if isinstance(reward, str):
        return reward
    if isinstance(reward, list):
        return ", ".join(str(item.get("name") if isinstance(item, dict) else item) for item in reward[:4])
    if not isinstance(reward, dict):
        return str(reward)
    parts: list[str] = []
    gold = reward.get("gold") or reward.get("receive_gold") or reward.get("gain_gold")
    exp = reward.get("exp") or reward.get("reward_exp") or reward.get("xp")
    if gold:
        parts.append(f"{gold}G")
    if exp:
        parts.append(f"EXP {exp}")
    items = reward.get("items") or reward.get("item_add")
    item_names = []
    for item in items if isinstance(items, list) else ([] if items in (None, "") else [items]):
        if isinstance(item, dict):
            item_names.append(str(item.get("name") or item.get("item_name") or item))
        else:
            item_names.append(str(item))
    if item_names:
        parts.append(", ".join(item_names[:4]))
    description = str(reward.get("description") or "")
    if description:
        parts.append(description)
    return " / ".join(part for part in parts if part)


def _prompt_parts_from_look(look: str) -> list[str]:
    parts = []
    for item in look.replace("\n", ",").split(","):
        text = item.strip()
        if text:
            parts.append(text)
    return parts[:12]


def _character_attributes(character: dict[str, object]) -> dict[str, int]:
    extra = character.get("extra")
    attrs: dict[str, object] = {}
    direct_attrs = character.get("attributes")
    if isinstance(direct_attrs, dict):
        attrs.update(direct_attrs)
    if isinstance(extra, dict):
        direct = extra.get("attributes")
        if isinstance(direct, dict):
            attrs.update(direct)
        ability = extra.get("ability")
        if isinstance(ability, dict):
            nested = ability.get("attributes")
            if isinstance(nested, dict):
                attrs.update(nested)
    return {
        "str": _safe_int(attrs.get("str", 10), 10),
        "dex": _safe_int(attrs.get("dex", 10), 10),
        "con": _safe_int(attrs.get("con", 10), 10),
        "int": _safe_int(attrs.get("int", 10), 10),
        "wis": _safe_int(attrs.get("wis", 10), 10),
        "cha": _safe_int(attrs.get("cha", 10), 10),
    }


def _format_character_status_detail(data: dict[str, object], encounter: dict[str, object], *, is_player: bool, language: str = "ja") -> str:
    attrs = _character_attributes(data)
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
    level_text = str(data.get("level") or data.get("lv") or extra.get("level") or "1")
    hp_text = str(
        data.get("hp")
        or data.get("health")
        or f"{data.get('current_hp', extra.get('current_hp', '-'))}/{data.get('max_hp', extra.get('max_hp', '-'))}"
    )
    sp_text = str(data.get("sp") or f"{data.get('current_sp', extra.get('current_sp', '-'))}/{data.get('max_sp', extra.get('max_sp', '-'))}")
    equipment = data.get("equipment") if isinstance(data.get("equipment"), dict) else {}
    equipment_lines: list[str] = []
    if isinstance(equipment, dict):
        for slot, item in equipment.items():
            if isinstance(item, dict) and item:
                equipment_lines.append(f"{tr_enum('equipment_slot', slot, language)}: {_item_label(item, language=language)}")
    field = lambda key: tr_enum("actor_detail", key, language)
    unknown = tr_enum("roster", "unknown", language)
    state_id = str(data.get("state") or "present")
    state_label = tr_enum("actor_state", state_id, language, fallback=state_id)
    affinity_value = _safe_int(extra.get("affinity", extra.get("trust", 0)), 0) if isinstance(extra, dict) else 0
    affinity_state = _affinity_state_label(affinity_value, language)
    lines = [
        f"[{field('current_status')}]",
        f"{field('name')}: {data.get('name') or unknown}",
        f"{field('gender_age')}: {_join_nonempty(_display_gender(data.get('gender'), language), data.get('age')) or '-'}",
        f"{field('location')}: {data.get('location') or '-'}",
        f"{field('state')}: {state_label}",
        f"{tr_enum('status_field', 'level', language)}: {level_text}",
        f"HP: {hp_text}",
        f"{field('sp')}: {sp_text}",
        f"{field('gold')}: {data.get('gold') or 0}",
        f"{field('affinity')}: {affinity_value} ({affinity_state})" if not is_player else "",
        f"{field('equipment')}: " + (" / ".join(equipment_lines) if equipment_lines else "-"),
        f"{field('attributes')}: "
        + ", ".join(
            [
                f"STR {attrs['str']}",
                f"DEX {attrs['dex']}",
                f"CON {attrs['con']}",
                f"INT {attrs['int']}",
                f"WIS {attrs['wis']}",
                f"CHA {attrs['cha']}",
            ]
        ),
    ]
    if encounter:
        if is_player:
            lines.append(f"{field('battle_hp')}: {encounter.get('player_hp', '-')}")
            lines.append(f"{field('battle_sp')}: {encounter.get('player_sp', '-')}")
            lines.append(f"{field('battle_status')}: {encounter.get('player_status') or '-'}")
        else:
            data_name = str(data.get("name") or "")
            data_uuid = str(data.get("uuid") or extra.get("uuid") or "")
            matched_entry: dict[str, object] | None = None
            raw_opponents = encounter.get("opponents")
            for entry in raw_opponents if isinstance(raw_opponents, list) else []:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("name") or "") == data_name or (data_uuid and str(entry.get("uuid") or "") == data_uuid):
                    matched_entry = entry
                    break
            if matched_entry is None and encounter.get("opponent_name") == data.get("name"):
                matched_entry = encounter
            if matched_entry is not None:
                hp_value = matched_entry.get("opponent_hp", data.get("current_hp", extra.get("current_hp", "-")))
                max_hp_value = matched_entry.get("opponent_max_hp", data.get("max_hp", extra.get("max_hp", "")))
                hp_display = f"{hp_value}/{max_hp_value}" if max_hp_value else str(hp_value)
                lines.append(f"{field('battle_hp')}: {hp_display}")
                lines.append(f"{field('battle_status')}: {matched_entry.get('opponent_status') or matched_entry.get('status') or '-'}")
    lines.extend(
        [
            "",
            f"[{field('appearance')}]",
            _short_display(data.get("look")) or "-",
            _short_display(data.get("personality")) or "",
            _short_display(data.get("backstory")) or "",
        ]
    )
    lines.extend(
        _format_status_effect_section(
            field("status_effects"),
            data.get("status_effects"),
        )
    )
    lines.extend(_format_named_description_section(field("traits"), data.get("traits")))
    lines.extend(_format_skill_section(field("skills"), data.get("skills"), language=language))
    lines.extend(_format_inventory_section(_character_inventory_value(data), language=language))
    return "\n".join(line for line in lines if line is not None)


def _display_gender(value: object, language: str = "ja") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = raw.lower()
    if raw in {"女", "女性", "♀"}:
        key = "female"
    elif raw in {"男", "男性", "♂"}:
        key = "male"
    elif raw in {"無", "無性", "無性別", "・"}:
        key = "none"
    return tr_enum("gender", key, language, fallback=raw)


def _affinity_state_label(value: int, language: str = "ja") -> str:
    if value <= -80:
        return "Mortal enemy" if str(language).lower().startswith("en") else "完全な敵対"
    if value <= -40:
        return "Hostile" if str(language).lower().startswith("en") else "敵対"
    if value <= -10:
        return "Distrust" if str(language).lower().startswith("en") else "不信"
    if value >= 80:
        return "Absolute trust" if str(language).lower().startswith("en") else "完全な信頼"
    if value >= 40:
        return "Trusted" if str(language).lower().startswith("en") else "信頼"
    if value >= 10:
        return "Friendly" if str(language).lower().startswith("en") else "友好的"
    return "Neutral" if str(language).lower().startswith("en") else "中立"


def _format_status_effect_section(title: str, value: object) -> list[str]:
    return _format_display_entry_section(
        title,
        value,
        description_keys=(
            "llm_effect",
            "send_llm",
            "send_llm_text",
            "llm_text",
            "desc",
            "description",
            "remove_condition",
            "condition_cancell",
            "effect_text",
            "display_effect",
            "mechanical_effect",
            "effect",
            "summary",
            "text",
            "note",
            "details",
        ),
    )


def _character_inventory_value(data: dict[str, object]) -> object:
    value = data.get("inventory")
    return value if isinstance(value, list) else []


def _format_named_description_section(title: str, value: object) -> list[str]:
    return _format_display_entry_section(
        title,
        value,
        description_keys=("desc",),
    )


def _format_skill_section(title: str, value: object, *, language: str = "ja") -> list[str]:
    entries = value if isinstance(value, list) else []
    lines = ["", f"[{title}]"]
    if not entries:
        lines.append("-")
        return lines
    cost_label = "SP Cost" if str(language).lower().startswith("en") else "消費SP"
    for entry in entries:
        if isinstance(entry, dict):
            name = _display_entry_name(entry)
            description = _display_entry_description(
                entry,
                ("desc", "effect_text", "display_effect", "effect", "summary", "text", "note", "details"),
            )
            cost = _skill_display_sp_cost(entry)
            cost_text = f"({cost_label}:{cost})" if cost is not None else ""
            if description:
                lines.append(f"- {name}: {description}{cost_text}")
            else:
                lines.append(f"- {name}{cost_text}")
        else:
            lines.append(f"- {_short_display(entry)}")
    return lines


def _skill_display_sp_cost(entry: dict[str, object]) -> int | None:
    if entry.get("usesp") not in (None, ""):
        return max(1, min(12, _safe_int(str(entry.get("usesp")), 1)))
    return None


def _format_display_entry_section(title: str, value: object, *, description_keys: tuple[str, ...]) -> list[str]:
    entries = value if isinstance(value, list) else []
    lines = ["", f"[{title}]"]
    if not entries:
        lines.append("-")
        return lines
    for entry in entries:
        if isinstance(entry, dict):
            name = _display_entry_name(entry)
            description = _display_entry_description(entry, description_keys)
            lines.append(f"- {name}" + (f": {description}" if description else ""))
        else:
            lines.append(f"- {_short_display(entry)}")
    return lines


def _display_entry_name(entry: dict[str, object]) -> str:
    for key in ("display_name", "label", "name", "title", "trait", "skill", "status", "status_name"):
        text = _short_display(entry.get(key))
        if text:
            return text
    return "?"


def _display_entry_description(entry: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str):
            text = _short_display(value)
            if text and text != _display_entry_name(entry):
                return text
        if isinstance(value, dict):
            text = _display_entry_description(value, keys)
            if text and text != _display_entry_name(entry):
                return text
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text = _display_entry_description(item, keys)
                else:
                    text = _short_display(item)
                if text and text != _display_entry_name(entry):
                    return text
    for key in keys:
        value = entry.get(key)
        if isinstance(value, (int, float, bool)) and value not in (None, ""):
            return _short_display(value)
    return ""


def _format_entry_section(title: str, value: object, fields: tuple[str, ...]) -> list[str]:
    entries = value if isinstance(value, list) else []
    lines = ["", f"[{title}]"]
    if not entries:
        lines.append("-")
        return lines
    for entry in entries:
        if isinstance(entry, dict):
            name = _short_display(entry.get("name")) or _short_display(entry.get("title")) or "?"
            details = [_short_display(entry.get(field)) for field in fields if field not in {"name", "title"}]
            detail_text = " / ".join(text for text in details if text)
            lines.append(f"- {name}" + (f": {detail_text}" if detail_text else ""))
        else:
            lines.append(f"- {_short_display(entry)}")
    return lines


def _format_inventory_section(value: object, language: str = "ja") -> list[str]:
    inventory = value if isinstance(value, list) else []
    lines = ["", f"[{tr_enum('actor_detail', 'inventory', language)}]"]
    if not inventory:
        lines.append("-")
        return lines
    for item in inventory[:12]:
        if isinstance(item, dict):
            lines.append(f"- {_item_label(item, language=language)}")
        else:
            lines.append(f"- {_short_display(item)}")
    if len(inventory) > 12:
        lines.append(tr_enum_format("actor_detail", "more", language, count=len(inventory) - 12))
    return lines


def _join_nonempty(*values: object) -> str:
    return " / ".join(text for text in (_short_display(value) for value in values) if text)


def _short_display(value: object, limit: int = 180) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _fit_image(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    width = max(max_width, 1)
    height = max(max_height, 1)
    ratio = min(width / image.width, height / image.height)
    size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return image.resize(size, resampling)


def _cover_image(image: Image.Image, width: int, height: int) -> Image.Image:
    target_width = max(width, 1)
    target_height = max(height, 1)
    ratio = max(target_width / image.width, target_height / image.height)
    resized_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    resized = image.resize(resized_size, resampling)
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _fit_subject_image(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    fitted = _fit_image(image, max_width, max_height)
    return fitted


def _subject_image_path(image_paths: dict[str, str], preferred_keys: tuple[str, ...]) -> str:
    for key in preferred_keys:
        value = image_paths.get(key)
        if value and Path(value).is_file():
            return str(value)
    for value in image_paths.values():
        if value and Path(value).is_file():
            return str(value)
    return ""


def _default_player_items() -> list[dict[str, object]]:
    return starter_items()


def _default_loot_items(location_name: str) -> list[dict[str, object]]:
    return []


def _default_vendor_items(owner_name: str) -> list[dict[str, object]]:
    return generate_loot_table_items("shop_general_store", context=owner_name, source="default_vendor")


def _item_value(item: dict[str, object]) -> int:
    return get_item_value(item)


def _item_label(item: dict[str, object], price_mode: str = "", language: str = "ja") -> str:
    return format_item_label(item, price_mode=price_mode, language=language)


def _insert_item_row(listbox: tk.Listbox, item: dict[str, object], price_mode: str = "", language: str = "ja") -> None:
    index = listbox.size()
    listbox.insert("end", _item_label(item, price_mode=price_mode, language=language))
    try:
        listbox.itemconfig(index, fg=item_rarity_color(item))
    except tk.TclError:
        pass


def _task_result_message(result, language: str = "ja") -> str:
    table = UI_TEXT.get(language, UI_TEXT["ja"])
    text = lambda key: table.get(key, UI_TEXT["en"].get(key, key))
    path = getattr(result, "path", None)
    backend = getattr(result, "backend", None)
    if path:
        if backend:
            return text("task_generated_by").format(backend=backend, path=path)
        return text("task_generated").format(path=path)
    if isinstance(result, Path):
        return text("task_path").format(path=result)
    if isinstance(result, str):
        return text("task_text_applied")
    return ""


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _typewriter_stable_prefix_length(current: str, target: str) -> int:
    prefix_len = _common_prefix_length(current, target)
    if prefix_len == len(current) or prefix_len == len(target):
        return prefix_len
    if current and prefix_len >= int(len(current) * 0.6):
        return prefix_len

    max_overlap = min(len(current), len(target))
    for overlap in range(max_overlap, 0, -1):
        if current[-overlap:] == target[:overlap]:
            return overlap
    return prefix_len


UI_TEXT = {
    "en": {
        "menu_world": "World",
        "menu_import_world": "Import World...",
        "menu_export_world": "Export Current World...",
        "menu_navigate": "Navigate",
        "menu_title": "Title",
        "menu_world_select": "World Select",
        "menu_settings": "Settings",
        "menu_generation_logs": "Generation Logs",
        "menu_game": "Game",
        "settings_tab_overview": "Overview",
        "settings_tab_llm": "LLM",
        "settings_tab_images": "Images",
        "settings_tab_ui": "UI / Display",
        "settings_tab_storage": "Storage / Logs",
        "settings_language": "Language",
        "settings_apply_llm": "Apply",
        "settings_apply_image": "Apply Image",
        "settings_apply_ui": "Apply UI",
        "settings_refresh": "Refresh",
        "settings_check_assets": "Check Assets",
        "settings_import_world": "Import World",
        "settings_export_current": "Export Current",
        "settings_generation_logs": "Generation Logs",
        "settings_back": "Back",
    },
    "ja": {
        "menu_world": "ワールド",
        "menu_import_world": "ワールド読込...",
        "menu_export_world": "現在のワールド出力...",
        "menu_navigate": "移動",
        "menu_title": "タイトル",
        "menu_world_select": "ワールド選択",
        "menu_settings": "設定",
        "menu_generation_logs": "生成ログ",
        "menu_game": "ゲーム",
        "settings_tab_overview": "概要",
        "settings_tab_llm": "LLM",
        "settings_tab_images": "画像生成",
        "settings_tab_ui": "UI / 表示",
        "settings_tab_storage": "保存 / ログ",
        "settings_language": "言語",
        "settings_apply_llm": "適用",
        "settings_apply_image": "画像設定を適用",
        "settings_apply_ui": "UI設定を適用",
        "settings_refresh": "更新",
        "settings_check_assets": "アセット確認",
        "settings_import_world": "ワールド読込",
        "settings_export_current": "現在のワールド出力",
        "settings_generation_logs": "生成ログ",
        "settings_back": "戻る",
    },
}


UI_TEXT["en"].update(
    {
        "title_subtitle": "Local AI RPG",
        "title_continue_latest": "Continue Latest",
        "title_new_world": "New World",
        "title_world_select": "World Select",
        "title_settings": "Settings",
        "title_generation_logs": "Generation Logs",
        "title_exit": "Exit",
        "common_back": "Back",
        "common_game": "Game",
        "common_settings": "Settings",
        "common_refresh": "Refresh",
        "common_generate": "Generate",
        "world_generation_title": "World Generation",
        "world_generation_subtitle": "Create a new world through the AI managers.",
        "world_name": "World Name",
        "world_premise": "Premise",
        "world_crime_risk": "Crime Risk in Towns",
        "world_enemy_strength": "Enemy Strength in Battle",
        "world_generate": "Generate World",
        "world_generation_progress_start": "Preparing world generation...",
        "world_progress_working": "Generating world",
        "world_progress_content_check": "Checking world premise",
        "world_progress_overview": "Generating world overview",
        "world_progress_locations": "Generating locations",
        "world_progress_dungeon_subnodes": "Finalizing dungeons",
        "world_progress_story": "Generating story",
        "world_progress_settlement": "Generating starting settlement",
        "world_progress_characters": "Generating NPCs",
        "world_progress_quests": "Generating quest outcomes",
        "world_progress_initial": "Generating opening scene",
        "world_progress_completed": "World generation complete",
        "world_select_title": "World Select",
        "saved_games": "Saved Games",
        "world_data": "World Data",
        "world_start_note": "Starting a world opens character setup.",
        "load_save": "Load Save",
        "start_selected_world": "Start Selected World",
        "import_world": "Import World",
        "character_setup_title": "Create a Character...",
        "character_backstory": "Backstory:",
        "character_appearance": "Appearance:",
        "character_age": "Age",
        "character_preset": "Preset",
        "character_preview_generate": "Generate Portrait",
        "character_preview_refresh": "Refresh",
        "character_strength": "Strength",
        "character_dexterity": "Dexterity",
        "character_constitution": "Endurance",
        "character_intelligence": "Intelligence",
        "character_wisdom": "Judgment",
        "character_charisma": "Charm",
        "character_gold": "Gold",
        "character_skills": "Skills:",
        "character_traits": "Traits:",
        "character_edit": "Edit",
        "character_apply": "Apply",
        "character_close": "Close",
        "character_skill_settings": "Skill Settings",
        "character_trait_settings": "Trait Settings",
        "character_skill_hint": "name | category | description | SP cost | power 1-5",
        "character_trait_hint": "name | description",
        "character_entry_name_skill": "Skill Name",
        "character_entry_name_trait": "Trait Name",
        "character_entry_description": "Description",
        "character_entry_result": "Generated Result",
        "character_entry_element": "Element",
        "character_entry_power": "Power",
        "character_entry_sp_cost": "SP Cost",
        "character_entry_generated_effect": "Effect",
        "character_entry_empty_result": "The AI did not return a usable entry.",
        "character_bp_over": "Bonus points are over the limit.",
        "character_need_world_image": "Generate or select a world before creating a character image.",
        "character_need_world_details": "Generate or select a world before generating character details.",
        "character_generating_preview": "Generating character preview...",
        "character_generating_entries": "Generating character {kind}...",
        "character_world_need": "Generate or select a world first.",
        "character_world_label": "World",
        "character_world_start": "Start",
        "character_start_game": "Start Adventure",
        "settings_llm_backend": "LLM Backend",
        "settings_context_tokens": "Context Tokens",
        "settings_llm_info": "LLM backend chooses local llama.cpp CPU/Vulkan/CUDA or cloud providers. Context Tokens controls the local GGUF context size used by llama-server.",
        "settings_quality": "Quality",
        "settings_sampler": "Sampler",
        "settings_scheduler": "Scheduler",
        "settings_lora_prompt": "LoRA Prompt",
        "settings_vae": "VAE",
        "settings_taesd": "TAESD",
        "settings_lora_dir": "LoRA Dir",
        "settings_negative_background": "Negative Background",
        "settings_negative_character": "Negative Character",
        "settings_negative_monster": "Negative Monster",
        "settings_negative_cg": "Negative CG",
        "settings_negative_prompt": "Negative Prompt",
        "settings_graphic_model_folder_hint": "If you already have a model, place it in the folder opened by the button on the right.",
        "settings_open_graphic_model_folder": "Open Image Model Folder",
        "settings_font": "Font",
        "settings_font_path": "Font Path",
        "settings_font_size": "Font Size",
        "settings_text_speed": "Text Speed",
        "settings_generate_images": "Generate Images",
        "settings_storage_info": "Config: {config}\nAppData: {appdata}\nRuntime: {runtime}\nOutput: {output}\nGeneration logs are available from this tab or the game screen.",
        "generation_logs_title": "Generation Logs",
        "generation_logs_entries": "Entries",
        "generation_logs_detail": "Detail",
        "generation_logs_clear_selection": "Clear Selection",
        "layers_title": "Layers",
        "layers_background": "Background",
        "layers_characters": "Characters",
        "layers_monsters": "Monsters",
        "game_inventory": "Inventory",
        "game_loot": "Loot",
        "game_world_map": "World Map",
        "game_subnode_map": "Area Map",
        "game_quest_status": "Quest",
        "game_trade": "Trade",
        "game_craft": "Craft",
        "game_save": "Save",
        "game_setting": "Setting",
        "game_submenu_continue": "Continue Game",
        "game_submenu_exit": "End Game",
        "game_submenu_settings": "Settings",
        "game_logs": "Logs",
        "game_cancel": "Cancel",
        "game_send": "send",
        "game_generating": "Generating",
        "task_generation_failed_log": "Generation failed.",
        "choice_move": "Move",
        "choice_quest_board": "Open quest board",
        "move_window_title": "Move",
        "move_window_hint": "Select a destination.",
        "move_window_confirm": "Move",
        "move_window_empty": "There is nowhere you can move right now.",
        "move_window_world": "World",
        "move_window_subnode": "Area",
        "move_window_external": "This route leaves the current area.",
        "move_window_unvisited": "Unvisited adjacent location.",
        "world_map_title": "World Map",
        "world_map_move": "Move to Selected Location",
        "world_map_no_locations": "No visited locations are recorded yet.",
        "world_map_drag_hint": "Drag to scroll. Hover a location to inspect it, then click to select.",
        "subnode_map_title": "Area Map",
        "subnode_map_move": "Move to Selected Place",
        "subnode_map_no_locations": "No internal map is available here.",
        "subnode_map_drag_hint": "Drag to scroll. Hover a place to inspect it, then click to select.",
        "quest_board_title": "Guild Quest Board",
        "quest_board_accept": "Accept",
        "quest_board_empty": "No quests are available.",
        "quest_board_not_guild": "The quest board is available inside the guild.",
        "quest_board_reward": "Reward",
        "quest_board_status": "Status",
        "quest_board_danger": "Danger",
        "quest_board_objective": "Objective",
        "quest_status_title": "Active Quest",
        "quest_status_empty": "No quest is currently active.",
        "quest_status_missing": "The active quest record was not found.",
        "quest_status_name": "Quest",
        "quest_status_destination": "Destination",
        "quest_status_subnode": "Target Place",
        "quest_status_deadline": "Remaining Time",
        "quest_status_todo": "To Do",
        "quest_status_no_entries": "Objective details have not been created yet.",
        "quest_status_continue": "Continue the quest objective.",
        "task_world_map_travel": "Traveling...",
        "task_subnode_map_travel": "Moving...",
        "task_accepting_quest": "Accepting quest...",
        "game_initial_log": "Start or load a world from the title screen.\n",
        "inventory_title": "Inventory",
        "inventory_details": "Details",
        "loot_title": "Loot",
        "trade_title": "Trade",
        "craft_title": "Craft",
        "craft_materials": "Materials",
        "craft_create": "Create",
        "craft_preview": "Preview",
        "craft_empty_help": "Select two or more materials. Include equipment to enhance it, or combine materials to craft an item.",
        "player_label": "Player",
        "trade_no_target": "No nearby NPC is available for trade.",
        "trade_not_enough_gold": "Not enough gold.",
        "trade_target_not_enough_gold": "{name} does not have enough gold.",
        "trade_stock_changed": "> [Shop] {name}'s stock changed for the day.",
        "trade_buy_price": "Buy: {price}G",
        "trade_sell_price": "Sell: {price}G",
        "dialog_import_world": "Import World",
        "dialog_export_world": "Export Current World",
        "dialog_imported_world": "Imported: {name}",
        "dialog_no_current_world": "No current world is available to export.",
        "dialog_generation_failed": "Generation failed. Check Generation Logs for details.",
        "dialog_file_fantasia_worlds": "Fantasia worlds",
        "dialog_file_all": "All files",
        "dialog_file_world_package": "Fantasia world package",
        "dialog_file_world_json": "World JSON",
        "task_importing_world": "Importing world...",
        "task_exporting_world": "Exporting world...",
        "empty_no_saved_games": "No saved games",
        "empty_no_worlds": "No worlds",
        "empty_no_generation_logs": "No generation logs",
        "empty_no_generation_logs_detail": "No generation logs were found.",
        "asset_check_title": "Asset Check",
        "settings_yes": "yes",
        "settings_no": "no",
        "settings_label_config": "Config",
        "settings_label_appdata": "AppData",
        "settings_label_runtime": "Runtime",
        "settings_label_output": "Output",
        "settings_label_prompt_templates": "Prompt templates",
        "settings_label_font_family": "Font family",
        "settings_label_font_size": "Font size",
        "settings_label_font_path": "Font path",
        "settings_label_font_file": "Font file",
        "settings_label_font_loaded": "Font loaded",
        "settings_label_language": "Language",
        "settings_label_llm_backend": "LLM backend",
        "settings_label_llm_mode": "LLM mode",
        "settings_label_llm_context_tokens": "LLM context tokens",
        "settings_label_llama_cpu_server": "llama CPU server",
        "settings_label_llama_vulkan_server": "llama Vulkan server",
        "settings_label_llama_cuda_server": "llama CUDA server",
        "settings_label_llama_log_dir": "llama log dir",
        "settings_label_cloud_openai_model": "Cloud OpenAI model",
        "settings_label_cloud_xai_model": "Cloud xAI model",
        "settings_label_cloud_gemini_model": "Cloud Gemini model",
        "settings_label_openai_key_env": "OpenAI key env",
        "settings_label_xai_key_env": "xAI key env",
        "settings_label_gemini_key_env": "Gemini key env",
        "settings_label_image_backend": "Image backend",
        "settings_label_image_quality": "Image quality preset",
        "settings_label_image_sampler": "Image sampler",
        "settings_label_image_scheduler": "Image scheduler",
        "settings_label_image_server": "Image server",
        "settings_label_sdxl_checkpoint": "SDXL checkpoint",
        "settings_label_sd_server_log_dir": "sd-server log dir",
        "settings_label_known_worlds": "Known worlds",
        "settings_label_save_slots": "Save slots",
    }
)

UI_TEXT["ja"].update(
    {
        "menu_world": "ワールド",
        "menu_import_world": "ワールドを読み込み...",
        "menu_export_world": "現在のワールドを書き出し...",
        "menu_navigate": "移動",
        "menu_title": "タイトル",
        "menu_world_select": "ワールド選択",
        "menu_settings": "設定",
        "menu_generation_logs": "生成ログ",
        "menu_game": "ゲーム",
        "settings_tab_overview": "概要",
        "settings_tab_llm": "LLM",
        "settings_tab_images": "画像",
        "settings_tab_ui": "UI / 表示",
        "settings_tab_storage": "保存 / ログ",
        "settings_language": "言語",
        "settings_apply_llm": "適用",
        "settings_apply_image": "画像設定を適用",
        "settings_apply_ui": "UI設定を適用",
        "settings_refresh": "更新",
        "settings_check_assets": "アセット確認",
        "settings_import_world": "ワールド読み込み",
        "settings_export_current": "現在のワールドを書き出し",
        "settings_generation_logs": "生成ログ",
        "settings_back": "戻る",
        "title_subtitle": "ローカルAI RPG",
        "title_continue_latest": "続きから",
        "title_new_world": "新しいワールド",
        "title_world_select": "ワールド選択",
        "title_settings": "設定",
        "title_generation_logs": "生成ログ",
        "title_exit": "終了",
        "common_back": "戻る",
        "common_game": "ゲーム",
        "common_settings": "設定",
        "common_refresh": "更新",
        "common_generate": "生成",
        "world_generation_title": "ワールド生成",
        "world_generation_subtitle": "AIマネージャで新しい世界を作ります。",
        "world_name": "世界名",
        "world_premise": "前提",
        "world_crime_risk": "街中での犯罪行為のリスク",
        "world_enemy_strength": "戦闘時の敵の強さ",
        "world_generate": "ワールド生成",
        "world_generation_progress_start": "ワールド生成を準備中...",
        "world_progress_working": "ワールド生成中",
        "world_progress_content_check": "内容確認中",
        "world_progress_overview": "世界概要を生成中",
        "world_progress_locations": "ロケーション生成中",
        "world_progress_dungeon_subnodes": "ダンジョン仕上げ中",
        "world_progress_story": "ストーリー生成中",
        "world_progress_settlement": "初期拠点を生成中",
        "world_progress_characters": "NPC生成中",
        "world_progress_quests": "クエストと報酬を生成中",
        "world_progress_initial": "初期場面を生成中",
        "world_progress_completed": "ワールド生成完了",
        "world_select_title": "ワールド選択",
        "saved_games": "セーブデータ",
        "world_data": "ワールドデータ",
        "world_start_note": "ワールド開始時にキャラクター設定を開きます。",
        "load_save": "セーブをロード",
        "start_selected_world": "選択したワールドで開始",
        "import_world": "ワールド読み込み",
        "character_setup_title": "キャラクターを作る...",
        "character_backstory": "出自:",
        "character_appearance": "外見:",
        "character_age": "年齢",
        "character_preset": "プリセット",
        "character_preview_generate": "立ち絵生成",
        "character_preview_refresh": "更新",
        "character_strength": "筋力",
        "character_dexterity": "器用",
        "character_constitution": "耐久",
        "character_intelligence": "知力",
        "character_wisdom": "判断",
        "character_charisma": "魅力",
        "character_gold": "所持金",
        "character_skills": "スキル:",
        "character_traits": "特質:",
        "character_edit": "設定",
        "character_apply": "適用",
        "character_close": "閉じる",
        "character_skill_settings": "スキル設定",
        "character_trait_settings": "特質設定",
        "character_skill_hint": "名前 | 種別 | 説明 | SP消費 | 強力度1-5",
        "character_trait_hint": "名前 | 説明",
        "character_entry_name_skill": "スキル名",
        "character_entry_name_trait": "体質名",
        "character_entry_description": "説明",
        "character_entry_result": "生成結果",
        "character_entry_element": "属性",
        "character_entry_power": "強力度",
        "character_entry_sp_cost": "消費SP",
        "character_entry_generated_effect": "効果",
        "character_entry_empty_result": "AIが使用可能な項目を返しませんでした。",
        "character_bp_over": "BPが上限を超えています。",
        "character_need_world_image": "キャラクター画像を作る前に、ワールドを生成または選択してください。",
        "character_need_world_details": "キャラクター詳細を生成する前に、ワールドを生成または選択してください。",
        "character_generating_preview": "キャラクター立ち絵を生成中...",
        "character_generating_entries": "キャラクター{kind}を生成中...",
        "character_world_need": "先にワールドを生成または選択してください。",
        "character_world_label": "世界",
        "character_world_start": "開始地点",
        "character_start_game": "冒険を始める",
        "settings_llm_backend": "LLMバックエンド",
        "settings_context_tokens": "コンテキストトークン",
        "settings_llm_info": "LLMバックエンドでは、ローカルの llama.cpp CPU/Vulkan/CUDA またはクラウドプロバイダを選択できます。コンテキストトークンは llama-server が使うローカルGGUFのコンテキスト長です。",
        "settings_quality": "品質",
        "settings_sampler": "サンプラー",
        "settings_scheduler": "スケジューラ",
        "settings_lora_prompt": "LoRAプロンプト",
        "settings_vae": "VAE",
        "settings_taesd": "TAESD",
        "settings_lora_dir": "LoRAフォルダ",
        "settings_negative_background": "ネガティブ(背景)",
        "settings_negative_character": "ネガティブ(キャラ)",
        "settings_negative_monster": "ネガティブ(モンスター)",
        "settings_negative_cg": "ネガティブ(CG)",
        "settings_negative_prompt": "ネガティブプロンプト",
        "settings_graphic_model_folder_hint": "すでにモデルを持っている場合は、右のボタンから開くフォルダにモデルを入れてください",
        "settings_open_graphic_model_folder": "画像モデルフォルダを開く",
        "settings_font": "フォント",
        "settings_font_path": "フォントパス",
        "settings_font_size": "フォントサイズ",
        "settings_text_speed": "テキスト速度",
        "settings_generate_images": "画像を生成する",
        "settings_storage_info": "Config: {config}\nAppData: {appdata}\nRuntime: {runtime}\nOutput: {output}\n生成ログはこのタブまたはゲーム画面から確認できます。",
        "generation_logs_title": "生成ログ",
        "generation_logs_entries": "一覧",
        "generation_logs_detail": "詳細",
        "generation_logs_clear_selection": "選択解除",
        "layers_title": "レイヤー",
        "layers_background": "背景",
        "layers_characters": "キャラ",
        "layers_monsters": "モンスター",
        "game_inventory": "所持品",
        "game_loot": "漁る",
        "game_world_map": "世界地図",
        "game_subnode_map": "\u30b5\u30d6\u30de\u30c3\u30d7",
        "game_quest_status": "依頼確認",
        "game_trade": "取引",
        "game_craft": "クラフト",
        "game_save": "保存",
        "game_setting": "設定",
        "game_submenu_continue": "ゲームを続ける",
        "game_submenu_exit": "ゲームを終了",
        "game_submenu_settings": "設定",
        "game_logs": "ログ",
        "game_cancel": "中止",
        "game_send": "送信",
        "game_generating": "生成中",
        "task_generation_failed_log": "生成に失敗した",
        "choice_move": "移動する",
        "choice_quest_board": "依頼掲示板を確認する",
        "move_window_title": "移動",
        "move_window_hint": "移動先を選択してください。",
        "move_window_confirm": "移動する",
        "move_window_empty": "現在移動できる場所はありません。",
        "move_window_world": "ワールド",
        "move_window_subnode": "内部",
        "move_window_external": "現在のエリアから外へ出る経路です。",
        "move_window_unvisited": "未訪問の隣接地点です。",
        "world_map_title": "世界地図",
        "world_map_move": "選択した場所へ移動",
        "world_map_no_locations": "訪問済みの場所がまだ記録されていません。",
        "world_map_drag_hint": "ドラッグでスクロール。場所にカーソルを合わせると詳細、クリックで選択できます。",
        "subnode_map_title": "\u30b5\u30d6\u30ce\u30fc\u30c9\u30de\u30c3\u30d7",
        "subnode_map_move": "\u9078\u629e\u3057\u305f\u5834\u6240\u3078\u79fb\u52d5",
        "subnode_map_no_locations": "\u3053\u3053\u3067\u306f\u5185\u90e8\u30de\u30c3\u30d7\u3092\u958b\u3051\u307e\u305b\u3093\u3002",
        "subnode_map_drag_hint": "\u30c9\u30e9\u30c3\u30b0\u3067\u30b9\u30af\u30ed\u30fc\u30eb\u3002\u5834\u6240\u306b\u30ab\u30fc\u30bd\u30eb\u3092\u5408\u308f\u305b\u308b\u3068\u8a73\u7d30\u3001\u30af\u30ea\u30c3\u30af\u3067\u9078\u629e\u3067\u304d\u307e\u3059\u3002",
        "quest_board_title": "ギルドの依頼掲示板",
        "quest_board_accept": "受ける",
        "quest_board_empty": "現在受けられる依頼はありません。",
        "quest_board_not_guild": "依頼掲示板はギルドの中で確認できます。",
        "quest_board_reward": "報酬",
        "quest_board_status": "状態",
        "quest_board_danger": "危険度",
        "quest_board_objective": "目的",
        "quest_status_title": "受注中の依頼",
        "quest_status_empty": "現在受注中の依頼はありません。",
        "quest_status_missing": "受注中の依頼データが見つかりません。",
        "quest_status_name": "依頼",
        "quest_status_destination": "向かう場所",
        "quest_status_subnode": "目的サブノード",
        "quest_status_deadline": "残り時間",
        "quest_status_todo": "やるべきこと",
        "quest_status_no_entries": "依頼目標の詳細はまだ作成されていません。",
        "quest_status_continue": "依頼目標を進める",
        "task_world_map_travel": "移動中...",
        "task_subnode_map_travel": "\u79fb\u52d5\u4e2d...",
        "task_accepting_quest": "依頼を受注中...",
        "game_initial_log": "タイトル画面からワールドを開始またはロードしてください。\n",
        "inventory_title": "所持品",
        "inventory_details": "詳細",
        "loot_title": "漁る",
        "trade_title": "取引",
        "craft_title": "クラフト",
        "craft_materials": "素材",
        "craft_create": "作成",
        "craft_preview": "作成予定",
        "craft_empty_help": "素材を2つ以上選んでください。装備を含めると武具強化、素材のみなら合成になります。",
        "player_label": "プレイヤー",
        "trade_no_target": "取引できる近くのNPCがいません。",
        "trade_not_enough_gold": "所持金が足りません。",
        "trade_target_not_enough_gold": "{name}の所持金が足りません。",
        "trade_stock_changed": "> [店] {name}の商品が入れ替わった。",
        "trade_buy_price": "購入: {price}G",
        "trade_sell_price": "売却: {price}G",
        "dialog_import_world": "ワールド読み込み",
        "dialog_export_world": "現在のワールドを書き出し",
        "dialog_imported_world": "読み込み完了: {name}",
        "dialog_no_current_world": "書き出せる現在のワールドがありません。",
        "dialog_generation_failed": "生成に失敗しました。詳細は生成ログを確認してください。",
        "dialog_file_fantasia_worlds": "Fantasiaワールド",
        "dialog_file_all": "すべてのファイル",
        "dialog_file_world_package": "Fantasiaワールドパッケージ",
        "dialog_file_world_json": "ワールドJSON",
        "task_importing_world": "ワールドを読み込み中...",
        "task_exporting_world": "ワールドを書き出し中...",
        "empty_no_saved_games": "セーブデータなし",
        "empty_no_worlds": "ワールドなし",
        "empty_no_generation_logs": "生成ログなし",
        "empty_no_generation_logs_detail": "生成ログは見つかりませんでした。",
        "asset_check_title": "アセット確認",
        "settings_yes": "はい",
        "settings_no": "いいえ",
        "settings_label_config": "設定ファイル",
        "settings_label_appdata": "AppData",
        "settings_label_runtime": "ランタイム",
        "settings_label_output": "出力先",
        "settings_label_prompt_templates": "プロンプトテンプレート",
        "settings_label_font_family": "フォントファミリ",
        "settings_label_font_size": "フォントサイズ",
        "settings_label_font_path": "フォントパス",
        "settings_label_font_file": "フォントファイル",
        "settings_label_font_loaded": "フォント読み込み",
        "settings_label_language": "言語",
        "settings_label_llm_backend": "LLMバックエンド",
        "settings_label_llm_mode": "LLMモード",
        "settings_label_llm_context_tokens": "LLMコンテキストトークン",
        "settings_label_llama_cpu_server": "llama CPUサーバー",
        "settings_label_llama_vulkan_server": "llama Vulkanサーバー",
        "settings_label_llama_cuda_server": "llama CUDAサーバー",
        "settings_label_llama_log_dir": "llamaログフォルダ",
        "settings_label_cloud_openai_model": "Cloud OpenAIモデル",
        "settings_label_cloud_xai_model": "Cloud xAIモデル",
        "settings_label_cloud_gemini_model": "Cloud Geminiモデル",
        "settings_label_openai_key_env": "OpenAIキー環境変数",
        "settings_label_xai_key_env": "xAIキー環境変数",
        "settings_label_gemini_key_env": "Geminiキー環境変数",
        "settings_label_image_backend": "画像バックエンド",
        "settings_label_image_quality": "画像品質プリセット",
        "settings_label_image_sampler": "画像サンプラー",
        "settings_label_image_scheduler": "画像スケジューラ",
        "settings_label_image_server": "画像サーバー",
        "settings_label_sdxl_checkpoint": "SDXLチェックポイント",
        "settings_label_sd_server_log_dir": "sd-serverログフォルダ",
        "settings_label_known_worlds": "登録ワールド数",
        "settings_label_save_slots": "セーブ数",
    }
)


UI_TEXT["en"].update(
    {
        "dialog_error_title": "Error",
        "error_no_save_selected": "No save slot is selected.",
        "error_no_world_selected": "No world is selected.",
        "error_unknown_llm_backend": "Unknown LLM backend: {backend}",
        "error_llm_context_min": "LLM context tokens must be 1024 or greater.",
        "error_font_size_min": "Font size must be 6 or greater.",
        "error_text_speed_min": "Text speed must be 0 or greater.",
        "log_loaded": "[Loaded] {world} / {player}",
        "log_prepared_world": "[Prepared World] {world}",
        "log_settings_llm": "[Settings] LLM backend: {backend}, context: {context_size}",
        "log_settings_image": "[Settings] Image generation settings updated.",
        "log_settings_ui": "[Settings] UI settings updated.",
        "log_world_generated": "[World Generated]",
        "log_started_game": "[Started Game] {world} / {player}",
        "log_saved": "[Saved] {path}",
        "log_imported_world": "[Imported World] {world}\n{path}",
        "log_exported_world": "[Exported World] {path}",
        "log_character_preview": "[Character Preview] {path}",
        "log_character_generated": "[Character {kind} Generated]",
        "log_error": "[Error] {error}",
        "task_creating_world": "Creating world...",
        "task_generating_scene_image": "Generating scene image...",
        "task_generating_character_image": "Generating character image...",
        "task_generating_monster_image": "Generating monster image...",
        "task_generating_player_image": "Generating player image...",
        "task_generating_cg_image": "Generating CG image...",
        "task_image_generation_disabled": "Image generation is OFF.",
        "task_resolving_free_action": "Resolving free action...",
        "task_resolving_choice": "Resolving choice...",
        "task_generating_status": "Generating: {name} ({elapsed}s)",
        "task_canceling_status": "Canceling: {name}",
        "task_failed_status": "Generation failed",
        "task_started": "Task started.",
        "task_result_ignored_after_cancel": "Task result was ignored after cancellation.",
        "task_was_cancelled": "Task was cancelled.",
        "task_cancel_requested": "Cancellation was requested.",
        "task_cancel_error": "Cancellation request raised an error.",
        "task_failed_detail": "Task failed. See this entry for details.",
        "task_completed": "Task completed.",
        "task_generated_by": "Generated by {backend}: {path}",
        "task_generated": "Generated: {path}",
        "task_path": "Path: {path}",
        "task_text_applied": "Text result was applied.",
    }
)


UI_TEXT["ja"].update(
    {
        "dialog_error_title": "エラー",
        "error_no_save_selected": "セーブデータが選択されていません。",
        "error_no_world_selected": "ワールドが選択されていません。",
        "error_unknown_llm_backend": "不明なLLMバックエンドです: {backend}",
        "error_llm_context_min": "LLMコンテキストトークンは1024以上にしてください。",
        "error_font_size_min": "フォントサイズは6以上にしてください。",
        "error_text_speed_min": "テキスト速度は0以上にしてください。",
        "log_loaded": "[読込] {world} / {player}",
        "log_prepared_world": "[ワールド準備] {world}",
        "log_settings_llm": "[設定] LLMバックエンド: {backend}, コンテキスト: {context_size}",
        "log_settings_image": "[設定] 画像生成設定を更新しました。",
        "log_settings_ui": "[設定] UI設定を更新しました。",
        "log_world_generated": "[ワールド生成]",
        "log_started_game": "[ゲーム開始] {world} / {player}",
        "log_saved": "[保存] {path}",
        "log_imported_world": "[ワールド読込] {world}\n{path}",
        "log_exported_world": "[ワールド書出] {path}",
        "log_character_preview": "[キャラクタープレビュー] {path}",
        "log_character_generated": "[キャラクター{kind}生成]",
        "log_error": "[エラー] {error}",
        "task_creating_world": "ワールドを生成中...",
        "task_generating_scene_image": "シーン画像を生成中...",
        "task_generating_character_image": "キャラクター画像を生成中...",
        "task_generating_monster_image": "モンスター画像を生成中...",
        "task_generating_player_image": "プレイヤー画像を生成中...",
        "task_generating_cg_image": "CG画像を生成中...",
        "task_image_generation_disabled": "画像生成はOFFです",
        "task_resolving_free_action": "自由行動を処理中...",
        "task_resolving_choice": "選択肢を処理中...",
        "task_generating_status": "生成中: {name} ({elapsed}s)",
        "task_canceling_status": "キャンセル中: {name}",
        "task_failed_status": "生成に失敗しました",
        "task_started": "タスクを開始しました。",
        "task_result_ignored_after_cancel": "キャンセル後のタスク結果を破棄しました。",
        "task_was_cancelled": "タスクはキャンセルされました。",
        "task_cancel_requested": "キャンセルを要求しました。",
        "task_cancel_error": "キャンセル要求中にエラーが発生しました。",
        "task_failed_detail": "タスクに失敗しました。詳細はこの項目を確認してください。",
        "task_completed": "タスクが完了しました。",
        "task_generated_by": "{backend}で生成しました: {path}",
        "task_generated": "生成しました: {path}",
        "task_path": "パス: {path}",
        "task_text_applied": "テキスト結果を反映しました。",
    }
)


UI_TEXT["en"].update(
    {
        "settings_detect_device": "Detect Device",
        "settings_local_model": "Local GGUF Model",
        "settings_download_model": "Download Model",
        "settings_sdxl_model": "SDXL Checkpoint",
        "settings_download_sdxl_model": "Download SDXL",
        "settings_cloud_llm": "Cloud LLM",
        "settings_api_key": "API Key",
        "wizard_title": "Initial Setup",
        "wizard_body": "Open Settings first and configure the models.",
        "error_no_model_selected": "No local model is selected.",
        "error_no_sdxl_model_selected": "No SDXL model is selected.",
        "dialog_model_downloaded": "Model download completed:\n{path}",
        "task_downloading_model": "Downloading {name}...",
        "task_downloading_model_progress": "Downloading {name} ({percent}%)",
        "task_downloading_model_bytes": "Downloading {name} ({mb} MB)",
        "settings_label_device": "Device",
        "settings_label_local_model": "Local model",
        "settings_label_selected_model": "Selected download model",
    }
)


UI_TEXT["ja"].update(
    {
        "settings_detect_device": "デバイス検出",
        "settings_local_model": "ローカルGGUFモデル",
        "settings_download_model": "モデルをダウンロード",
        "settings_sdxl_model": "SDXLチェックポイント",
        "settings_download_sdxl_model": "SDXLをダウンロード",
        "settings_cloud_llm": "クラウドLLM",
        "settings_api_key": "APIキー",
        "wizard_title": "初回設定",
        "wizard_body": "最初に設定を開き、モデルの設定を行ってください",
        "error_no_model_selected": "ローカルモデルが選択されていません。",
        "error_no_sdxl_model_selected": "SDXLモデルが選択されていません。",
        "dialog_model_downloaded": "モデルのダウンロードが完了しました:\n{path}",
        "task_downloading_model": "{name}をダウンロード中...",
        "task_downloading_model_progress": "{name}をダウンロード中（{percent}%）",
        "task_downloading_model_bytes": "{name}をダウンロード中（{mb} MB）",
        "settings_label_device": "デバイス",
        "settings_label_local_model": "ローカルモデル",
        "settings_label_selected_model": "選択中のダウンロードモデル",
    }
)


UI_TEXT["en"].update(
    {
        "settings_label_crashlog_dir": "crashlog dir",
        "settings_fetch_cloud_models": "Fetch Official Models",
        "error_no_cloud_models_fetched": "No models were returned from {provider}.",
        "dialog_cloud_models_fetched": "Fetched {count} models from {provider}.",
        "task_fetching_cloud_models": "Fetching {provider} models...",
        "wizard_body": "Open Settings first and configure the models.",
    }
)


UI_TEXT["ja"].update(
    {
        "settings_label_crashlog_dir": "クラッシュログフォルダ",
        "settings_fetch_cloud_models": "公式モデル一覧取得",
        "error_no_cloud_models_fetched": "{provider} からモデル一覧を取得できませんでした。",
        "dialog_cloud_models_fetched": "{provider} から {count} 件のモデルを取得しました。",
        "task_fetching_cloud_models": "{provider} のモデル一覧を取得中...",
        "wizard_body": "最初に設定を開き、モデルの設定を行ってください",
    }
)


UI_TEXT["en"].update({"settings_label_log_dir": "Log dir"})
UI_TEXT["ja"].update({"settings_label_log_dir": "ログフォルダ"})

UI_TEXT["en"].update(
    {
        "settings_category_llm": "LLM",
        "settings_category_images": "Images",
        "settings_category_ui": "UI / Display",
        "settings_category_debug": "Debug",
        "settings_llm_title": "[LLM Settings]",
        "settings_image_title": "[Image Settings]",
        "settings_ui_title": "[UI / Display Settings]",
        "settings_debug_title": "[Debug]",
        "settings_apply": "Apply",
        "settings_close": "Close",
        "settings_check_generation_logs": "Check Generation Logs",
        "settings_model": "Model",
        "settings_context_hint": "If generation fails because the context is too small, increase this value.",
        "settings_repeat_suppression": "Repeat Suppression",
        "settings_repeat_hint": "Local LLM only. Suppresses repeated wording.",
        "settings_temperature": "Temperature",
        "settings_temperature_hint": "Higher values may broaden expression, but accuracy can decrease. 0.0-0.3 is recommended.",
        "settings_local_model_folder_hint": "If you already have a model, place it in the language model folder from the button on the right.",
        "settings_open_text_model_folder": "Open Language Model Folder",
        "error_llm_temperature_min": "Temperature must be 0 or greater.",
    }
)
UI_TEXT["ja"].update(
    {
        "settings_category_llm": "LLM",
        "settings_category_images": "画像",
        "settings_category_ui": "UI/表示",
        "settings_category_debug": "デバッグ",
        "settings_llm_title": "【LLM設定】",
        "settings_image_title": "【画像設定】",
        "settings_ui_title": "【UI/表示設定】",
        "settings_debug_title": "【デバッグ】",
        "settings_apply": "適応",
        "settings_close": "閉じる",
        "settings_check_generation_logs": "生成ログを確認",
        "settings_model": "モデル",
        "settings_context_hint": "生成に失敗する場合はこの数値を増やしてください",
        "settings_repeat_suppression": "繰り返し抑制",
        "settings_repeat_hint": "ローカルLLM専用、繰り返しを抑制します。",
        "settings_temperature": "温度",
        "settings_temperature_hint": "上げると表現の幅が広がる可能性がありますが、正確性が下がる恐れがあります。0〜0.3推奨。",
        "settings_local_model_folder_hint": "すでにモデルを持っている場合は、右のボタンから開くフォルダにモデルを入れてください",
        "settings_open_text_model_folder": "言語モデルフォルダを開く",
        "error_llm_temperature_min": "温度は0以上にしてください。",
    }
)

UI_TEXT["en"].update(
    {
        "settings_allow_any_action_concept": "Make Any Action / Concept Possible",
        "settings_allow_any_action_concept_hint": "Debug only. Disables the world-feasibility guardrail before action resolution.",
        "log_settings_debug": "[Settings] Debug settings updated.",
    }
)
UI_TEXT["ja"].update(
    {
        "settings_allow_any_action_concept": "あらゆる行動・概念を実現可能にする",
        "settings_allow_any_action_concept_hint": "デバッグ用。この設定をONにすると、世界観や状況に合わない行動を弾く事前ガードを無効化します。",
        "log_settings_debug": "[設定] デバッグ設定を更新しました。",
    }
)

UI_TEXT["en"].update(
    {
        "settings_reveal_world_map_on_generation": "Reveal Full World Map On Generation",
        "settings_reveal_world_map_on_generation_hint": "Debug only. Newly generated worlds show every world-map node immediately.",
        "settings_debug_free_location_travel": "Ignore Restrictions And Freely Move To All Locations",
        "settings_debug_free_location_travel_hint": "Debug only. Allows travel to known world-map locations even from dangerous areas or blocked subnodes.",
        "settings_debug_disable_movement_time_passage": "Disable Time Passage On Movement",
        "settings_debug_disable_movement_time_passage_hint": "Debug only. Moving on the world map or inside dungeons does not advance time.",
        "settings_debug_disable_dungeon_random_encounters": "Disable Dungeon Random Enemy Spawns",
        "settings_debug_disable_dungeon_random_encounters_hint": "Debug only. First visits to dangerous dungeon subnodes do not roll random enemy encounters.",
    }
)
UI_TEXT["ja"].update(
    {
        "settings_reveal_world_map_on_generation": "生成時にすべてのワールドマップを表示する",
        "settings_reveal_world_map_on_generation_hint": "デバッグ用。新規ワールド生成完了時、全ロケーションを世界地図に表示します。",
        "settings_debug_free_location_travel": "制限を無視してすべてのロケーションを自由に移動できるようにする",
        "settings_debug_free_location_travel_hint": "デバッグ用。危険地帯やサブノード制限を無視して、登録済みロケーションへ移動できます。",
        "settings_debug_disable_movement_time_passage": "移動時の時間経過無効化",
        "settings_debug_disable_movement_time_passage_hint": "デバッグ用。ワールドマップ移動やダンジョン内移動で時間が経過しなくなります。",
        "settings_debug_disable_dungeon_random_encounters": "ダンジョン内のランダム敵出現無効化",
        "settings_debug_disable_dungeon_random_encounters_hint": "デバッグ用。危険なダンジョンサブノード初訪問時のランダム敵出現を無効化します。",
    }
)

UI_TEXT["en"].update(
    {
        "title_subtitle": "AI-driven RPG",
        "title_continue_latest": "Continue",
        "title_new_world": "Create World",
        "title_world_select": "Start With Created World",
        "title_settings": "Settings",
        "title_exit": "Exit",
        "common_back": "Back",
        "world_select_title": "World Select",
        "start_selected_world": "Start With Selected World",
        "import_world": "Import World",
        "export_selected_world": "Export Selected World",
        "continue_select_title": "Character Select",
        "continue_selected_character": "Resume With Selected Character",
    }
)
UI_TEXT["ja"].update(
    {
        "title_subtitle": "AI駆動RPG",
        "title_continue_latest": "続きから",
        "title_new_world": "ワールド作成",
        "title_world_select": "作成したワールドで始める",
        "title_settings": "設定",
        "title_exit": "終了",
        "common_back": "戻る",
        "world_select_title": "ワールド選択",
        "start_selected_world": "選択したワールドで開始",
        "import_world": "ワールドをインポート",
        "export_selected_world": "選択したワールドをエクスポート",
        "continue_select_title": "キャラ 選択",
        "continue_selected_character": "選択したキャラで再開",
    }
)


UI_TEXT["en"].update(
    {
        "settings_show_button_help": "Show Button Help",
        "settings_show_button_help_hint": "When enabled, hovering the lower game buttons shows the button name and a short explanation.",
        "game_cg": "Create CG",
        "game_tutorial": "Tutorial",
        "game_tutorial_title": "Tutorial",
        "game_tutorial_prev": "Previous",
        "game_tutorial_next": "Next",
        "game_tutorial_page": "{page}/{total}",
        "game_inventory_help": "Check, use, equip, or move items you are carrying.",
        "game_craft_help": "Combine materials or equipment to create or improve items.",
        "game_loot_help": "Open nearby containers or loot found in the current place.",
        "game_world_map_help": "View visited locations and travel along known routes.",
        "game_quest_status_help": "Check the active quest destination, target place, and current objective.",
        "game_subnode_map_help": "View the internal map of the current town, facility, or dungeon.",
        "game_cg_help": "Generate a CG image from the latest log, visible characters, status effects, and current location.",
        "game_tutorial_help": "Open beginner guide pages for what to do next.",
        "game_save_help": "Save the current adventure.",
        "game_setting_help": "Open the submenu for continuing, ending the game, or changing settings.",
        "world_create_tutorial_title": "World Generation Guide",
        "world_create_tutorial_body": (
            "World Name: the name shown in saves and world selection.\n\n"
            "Premise: describe the world tone, important rules, and what kind of adventure you want.\n\n"
            "Initial Locations: choose how many world map locations are generated first. More locations take longer.\n\n"
            "Crime Risk in Towns: controls how strongly towns react to crimes.\n\n"
            "Enemy Strength in Battle: adjusts combat difficulty.\n\n"
            "Press Generate World when ready. After the world is complete, character creation opens."
        ),
        "character_setup_tutorial_title": "Character Creation Guide",
        "character_setup_tutorial_body": (
            "Set your name, gender, backstory, appearance, and age. The portrait area on the left is a preview, and portrait generation is optional.\n\n"
            "BP is spent only on the six stats. Strength helps physical force, Dexterity helps tools and crafting, Endurance increases toughness, Intelligence helps knowledge and magic, Judgment helps perception and will, and Charm helps social actions.\n\n"
            "Skills and traits are edited one at a time by pressing their name buttons. They do not consume BP.\n\n"
            "When everything looks right, press Start Adventure at the lower right."
        ),
        "tutorial_page_start_title": "First Steps",
        "tutorial_page_start_body": (
            "Read the log first. It describes the current scene and what just happened.\n\n"
            "The choice buttons are safe suggestions from the game. You can also type a free action in the input field, such as asking an NPC a question or inspecting an object.\n\n"
            "If an action does not fit the world or the situation, the game can reject it without spending progress."
        ),
        "tutorial_page_maps_title": "Movement And Maps",
        "tutorial_page_maps_body": (
            "In towns, use the town map or choices to move between facilities.\n\n"
            "World Map shows places you have visited or learned about. Area Map shows subnodes inside the current location, such as dungeon rooms or town facilities.\n\n"
            "Dangerous places often require adjacent movement inside the area map, so check your route before pushing deeper."
        ),
        "tutorial_page_items_title": "Items And Saving",
        "tutorial_page_items_body": (
            "Inventory opens your carried items. Loot opens nearby containers or items on the scene. Craft combines materials and can improve equipment.\n\n"
            "Your carried inventory has a limit, so use storage, shops, and crafting to keep it organized.\n\n"
            "Use Save often, especially before entering a dangerous area or starting a quest."
        ),
        "tutorial_page_quests_title": "Quests And Combat",
        "tutorial_page_quests_body": (
            "Guild quests are taken from the guild quest board. Active quests show in the information panel with their remaining time.\n\n"
            "Combat uses HP, SP, attack, defense, skills, conditions, and NPC behavior. Some enemies may attack, flee, surrender, capture, or negotiate depending on the world and their personality.\n\n"
            "If you are unsure what to do, look around, talk to nearby NPCs, check the map, or return to town."
        ),
        "tutorial_page_first_goal_title": "What To Do First",
        "tutorial_page_first_goal_body": (
            "A good first goal is buying a home. Even an inexpensive 500 Gold home lets you rest for free and recover HP and SP.\n\n"
            "Early on, buy and equip armor even if its defense is low. A little protection matters before entering dangerous areas.\n\n"
            "Use crafting whenever you can. Cooking food restores more hunger than eating raw ingredients."
        )
    }
)
UI_TEXT["ja"].update(
    {
        "settings_show_button_help": "ボタン説明を表示する",
        "settings_show_button_help_hint": "ONにすると、ゲーム画面下部のボタンにカーソルを合わせた時に名称と短い説明を表示します。",
        "game_cg": "CG作成",
        "game_tutorial": "チュートリアル",
        "game_tutorial_title": "チュートリアル",
        "game_tutorial_prev": "前へ",
        "game_tutorial_next": "次へ",
        "game_tutorial_page": "{page}/{total}",
        "game_inventory_help": "持っているアイテムの確認、使用、装備、移動を行います。",
        "game_craft_help": "素材や装備を組み合わせて、アイテム作成や武具強化を行います。",
        "game_loot_help": "今いる場所の箱や落ちている物を確認します。",
        "game_world_map_help": "訪れた場所や知っている経路を確認し、既知の道を移動します。",
        "game_quest_status_help": "受注中の依頼、向かう場所、目的サブノード、やるべきことを確認します。",
        "game_subnode_map_help": "街、施設、ダンジョン内部のマップを確認します。",
        "game_cg_help": "直近ログ、見えている人物、状態異常、現在地からCG画像を生成します。",
        "game_tutorial_help": "次に何をすればよいかを確認できる初心者向けガイドを開きます。",
        "game_save_help": "現在の冒険を保存します。",
        "game_setting_help": "ゲーム継続、終了、設定を選ぶサブメニューを開きます。",
        "world_create_tutorial_title": "ワールド生成の説明",
        "world_create_tutorial_body": (
            "世界名: セーブやワールド選択に表示される名前です。\n\n"
            "前提: 世界観、重要なルール、遊びたい冒険の方向性を書きます。\n\n"
            "街中での犯罪行為のリスク: 街が犯罪行為にどれくらい厳しく反応するかを決めます。\n\n"
            "戦闘時の敵の強さ: 戦闘難易度を調整します。\n\n"
            "準備ができたらワールド生成を押してください。生成が終わるとキャラクター作成へ進みます。"
        ),
        "character_setup_tutorial_title": "キャラクター作成の説明",
        "character_setup_tutorial_body": (
            "名前、性別、出自、外見、年齢を設定します。左側は立ち絵プレビューで、画像生成は任意です。\n\n"
            "BPはステータスの強化に使います。筋力は力仕事や物理攻撃、器用は道具やクラフト、耐久は打たれ強さ、知力は知識や魔法、判断は観察や意志、魅力は会話や交渉に関わります。\n\n"
            "スキルと体質は名前のボタンを押して1つずつ編集します。\n\n"
            "内容が決まったら右下の「冒険を始める」を押してください。"
        ),
        "tutorial_page_start_title": "まず最初に",
        "tutorial_page_start_body": (
            "まずはログを読みます。今いる場面と、直前に何が起きたかが書かれています。\n\n"
            "選択肢ボタンはゲームが提案する安全な行動です。入力欄には、NPCに質問する、物を調べるなどの自由行動も書けます。\n\n"
            "世界観や状況に合わない行動は、進行せずに拒否されることがあります。"
        ),
        "tutorial_page_maps_title": "移動とマップ",
        "tutorial_page_maps_body": (
            "街では街の地図や選択肢から施設へ移動します。\n\n"
            "ワールドマップは訪れた場所や知っている経路を表示します。サブノードマップは、ダンジョンの部屋や街の施設など、現在地内部の地図です。\n\n"
            "危険な場所では内部マップを隣接移動することが多いので、奥へ進む前に経路を確認してください。"
        ),
        "tutorial_page_items_title": "アイテムと保存",
        "tutorial_page_items_body": (
            "所持品では持っているアイテムを確認します。漁るでは今いる場面の箱や落ちている物を確認します。クラフトでは素材を組み合わせたり装備を強化できます。\n\n"
            "持ち歩けるアイテム数には上限があります。保管箱、店、クラフトを使って整理しましょう。\n\n"
            "危険地帯へ入る前やクエスト開始前は、こまめに保存すると安心です。"
        ),
        "tutorial_page_quests_title": "依頼と戦闘",
        "tutorial_page_quests_body": (
            "ギルドの依頼は、ギルド内の依頼掲示板から受けます。受注中の依頼と残り時間は情報欄に表示されます。\n\n"
            "戦闘ではHP、SP、攻撃力、防御力、スキル、状態、NPCの性格が関わります。敵は世界観や性格によって、攻撃、逃亡、降伏、捕獲、交渉などを選ぶことがあります。\n\n"
            "迷った時は、周囲を見回す、近くのNPCに話す、マップを確認する、街へ戻る、などを試してください。"
        ),
        "tutorial_page_first_goal_title": "初めに何をすればいいか",
        "tutorial_page_first_goal_body": (
            "まずは家を買うことを目標にしましょう。500Goldの安い家でも、無料で休憩してHPとSPを回復できるようになります。\n\n"
            "初めのうちは、防御力が低い防具でも購入して装備した方が安全です。危険地帯へ入る前の少しの防御が生存につながります。\n\n"
            "クラフトも活用しましょう。食料を調理すると、そのまま食べるより多くの満腹度を回復できます。"
        )
    }
)


UI_TEXT["en"].update(
    {
        "craft_intent": "Category",
        "craft_intent_auto": "Auto",
        "craft_intent_mix": "Mix",
        "craft_intent_synthesis": "Synthesis",
        "craft_intent_smithing": "Smithing",
        "craft_intent_alchemy": "Alchemy",
        "craft_intent_cooking": "Cooking",
    }
)
UI_TEXT["ja"].update(
    {
        "craft_intent": "カテゴリ",
        "craft_intent_auto": "おまかせ",
        "craft_intent_mix": "混合",
        "craft_intent_synthesis": "合成",
        "craft_intent_smithing": "鍛冶",
        "craft_intent_alchemy": "錬金術",
        "craft_intent_cooking": "料理",
    }
)


def _ui_text(config_data, key: str) -> str:
    language = getattr(config_data, "language", "ja")
    table = UI_TEXT.get(language, UI_TEXT["ja"])
    return table.get(key, UI_TEXT["en"].get(key, key))


def _craft_intent_label(config_data, intent_id: str) -> str:
    key = CRAFT_INTENT_UI_KEYS.get(str(intent_id or ""), CRAFT_INTENT_UI_KEYS["auto"])
    return _ui_text(config_data, key)


def _craft_intent_options(config_data) -> tuple[str, ...]:
    return tuple(_craft_intent_label(config_data, intent_id) for intent_id in CRAFT_INTENT_IDS)


def _craft_intent_id_from_label(config_data, label: str) -> str:
    value = str(label or "").strip()
    for intent_id in CRAFT_INTENT_IDS:
        if value == _craft_intent_label(config_data, intent_id):
            return intent_id
    return "auto"


def _builtin_font_label(language: str = "ja") -> str:
    if str(language).lower().startswith("en"):
        return f"Built-in Font ({BUILTIN_FONT_NAME})"
    return f"内蔵フォント ({BUILTIN_FONT_NAME})"


def _font_options(root: tk.Misc, language: str = "ja") -> tuple[str, ...]:
    try:
        families = sorted({str(name).strip() for name in tkfont.families(root) if str(name).strip()}, key=str.casefold)
    except tk.TclError:
        families = []
    return (_builtin_font_label(language), *families)


def _font_label_from_config(config_data, root: tk.Misc | None = None) -> str:
    family = str(getattr(config_data, "font_family", "") or "").strip()
    if family:
        return family
    return _builtin_font_label(getattr(config_data, "language", "ja"))


def _font_family_from_label(label: str, language: str = "ja") -> str:
    text = str(label or "").strip()
    builtin_labels = {
        _builtin_font_label(language),
        _builtin_font_label("ja"),
        _builtin_font_label("en"),
        BUILTIN_FONT_NAME,
    }
    return "" if text in builtin_labels else text


def _image_generation_enabled_config(config_data) -> bool:
    value = config_data.ui_setting.get("generate_images", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "disabled"}
    return bool(value)


def _world_crime_risk_label(value: str, language: str = "ja") -> str:
    key = str(value or DEFAULT_WORLD_CRIME_RISK).strip().lower().replace("-", "_").replace(" ", "_")
    english = {
        "none": "None",
        "normal": "Normal",
        "strict": "Strict",
    }
    japanese = {
        "none": "無し",
        "normal": "普通",
        "strict": "かなりシビア",
    }
    table = english if str(language).lower().startswith("en") else japanese
    return table.get(key, table[DEFAULT_WORLD_CRIME_RISK])


def _world_crime_risk_options(language: str = "ja") -> tuple[str, ...]:
    return tuple(_world_crime_risk_label(value, language) for value in ("none", "normal", "strict"))


def _world_crime_risk_from_label(label: str) -> str:
    text = str(label or "").strip().lower()
    if text in {"normal", "普通"}:
        return "normal"
    if text in {"strict", "hard", "severe", "かなりシビア", "シビア"}:
        return "strict"
    return DEFAULT_WORLD_CRIME_RISK


def _world_enemy_strength_label(value: str, language: str = "ja") -> str:
    key = str(value or DEFAULT_WORLD_ENEMY_STRENGTH).strip().lower().replace("-", "_").replace(" ", "_")
    english = {
        "weak": "Weak",
        "normal": "Normal",
        "strong": "Strong",
    }
    japanese = {
        "weak": "弱め",
        "normal": "普通",
        "strong": "強め",
    }
    table = english if str(language).lower().startswith("en") else japanese
    return table.get(key, table[DEFAULT_WORLD_ENEMY_STRENGTH])


def _world_enemy_strength_options(language: str = "ja") -> tuple[str, ...]:
    return tuple(_world_enemy_strength_label(value, language) for value in ("weak", "normal", "strong"))


def _world_enemy_strength_from_label(label: str) -> str:
    text = str(label or "").strip().lower()
    if text in {"weak", "easy", "弱め"}:
        return "weak"
    if text in {"strong", "hard", "強め"}:
        return "strong"
    return DEFAULT_WORLD_ENEMY_STRENGTH


def _world_map_node_detail(node: dict[str, object], current_location: object = "", language: str = "ja") -> str:
    name = str(node.get("name") or "")
    kind = str(node.get("kind") or "")
    danger = str(node.get("danger") if node.get("danger") is not None else "0")
    description = str(node.get("description") or "")
    english = str(language).lower().startswith("en")
    marker = " / current" if english and name and name == str(current_location or "") else " / 現在地" if name and name == str(current_location or "") else ""
    if english:
        parts = [f"{name}{marker}", f"Kind: {kind or '-'} / Danger: {danger}"]
    else:
        parts = [f"{name}{marker}", f"種別: {kind or '-'} / 危険度: {danger}"]
    if description:
        parts.append(description)
    return "\n".join(parts)


def _subnode_map_node_detail(node: dict[str, object], data: dict[str, object], language: str = "ja") -> str:
    name = str(node.get("name") or "")
    kind = str(node.get("kind") or "")
    description = str(node.get("description") or "")
    english = str(language).lower().startswith("en")
    current = bool(node.get("current"))
    external = bool(node.get("external"))
    marker = " / current" if english and current else " / \u73fe\u5728\u5730" if current else ""
    if english:
        parts = [f"{name}{marker}", f"Kind: {kind or '-'}"]
        if external:
            parts.append(f"Destination: {node.get('target_location') or '-'} / subnode: {node.get('target_subnode') or '-'}")
        else:
            parts.append(f"Movement: {data.get('movement') or '-'}")
    else:
        parts = [f"{name}{marker}", f"\u7a2e\u5225: {kind or '-'}"]
        if external:
            parts.append(f"\u79fb\u52d5\u5148: {node.get('target_location') or '-'} / \u63a5\u7d9a\u5730\u70b9: {node.get('target_subnode') or '-'}")
        else:
            parts.append(f"\u79fb\u52d5\u30eb\u30fc\u30eb: {data.get('movement') or '-'}")
    if description:
        parts.append(description)
    return "\n".join(parts)


def _quest_status_internal_place_id(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text or text == "-":
        return False
    if text in {"gate", "entrance", "entrance_b", "deepest", "depths", "default"}:
        return True
    return text.startswith(("main_", "side_", "quest:", "facility:", "home:", "capture:", "subarea:"))


def _world_generation_progress_text(config_data, payload: dict[str, object]) -> str:
    phase = str(payload.get("phase") or "")
    percent = max(0, min(100, _safe_int(str(payload.get("percent", 0)), 0)))
    item_current = _safe_int(str(payload.get("item_current", 0)), 0)
    item_total = _safe_int(str(payload.get("item_total", 0)), 0)
    message = str(payload.get("message") or "").strip()
    key_by_phase = {
        "content_check": "world_progress_content_check",
        "world_overview": "world_progress_overview",
        "location_graph": "world_progress_locations",
        "dungeon_subnodes": "world_progress_dungeon_subnodes",
        "story": "world_progress_story",
        "settlement": "world_progress_settlement",
        "characters": "world_progress_characters",
        "quests": "world_progress_quests",
        "initial_narration": "world_progress_initial",
        "completed": "world_progress_completed",
    }
    label = _ui_text(config_data, key_by_phase.get(phase, "world_progress_working"))
    if phase in {"location_graph", "dungeon_subnodes", "characters"} and item_total:
        if str(getattr(config_data, "language", "ja")).lower().startswith("en"):
            label = f"{label} ({item_current}/{item_total})"
        else:
            label = f"{label}（{item_current}/{item_total}）"
    elif not label or label.startswith("world_progress_"):
        label = message or _ui_text(config_data, "world_progress_working")
    return f"{label} ({percent}%)"


def _world_generation_phase_rank(phase: str) -> int:
    order = {
        "content_check": 0,
        "world_overview": 1,
        "location_graph": 2,
        "dungeon_subnodes": 3,
        "story": 4,
        "settlement": 5,
        "characters": 6,
        "quests": 7,
        "initial_narration": 8,
        "completed": 9,
    }
    return order.get(str(phase or ""), 0)


def _debug_device_summary(info, language: str = "ja") -> str:
    vram = getattr(info, "vram_size_gb", 0) or "-"
    ram = getattr(info, "memory_size_gb", 0) or "-"
    cuda = bool(getattr(info, "is_torch_cuda_usable", False))
    vulkan = bool(getattr(info, "is_vulkan_usable", False))
    recommended = str(getattr(info, "recommended_llm_backend", "") or "llama_cpp_completion_cpu")
    if str(language).lower().startswith("en"):
        available = "available"
        unavailable = "unavailable"
        return "\n".join(
            [
                f"VRAM: {vram}GB",
                f"RAM: {ram}GB",
                f"CUDA backend: {available if cuda else unavailable}",
                f"Vulkan backend: {available if vulkan else unavailable}",
                f"Recommended LLM backend: {recommended}",
            ]
        )
    available = "利用可能"
    unavailable = "利用不可"
    return "\n".join(
        [
            f"VRAM: {vram}GB",
            f"RAM: {ram}GB",
            f"CUDAバックエンド: {available if cuda else unavailable}",
            f"Vulkanバックエンド: {available if vulkan else unavailable}",
            f"推奨LLMバックエンド: {recommended}",
        ]
    )


def _language_options() -> tuple[str, ...]:
    return ("日本語", "English")


def _language_label(language: str) -> str:
    return "English" if str(language).strip().lower().startswith("en") else "日本語"


def _language_code(label: str) -> str:
    return "en" if str(label).strip().lower().startswith("english") else "ja"


def _llm_backend_options() -> tuple[str, ...]:
    return (
        "llama_cpp_completion_cpu",
        "llama_cpp_completion_vulkan",
        "llama_cpp_completion_cuda",
        "cloud_openai",
        "cloud_xai",
        "cloud_gemini",
    )


def _llm_backend_label_options(language: str) -> tuple[str, ...]:
    return tuple(_llm_backend_label(backend, language) for backend in _llm_backend_options())


def _llm_backend_label(backend: str, language: str = "ja") -> str:
    english = {
        "llama_cpp_completion_cpu": "Local LLM (CPU)",
        "llama_cpp_completion_vulkan": "Local LLM (Vulkan)",
        "llama_cpp_completion_cuda": "Local LLM (CUDA)",
        "cloud_openai": "Cloud (OpenAI)",
        "cloud_xai": "Cloud (xAI)",
        "cloud_gemini": "Cloud (Gemini)",
    }
    japanese = {
        "llama_cpp_completion_cpu": "ローカルLLM (CPU)",
        "llama_cpp_completion_vulkan": "ローカルLLM (Vulkan)",
        "llama_cpp_completion_cuda": "ローカルLLM (CUDA)",
        "cloud_openai": "クラウド (OpenAI)",
        "cloud_xai": "クラウド (xAI)",
        "cloud_gemini": "クラウド (Gemini)",
    }
    table = english if str(language).lower().startswith("en") else japanese
    return table.get(backend, backend)


def _llm_backend_from_label(label: str, language: str = "ja") -> str:
    text = str(label or "").strip()
    if text in _llm_backend_options():
        return text
    for backend in _llm_backend_options():
        if text in {_llm_backend_label(backend, language), _llm_backend_label(backend, "en"), _llm_backend_label(backend, "ja")}:
            return backend
    return text


def _llm_temperature_text(config_data) -> str:
    default = config_data.completion_parameters.get("default") if isinstance(config_data.completion_parameters, dict) else {}
    value = default.get("temperature", 0.9) if isinstance(default, dict) else 0.9
    return str(value)


def _llm_repeat_suppression_enabled(config_data) -> bool:
    default = config_data.completion_parameters.get("default") if isinstance(config_data.completion_parameters, dict) else {}
    if not isinstance(default, dict):
        return True
    value = default.get("repeat_penalty", None)
    if value is None:
        return True
    try:
        return float(value) > 1.0
    except (TypeError, ValueError):
        return True


def _selected_model_label(config_data) -> str:
    local_llm = config_data.local_llm
    selected_id = str(local_llm.get("selected_model_id") or "")
    for option in local_llm_model_options(config_data):
        if selected_id and option.model_id == selected_id:
            return _localized_model_label(option, config_data.language)
        model_path = str(local_llm.get("model_path") or "")
        if model_path and Path(model_path).name == option.path.name:
            return _localized_model_label(option, config_data.language)
    options = local_llm_model_options(config_data)
    return _localized_model_label(options[0], config_data.language) if options else ""


def _selected_sdxl_model_label(config_data) -> str:
    sdxl = config_data.sdxl
    selected_id = str(sdxl.get("selected_model_id") or "")
    for option in sdxl_model_options(config_data):
        if selected_id and option.model_id == selected_id:
            return _localized_model_label(option, config_data.language)
        checkpoint_path = str(sdxl.get("checkpoint_path") or "")
        if checkpoint_path and Path(checkpoint_path).name == option.path.name:
            return _localized_model_label(option, config_data.language)
    options = sdxl_model_options(config_data)
    return _localized_model_label(options[0], config_data.language) if options else ""


def _local_model_labels(config_data, language: str) -> tuple[str, ...]:
    return tuple(_localized_model_label(option, language) for option in local_llm_model_options(config_data))


def _sdxl_model_labels(config_data, language: str) -> tuple[str, ...]:
    return tuple(_localized_model_label(option, language) for option in sdxl_model_options(config_data))


def _localized_model_label(option, language: str) -> str:
    if language == "en":
        return model_label(option)
    suffix = "取得済み" if option.path.is_file() else "未取得"
    return f"{option.display_name} ({suffix})"


def _project_relative_path_text(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path(CONFIG_PATH).parent.resolve())).replace("\\", "/")
    except ValueError:
        try:
            return str(path.resolve().relative_to(PORTABLE_ROOT.resolve())).replace("\\", "/")
        except ValueError:
            return str(path)


def _cloud_model_options(provider: str, config_data=None) -> tuple[str, ...]:
    if config_data is not None:
        return cached_cloud_model_ids(config_data, provider)
    return {
        "openai": ("gpt-5.1-mini", "gpt-5.1", "gpt-5.1-nano"),
        "xai": ("grok-4.3", "grok-4.3-mini", "grok-4"),
        "gemini": ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"),
    }.get(provider, ())


def _cloud_default_env(provider: str) -> str:
    return {
        "openai": "OPENAI_API_KEY",
        "xai": "XAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }[provider]


def _quality_preset_options(image_config: dict) -> tuple[str, ...]:
    names = list(QUALITY_PRESETS.keys())
    custom = image_config.get("quality_presets")
    if isinstance(custom, dict):
        for name in custom:
            text = str(name)
            if text not in names:
                names.append(text)
    if "custom" not in names:
        names.append("custom")
    return tuple(names)


def _sampler_options() -> tuple[str, ...]:
    return (
        "euler",
        "euler_a",
        "heun",
        "dpm2",
        "dpm++2s_a",
        "dpm++2m",
        "dpm++2mv2",
        "ipndm",
        "ipndm_v",
        "lcm",
        "ddim_trailing",
        "tcd",
        "res_multistep",
        "res_2s",
        "er_sde",
        "euler_cfg_pp",
        "euler_a_cfg_pp",
    )


def _scheduler_options() -> tuple[str, ...]:
    return (
        "discrete",
        "karras",
        "exponential",
        "ays",
        "gits",
        "smoothstep",
        "sgm_uniform",
        "simple",
        "kl_optimal",
        "lcm",
        "bong_tangent",
        "ltx2",
    )


def _llm_backend_mode(backend: str) -> str:
    if backend.startswith("llama_cpp_completion"):
        return "local"
    if backend.startswith("cloud_"):
        return "cloud"
    return "unknown"


def _local_llm_server_path_text(local_llm: dict, kind: str) -> str:
    server_paths = local_llm.get("server_paths")
    if isinstance(server_paths, dict) and server_paths.get(kind):
        return str(server_paths[kind])
    explicit_key = f"{kind}_server_path"
    if local_llm.get(explicit_key):
        return str(local_llm[explicit_key])
    return str(local_llm.get("server_path", ""))


def _cloud_model_text(cloud_llm: dict, provider: str) -> str:
    provider_config = cloud_llm.get(provider)
    if isinstance(provider_config, dict) and provider_config.get("model"):
        return str(provider_config["model"])
    model_config = cloud_llm.get("model")
    if isinstance(model_config, dict):
        return str(model_config.get(provider, ""))
    return str(model_config or "")


def _cloud_key_value(config_data, provider: str) -> str:
    cloud_llm = config_data.cloud_llm
    provider_config = cloud_llm.get(provider)
    env_name = ""
    if isinstance(provider_config, dict):
        env_name = str(provider_config.get("api_key_env") or "")
    env_name = env_name or _cloud_default_env(provider)
    env_setting = config_data.environment_setting
    return str(
        env_setting.get(env_name)
        or env_setting.get(env_name.lower())
        or env_setting.get(f"{provider}_api_key")
        or ""
    )


def _cloud_key_status(config_data, provider: str) -> str:
    cloud_llm = config_data.cloud_llm
    provider_config = cloud_llm.get(provider)
    env_name = ""
    if isinstance(provider_config, dict):
        env_name = str(provider_config.get("api_key_env") or "")
    api_key_env = cloud_llm.get("api_key_env")
    if not env_name and isinstance(api_key_env, dict):
        env_name = str(api_key_env.get(provider) or "")
    env_name = env_name or _cloud_default_env(provider)
    env_setting = config_data.environment_setting
    configured = bool(
        env_setting.get(env_name)
        or env_setting.get(env_name.lower())
        or env_setting.get(f"{provider}_api_key")
        or os.environ.get(env_name)
    )
    return f"{env_name} ({'set' if configured else 'not set'})"


def _mode_display(mode: str, language: str = "ja") -> tuple[str, str, str]:
    if mode == "game_over":
        return tr_enum("mode", "game_over", language), "#1f1f1f", "#ffb0b0"
    if mode == "battle":
        return tr_enum("mode", "battle", language), "#5a2328", "#ffd7d7"
    if mode == "conversation":
        return tr_enum("mode", "conversation", language), "#183f46", "#cdf7ff"
    return tr_enum("mode", "exploration", language), "#3a3320", "#f8df95"


def _mode_choices_title(mode: str, language: str = "ja") -> str:
    if mode == "game_over":
        return tr_enum("mode_choices_title", "game_over", language)
    if mode == "battle":
        return tr_enum("mode_choices_title", "battle", language)
    if mode == "conversation":
        return tr_enum("mode_choices_title", "conversation", language)
    return tr_enum("mode_choices_title", "exploration", language)


def _mode_action_label(mode: str, language: str = "ja") -> str:
    if mode == "game_over":
        return tr_enum("mode_action_label", "game_over", language)
    if mode == "battle":
        return tr_enum("mode_action_label", "battle", language)
    if mode == "conversation":
        return tr_enum("mode_action_label", "conversation", language)
    return tr_enum("mode_action_label", "exploration", language)


def _choice_button_colors(mode: str) -> tuple[str, str]:
    if mode == "game_over":
        return "#2f2424", "#4a3030"
    if mode == "battle":
        return "#44242c", "#61313a"
    if mode == "conversation":
        return "#1f3f49", "#295560"
    return "#20283a", "#2d3850"


def _empty_choices_text(mode: str, language: str = "ja") -> str:
    if mode == "game_over":
        return tr_enum("mode_empty_choices", "game_over", language)
    if mode == "battle":
        return tr_enum("mode_empty_choices", "battle", language)
    if mode == "conversation":
        return tr_enum("mode_empty_choices", "conversation", language)
    return tr_enum("mode_empty_choices", "exploration", language)


def _initial_world_choices(world: WorldData, language: str = "ja") -> list[str]:
    choices = [
        tr_enum("initial_choice", "look_around", language),
        tr_enum("initial_choice", "move", language),
    ]
    return _limit_exploration_choices(choices)


def _limit_exploration_choices(choices: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for choice in choices:
        text = str(choice).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= MAX_EXPLORATION_CHOICES:
            break
    return result


def _is_direct_quest_accept_choice_text(choice: object) -> bool:
    text = str(choice or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if "掲示板" in text or "quest board" in lowered or "bulletin" in lowered:
        return False
    accept_words = ("受け", "受注", "引き受け", "引受", "請け")
    quest_words = ("依頼", "クエスト", "仕事")
    if any(word in text for word in accept_words) and any(word in text for word in quest_words):
        return True
    return any(word in lowered for word in ("accept", "take quest", "take the quest")) and any(
        word in lowered for word in ("quest", "request", "job")
    )


def _is_invalid_runtime_control_choice_text(choice: object) -> bool:
    lowered = str(choice or "").strip().casefold()
    return lowered in {"restart", "re-start", "retry", "リスタート", "再スタート", "やり直す", "ゲームを再開"}


def _is_trade_negotiation_text(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(
        keyword in text
        for keyword in (
            "値引",
            "値切",
            "まけて",
            "安く",
            "価格交渉",
            "値段交渉",
            "割引",
            "discount",
            "haggle",
            "bargain",
            "negotiate price",
            "lower price",
            "cheaper",
        )
    )


def _is_direct_craft_action_text(value: object) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text:
        return False
    craft_words = (
        "craft",
        "combine",
        "make",
        "create",
        "forge",
        "process",
        "加工",
        "合成",
        "クラフト",
        "作る",
        "作成",
        "製作",
        "鍛造",
        "強化",
    )
    connectors = ("と", "、", ",", "+", " and ", " with ", " using ", "から", "で")
    return any(word in lowered or word in text for word in craft_words) and any(
        connector in lowered or connector in text for connector in connectors
    )


def _simple_name_match(left: object, right: object) -> bool:
    left_text = "".join(str(left or "").casefold().split())
    right_text = "".join(str(right or "").casefold().split())
    if not left_text or not right_text:
        return False
    return left_text == right_text or left_text in right_text or right_text in left_text


if __name__ == "__main__":
    main()
