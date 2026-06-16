from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
import time
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .assets import check_runtime_assets, format_asset_report
from .cloud_models import cached_cloud_model_ids, fetch_cloud_model_ids
from .config import load_config
from .crashlog import install_crash_logging, install_tk_crash_logging
from .device import detect_device, device_report
from .game import DEFAULT_GUILD_NAME, GameEngine
from .generation_log import append_task_event, format_generation_log_detail, list_generation_logs
from .i18n import tr_enum, tr_enum_format
from .imagegen import QUALITY_PRESETS, MockSdxlBackend, create_image_backend
from .items import (
    add_item_stack,
    craft_items,
    generate_loot_items,
    generate_vendor_items,
    item_hp_delta,
    item_sp_delta,
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
from .paths import CONFIG_PATH, CRASHLOG_DIR, LOG_DIR, OUTPUT_DIR, PORTABLE_ROOT, RUNTIME_DIR
from .prompt_templates import PromptTemplateStore, resolve_prompt_template_dir
from .save_store import SaveStore
from .text_encoding import check_project_encoding, configure_stdio_encoding, format_encoding_report
from .ui_font import configure_ui_fonts
from .world_model import CharacterData, GameStateData, LocationData, WorldData


MAX_EXPLORATION_CHOICES = 5
GAME_BOTTOM_ROW_HEIGHT = 360
GAME_STATUS_PANEL_HEIGHT = 228
GAME_LOG_PANEL_HEIGHT = 176
CHARACTER_STAT_BASE = 8
CHARACTER_BONUS_POINTS = 12
CHARACTER_STAT_MAX = CHARACTER_STAT_BASE + CHARACTER_BONUS_POINTS


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
        self.geometry(f"{width}x{height}")
        self.minsize(960, 640)

        self.engine = GameEngine(
            create_llm_backend(self.config_data),
            create_image_backend(self.config_data),
            JsonStore(),
            self.save_store,
            PromptTemplateStore(resolve_prompt_template_dir(self.config_data.prompt_template_path)),
        )
        self.preview_image: ImageTk.PhotoImage | None = None
        self.stage_source_image: Image.Image | None = None
        self.stage_image: ImageTk.PhotoImage | None = None
        self.stage_image_refs: list[ImageTk.PhotoImage] = []
        self.roster_image_refs: list[ImageTk.PhotoImage] = []
        self.roster_hitboxes: dict[int, list[tuple[int, int, int, int, dict[str, object]]]] = {}
        self.character_preview_image: ImageTk.PhotoImage | None = None
        self.image_cache: dict[str, Image.Image] = {}
        self.choice_buttons: list[ttk.Button] = []
        self.task_buttons: list[tk.Widget] = []
        self.screens: dict[str, tk.Frame] = {}
        self.generation_log_entries = []
        self.task_sequence_id = 0
        self.current_task_id = 0
        self.current_task_name = ""
        self.current_task_started_at = 0.0
        self.current_task_cancel_requested = False
        self.task_tick_after_id: str | None = None
        self.visual_task_after_id: str | None = None
        self.typewriter_after_id: str | None = None
        self.typewriter_target_text = ""
        self.typewriter_index = 0
        self.log_typewriter_base_text = ""
        self.current_screen_name = "title"
        self.settings_back_screen = "title"
        self.generation_logs_back_screen = "title"
        self.battle_choice_menu = ""
        self.character_skill_entries: list[dict[str, object]] = []
        self.character_trait_entries: list[dict[str, object]] = []
        self.character_entry_tooltip: tk.Toplevel | None = None
        self.character_entry_tooltip_label: tk.Label | None = None

        self._build_menu()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._maybe_open_first_run_wizard)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        world_menu = tk.Menu(menu_bar, tearoff=False)
        world_menu.add_command(label=_ui_text(self.config_data, "menu_import_world"), command=self._import_world_dialog)
        world_menu.add_command(label=_ui_text(self.config_data, "menu_export_world"), command=self._export_world_dialog)
        menu_bar.add_cascade(label=_ui_text(self.config_data, "menu_world"), menu=world_menu)
        navigate_menu = tk.Menu(menu_bar, tearoff=False)
        navigate_menu.add_command(label=_ui_text(self.config_data, "menu_title"), command=lambda: self._show_screen("title"))
        navigate_menu.add_command(label=_ui_text(self.config_data, "menu_world_select"), command=lambda: self._show_screen("world_select"))
        navigate_menu.add_command(label=_ui_text(self.config_data, "menu_settings"), command=self._open_settings_screen)
        navigate_menu.add_command(label=_ui_text(self.config_data, "menu_generation_logs"), command=self._open_generation_logs_screen)
        navigate_menu.add_command(label=_ui_text(self.config_data, "menu_game"), command=lambda: self._show_screen("game"))
        menu_bar.add_cascade(label=_ui_text(self.config_data, "menu_navigate"), menu=navigate_menu)
        self.config(menu=menu_bar)

    def _build_ui(self) -> None:
        self.configure(bg="#0d1017")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        language = self.config_data.language
        self.status_var = tk.StringVar(value=tr_enum("app_status", "no_world_loaded", language))
        self.mode_name_var = tk.StringVar(value=tr_enum("mode", "exploration", language))
        self.choices_title_var = tk.StringVar(value=tr_enum("mode_choices_title", "exploration", language))
        self.action_label_var = tk.StringVar(value=tr_enum("mode_action_label", "exploration", language))
        self.task_status_var = tk.StringVar(value="")
        self.llm_backend_var = tk.StringVar(value=self.config_data.llm_backend)
        self.llm_context_size_var = tk.StringVar(value=str(self.config_data.llm_context_size))
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
        self.image_negative_background_var = tk.StringVar(value=str(negative_prompts.get("background", "")))
        self.image_negative_character_var = tk.StringVar(value=str(negative_prompts.get("character", "")))
        self.image_negative_monster_var = tk.StringVar(value=str(negative_prompts.get("monster", "")))
        self.ui_font_path_var = tk.StringVar(value=str(self.config_data.font_path))
        self.ui_font_size_var = tk.StringVar(value=str(self.config_data.font_size))
        self.ui_text_speed_var = tk.StringVar(value=str(self.config_data.ui_setting.get("text_speed", 0.02)))
        self.ui_language_var = tk.StringVar(value=_language_label(self.config_data.language))
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
        self.character_gold_var = tk.StringVar(value="0")
        self.character_ability_points_var = tk.StringVar(value=f"BP:{CHARACTER_BONUS_POINTS}")
        self.premise_var = tk.StringVar(value="Misty frontier, old magic, exploration")
        self.action_var = tk.StringVar(value=tr_enum("initial_choice", "look_around", language))
        self.layer_background_var = tk.BooleanVar(value=True)
        self.layer_characters_var = tk.BooleanVar(value=True)
        self.layer_monsters_var = tk.BooleanVar(value=True)
        self.save_slots = []
        self.world_slots = []
        self.character_setup_back_screen = "world_create"
        self.last_character_preview_path = ""
        self.last_character_preview_name = ""

        self.screen_container = tk.Frame(self, bg="#0d1017")
        self.screen_container.grid(row=0, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self._build_title_screen()
        self._build_world_create_screen()
        self._build_character_setup_screen_v2()
        self._build_world_select_screen()
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

    def _maybe_open_first_run_wizard(self) -> None:
        setup = self.config_data.raw.get("setup", {})
        if isinstance(setup, dict) and setup.get("completed"):
            return
        self._open_first_run_wizard()

    def _create_screen(self, name: str) -> tk.Frame:
        frame = tk.Frame(self.screen_container, bg="#0d1017")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.screens[name] = frame
        return frame

    def _show_screen(self, name: str) -> None:
        if name == "world_select":
            self._refresh_world_select_screen()
        if name == "settings":
            self._refresh_settings_screen()
        if name == "generation_logs":
            self._refresh_generation_log_screen()
        if name == "character_setup":
            self._refresh_character_setup_screen()
        self.screens[name].tkraise()
        self.current_screen_name = name
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
        if self.current_screen_name != "generation_logs":
            self.generation_logs_back_screen = self.current_screen_name
        self._show_screen("generation_logs")

    def _back_from_generation_logs_screen(self) -> None:
        self._show_screen(self.generation_logs_back_screen or "title")

    def _rebuild_settings_screen(self) -> None:
        existing = self.screens.get("settings")
        if existing is not None:
            existing.destroy()
        self._build_settings_screen()
        if self.current_screen_name == "settings":
            self._show_screen("settings")

    def _build_title_screen(self) -> None:
        screen = self._create_screen("title")
        panel = tk.Frame(screen, bg="#111722", padx=36, pady=32, highlightbackground="#2b3142", highlightthickness=1)
        panel.grid(row=0, column=0)
        panel.columnconfigure(0, weight=1)

        tk.Label(panel, text="Fantasia", bg="#111722", fg="#f4d27a", font=self.ui_fonts.bold(20)).grid(row=0, column=0, sticky="ew")
        tk.Label(panel, text=_ui_text(self.config_data, "title_subtitle"), bg="#111722", fg="#b8c0d5", font=self.ui_fonts.normal(-1)).grid(row=1, column=0, sticky="ew", pady=(0, 28))
        self._screen_button(panel, _ui_text(self.config_data, "title_continue_latest"), self._continue_latest, 2)
        self._screen_button(panel, _ui_text(self.config_data, "title_new_world"), lambda: self._show_screen("world_create"), 3)
        self._screen_button(panel, _ui_text(self.config_data, "title_world_select"), lambda: self._show_screen("world_select"), 4)
        self._screen_button(panel, _ui_text(self.config_data, "title_settings"), self._open_settings_screen, 5)
        self._screen_button(panel, _ui_text(self.config_data, "title_generation_logs"), self._open_generation_logs_screen, 6)
        self._screen_button(panel, _ui_text(self.config_data, "title_exit"), self._on_close, 7)

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

        actions = tk.Frame(panel, bg="#111722")
        actions.grid(row=6, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        self._screen_button(actions, _ui_text(self.config_data, "common_back"), lambda: self._show_screen("title"), 0, column=0, sticky="w")
        tk.Label(actions, textvariable=self.task_status_var, bg="#111722", fg="#b8c0d5").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.create_world_btn = self._screen_button(actions, _ui_text(self.config_data, "world_generate"), self._start_world_creation, 0, column=2)
        self.task_buttons.append(self.create_world_btn)

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
        self.character_traits_text.insert("1.0", "冷静 | 危機でも判断力を失いにくい | 2\n旅慣れ | 野外行動に慣れている | 1")
        self.character_skills_text.insert("1.0", "一閃 | physical | 武器で素早く斬り込む基本技 | 5\n応急手当 | other | 簡単な治療で体勢を立て直す | 3")

        actions = tk.Frame(panel, bg="#111722")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        actions.columnconfigure(1, weight=1)
        self._screen_button(actions, "Back", self._back_from_character_setup, 0, column=0, sticky="w")
        tk.Label(actions, textvariable=self.task_status_var, bg="#111722", fg="#b8c0d5").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.start_game_btn = self._screen_button(actions, "Start Game", self._start_game_with_character, 0, column=2, sticky="e")
        self.task_buttons.append(self.start_game_btn)

    def _build_world_select_screen(self) -> None:
        screen = self._create_screen("world_select")
        screen.rowconfigure(1, weight=1)

        header = self._screen_topbar(screen, _ui_text(self.config_data, "world_select_title"))
        self._screen_button(header, _ui_text(self.config_data, "common_back"), self._back_from_settings_screen, 0, column=1, sticky="e")

        content = tk.Frame(screen, bg="#0d1017", padx=14, pady=14)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(1, weight=1)

        tk.Label(content, text=_ui_text(self.config_data, "saved_games"), bg="#0d1017", fg="#f4d27a", font=self.ui_fonts.bold(-2)).grid(row=0, column=0, sticky="w")
        tk.Label(content, text=_ui_text(self.config_data, "world_data"), bg="#0d1017", fg="#f4d27a", font=self.ui_fonts.bold(-2)).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.save_listbox = tk.Listbox(content, bg="#111722", fg="#e6edf7", selectbackground="#2d3850", relief="flat")
        self.save_listbox.grid(row=1, column=0, sticky="nsew", pady=(6, 10), padx=(0, 6))
        self.world_listbox = tk.Listbox(content, bg="#111722", fg="#e6edf7", selectbackground="#2d3850", relief="flat")
        self.world_listbox.grid(row=1, column=1, sticky="nsew", pady=(6, 10), padx=(6, 0))
        tk.Label(content, text=_ui_text(self.config_data, "world_start_note"), bg="#0d1017", fg="#b8c0d5").grid(row=2, column=1, sticky="w", padx=(12, 0))
        self._screen_button(content, _ui_text(self.config_data, "load_save"), self._load_selected_save, 3, column=0, sticky="w")
        self._screen_button(content, _ui_text(self.config_data, "common_refresh"), self._refresh_world_select_screen, 4, column=0, sticky="w")
        self._screen_button(content, _ui_text(self.config_data, "start_selected_world"), self._start_selected_world, 4, column=1, sticky="e")
        self._screen_button(content, _ui_text(self.config_data, "import_world"), self._import_world_dialog, 5, column=1, sticky="e")

    def _build_settings_screen(self) -> None:
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
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_generation_logs"), self._open_generation_logs_screen, 0, column=4)
        self._screen_button(storage_actions, _ui_text(self.config_data, "settings_back"), self._back_from_settings_screen, 0, column=6, sticky="e")

    def _build_generation_log_screen(self) -> None:
        screen = self._create_screen("generation_logs")
        screen.rowconfigure(1, weight=1)

        header = self._screen_topbar(screen, _ui_text(self.config_data, "generation_logs_title"))
        self._screen_button(header, _ui_text(self.config_data, "common_game"), lambda: self._show_screen("game"), 0, column=1, sticky="e")
        self._screen_button(header, _ui_text(self.config_data, "common_settings"), self._open_settings_screen, 0, column=2, sticky="e")
        self._screen_button(header, _ui_text(self.config_data, "common_back"), self._back_from_generation_logs_screen, 0, column=3, sticky="e")

        panel = tk.Frame(screen, bg="#0d1017", padx=14, pady=14)
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=2)
        panel.columnconfigure(1, weight=5)
        panel.rowconfigure(1, weight=1)

        tk.Label(panel, text=_ui_text(self.config_data, "generation_logs_entries"), bg="#0d1017", fg="#f4d27a", font=self.ui_fonts.bold(-3)).grid(row=0, column=0, sticky="w")
        tk.Label(panel, text=_ui_text(self.config_data, "generation_logs_detail"), bg="#0d1017", fg="#f4d27a", font=self.ui_fonts.bold(-3)).grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.generation_log_listbox = tk.Listbox(
            panel,
            bg="#111722",
            fg="#e6edf7",
            selectbackground="#2d3850",
            relief="flat",
            exportselection=False,
        )
        self.generation_log_listbox.grid(row=1, column=0, sticky="nsew", pady=(6, 10), padx=(0, 6))
        self.generation_log_listbox.bind("<<ListboxSelect>>", lambda _event: self._show_selected_generation_log())

        self.generation_log_text = tk.Text(
            panel,
            wrap="none",
            bg="#111722",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            padx=10,
            pady=8,
            font=self.ui_fonts.normal(-5),
        )
        self.generation_log_text.grid(row=1, column=1, sticky="nsew", pady=(6, 10), padx=(6, 0))
        self.generation_log_text.configure(state="disabled")

        actions = tk.Frame(panel, bg="#0d1017")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(5, weight=1)
        self._screen_button(actions, _ui_text(self.config_data, "common_refresh"), self._refresh_generation_log_screen, 0, column=0, sticky="w")
        self._screen_button(actions, _ui_text(self.config_data, "generation_logs_clear_selection"), self._clear_generation_log_selection, 0, column=1, sticky="w")

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
        self.image_btn = ttk.Button(tools, text="Scene", command=self._generate_image)
        self.image_btn.grid(row=1, column=0, sticky="ew", pady=(6, 4), padx=(0, 4))
        self.character_image_btn = ttk.Button(tools, text="Character", command=self._generate_character_image)
        self.character_image_btn.grid(row=1, column=1, sticky="ew", pady=(6, 4), padx=(4, 0))
        self.monster_image_btn = ttk.Button(tools, text="Monster", command=self._generate_monster_image)
        self.monster_image_btn.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.save_btn = ttk.Button(tools, text="Save", command=self._save_game)
        self.save_btn.grid(row=2, column=1, sticky="ew", padx=(4, 0))
        self.logs_btn = ttk.Button(tools, text="Logs", command=lambda: self._show_screen("generation_logs"))
        self.logs_btn.grid(row=3, column=0, sticky="ew", pady=(4, 0), padx=(0, 4))
        self.cancel_task_btn = ttk.Button(tools, text="Cancel", command=self._cancel_current_task, state="disabled")
        self.cancel_task_btn.grid(row=3, column=1, sticky="ew", pady=(4, 0), padx=(4, 0))
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

        self.action_btn = ttk.Button(action_bar, text="Send", command=self._send_action)
        self.action_btn.grid(row=0, column=2)
        self.task_buttons.append(self.action_btn)
        self._refresh_choices()
        self._refresh_status_panel()
        self._render_stage()

    def _build_character_setup_screen_v2(self) -> None:
        screen = self._create_screen("character_setup")
        screen.configure(bg="#000000")
        screen.columnconfigure(0, weight=3)
        screen.columnconfigure(1, weight=4)
        screen.columnconfigure(2, weight=3)
        screen.rowconfigure(1, weight=1)

        tk.Label(
            screen,
            text=_ui_text(self.config_data, "character_setup_title"),
            bg="#000000",
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(8),
        ).grid(row=0, column=0, sticky="ew", padx=(64, 18), pady=(34, 18))

        left = tk.Frame(screen, bg="#000000")
        left.grid(row=1, column=0, sticky="nsew", padx=(64, 28), pady=(0, 28))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        left.rowconfigure(4, weight=1)

        name_row = tk.Frame(left, bg="#000000")
        name_row.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        name_row.columnconfigure(0, weight=1)
        self.character_name_entry = tk.Entry(
            name_row,
            textvariable=self.player_var,
            bg="#070707",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            font=self.ui_fonts.normal(0),
        )
        self.character_name_entry.grid(row=0, column=0, sticky="ew", ipady=8)
        self.character_gender_label_var = tk.StringVar(value=_gender_button_label(self.character_gender_var.get()))
        self.character_gender_btn = self._instant_button(
            name_row,
            self.character_gender_label_var.get(),
            self._cycle_character_gender,
        )
        self.character_gender_btn.grid(row=0, column=1, sticky="ew", padx=(18, 0), ipady=7)
        self._instant_button(name_row, "◇", self._reset_character_preset).grid(row=0, column=2, sticky="ew", padx=(12, 0), ipady=7)

        self.character_backstory_text = self._instant_labeled_text(left, _ui_text(self.config_data, "character_backstory"), 1, height=8)
        self.character_look_text = self._instant_labeled_text(left, _ui_text(self.config_data, "character_appearance"), 3, height=7)

        age_panel = self._instant_panel(left, 5, 0, sticky="ew", pady=(10, 18))
        age_panel.columnconfigure(1, weight=1)
        tk.Label(age_panel, text=_ui_text(self.config_data, "character_age"), bg="#050505", fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=0, column=0, padx=48, pady=22)
        tk.Label(age_panel, textvariable=self.character_age_var, bg="#050505", fg="#f2f2f2", font=self.ui_fonts.bold(-2)).grid(row=0, column=1)
        self._instant_button(age_panel, "-", lambda: self._adjust_character_number(self.character_age_var, -1, 1, 120)).grid(row=0, column=2, padx=(8, 4), pady=9, ipadx=13, ipady=9)
        self._instant_button(age_panel, "+", lambda: self._adjust_character_number(self.character_age_var, 1, 1, 120)).grid(row=0, column=3, padx=(4, 18), pady=9, ipadx=13, ipady=9)

        bottom_left = tk.Frame(left, bg="#000000")
        bottom_left.grid(row=6, column=0, sticky="ew")
        bottom_left.columnconfigure(0, weight=1)
        bottom_left.columnconfigure(1, weight=1)
        self._instant_button(bottom_left, _ui_text(self.config_data, "common_back"), self._back_from_character_setup).grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=12)
        self._instant_button(bottom_left, _ui_text(self.config_data, "character_preset"), self._reset_character_preset).grid(row=0, column=1, sticky="ew", padx=(10, 0), ipady=12)

        center = tk.Frame(screen, bg="#000000")
        center.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(28, 28), pady=(60, 28))
        center.columnconfigure(0, weight=1)
        center.rowconfigure(0, weight=1)
        self.character_preview_canvas = tk.Canvas(
            center,
            bg="#050505",
            highlightbackground="#d8d4cf",
            highlightcolor="#d8d4cf",
            highlightthickness=1,
            relief="flat",
        )
        self.character_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.character_preview_canvas.bind("<Configure>", lambda _event: self._render_character_preview())
        preview_actions = tk.Frame(center, bg="#000000")
        preview_actions.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        preview_actions.columnconfigure(0, weight=1)
        preview_actions.columnconfigure(1, weight=1)
        self.character_preview_generate_btn = self._instant_button(preview_actions, _ui_text(self.config_data, "character_preview_generate"), self._generate_character_preview_image)
        self.character_preview_generate_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=10)
        self.character_preview_refresh_btn = self._instant_button(preview_actions, _ui_text(self.config_data, "character_preview_refresh"), self._render_character_preview)
        self.character_preview_refresh_btn.grid(row=0, column=1, sticky="ew", padx=(8, 0), ipady=10)
        self.task_buttons.append(self.character_preview_generate_btn)

        right = tk.Frame(screen, bg="#000000")
        right.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(28, 64), pady=(60, 28))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        stats_panel = self._instant_panel(right, 0, 0, sticky="ew", pady=(0, 20))
        stats_panel.columnconfigure(1, weight=1)
        stat_rows = (
            (_ui_text(self.config_data, "character_strength"), self.character_str_var, 0),
            (_ui_text(self.config_data, "character_dexterity"), self.character_dex_var, 1),
            (_ui_text(self.config_data, "character_constitution"), self.character_con_var, 2),
            (_ui_text(self.config_data, "character_intelligence"), self.character_int_var, 3),
            (_ui_text(self.config_data, "character_wisdom"), self.character_wis_var, 4),
            (_ui_text(self.config_data, "character_charisma"), self.character_cha_var, 5),
            (_ui_text(self.config_data, "character_gold"), self.character_gold_var, 6),
        )
        for label, variable, row in stat_rows:
            self._character_stat_row(stats_panel, label, variable, row)

        skills_panel = self._instant_panel(right, 1, 0, sticky="nsew", pady=(0, 20))
        skills_panel.columnconfigure(0, weight=1)
        skills_panel.rowconfigure(1, weight=1)
        tk.Label(skills_panel, text=_ui_text(self.config_data, "character_skills"), bg="#050505", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", pady=(10, 6))
        self.character_skills_text = self._instant_text(skills_panel, 1, 0, height=4, padx=48, pady=(0, 8))
        skills_actions = tk.Frame(skills_panel, bg="#050505")
        skills_actions.grid(row=2, column=0, sticky="ew", padx=48, pady=(0, 12))
        skills_actions.columnconfigure(0, weight=1)
        skills_actions.columnconfigure(1, weight=1)
        self._instant_button(skills_actions, _ui_text(self.config_data, "character_edit"), lambda: self._open_character_list_editor("skills")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._instant_button(skills_actions, _ui_text(self.config_data, "common_generate"), lambda: self._generate_character_setup_entries("skills")).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        traits_panel = self._instant_panel(right, 2, 0, sticky="nsew", pady=(0, 20))
        traits_panel.columnconfigure(0, weight=1)
        traits_panel.rowconfigure(1, weight=1)
        tk.Label(traits_panel, text=_ui_text(self.config_data, "character_traits"), bg="#050505", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", pady=(10, 6))
        self.character_traits_text = self._instant_text(traits_panel, 1, 0, height=3, padx=48, pady=(0, 8))
        traits_actions = tk.Frame(traits_panel, bg="#050505")
        traits_actions.grid(row=2, column=0, sticky="ew", padx=48, pady=(0, 14))
        traits_actions.columnconfigure(0, weight=1)
        traits_actions.columnconfigure(1, weight=1)
        self._instant_button(traits_actions, _ui_text(self.config_data, "character_edit"), lambda: self._open_character_list_editor("traits")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._instant_button(traits_actions, _ui_text(self.config_data, "common_generate"), lambda: self._generate_character_setup_entries("traits")).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ability_panel = self._instant_panel(right, 3, 0, sticky="ew", pady=(0, 20))
        tk.Label(
            ability_panel,
            textvariable=self.character_ability_points_var,
            bg="#050505",
            fg="#f2f2f2",
            font=self.ui_fonts.bold(-2),
        ).grid(row=0, column=0, sticky="ew", pady=15)

        start_panel = self._instant_panel(right, 4, 0, sticky="ew")
        self.start_game_btn = self._instant_button(start_panel, _ui_text(self.config_data, "character_start_game"), self._start_game_with_character, fg="#f2f2f2")
        self.start_game_btn.grid(row=0, column=0, sticky="ew", padx=14, pady=14, ipady=20)
        self.task_buttons.append(self.start_game_btn)

        self.character_backstory_text.insert("1.0", "辺境の村で育った駆け出しの冒険者。")
        self.character_look_text.insert("1.0", "short hair, clear eyes, leather armor, practical travel cloak")
        self.character_personality_text = tk.Text(left, height=1)
        self.character_personality_text.insert("1.0", "慎重だが、困っている人を見捨てられない。")
        self._set_character_entries(
            "skills",
            _parse_character_skills(
                "一閃 | physical | 武器で素早く斬り込む基本技 | 5 | 2\n"
                "応急手当 | support | 簡単な治療で体勢を立て直す | 3 | 1"
            ),
        )
        self._set_character_entries(
            "traits",
            _parse_character_traits(
                "冷静 | 危機でも判断力を失いにくい | 1\n"
                "旅慣れ | 野外行動に慣れている | 1"
            ),
        )
        self._bind_character_entry_tooltip(self.character_skills_text, "skills")
        self._bind_character_entry_tooltip(self.character_traits_text, "traits")

        self.character_world_summary_text = tk.Text(center, height=1)
        self.character_world_summary_text.configure(state="disabled")
        for variable in (
            self.character_str_var,
            self.character_dex_var,
            self.character_con_var,
            self.character_int_var,
            self.character_wis_var,
            self.character_cha_var,
            self.character_gold_var,
            self.character_age_var,
            self.player_var,
            self.character_gender_var,
            self.character_category_var,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_character_setup_points())
        self._refresh_character_setup_points()

    def _build_game_screen_v2(self) -> None:
        screen = self._create_screen("game")
        screen.configure(bg="#000000")
        screen.columnconfigure(0, weight=2)
        screen.columnconfigure(1, weight=5)
        screen.columnconfigure(2, weight=2)
        screen.rowconfigure(0, weight=1)
        screen.rowconfigure(1, weight=0, minsize=GAME_BOTTOM_ROW_HEIGHT)

        left_choices = tk.Frame(screen, bg="#000000")
        left_choices.grid(row=0, column=0, sticky="nsew", padx=(38, 28), pady=(84, 22))
        left_choices.columnconfigure(0, weight=1)
        left_choices.rowconfigure(0, weight=1)
        self.choice_frame = tk.Frame(left_choices, bg="#000000")
        self.choice_frame.grid(row=0, column=0, sticky="nsew")
        self.choice_frame.columnconfigure(0, weight=1)

        stage_frame = tk.Frame(screen, bg="#000000", highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=1)
        stage_frame.grid(row=0, column=1, sticky="nsew", padx=(28, 28), pady=(64, 22))
        stage_frame.rowconfigure(0, weight=1)
        stage_frame.columnconfigure(0, weight=1)
        self.stage_canvas = tk.Canvas(stage_frame, bg="#000000", highlightthickness=0)
        self.stage_canvas.grid(row=0, column=0, sticky="nsew")
        self.stage_canvas.bind("<Configure>", lambda _event: self._render_stage())

        right_roster = tk.Frame(screen, bg="#000000")
        right_roster.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(28, 38), pady=(64, 28))
        right_roster.columnconfigure(0, weight=1)
        right_roster.rowconfigure(0, weight=2)
        right_roster.rowconfigure(1, weight=1)
        self.npc_roster_canvas = tk.Canvas(right_roster, bg="#000000", highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=1)
        self.npc_roster_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.npc_roster_canvas.bind("<Configure>", lambda _event: self._render_actor_rosters())
        self.npc_roster_canvas.bind("<Button-1>", self._on_roster_click)
        self.player_roster_canvas = tk.Canvas(right_roster, bg="#000000", highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=1)
        self.player_roster_canvas.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.player_roster_canvas.bind("<Configure>", lambda _event: self._render_actor_rosters())
        self.player_roster_canvas.bind("<Button-1>", self._on_roster_click)

        player_panel = self._instant_panel(screen, 1, 0, sticky="nsew", padx=(38, 28), pady=(22, 28))
        player_panel.columnconfigure(0, weight=1)
        player_panel.rowconfigure(0, weight=0, minsize=GAME_STATUS_PANEL_HEIGHT)
        self.player_status_text = self._instant_text(
            player_panel,
            0,
            0,
            height=8,
            padx=10,
            pady=(10, 4),
            fixed_height=GAME_STATUS_PANEL_HEIGHT,
        )
        tool_row = tk.Frame(player_panel, bg="#050505")
        tool_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(12, 8))
        for column in range(7):
            tool_row.columnconfigure(column, weight=1)
        self.inventory_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_inventory"), self._open_player_inventory)
        self.loot_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_loot"), self._open_loot_inventory)
        self.trade_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_trade"), self._open_trade_inventory)
        self.craft_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_craft"), self._open_craft_window)
        self.save_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_save"), self._save_game)
        self.logs_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_logs"), self._open_generation_logs_screen)
        self.cancel_task_btn = self._instant_button(tool_row, _ui_text(self.config_data, "game_cancel"), self._cancel_current_task)
        for column, button in enumerate((self.inventory_btn, self.loot_btn, self.trade_btn, self.craft_btn, self.save_btn, self.logs_btn, self.cancel_task_btn)):
            button.grid(row=0, column=column, sticky="ew", padx=3, pady=3)
        self.cancel_task_btn.configure(state="disabled")
        self.task_buttons.extend([self.inventory_btn, self.loot_btn, self.trade_btn, self.craft_btn, self.save_btn])

        center_bottom = tk.Frame(screen, bg="#000000")
        center_bottom.grid(row=1, column=1, sticky="nsew", padx=(28, 28), pady=(22, 28))
        center_bottom.columnconfigure(0, weight=1)
        center_bottom.rowconfigure(0, weight=0, minsize=GAME_LOG_PANEL_HEIGHT)
        self.log_text = self._instant_text(
            center_bottom,
            0,
            0,
            height=8,
            padx=12,
            pady=(0, 8),
            fixed_height=GAME_LOG_PANEL_HEIGHT,
        )
        self._replace_text(self.log_text, _ui_text(self.config_data, "game_initial_log"))

        action_bar = tk.Frame(center_bottom, bg="#000000")
        action_bar.grid(row=1, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        self.action_entry = tk.Entry(
            action_bar,
            textvariable=self.action_var,
            bg="#050505",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            font=self.ui_fonts.normal(-1),
        )
        self.action_entry.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 10))
        self.action_entry.bind("<Return>", lambda _event: self._send_action())
        self.action_btn = self._instant_button(action_bar, _ui_text(self.config_data, "game_send"), self._send_action)
        self.action_btn.grid(row=0, column=1, sticky="ns", ipadx=18)
        self.task_buttons.append(self.action_btn)

        task_row = tk.Frame(center_bottom, bg="#000000")
        task_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        task_row.columnconfigure(0, weight=1)
        self.task_status_label = tk.Label(task_row, textvariable=self.task_status_var, bg="#000000", fg="#d8d4cf", anchor="w", font=self.ui_fonts.normal(-5))
        self.task_status_label.grid(row=0, column=0, sticky="ew")
        self.task_progress = ttk.Progressbar(task_row, mode="indeterminate")
        self.task_progress.grid(row=0, column=1, sticky="ew", padx=(8, 0))

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
        panel = tk.Frame(parent, bg="#050505", highlightbackground="#d8d4cf", highlightcolor="#d8d4cf", highlightthickness=1)
        panel.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky=sticky, padx=padx, pady=pady)
        return panel

    def _instant_button(self, parent: tk.Widget, text: str, command, fg: str = "#f2f2f2") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#050505",
            fg=fg,
            activebackground="#181818",
            activeforeground="#ffffff",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#d8d4cf",
            font=self.ui_fonts.bold(-3),
            padx=8,
            pady=4,
        )

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
            holder_bg = "#000000"
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
            bg="#050505",
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
        tk.Label(frame, text=label, bg="#050505", fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        return self._instant_text(frame, 1, 0, height=height, padx=8, pady=(4, 8))

    def _character_stat_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, row: int) -> None:
        tk.Label(parent, text=label, bg="#050505", fg="#f2f2f2", anchor="w", font=self.ui_fonts.bold(-2)).grid(row=row, column=0, sticky="ew", padx=(72, 8), pady=(8 if row == 0 else 2, 2))
        tk.Label(parent, textvariable=variable, bg="#050505", fg="#f2f2f2", anchor="center", width=4, font=self.ui_fonts.bold(-2)).grid(row=row, column=1, sticky="ew")
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
        self.character_gold_var.set("0")
        if hasattr(self, "character_backstory_text"):
            self.character_backstory_text.delete("1.0", "end")
            self.character_backstory_text.insert("1.0", "辺境の村で育った駆け出しの冒険者。")
        if hasattr(self, "character_look_text"):
            self.character_look_text.delete("1.0", "end")
            self.character_look_text.insert("1.0", "short hair, clear eyes, leather armor, practical travel cloak")
        if hasattr(self, "character_skills_text"):
            self._set_character_entries(
                "skills",
                _parse_character_skills(
                    "一閃 | physical | 武器で素早く斬り込む基本技 | 5 | 2\n"
                    "応急手当 | support | 簡単な治療で体勢を立て直す | 3 | 1"
                ),
            )
        if hasattr(self, "character_traits_text"):
            self._set_character_entries(
                "traits",
                _parse_character_traits(
                    "冷静 | 危機でも判断力を失いにくい | 1\n"
                    "旅慣れ | 野外行動に慣れている | 1"
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
        canvas.create_rectangle(0, 0, width, height, fill="#050505", outline="")
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
        character = self.engine.state.world_data.characters.get(self.player_var.get().strip())
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
        if self.engine.state.world_data.world_name == "unknown":
            self._show_error(ValueError(_ui_text(self.config_data, "character_need_world_image")))
            return
        character = self._character_from_setup()

        def task():
            character.flags["is_player"] = True
            character.flags.setdefault("source", "character_setup_preview")
            self.engine.state.world_data.characters[character.name] = character
            return self.engine.generate_character_image(character.name, save_game=False)

        def done(result) -> None:
            self.last_character_preview_path = str(result.path)
            self.last_character_preview_name = self.player_var.get().strip()
            self.image_cache.clear()
            self._render_character_preview()
            self._append_log("\n" + _ui_text(self.config_data, "log_character_preview").format(path=result.path) + "\n")

        self._run_task(_ui_text(self.config_data, "character_generating_preview"), task, done)

    def _open_character_list_editor(self, kind: str) -> None:
        source = self.character_skills_text if kind == "skills" else self.character_traits_text
        title = _ui_text(self.config_data, "character_skill_settings" if kind == "skills" else "character_trait_settings")
        hint = (
            _ui_text(self.config_data, "character_skill_hint")
            if kind == "skills"
            else _ui_text(self.config_data, "character_trait_hint")
        )
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg="#000000")
        dialog.geometry("720x520")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text=hint,
            bg="#000000",
            fg="#d8d4cf",
            anchor="w",
            font=self.ui_fonts.bold(-2),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        editor = tk.Text(
            dialog,
            wrap="word",
            bg="#050505",
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
        else:
            editor.insert("1.0", source.get("1.0", "end-1c"))

        actions = tk.Frame(dialog, bg="#000000")
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "common_generate"), lambda: self._generate_character_setup_entries(kind, editor)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_apply"), lambda: self._apply_character_list_editor(kind, editor, dialog)).grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _apply_character_list_editor(self, kind: str, editor: tk.Text, dialog: tk.Toplevel) -> None:
        self._set_character_list_text(kind, editor.get("1.0", "end").strip())
        dialog.destroy()
        self._render_character_preview()

    def _generate_character_setup_entries(self, kind: str, target_text: tk.Text | None = None) -> None:
        if self.engine.state.world_data.world_name == "unknown":
            self._show_error(ValueError(_ui_text(self.config_data, "character_need_world_details")))
            return
        character = self._character_from_setup()

        def task():
            if kind == "skills":
                return self.engine.generate_character_setup_skills(character)
            return self.engine.generate_character_setup_traits(character)

        def done(entries) -> None:
            normalized = _normalise_character_skills(entries) if kind == "skills" else _normalise_character_traits(entries)
            text = _format_character_skills(normalized) if kind == "skills" else _format_character_traits(normalized)
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
        entries = _normalise_character_skills(entries) if kind == "skills" else _normalise_character_traits(entries)
        if kind == "skills":
            self.character_skill_entries = entries
        else:
            self.character_trait_entries = entries
        widget = self.character_skills_text if kind == "skills" else self.character_traits_text
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", _format_character_entry_names(entries))
        widget.configure(state="disabled")

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
                bg="#050505",
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
        label.configure(text=_character_entry_tooltip_text(entries[line], kind))
        tooltip.geometry(f"+{event.x_root + 18}+{event.y_root + 14}")
        tooltip.deiconify()

    def _hide_character_entry_tooltip(self, _event=None) -> None:
        if self.character_entry_tooltip is not None and self.character_entry_tooltip.winfo_exists():
            self.character_entry_tooltip.withdraw()

    def _player_status_text(self) -> str:
        state = self.engine.state
        player = self._player_character_dict()
        attrs = _character_attributes(player)
        gold = int(player.get("gold") or state.gold or 0)
        progress = self.engine.player_progress()
        time_label = self.engine.current_time_label()
        combat_stats = self.engine.player_combat_stats()
        atk = int(combat_stats.get("attack") or 0)
        atk_bonus = int(combat_stats.get("attack_bonus") or 0)
        defense = int(combat_stats.get("defense") or 0)
        defense_bonus = int(combat_stats.get("defense_bonus") or 0)
        stamina = attrs.get("sta", attrs.get("stamina", 10))
        player_extra = player.get("extra") if isinstance(player.get("extra"), dict) else {}
        max_sp_value = self.engine.state.extra.get("max_sp")
        if max_sp_value is None:
            max_sp_value = player.get("max_sp") or player_extra.get("max_sp")
        current_sp_value = self.engine.state.extra.get("current_sp")
        if current_sp_value is None:
            current_sp_value = player_extra.get("current_sp")
        max_sp = _safe_int(max_sp_value, 0)
        current_sp = _safe_int(current_sp_value, max_sp)
        location = state.current_location or state.world_data.starting_location or "unknown"
        language = self.config_data.language
        label = lambda key: tr_enum("status_field", key, language)
        lines = [
            f"{label('attack')}:{atk}({atk_bonus:+d})",
            f"{label('defense')}:{defense}({defense_bonus:+d})",
            f"{label('level')}:{progress.get('level', 1)}",
            f"{label('exp')}:{progress.get('exp', 0)}/{progress.get('next_exp', 5)}",
            f"{label('gold')}:{gold}",
            f"{label('time')}:{time_label}",
            f"{label('stamina')}:{stamina}/10",
            f"{label('sp')}:{current_sp}/{max_sp or '?'}",
            f"{label('location')}:{location}",
        ]
        if state.active_quest:
            lines.append(f"{label('quest')}:{state.active_quest}")
        return "\n".join(lines)

    def _player_character_dict(self) -> dict[str, object]:
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            return self.engine.state.party[0]
        player = self.engine.state.world_data.characters.get(self.engine.state.player_name)
        return player.to_dict() if player else {}

    def _render_actor_rosters(self) -> None:
        if not hasattr(self, "npc_roster_canvas"):
            return
        self.roster_image_refs = []
        self._draw_roster_canvas(self.npc_roster_canvas, self._npc_roster_items(), "NPC / ENEMY")
        self._draw_roster_canvas(self.player_roster_canvas, self._player_roster_items(), "PLAYER")

    def _draw_roster_canvas(self, canvas: tk.Canvas, items: list[dict[str, object]], title: str) -> None:
        canvas.delete("all")
        self.roster_hitboxes[id(canvas)] = []
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.create_rectangle(0, 0, width, height, fill="#050505", outline="")
        language = self.config_data.language
        is_player_panel = title == "PLAYER"
        if not items:
            canvas.create_text(
                width // 2,
                height // 2,
                text=tr_enum("roster", "no_player" if is_player_panel else "no_npc", language),
                fill="#575757",
                font=self.ui_fonts.bold(-2),
            )
            return
        visible_items = items[:1] if is_player_panel else items[:4]
        row_height = height if is_player_panel else max(76, min(116, height // max(1, min(len(items), 4))))
        for index, item in enumerate(visible_items):
            top = index * row_height
            bottom = min(height, top + row_height)
            self.roster_hitboxes[id(canvas)].append((0, top, width, bottom, item))
            canvas.create_rectangle(0, top, width, bottom, fill="#050505", outline="#d8d4cf")
            image = item.get("image")
            image_box = min(
                max(56, int(width * (0.42 if is_player_panel else 0.28))),
                max(56, row_height - 12),
                132 if is_player_panel else 96,
            )
            if isinstance(image, Image.Image):
                display = _cover_image(image, image_box, image_box)
                photo = ImageTk.PhotoImage(display)
                self.roster_image_refs.append(photo)
                canvas.create_image(8, top + max(6, (row_height - image_box) // 2), image=photo, anchor="nw")
            elif is_player_panel:
                canvas.create_rectangle(8, top + max(6, (row_height - image_box) // 2), 8 + image_box, top + max(6, (row_height - image_box) // 2) + image_box, outline="#575757")
                canvas.create_text(8 + image_box // 2, top + row_height // 2, text=tr_enum("roster", "face", language), fill="#575757", font=self.ui_fonts.bold(-5))
            text_x = image_box + 24 if width > 240 else 74
            name = str(item.get("name") or tr_enum("roster", "unknown", language))
            subtitle = str(item.get("subtitle") or "")
            hp = str(item.get("hp") or "")
            sp = str(item.get("sp") or "")
            canvas.create_text(width - 8, top + 14, text=hp, fill="#f2f2f2", anchor="ne", font=self.ui_fonts.bold(-4))
            if sp:
                canvas.create_text(width - 8, top + 34, text=sp, fill="#a8d8ff", anchor="ne", font=self.ui_fonts.bold(-4))
            name_y = top + (58 if sp else 38)
            subtitle_y = name_y + 24
            canvas.create_text(width - 8, name_y, text=name, fill="#f2f2f2", anchor="ne", font=self.ui_fonts.bold(-2), width=max(80, width - text_x - 12))
            if subtitle:
                canvas.create_text(width - 8, subtitle_y, text=subtitle, fill="#d8d4cf", anchor="ne", font=self.ui_fonts.normal(-5), width=max(80, width - text_x - 12))

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
        dialog = tk.Toplevel(self)
        dialog.title(tr_enum_format("roster", "status_title", language, name=name))
        dialog.configure(bg="#000000")
        dialog.geometry("680x620")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text=name,
            bg="#000000",
            fg="#f2f2f2",
            anchor="w",
            font=self.ui_fonts.bold(1),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        detail = tk.Text(
            dialog,
            wrap="word",
            bg="#050505",
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

        actions = tk.Frame(dialog, bg="#000000")
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, "閉じる", dialog.destroy).grid(row=0, column=1, sticky="e")

    def _actor_status_detail_text(self, item: dict[str, object]) -> str:
        language = self.config_data.language
        kind = str(item.get("kind") or "")
        name = str(item.get("name") or "")
        encounter = item.get("encounter") if isinstance(item.get("encounter"), dict) else {}
        if kind == "monster":
            monster = self.engine.state.world_data.monsters.get(name)
            if not monster:
                return f"{name}\n\n{tr_enum('roster', 'no_monster_data', language)}"
            return _format_monster_status_detail(monster.to_dict(), encounter, language=language)

        if kind in {"player", "character"}:
            character = self.engine.state.world_data.characters.get(name)
            data = character.to_dict() if character else {}
            if kind == "player":
                player = self._player_character_dict()
                data = {**data, **player} if data else player
                encounter = self.engine.state.flags.get("active_encounter") if isinstance(self.engine.state.flags.get("active_encounter"), dict) else {}
            if not data:
                return f"{name}\n\n{tr_enum('roster', 'no_character_data', language)}"
            return _format_character_status_detail(data, encounter if isinstance(encounter, dict) else {}, is_player=kind == "player", language=language)

        return f"{name}\n\n{tr_enum('roster', 'no_status_data', language)}"

    def _npc_roster_items(self) -> list[dict[str, object]]:
        state = self.engine.state
        language = self.config_data.language
        items: list[dict[str, object]] = []
        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("status") != "ended":
            name = str(active_encounter.get("opponent_name") or tr_enum("roster", "unknown", language))
            opponent_type = str(active_encounter.get("opponent_type") or "")
            hp = active_encounter.get("opponent_hp")
            image: Image.Image | None = None
            if opponent_type == "monster":
                monster = state.world_data.monsters.get(name)
                if monster:
                    image = self._actor_image_from_paths(monster.image_paths, ("face_image", "add_border_image", "no_bg_image", "base_image", "generated_image"))
            else:
                character = state.world_data.characters.get(name)
                if character:
                    image = self._actor_image_from_paths(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image"))
            items.append(
                {
                    "name": name,
                    "subtitle": opponent_type or "enemy",
                    "hp": f"HP:{hp}" if hp is not None else "",
                    "image": image,
                    "kind": "monster" if opponent_type == "monster" else "character",
                    "encounter": active_encounter,
                }
            )
            return items

        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            name = str(active_conversation.get("character") or "")
            character = state.world_data.characters.get(name)
            if character:
                items.append(
                    {
                        "name": character.name,
                        "subtitle": character.role or character.category or "NPC",
                        "hp": "",
                        "image": self._actor_image_from_paths(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")),
                        "kind": "character",
                    }
                )
            return items

        current_location = self._current_location_name()
        for character in state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not self._character_is_present_at(character, current_location):
                continue
            items.append(
                {
                    "name": character.name,
                    "subtitle": character.role or character.category or "NPC",
                    "hp": "",
                    "image": self._actor_image_from_paths(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")),
                    "kind": "character",
                }
            )
            if len(items) >= 3:
                break
        return items

    def _player_roster_items(self) -> list[dict[str, object]]:
        player = self._player_character_dict()
        if not player:
            return []
        image_paths = player.get("image_paths")
        player_name = str(player.get("name") or self.engine.state.player_name)
        if (not isinstance(image_paths, dict) or not _subject_image_path(image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image"))) and player_name:
            character = self.engine.state.world_data.characters.get(player_name)
            if character and character.image_paths:
                image_paths = character.image_paths
        image = self._actor_image_from_paths(image_paths if isinstance(image_paths, dict) else {}, ("face_image", "add_border_image", "no_bg_image", "generated_image"))
        attrs = _character_attributes(player)
        name = player_name
        extra = player.get("extra")
        extra_level = extra.get("level") if isinstance(extra, dict) else ""
        level = str(player.get("level") or player.get("lv") or extra_level or "")
        encounter = self.engine.state.flags.get("active_encounter")
        if isinstance(encounter, dict) and encounter.get("status") != "ended":
            hp = f"{encounter.get('player_hp', '-')}/{encounter.get('player_max_hp', '-')}"
            sp = f"{encounter.get('player_sp', '-')}/{encounter.get('player_max_sp', '-')}"
        else:
            extra_data = extra if isinstance(extra, dict) else {}
            hp = str(player.get("hp") or player.get("health") or f"{extra_data.get('current_hp', '-')}/{extra_data.get('max_hp', '-')}")
            sp = str(player.get("sp") or f"{extra_data.get('current_sp', '-')}/{extra_data.get('max_sp', '-')}")
        subtitle = f"Lv:{level or '1'}"
        return [{"name": name, "subtitle": subtitle, "hp": f"HP:{hp}", "sp": f"SP:{sp}", "image": image, "attrs": attrs, "kind": "player"}]

    def _actor_image_from_paths(self, image_paths: dict[str, str], keys: tuple[str, ...]) -> Image.Image | None:
        return self._load_layer_image(_subject_image_path(image_paths, keys))

    def _current_location_name(self) -> str:
        state = self.engine.state
        return state.current_location or state.world_data.starting_location or "unknown"

    def _character_is_present_at(self, character: CharacterData, location: str) -> bool:
        actor_location = character.location or str(character.flags.get("current_location") or "")
        if not actor_location:
            return False
        if actor_location != location:
            return False
        return _actor_state_is_present(character.state or str(character.flags.get("state") or "present"))

    def _monster_is_present_at(self, monster, location: str) -> bool:
        actor_location = monster.location or str(monster.flags.get("current_location") or "")
        if not actor_location:
            return False
        if actor_location != location:
            return False
        return _actor_state_is_present(monster.state or str(monster.flags.get("state") or "present"))

    def _maybe_open_map_or_board_for_action(self, action: str) -> bool:
        text = str(action or "").strip().lower()
        if not text:
            return False
        if any(word in text for word in ("依頼掲示板", "掲示板", "quest board", "request board")):
            self._open_quest_board_window()
            return True
        if any(word in text for word in ("地図", "マップ", "map")):
            self._open_map_window()
            return True
        return False

    def _open_map_window(self) -> None:
        facilities = self.engine.current_location_facilities()
        if not facilities:
            self._show_error(ValueError(_ui_text(self.config_data, "map_no_facilities")))
            return
        dialog = tk.Toplevel(self)
        dialog.title(_ui_text(self.config_data, "map_title"))
        dialog.configure(bg="#000000")
        dialog.geometry("760x520")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=2)
        dialog.rowconfigure(1, weight=1)

        tk.Label(dialog, text=_ui_text(self.config_data, "map_title"), bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(0)).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))
        listbox = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        listbox.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 10))
        detail = tk.Text(dialog, bg="#050505", fg="#f2f2f2", relief="solid", bd=1, wrap="word", height=12, font=self.ui_fonts.normal(-2))
        detail.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 10))

        for facility in facilities:
            listbox.insert("end", str(facility.get("name") or ""))

        def selected_facility() -> dict | None:
            selection = listbox.curselection()
            if not selection:
                return None
            index = int(selection[0])
            if index < 0 or index >= len(facilities):
                return None
            return facilities[index]

        def update_detail(_event=None) -> None:
            facility = selected_facility()
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            if facility:
                lines = [
                    str(facility.get("name") or ""),
                    f"{_ui_text(self.config_data, 'map_type')}: {facility.get('type') or '-'}",
                    f"{_ui_text(self.config_data, 'map_npc')}: {facility.get('npc_name') or '-'}",
                    "",
                    str(facility.get("description") or ""),
                ]
                detail.insert("1.0", "\n".join(lines))
            detail.configure(state="disabled")

        def travel() -> None:
            facility = selected_facility()
            if not facility:
                return
            dialog.destroy()
            self._run_task(
                _ui_text(self.config_data, "task_moving_facility"),
                lambda name=str(facility.get("name") or ""): self.engine.travel_to_facility(name),
                self._set_log,
            )

        listbox.bind("<<ListboxSelect>>", update_detail)
        listbox.bind("<ButtonRelease-1>", lambda _event: travel())
        listbox.bind("<Double-Button-1>", lambda _event: travel())
        if facilities:
            listbox.selection_set(0)
            update_detail()

        actions = tk.Frame(dialog, bg="#000000")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "map_move"), travel).grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=2, sticky="e")

    def _open_quest_board_window(self) -> None:
        if not self.engine.is_current_location_guild():
            if self.engine.is_current_location_settlement():
                self._set_log(self.engine.travel_to_facility(DEFAULT_GUILD_NAME))
            if not self.engine.is_current_location_guild():
                self._show_error(ValueError(_ui_text(self.config_data, "quest_board_not_guild")))
                return
        quests = self.engine.available_quest_board_quests()
        dialog = tk.Toplevel(self)
        dialog.title(_ui_text(self.config_data, "quest_board_title"))
        dialog.configure(bg="#000000")
        dialog.geometry("820x560")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=2)
        dialog.rowconfigure(1, weight=1)

        tk.Label(dialog, text=_ui_text(self.config_data, "quest_board_title"), bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(0)).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))
        listbox = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        listbox.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 10))
        detail = tk.Text(dialog, bg="#050505", fg="#f2f2f2", relief="solid", bd=1, wrap="word", height=12, font=self.ui_fonts.normal(-2))
        detail.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 10))

        for quest in quests:
            listbox.insert("end", quest.name)
        if not quests:
            listbox.insert("end", _ui_text(self.config_data, "quest_board_empty"))

        tooltip = tk.Toplevel(dialog)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tooltip.configure(bg="#d8d4cf")
        tooltip_label = tk.Label(tooltip, bg="#050505", fg="#f2f2f2", justify="left", anchor="w", bd=1, relief="solid", padx=8, pady=6, font=self.ui_fonts.normal(-3))
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
        listbox.bind("<ButtonRelease-1>", lambda _event: accept())
        listbox.bind("<Double-Button-1>", lambda _event: accept())
        dialog.bind("<Destroy>", lambda _event: tooltip.destroy() if tooltip.winfo_exists() else None, add="+")
        if quests:
            listbox.selection_set(0)
        update_detail()

        actions = tk.Frame(dialog, bg="#000000")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "quest_board_accept"), accept).grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), dialog.destroy).grid(row=0, column=2, sticky="e")

    def _open_player_inventory(self) -> None:
        self._open_inventory_window(_ui_text(self.config_data, "inventory_title"), _ui_text(self.config_data, "inventory_details"), [], mode="inventory")

    def _open_loot_inventory(self) -> None:
        location = self.engine.state.world_data.ensure_location(self.engine.state.current_location)
        inventory = location.extra.setdefault("inventory", [])
        if not isinstance(inventory, list):
            inventory = []
            location.extra["inventory"] = inventory
        if not location.flags.get("inventory_seeded") and not inventory:
            context = " ".join(part for part in (location.area, location.description) if part)
            inventory.extend(generate_loot_items(location.name, context))
            location.flags["inventory_seeded"] = True
        self._open_inventory_window(_ui_text(self.config_data, "loot_title"), location.name, inventory, mode="loot")

    def _open_trade_inventory(self) -> None:
        character = self._trade_target_character()
        if character is None:
            self._show_error(ValueError(_ui_text(self.config_data, "trade_no_target")))
            return
        if not character.inventory:
            context = " ".join(
                part
                for part in (character.role, character.category, character.personality, character.backstory)
                if part
            )
            character.inventory.extend(generate_vendor_items(character.name, context))
            character.gold = character.gold or 120
        self._open_inventory_window(_ui_text(self.config_data, "trade_title"), character.name, character.inventory, mode="shop", target_character=character)

    def _trade_target_character(self) -> CharacterData | None:
        active = self.engine.state.flags.get("active_conversation")
        if isinstance(active, dict):
            name = str(active.get("character") or "")
            character = self.engine.state.world_data.characters.get(name)
            if character and not character.flags.get("is_player"):
                return character
        current_location = self._current_location_name()
        for character in self.engine.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if self._character_is_present_at(character, current_location):
                return character
        return None

    def _open_craft_window(self) -> None:
        player_inventory = self._player_inventory()
        language = self.config_data.language
        craft_inventory: list[dict[str, object]] = []
        dialog = tk.Toplevel(self)
        dialog.title(_ui_text(self.config_data, "craft_title"))
        dialog.configure(bg="#000000")
        dialog.geometry("900x620")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=0)
        dialog.columnconfigure(2, weight=1)
        dialog.rowconfigure(1, weight=1)

        detail_var = tk.StringVar(value="")
        tk.Label(dialog, text=_ui_text(self.config_data, "game_inventory"), bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        tk.Label(dialog, text=_ui_text(self.config_data, "craft_materials"), bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=2, sticky="ew", padx=16, pady=(14, 6))
        player_list = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        craft_list = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        player_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        craft_list.grid(row=1, column=2, sticky="nsew", padx=16, pady=(0, 8))

        controls = tk.Frame(dialog, bg="#000000")
        controls.grid(row=1, column=1, sticky="ns", pady=(70, 8))
        add_btn = self._instant_button(controls, ">>", lambda: add_material())
        remove_btn = self._instant_button(controls, "<<", lambda: remove_material())
        add_btn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4), ipadx=14, ipady=8)
        remove_btn.grid(row=1, column=0, sticky="ew", padx=8, pady=4, ipadx=14, ipady=8)

        tk.Label(
            dialog,
            textvariable=detail_var,
            bg="#000000",
            fg="#d8d4cf",
            anchor="w",
            justify="left",
            wraplength=820,
            font=self.ui_fonts.normal(-3),
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 0))

        actions = tk.Frame(dialog, bg="#000000")
        actions.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(10, 14))
        actions.columnconfigure(0, weight=1)
        self._instant_button(actions, _ui_text(self.config_data, "craft_create"), lambda: craft_selected()).grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._instant_button(actions, _ui_text(self.config_data, "character_close"), lambda: close_dialog()).grid(row=0, column=2, sticky="e")

        def refresh() -> None:
            player_list.delete(0, "end")
            craft_list.delete(0, "end")
            for item in player_inventory:
                _insert_item_row(player_list, item, language=language)
            for item in craft_inventory:
                _insert_item_row(craft_list, item, language=language)
            if craft_inventory:
                preview, message = craft_items(craft_inventory, language=language)
                if preview:
                    detail_var.set(f"{_ui_text(self.config_data, 'craft_preview')}: {_item_label(preview, language=language)} / {message}")
                else:
                    detail_var.set(message)
            else:
                detail_var.set(_ui_text(self.config_data, "craft_empty_help"))

        def selected_index(listbox: tk.Listbox) -> int | None:
            selection = listbox.curselection()
            if not selection:
                return None
            return int(selection[0])

        def add_material() -> None:
            index = selected_index(player_list)
            if index is None or index >= len(player_inventory):
                return
            item = normalise_item(player_inventory[index])
            if item.get("equipped"):
                self.engine._unequip_player_slot(str(item.get("equipment_slot") or ""), source="craft")
            moved = transfer_item_stack(player_inventory, craft_inventory, index, 1, source="craft")
            if moved:
                self._save_inventory_change()
                refresh()

        def remove_material() -> None:
            index = selected_index(craft_list)
            if index is None or index >= len(craft_inventory):
                return
            moved = transfer_item_stack(craft_inventory, player_inventory, index, 1, source="craft_return")
            if moved:
                self._save_inventory_change()
                refresh()

        def craft_selected() -> None:
            if len(craft_inventory) < 2:
                result, message = craft_items(craft_inventory, language=language)
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
            result, message = craft_items(craft_inventory, language=language, craft_roll=craft_roll)
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
        target_character: CharacterData | None = None,
    ) -> None:
        player_inventory = self._player_inventory()
        language = self.config_data.language
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg="#000000")
        dialog.geometry("900x600")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.columnconfigure(1, weight=0)
        dialog.columnconfigure(2, weight=1)
        dialog.rowconfigure(1, weight=1)

        player_gold_var = tk.StringVar()
        target_gold_var = tk.StringVar()
        detail_var = tk.StringVar(value="")

        tk.Label(dialog, text=_ui_text(self.config_data, "player_label"), bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        tk.Label(dialog, text=target_name, bg="#000000", fg="#f2f2f2", font=self.ui_fonts.bold(-1)).grid(row=0, column=2, sticky="ew", padx=16, pady=(14, 6))

        player_list = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        target_list = tk.Listbox(dialog, bg="#050505", fg="#f2f2f2", selectbackground="#2d2d2d", relief="solid", bd=1, font=self.ui_fonts.normal(-2))
        player_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        target_list.grid(row=1, column=2, sticky="nsew", padx=16, pady=(0, 8))

        controls = tk.Frame(dialog, bg="#000000")
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

        tk.Label(dialog, textvariable=player_gold_var, bg="#000000", fg="#d8d4cf", anchor="w").grid(row=2, column=0, sticky="ew", padx=16)
        tk.Label(dialog, textvariable=target_gold_var, bg="#000000", fg="#d8d4cf", anchor="w").grid(row=2, column=2, sticky="ew", padx=16)

        tk.Label(
            dialog,
            textvariable=detail_var,
            bg="#000000",
            fg="#d8d4cf",
            anchor="w",
            justify="left",
            wraplength=820,
            font=self.ui_fonts.normal(-3),
        ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(6, 0))

        actions = tk.Frame(dialog, bg="#000000")
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
            bg="#050505",
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

        def refresh() -> None:
            player_list.delete(0, "end")
            target_list.delete(0, "end")
            for item in player_inventory:
                _insert_item_row(player_list, item, price_mode="sell" if mode == "shop" else "", language=language)
            for item in target_inventory:
                _insert_item_row(target_list, item, price_mode="buy" if mode == "shop" else "", language=language)
            player_gold_var.set(f"Gold: {self._player_gold()}")
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
            index = selected_index(player_list)
            if index is not None and index < len(player_inventory):
                item = normalise_item(player_inventory[index])
            else:
                index = selected_index(target_list)
                if index is not None and index < len(target_inventory):
                    item = normalise_item(target_inventory[index])
            if not item:
                detail_var.set("")
                return
            source = str(item.get("source") or "")
            detail_var.set(f"{_item_label(item, language=language)} / source:{source}".strip())

        def transfer_to_player(index: int, quantity: int = 1) -> bool:
            if index < 0 or index >= len(target_inventory):
                return False
            item = normalise_item(target_inventory[index])
            amount = min(max(1, quantity), _safe_int(item.get("quantity", 1), 1))
            price = _item_value(item) * amount
            if mode == "shop":
                if self._player_gold() < price:
                    messagebox.showwarning(_ui_text(self.config_data, "trade_title"), _ui_text(self.config_data, "trade_not_enough_gold"))
                    return False
                self._set_player_gold(self._player_gold() - price)
                if target_character:
                    target_character.gold += price
            moved = transfer_item_stack(target_inventory, player_inventory, index, amount, source="trade" if mode == "shop" else "loot")
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
                self.engine._unequip_player_slot(str(item.get("equipment_slot") or ""), source="inventory_transfer")
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
                    unit_price = max(1, _item_value(item))
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

        def use_selected_item() -> None:
            index = selected_index(player_list)
            if index is None:
                return
            used, message = use_inventory_item(player_inventory, index, language=language)
            if message:
                self._append_inventory_event(f"> [使用] {message}")
            if used:
                hp_event = self.engine.apply_player_hp_delta(
                    item_hp_delta(used),
                    source="item",
                    reason=str(used.get("name") or ""),
                    save_game=False,
                )
                if hp_event.get("line"):
                    self._append_inventory_event(str(hp_event["line"]))
                sp_event = self.engine.apply_player_sp_delta(
                    item_sp_delta(used),
                    source="item",
                    reason=str(used.get("name") or ""),
                    save_game=False,
                )
                if sp_event.get("line"):
                    self._append_inventory_event(str(sp_event["line"]))
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
        inventory = self.engine.state.inventory
        if not isinstance(inventory, list):
            inventory = []
            self.engine.state.inventory = inventory
        if not inventory and not self.engine.state.flags.get("starter_inventory_seeded"):
            inventory.extend(starter_items())
            self.engine.state.flags["starter_inventory_seeded"] = True
        return inventory

    def _player_gold(self) -> int:
        player = self._player_character_dict()
        return int(player.get("gold") or self.engine.state.gold or 0)

    def _set_player_gold(self, value: int) -> None:
        gold = max(0, int(value))
        self.engine.state.gold = gold
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            self.engine.state.party[0]["gold"] = gold
        character = self.engine.state.world_data.characters.get(self.engine.state.player_name)
        if character:
            character.gold = gold

    def _save_inventory_change(self) -> None:
        inventory = self._player_inventory()
        if self.engine.state.party and isinstance(self.engine.state.party[0], dict):
            self.engine.state.party[0]["inventory"] = inventory
        character = self.engine.state.world_data.characters.get(self.engine.state.player_name)
        if character:
            character.inventory = inventory
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

    def _maybe_open_inventory_for_action(self, action: str) -> bool:
        text = action.strip().lower()
        if not text:
            return False
        if any(keyword in text for keyword in ("inventory", "item", "所持品", "インベントリ", "持ち物")):
            self._open_player_inventory()
            return True
        if any(keyword in text for keyword in ("loot", "search", "漁", "探す", "拾う")):
            self._open_loot_inventory()
            return True
        if any(keyword in text for keyword in ("shop", "trade", "buy", "sell", "買", "売", "取引", "買い物")):
            self._open_trade_inventory()
            return True
        if any(keyword in text for keyword in ("craft", "combine", "upgrade", "クラフト", "合成", "強化")):
            self._open_craft_window()
            return True
        return False

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
        button = ttk.Button(parent, text=text, command=command)
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
        if not hasattr(self, "save_listbox"):
            return
        self.save_slots = self.save_store.list_saves()
        self.world_slots = self.save_store.list_worlds()
        self.save_listbox.delete(0, "end")
        self.world_listbox.delete(0, "end")
        for slot in self.save_slots:
            self.save_listbox.insert("end", slot.label)
        if not self.save_slots:
            self.save_listbox.insert("end", _ui_text(self.config_data, "empty_no_saved_games"))
        for slot in self.world_slots:
            self.world_listbox.insert("end", slot.label)
        if not self.world_slots:
            self.world_listbox.insert("end", _ui_text(self.config_data, "empty_no_worlds"))

    def _load_selected_save(self) -> None:
        selection = self.save_listbox.curselection()
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
        self.engine.state.flags["screen_mode"] = "exploration"
        self.character_setup_back_screen = "world_select"
        self._show_screen("character_setup")
        self._append_log("\n" + _ui_text(self.config_data, "log_prepared_world").format(world=world.world_name) + "\n")

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

    def _refresh_settings_screen(self) -> None:
        if not hasattr(self, "settings_text"):
            return
        self.llm_backend_var.set(self.config_data.llm_backend)
        self.llm_context_size_var.set(str(self.config_data.llm_context_size))
        self._load_llm_settings_vars()
        self._load_image_settings_vars()
        self._load_ui_settings_vars()
        self._replace_text(self.settings_text, self._settings_text())
        if hasattr(self, "device_info_text"):
            self._replace_text(self.device_info_text, device_report(self.device_info, self.config_data.language))

    def _apply_llm_backend_setting(self) -> None:
        backend = self.llm_backend_var.get().strip()
        if backend not in _llm_backend_options():
            self._show_error(ValueError(_ui_text(self.config_data, "error_unknown_llm_backend").format(backend=backend)))
            return
        try:
            context_size = int(self.llm_context_size_var.get().strip())
            if context_size < 1024:
                raise ValueError(_ui_text(self.config_data, "error_llm_context_min"))
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
        self.llm_context_size_var.set(str(self.config_data.llm_context_size))
        self.local_model_var.set(_selected_model_label(self.config_data))
        self.cloud_openai_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "openai"))
        self.cloud_xai_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "xai"))
        self.cloud_gemini_model_var.set(_cloud_model_text(self.config_data.cloud_llm, "gemini"))
        self.cloud_openai_key_var.set(_cloud_key_value(self.config_data, "openai"))
        self.cloud_xai_key_var.set(_cloud_key_value(self.config_data, "xai"))
        self.cloud_gemini_key_var.set(_cloud_key_value(self.config_data, "gemini"))
        if hasattr(self, "local_model_combo"):
            self.local_model_combo.configure(values=_local_model_labels(self.config_data, self.config_data.language))
        if hasattr(self, "cloud_model_combos"):
            for provider, combo in self.cloud_model_combos.items():
                combo.configure(values=_cloud_model_options(provider, self.config_data))

    def _save_llm_settings(self, backend: str, context_size: int, *, complete_setup: bool = False, lock_backend: bool = True) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ai_setting = raw.setdefault("ai_setting", {})
        local_model_setting = ai_setting.setdefault("local_model_setting", {})
        local_llm = dict(local_model_setting.get("local_llm", {}))
        selected_model = option_from_label(self.config_data, self.local_model_var.get())
        if selected_model is not None:
            local_llm = option_to_local_llm(selected_model, local_llm)
            context_size = int(local_llm.get("context_size") or context_size)
        local_model_setting["llm_backend"] = backend
        local_llm["context_size"] = context_size
        local_model_setting["local_llm"] = local_llm
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
        )

    def _open_first_run_wizard(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(_ui_text(self.config_data, "wizard_title"))
        dialog.configure(bg="#0d1017")
        dialog.geometry("880x700")
        dialog.transient(self)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        tk.Label(
            dialog,
            text=_ui_text(self.config_data, "wizard_title"),
            bg="#0d1017",
            fg="#f4d27a",
            font=self.ui_fonts.bold(2),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        tk.Label(
            dialog,
            text=_ui_text(self.config_data, "wizard_body"),
            bg="#0d1017",
            fg="#d8d4cf",
            anchor="w",
            justify="left",
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        body = tk.Frame(dialog, bg="#111722", padx=12, pady=12)
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(5, weight=1)

        tk.Label(body, text=_ui_text(self.config_data, "settings_llm_backend"), bg="#111722", fg="#b8c0d5").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(body, textvariable=self.llm_backend_var, values=_llm_backend_options(), state="readonly").grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(body, text=_ui_text(self.config_data, "settings_local_model"), bg="#111722", fg="#b8c0d5").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(body, textvariable=self.local_model_var, values=_local_model_labels(self.config_data, self.config_data.language), state="readonly").grid(row=1, column=1, sticky="ew", pady=4)
        tk.Label(body, text=_ui_text(self.config_data, "settings_sdxl_model"), bg="#111722", fg="#b8c0d5").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(body, textvariable=self.sdxl_model_var, values=_sdxl_model_labels(self.config_data, self.config_data.language), state="readonly").grid(row=2, column=1, sticky="ew", pady=4)
        tk.Label(body, text=_ui_text(self.config_data, "settings_context_tokens"), bg="#111722", fg="#b8c0d5").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(body, textvariable=self.llm_context_size_var, width=12).grid(row=3, column=1, sticky="w", pady=4)

        if not hasattr(self, "cloud_model_combos"):
            self.cloud_model_combos = {}
        cloud_controls = tk.LabelFrame(body, text=_ui_text(self.config_data, "settings_cloud_llm"), bg="#111722", fg="#f4d27a", padx=10, pady=8)
        cloud_controls.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        cloud_controls.columnconfigure(1, weight=1)
        cloud_controls.columnconfigure(3, weight=1)
        self._cloud_setting_row(cloud_controls, 0, "openai", "OpenAI", self.cloud_openai_model_var, self.cloud_openai_key_var, _cloud_model_options("openai", self.config_data))
        self._cloud_setting_row(cloud_controls, 1, "xai", "xAI", self.cloud_xai_model_var, self.cloud_xai_key_var, _cloud_model_options("xai", self.config_data))
        self._cloud_setting_row(cloud_controls, 2, "gemini", "Gemini", self.cloud_gemini_model_var, self.cloud_gemini_key_var, _cloud_model_options("gemini", self.config_data))
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("openai"), 3, column=0, sticky="ew")
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("xai"), 3, column=1, sticky="ew")
        self._screen_button(cloud_controls, _ui_text(self.config_data, "settings_fetch_cloud_models"), lambda: self._fetch_cloud_models("gemini"), 3, column=2, sticky="ew")

        report = tk.Text(body, wrap="word", height=8, bg="#0d1017", fg="#e6edf7", insertbackground="#e6edf7", relief="flat", padx=10, pady=8, font=self.ui_fonts.normal(-4))
        report.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        report.insert("1.0", device_report(self.device_info, self.config_data.language))
        report.configure(state="disabled")

        actions = tk.Frame(dialog, bg="#0d1017")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.columnconfigure(0, weight=1)
        self._screen_button(actions, _ui_text(self.config_data, "settings_download_model"), self._download_selected_local_model, 0, column=1, sticky="e")
        self._screen_button(actions, _ui_text(self.config_data, "settings_download_sdxl_model"), self._download_selected_sdxl_model, 0, column=2, sticky="e")
        self._screen_button(actions, _ui_text(self.config_data, "wizard_apply"), lambda: self._complete_first_run_wizard(dialog), 0, column=3, sticky="e")
        self._screen_button(actions, _ui_text(self.config_data, "wizard_skip"), lambda: self._skip_first_run_wizard(dialog), 0, column=4, sticky="e")

    def _complete_first_run_wizard(self, dialog: tk.Toplevel) -> None:
        try:
            context_size = int(self.llm_context_size_var.get().strip())
            self._save_llm_settings(self.llm_backend_var.get().strip(), context_size, complete_setup=True, lock_backend=True)
            self._apply_image_generation_setting()
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        dialog.destroy()

    def _skip_first_run_wizard(self, dialog: tk.Toplevel) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        setup = raw.setdefault("setup", {})
        setup["completed"] = True
        setup["backend_locked"] = True
        CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config_data = load_config()
        dialog.destroy()

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
        self.image_negative_background_var.set(str(negative_prompts.get("background", "")))
        self.image_negative_character_var.set(str(negative_prompts.get("character", "")))
        self.image_negative_monster_var.set(str(negative_prompts.get("monster", "")))
        if hasattr(self, "image_quality_combo"):
            self.image_quality_combo.configure(values=_quality_preset_options(image_config))
        if hasattr(self, "sdxl_model_combo"):
            self.sdxl_model_combo.configure(values=_sdxl_model_labels(self.config_data, self.config_data.language))

    def _load_ui_settings_vars(self) -> None:
        self.ui_font_path_var.set(str(self.config_data.font_path))
        self.ui_font_size_var.set(str(self.config_data.font_size))
        self.ui_text_speed_var.set(str(self.config_data.ui_setting.get("text_speed", 0.02)))
        self.ui_language_var.set(_language_label(self.config_data.language))

    def _apply_image_generation_setting(self) -> None:
        raw = json.loads(json.dumps(self.config_data.raw, ensure_ascii=False))
        ai_setting = raw.setdefault("ai_setting", {})
        local_model_setting = ai_setting.setdefault("local_model_setting", {})
        image_config = local_model_setting.setdefault("image_backend", {})
        sdxl_config = local_model_setting.setdefault("sdxl", {})
        image_config["quality_preset"] = self.image_quality_var.get().strip() or "balanced"
        image_config["sampling_method"] = self.image_sampler_var.get().strip()
        image_config["scheduler"] = self.image_scheduler_var.get().strip()
        image_config["lora_prompt"] = self.image_lora_prompt_var.get().strip()
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
        image_config["negative_prompts"] = negative_prompts
        sdxl_config["vae_path"] = self.image_vae_path_var.get().strip()
        sdxl_config["taesd_path"] = self.image_taesd_path_var.get().strip()
        sdxl_config["lora_model_dir"] = self.image_lora_dir_var.get().strip()
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
        ui_setting["font_path"] = self.ui_font_path_var.get().strip() or "assets/fonts/JF-Dot-MPlus10.ttf"
        ui_setting["font_size"] = font_size
        ui_setting["text_speed"] = text_speed
        ui_setting["language"] = _language_code(self.ui_language_var.get())
        try:
            CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.config_data = load_config()
            self.ui_fonts = configure_ui_fonts(self, self.config_data)
            self._build_menu()
            self._rebuild_settings_screen()
        except Exception as exc:
            self._show_error(exc)
            return
        self._refresh_settings_screen()
        self._append_log("\n" + _ui_text(self.config_data, "log_settings_ui") + "\n")

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
            f"{label('settings_vae')}: {sdxl.get('vae_path', '')}",
            f"{label('settings_taesd')}: {sdxl.get('taesd_path', '')}",
            f"{label('settings_lora_dir')}: {sdxl.get('lora_model_dir', '')}",
            f"{label('settings_lora_prompt')}: {image_config.get('lora_prompt', '')}",
            f"{label('settings_negative_background')}: {negative_prompts.get('background', '')}",
            f"{label('settings_negative_character')}: {negative_prompts.get('character', '')}",
            f"{label('settings_negative_monster')}: {negative_prompts.get('monster', '')}",
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
        self._run_task(
            _ui_text(self.config_data, "task_creating_world"),
            lambda: self.engine.create_world(self.world_name_var.get(), self.premise_var.get(), save_game=False),
            self._on_world_created,
        )

    def _on_world_created(self, text: str) -> None:
        self._show_screen("character_setup")
        self._replace_text(self.character_world_summary_text, self._character_world_summary())
        self._append_log("\n" + _ui_text(self.config_data, "log_world_generated") + "\n" + text + "\n")

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

    def _character_from_setup(self) -> CharacterData:
        name = self.player_var.get().strip() or "Player"
        character = CharacterData(
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
        character.traits = _normalise_character_traits(self.character_trait_entries or _parse_character_traits(self.character_traits_text.get("1.0", "end")))
        character.skills = _normalise_character_skills(self.character_skill_entries or _parse_character_skills(self.character_skills_text.get("1.0", "end")))
        character.extra["ability"] = {"attributes": attributes}
        character.extra["attributes"] = attributes
        character.image_generation_prompt = _prompt_parts_from_look(character.look)
        existing = self.engine.state.world_data.characters.get(name)
        if existing:
            character.image_paths.update(existing.image_paths)
            character.prompts.update(existing.prompts)
            if existing.extra.get("image_pipeline"):
                character.extra["image_pipeline"] = existing.extra.get("image_pipeline")
        if self.last_character_preview_path and self.last_character_preview_name == name:
            character.image_paths.setdefault("add_border_image", self.last_character_preview_path)
            character.image_paths.setdefault("generated_image", self.last_character_preview_path)
        return character

    def _generate_image(self) -> None:
        self._run_task(
            _ui_text(self.config_data, "task_generating_scene_image"),
            self.engine.generate_scene_image,
            lambda result: self._set_image(result.path),
        )

    def _generate_character_image(self) -> None:
        self._run_task(
            _ui_text(self.config_data, "task_generating_character_image"),
            self.engine.generate_character_image,
            lambda result: self._on_layer_image_generated(result.path),
        )

    def _generate_monster_image(self) -> None:
        self._run_task(
            _ui_text(self.config_data, "task_generating_monster_image"),
            self.engine.generate_monster_image,
            lambda result: self._on_layer_image_generated(result.path),
        )

    def _send_action(self) -> None:
        if self.current_task_id:
            return
        action = self.action_var.get()
        if self._maybe_open_map_or_board_for_action(action):
            self.action_var.set("")
            return
        if self._maybe_open_inventory_for_action(action):
            self.action_var.set("")
            return
        self.action_var.set("")
        self._run_task(
            _ui_text(self.config_data, "task_resolving_free_action"),
            lambda action=action: self.engine.resolve_action(action),
            self._set_log,
        )

    def _send_choice(self, choice: str) -> None:
        if self.current_task_id:
            return
        if self._screen_mode() == "battle" and self._handle_battle_menu_choice(choice):
            return
        if self._maybe_open_map_or_board_for_action(choice):
            return
        if self._maybe_open_inventory_for_action(choice):
            return
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
        location = state.current_location or world.starting_location or "unknown"
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
        if hasattr(self, "npc_roster_canvas"):
            self._render_actor_rosters()

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
        opponent_name = str(encounter.get("opponent_name") or tr_enum("roster", "unknown", language))
        opponent_type = str(encounter.get("opponent_type") or label("opponent"))
        player_hp = encounter.get("player_hp", "?")
        player_sp = encounter.get("player_sp", "?")
        opponent_hp = encounter.get("opponent_hp", "?")
        lines = [
            f"{label('state')}: {label('battle')}",
            f"{label('opponent')}: {opponent_name} ({opponent_type})",
            f"HP: {label('player')} {player_hp} / {label('opponent_hp')} {opponent_hp}",
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
        character = self.engine.state.world_data.characters.get(name)
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
            role = character.role or character.category or "npc"
            lines.append(f"- {character.name} / {role}")
        return "\n".join(lines)

    def _quest_info_text(self) -> str:
        quests = self.engine.state.world_data.quests[:8]
        if not quests:
            return "No quests yet."
        return "\n".join(f"- {quest.name} [{quest.status}]" for quest in quests)

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

    def _stage_character_layers(self) -> list[tuple[str, str]]:
        state = self.engine.state
        names: list[str] = []
        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            names.append(str(active_conversation.get("character") or ""))
        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("opponent_type") == "character":
            names.append(str(active_encounter.get("opponent_name") or ""))
        current_location = self._current_location_name()
        names.extend(
            character.name
            for character in state.world_data.characters.values()
            if not character.flags.get("is_player") and self._character_is_present_at(character, current_location)
        )
        layers: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name in names:
            if not name or name in seen:
                continue
            character = state.world_data.characters.get(name)
            if not character:
                continue
            image_path = _subject_image_path(character.image_paths, ("no_bg_image", "add_border_image", "generated_image", "face_image"))
            if image_path:
                layers.append((character.name, image_path))
                seen.add(name)
            if len(layers) >= 3:
                break
        return layers

    def _stage_monster_layers(self) -> list[tuple[str, str]]:
        state = self.engine.state
        names: list[str] = []
        active_encounter = state.flags.get("active_encounter")
        if isinstance(active_encounter, dict) and active_encounter.get("opponent_type") == "monster":
            names.append(str(active_encounter.get("opponent_name") or ""))
        current_location = self._current_location_name()
        names.extend(
            monster.name
            for monster in state.world_data.monsters.values()
            if self._monster_is_present_at(monster, current_location)
        )
        layers: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name in names:
            if not name or name in seen:
                continue
            monster = state.world_data.monsters.get(name)
            if not monster:
                continue
            image_path = _subject_image_path(monster.image_paths, ("no_bg_image", "add_border_image", "base_image", "generated_image", "face_image"))
            if image_path:
                layers.append((monster.name, image_path))
                seen.add(name)
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

    def _run_task(self, status: str, work, done) -> None:
        if self.current_task_id:
            return
        self.task_sequence_id += 1
        task_id = self.task_sequence_id
        self.current_task_id = task_id
        self.current_task_name = status
        self.current_task_started_at = time.time()
        self.current_task_cancel_requested = False
        self._set_buttons(False)
        if hasattr(self, "cancel_task_btn"):
            self.cancel_task_btn.configure(state="normal")
        if hasattr(self, "task_progress"):
            self.task_progress.start(14)
        self._set_task_status(_ui_text(self.config_data, "task_generating_status").format(name=status, elapsed=0))
        self._record_task_event("started", status, message=_ui_text(self.config_data, "task_started"))
        self._schedule_task_tick()

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                trace = traceback.format_exc()
                self.after(0, lambda exc=exc, trace=trace: self._finish_task_error(task_id, status, exc, trace))
            else:
                self.after(0, lambda result=result: self._finish_task_success(task_id, status, result, done))

        threading.Thread(target=runner, daemon=True).start()

    def _finish_task_success(self, task_id: int, status: str, result, done) -> None:
        if task_id != self.current_task_id:
            return
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
        self._set_task_status(_ui_text(self.config_data, "task_generating_status").format(name=self.current_task_name, elapsed=elapsed))
        self._schedule_task_tick()

    def _end_task(self, clear_status: bool) -> None:
        if self.task_tick_after_id:
            try:
                self.after_cancel(self.task_tick_after_id)
            except tk.TclError:
                pass
        self.task_tick_after_id = None
        if hasattr(self, "task_progress"):
            self.task_progress.stop()
        if hasattr(self, "cancel_task_btn"):
            self.cancel_task_btn.configure(state="disabled")
        self.current_task_id = 0
        self.current_task_name = ""
        self.current_task_started_at = 0.0
        self.current_task_cancel_requested = False
        self._set_buttons(True)
        if clear_status:
            self._set_task_status("")

    def _set_task_status(self, text: str) -> None:
        self.task_status_var.set(text)

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

    def _on_scene_image_generated(self, path: Path) -> None:
        self.engine.state.flags.pop("pending_background_location", None)
        self.image_cache.clear()
        self.stage_source_image = None
        self._refresh_status_panel()
        self._render_stage()

    def _on_cg_image_generated(self, path: Path) -> None:
        self.image_cache.clear()
        self.stage_source_image = None
        self._refresh_status_panel()
        self._render_stage()

    def _schedule_visual_updates(self) -> None:
        if self.visual_task_after_id:
            try:
                self.after_cancel(self.visual_task_after_id)
            except tk.TclError:
                pass
        self.visual_task_after_id = self.after(160, self._maybe_auto_generate_visuals)

    def _maybe_auto_generate_visuals(self) -> None:
        self.visual_task_after_id = None
        if self.current_task_id or self.current_screen_name != "game":
            return
        state = self.engine.state
        if state.world_data.world_name == "unknown":
            return
        if isinstance(state.flags.get("pending_cg_request"), dict):
            self._run_task(
                _ui_text(self.config_data, "task_generating_cg_image"),
                self.engine.generate_cg_image,
                lambda result: self._on_cg_image_generated(result.path),
            )
            return

        current_location = self._current_location_name()
        pending_background = str(state.flags.get("pending_background_location") or "")
        location_data = state.world_data.locations.get(current_location)
        if pending_background == current_location or (location_data is not None and not location_data.image_path):
            self._run_task(
                _ui_text(self.config_data, "task_generating_scene_image"),
                self.engine.generate_scene_image,
                lambda result: self._on_scene_image_generated(result.path),
            )
            return

        encounter = state.flags.get("active_encounter")
        if isinstance(encounter, dict) and encounter.get("status") != "ended":
            opponent_type = str(encounter.get("opponent_type") or "")
            opponent_name = str(encounter.get("opponent_name") or "")
            if opponent_type == "monster":
                monster = state.world_data.monsters.get(opponent_name)
                if monster and not _subject_image_path(monster.image_paths, ("face_image", "add_border_image", "no_bg_image", "base_image", "generated_image")):
                    self._run_task(
                        _ui_text(self.config_data, "task_generating_monster_image"),
                        lambda name=opponent_name: self.engine.generate_monster_image(name),
                        lambda result: self._on_layer_image_generated(result.path),
                    )
                    return
            elif opponent_type == "character":
                character = state.world_data.characters.get(opponent_name)
                if character and not _subject_image_path(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
                    self._run_task(
                        _ui_text(self.config_data, "task_generating_character_image"),
                        lambda name=opponent_name: self.engine.generate_character_image(name),
                        lambda result: self._on_layer_image_generated(result.path),
                    )
                    return

        active_conversation = state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            name = str(active_conversation.get("character") or "")
            character = state.world_data.characters.get(name)
            if character and not _subject_image_path(character.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
                self._run_task(
                    _ui_text(self.config_data, "task_generating_character_image"),
                    lambda name=name: self.engine.generate_character_image(name),
                    lambda result: self._on_layer_image_generated(result.path),
                )
                return

        player = state.world_data.characters.get(state.player_name)
        if player and not _subject_image_path(player.image_paths, ("face_image", "add_border_image", "no_bg_image", "generated_image")):
            self._run_task(
                _ui_text(self.config_data, "task_generating_player_image"),
                lambda name=state.player_name: self.engine.generate_character_image(name),
                lambda result: self._on_layer_image_generated(result.path),
            )

    def _handle_battle_menu_choice(self, choice: str) -> bool:
        if choice == "戻る":
            self.battle_choice_menu = ""
            self._refresh_choices()
            return True
        if choice in {"攻撃", "スキル", "行動", "逃走"}:
            self.battle_choice_menu = choice
            self._refresh_choices()
            return True
        self.battle_choice_menu = ""
        return False

    def _battle_menu_choices(self) -> list[str]:
        encounter = self.engine.state.flags.get("active_encounter")
        if not isinstance(encounter, dict) or encounter.get("status") == "ended":
            return [choice for choice in self.engine.state.choices if choice.strip()]
        menu = self.battle_choice_menu
        if not menu:
            return ["攻撃", "スキル", "行動", "逃走"]
        if menu == "攻撃":
            target = str(encounter.get("opponent_name") or "敵")
            return [f"{target}を攻撃する", "戻る"]
        if menu == "スキル":
            target = str(encounter.get("opponent_name") or "敵")
            skills = self._player_battle_skills()
            choices = [f"スキル: {skill['name']} -> {target} (SP {skill['sp_cost']})" for skill in skills[:4]]
            return choices + ["戻る"]
        if menu == "行動":
            actions = self._battle_free_actions(encounter)
            return actions[:4] + ["戻る"]
        if menu == "逃走":
            return ["逃走する", "戻る"]
        return ["攻撃", "スキル", "行動", "逃走"]

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
                skill_type = str(raw.get("skill_type") or raw.get("type") or "").lower()
                if "passive" in skill_type:
                    continue
                cost = _safe_int(raw.get("sp_cost") or raw.get("cost_sp") or raw.get("sp") or raw.get("mp_cost"), 0)
                if cost <= 0:
                    cost = _estimate_skill_sp_cost(raw)
                if cost <= 0:
                    continue
                skills.append({**raw, "name": name, "sp_cost": cost})
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
            if mode == "exploration":
                if self.engine.is_current_location_guild() and not self.engine.state.active_quest:
                    choices.insert(0, _ui_text(self.config_data, "choice_quest_board"))
                if self.engine.is_current_location_settlement():
                    choices.insert(0, _ui_text(self.config_data, "choice_open_map"))
                choices = _limit_exploration_choices(choices)
                self.engine.state.choices = choices
        if not choices:
            tk.Label(
                self.choice_frame,
                text=_empty_choices_text(mode, self.config_data.language),
                bg="#000000",
                fg="#596070",
                anchor="center",
                font=self.ui_fonts.bold(-2),
            ).grid(row=0, column=0, sticky="nsew", pady=10)
            return

        for index, choice in enumerate(choices):
            button = tk.Button(
                self.choice_frame,
                text=choice,
                command=lambda selected=choice: self._send_choice(selected),
                bg="#050505",
                fg="#f2f5fb",
                activebackground="#181818",
                activeforeground="#ffffff",
                relief="solid",
                bd=1,
                highlightthickness=1,
                highlightbackground="#d8d4cf",
                padx=10,
                pady=14,
                anchor="center",
                wraplength=300,
                font=self.ui_fonts.bold(-2),
            )
            button.grid(row=index, column=0, sticky="ew", pady=(0, 42 if index < len(choices) - 1 else 0))
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
    )
    try:
        print(engine.create_world("SaveSmokeWorld", "霧深い辺境と古い魔法", save_game=False))
        print(
            engine.apply_player_character(
                CharacterData(
                    name="SaveSmoke",
                    role="Player",
                    category="young woman",
                    gender="female",
                    age="20",
                    backstory="A smoke-test adventurer.",
                    look="short hair, leather armor, travel cloak",
                    personality="calm and curious",
                    traits=[{"name": "冷静", "description": "危機でも判断力を保つ", "severity": 2}],
                    skills=[{"name": "一閃", "element": "none", "description": "素早い攻撃", "skill_type": "physical", "sp_cost": 5}],
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
        first_choice = quest_choice or (engine.state.choices[0] if engine.state.choices else "地図を見る")
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
            "description": parts[1] if len(parts) > 1 else "",
        }
        if len(parts) > 2:
            power = _entry_power(parts[2])
            trait["power"] = power
            trait["strength_level"] = power
            trait["severity"] = power
        traits.append(trait)
    return _normalise_character_traits(traits)


def _parse_character_skills(text: str) -> list[dict[str, object]]:
    skills: list[dict[str, object]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.replace("｜", "|").replace("：", "|").split("|")]
        if not parts or not parts[0]:
            continue
        skill = {
            "name": parts[0],
            "element": parts[1] if len(parts) > 1 else "",
            "description": parts[2] if len(parts) > 2 else "",
            "skill_type": "physical",
            "sp_cost": _safe_int(parts[3], 0) if len(parts) > 3 else 0,
        }
        if not skill["sp_cost"]:
            skill["sp_cost"] = _estimate_skill_sp_cost(skill)
        power = _entry_power(parts[4] if len(parts) > 4 else skill, fallback=_skill_power_from_cost(int(skill["sp_cost"] or 0)))
        skill["power"] = power
        skill["strength_level"] = power
        skills.append(skill)
    return _normalise_character_skills(skills)


def _format_character_traits(traits: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for trait in _normalise_character_traits(traits):
        name = str(trait.get("name") or trait.get("trait") or "").strip()
        if not name:
            continue
        description = str(trait.get("description") or trait.get("effect") or "").strip()
        power = _entry_power(trait)
        lines.append(f"{name} | {description} | {power}".rstrip(" |"))
    return "\n".join(lines)


def _format_character_skills(skills: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for skill in _normalise_character_skills(skills):
        name = str(skill.get("name") or skill.get("skill") or "").strip()
        if not name:
            continue
        category = str(skill.get("category") or skill.get("element") or skill.get("skill_type") or "physical").strip()
        description = str(skill.get("description") or skill.get("effect") or "").strip()
        cost = skill.get("sp_cost", skill.get("cost_sp", skill.get("sp", 0)))
        if not cost:
            cost = _estimate_skill_sp_cost(skill)
        power = _entry_power(skill)
        lines.append(f"{name} | {category} | {description} | {cost} | {power}".rstrip(" |"))
    return "\n".join(lines)


def _format_character_entry_names(entries: list[dict[str, object]]) -> str:
    return "\n".join(
        str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
        for entry in entries
        if str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
    )


def _normalise_character_traits(traits: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in traits:
        if not isinstance(raw, dict):
            raw = {"name": str(raw)}
        name = str(raw.get("name") or raw.get("trait") or raw.get("title") or "").strip()
        if not name:
            continue
        trait = dict(raw)
        power = _entry_power(trait)
        trait["name"] = name
        trait["power"] = power
        trait["strength_level"] = power
        trait["severity"] = power
        result.append(trait)
    return result


def _normalise_character_skills(skills: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for raw in skills:
        if not isinstance(raw, dict):
            raw = {"name": str(raw)}
        name = str(raw.get("name") or raw.get("skill") or raw.get("title") or "").strip()
        if not name:
            continue
        skill = dict(raw)
        skill["name"] = name
        skill["skill_type"] = str(skill.get("skill_type") or skill.get("type") or skill.get("category") or "physical").strip().lower() or "physical"
        if not skill.get("sp_cost"):
            skill["sp_cost"] = _estimate_skill_sp_cost(skill)
        power = _entry_power(skill, fallback=_skill_power_from_cost(_safe_int(str(skill.get("sp_cost", 0)), 0)))
        if "passive" not in str(skill.get("skill_type") or "").lower():
            skill["sp_cost"] = max(_safe_int(str(skill.get("sp_cost", 0)), 0), _skill_sp_floor(power))
        skill["power"] = power
        skill["strength_level"] = power
        result.append(skill)
    return result


def _entry_power(value: object, fallback: int = 1) -> int:
    if isinstance(value, dict):
        for key in ("power", "strength_level", "strength", "power_level", "severity", "level", "rank"):
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


def _skill_power_from_cost(cost: int) -> int:
    if cost >= 16:
        return 5
    if cost >= 11:
        return 4
    if cost >= 7:
        return 3
    if cost >= 4:
        return 2
    return 1


def _skill_sp_floor(power: int) -> int:
    return {1: 2, 2: 4, 3: 7, 4: 11, 5: 16}.get(max(1, min(5, power)), 2)


def _character_entry_tooltip_text(entry: dict[str, object], kind: str) -> str:
    name = str(entry.get("name") or entry.get("skill") or entry.get("trait") or "").strip()
    power = _entry_power(entry)
    lines = [name, f"強力度: {power}/5"]
    if kind == "skills":
        sp_cost = entry.get("sp_cost", entry.get("cost_sp", entry.get("sp", "")))
        skill_type = str(entry.get("skill_type") or entry.get("category") or entry.get("element") or "").strip()
        if sp_cost not in (None, ""):
            lines.append(f"消費SP: {sp_cost}")
        if skill_type:
            lines.append(f"種別: {skill_type}")
    description = str(entry.get("description") or entry.get("effect") or entry.get("usefulness") or "").strip()
    if description:
        lines.extend(["", description])
    effects = entry.get("effects")
    if effects:
        lines.extend(["", "効果:", _compact_tooltip_value(effects)])
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
    items = reward.get("items") or reward.get("item_rewards") or reward.get("rewards")
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


def _estimate_skill_sp_cost(skill: dict[str, object]) -> int:
    text = json.dumps(skill, ensure_ascii=False).lower()
    skill_type = str(skill.get("skill_type") or skill.get("type") or skill.get("category") or "").lower()
    if "passive" in skill_type or "常時" in text:
        return 0
    power = _entry_power(skill, fallback=1)
    cost = 5
    if any(word in skill_type for word in ("magic", "spell", "support")):
        cost += 2
    if any(word in text for word in ("powerful", "major", "large", "area", "aoe", "all", "revive", "death", "強力", "大", "全体", "蘇生", "即死")):
        cost += 5
    numbers = [_safe_int(match.group(0), 0) for match in re.finditer(r"\d+", text)]
    if numbers:
        cost += min(8, max(numbers) // 2)
    power_floor = (0, 2, 4, 7, 11, 16)[power]
    return max(1, min(30, max(cost, power_floor)))


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
        "sta": _safe_int(attrs.get("sta", 10), 10),
        "stamina": _safe_int(attrs.get("stamina", 10), 10),
    }


def _format_character_status_detail(data: dict[str, object], encounter: dict[str, object], *, is_player: bool, language: str = "ja") -> str:
    attrs = _character_attributes(data)
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
    sp_text = f"{extra.get('current_sp', '-')}/{extra.get('max_sp', '-')}" if is_player else ""
    equipment = data.get("equipment") if isinstance(data.get("equipment"), dict) else extra.get("equipment")
    equipment_lines: list[str] = []
    if isinstance(equipment, dict):
        for slot, item in equipment.items():
            if isinstance(item, dict) and item:
                equipment_lines.append(f"{tr_enum('equipment_slot', slot, language)}: {_item_label(item, language=language)}")
    field = lambda key: tr_enum("actor_detail", key, language)
    unknown = tr_enum("roster", "unknown", language)
    actor_type = tr_enum("actor_type", "player" if is_player else "character", language)
    state_id = str(data.get("state") or "present")
    state_label = tr_enum("actor_state", state_id, language, fallback=state_id)
    lines = [
        f"[{field('current_status')}]",
        f"{field('name')}: {data.get('name') or unknown}",
        f"{field('type')}: {actor_type}",
        f"{field('role')}: {_join_nonempty(data.get('role'), data.get('category')) or '-'}",
        f"{field('gender_age')}: {_join_nonempty(data.get('gender'), data.get('age')) or '-'}",
        f"{field('location')}: {data.get('location') or '-'}",
        f"{field('state')}: {state_label}",
        f"{field('gold')}: {data.get('gold') or 0}",
        f"{field('sp')}: {sp_text}" if is_player else "",
        f"{field('equipment')}: " + (" / ".join(equipment_lines) if equipment_lines else "-") if is_player else "",
        f"{field('attributes')}: "
        + ", ".join(
            [
                f"STR {attrs['str']}",
                f"DEX {attrs['dex']}",
                f"CON {attrs['con']}",
                f"INT {attrs['int']}",
                f"WIS {attrs['wis']}",
                f"CHA {attrs['cha']}",
                f"STA {attrs['sta']}",
            ]
        ),
    ]
    if encounter:
        if is_player:
            lines.append(f"{field('battle_hp')}: {encounter.get('player_hp', '-')}")
            lines.append(f"{field('battle_sp')}: {encounter.get('player_sp', '-')}")
            lines.append(f"{field('battle_status')}: {encounter.get('player_status') or '-'}")
        elif encounter.get("opponent_name") == data.get("name"):
            lines.append(f"{field('battle_hp')}: {encounter.get('opponent_hp', '-')}")
            lines.append(f"{field('battle_status')}: {encounter.get('opponent_status') or '-'}")
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
        _format_entry_section(
            field("status_effects"),
            data.get("status_effects"),
            ("name", "description", "effect", "category", "scope", "stage", "severity", "long_term", "permanent", "persistent", "remaining_turns", "duration", "damage_per_turn", "hp_delta_per_turn", "remove_condition"),
        )
    )
    lines.extend(_format_entry_section(field("traits"), data.get("traits"), ("name", "description", "effect", "severity")))
    lines.extend(_format_entry_section(field("skills"), data.get("skills"), ("name", "skill_type", "element", "description", "effect", "sp_cost")))
    lines.extend(_format_inventory_section(data.get("inventory"), language=language))
    return "\n".join(line for line in lines if line is not None)


def _format_monster_status_detail(data: dict[str, object], encounter: dict[str, object], language: str = "ja") -> str:
    field = lambda key: tr_enum("actor_detail", key, language)
    unknown = tr_enum("roster", "unknown", language)
    state_id = str(data.get("state") or "present")
    state_label = tr_enum("actor_state", state_id, language, fallback=state_id)
    lines = [
        f"[{field('current_status')}]",
        f"{field('name')}: {data.get('name') or unknown}",
        f"{field('type')}: {tr_enum('actor_type', 'monster', language)}",
        f"{field('category')}: {data.get('category') or '-'}",
        f"{field('location')}: {data.get('location') or '-'}",
        f"{field('state')}: {state_label}",
    ]
    if encounter and encounter.get("opponent_name") == data.get("name"):
        lines.append(f"{field('battle_hp')}: {encounter.get('opponent_hp', '-')}")
        lines.append(f"{field('battle_status')}: {encounter.get('opponent_status') or '-'}")
    lines.extend(["", f"[{field('description')}]", _short_display(data.get("description")) or "-"])
    lines.extend(
        _format_entry_section(
            field("status_effects"),
            data.get("status_effects"),
            ("name", "description", "effect", "category", "scope", "stage", "severity", "long_term", "permanent", "persistent", "remaining_turns", "duration", "damage_per_turn", "hp_delta_per_turn", "remove_condition"),
        )
    )
    lines.extend(_format_entry_section(field("traits"), data.get("traits"), ("name", "description", "effect", "severity")))
    lines.extend(_format_entry_section(field("skills"), data.get("skills"), ("name", "skill_type", "element", "description", "effect", "sp_cost")))
    return "\n".join(lines)


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
    return generate_loot_items(location_name)


def _default_vendor_items(owner_name: str) -> list[dict[str, object]]:
    return generate_vendor_items(owner_name)


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
        "world_generate": "Generate World",
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
        "character_trait_hint": "name | description | power 1-5",
        "character_bp_over": "Bonus points are over the limit.",
        "character_need_world_image": "Generate or select a world before creating a character image.",
        "character_need_world_details": "Generate or select a world before generating character details.",
        "character_generating_preview": "Generating character preview...",
        "character_generating_entries": "Generating character {kind}...",
        "character_world_need": "Generate or select a world first.",
        "character_world_label": "World",
        "character_world_start": "Start",
        "character_start_game": "Start Life",
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
        "settings_font_path": "Font Path",
        "settings_font_size": "Font Size",
        "settings_text_speed": "Text Speed",
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
        "game_trade": "Trade",
        "game_craft": "Craft",
        "game_save": "Save",
        "game_logs": "Logs",
        "game_cancel": "Cancel",
        "game_send": "send",
        "choice_open_map": "Open map",
        "choice_quest_board": "Open quest board",
        "map_title": "Town Map",
        "map_move": "Move",
        "map_type": "Type",
        "map_npc": "NPC",
        "map_no_facilities": "No settlement map is available here.",
        "quest_board_title": "Guild Quest Board",
        "quest_board_accept": "Accept",
        "quest_board_empty": "No quests are available.",
        "quest_board_not_guild": "The quest board is available inside the guild.",
        "quest_board_reward": "Reward",
        "quest_board_status": "Status",
        "quest_board_objective": "Objective",
        "task_moving_facility": "Moving...",
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
        "world_generate": "ワールド生成",
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
        "character_trait_hint": "名前 | 説明 | 強力度1-5",
        "character_bp_over": "BPが上限を超えています。",
        "character_need_world_image": "キャラクター画像を作る前に、ワールドを生成または選択してください。",
        "character_need_world_details": "キャラクター詳細を生成する前に、ワールドを生成または選択してください。",
        "character_generating_preview": "キャラクター立ち絵を生成中...",
        "character_generating_entries": "キャラクター{kind}を生成中...",
        "character_world_need": "先にワールドを生成または選択してください。",
        "character_world_label": "世界",
        "character_world_start": "開始地点",
        "character_start_game": "人生を始める",
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
        "settings_font_path": "フォントパス",
        "settings_font_size": "フォントサイズ",
        "settings_text_speed": "テキスト速度",
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
        "game_trade": "取引",
        "game_craft": "クラフト",
        "game_save": "保存",
        "game_logs": "ログ",
        "game_cancel": "中止",
        "game_send": "送信",
        "choice_open_map": "地図を見る",
        "choice_quest_board": "依頼掲示板を見る",
        "map_title": "街の地図",
        "map_move": "移動",
        "map_type": "種類",
        "map_npc": "NPC",
        "map_no_facilities": "ここでは街の地図を開けません。",
        "quest_board_title": "ギルドの依頼掲示板",
        "quest_board_accept": "受ける",
        "quest_board_empty": "現在受けられる依頼はありません。",
        "quest_board_not_guild": "依頼掲示板はギルドの中で確認できます。",
        "quest_board_reward": "報酬",
        "quest_board_status": "状態",
        "quest_board_objective": "目的",
        "task_moving_facility": "施設へ移動中...",
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
        "wizard_body": "Fantasia detected your device and prepared recommended AI settings. Choose a local model to download or configure a cloud LLM in Settings.",
        "wizard_apply": "Apply",
        "wizard_skip": "Skip",
        "error_no_model_selected": "No local model is selected.",
        "error_no_sdxl_model_selected": "No SDXL model is selected.",
        "dialog_model_downloaded": "Model download completed:\n{path}",
        "task_downloading_model": "Downloading {name}...",
        "task_downloading_model_progress": "Downloading {name}: {percent}%",
        "task_downloading_model_bytes": "Downloading {name}: {mb} MB",
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
        "wizard_body": "デバイスを検出し、推奨AI設定を準備しました。ローカルモデルをダウンロードするか、設定画面でクラウドLLMを設定してください。",
        "wizard_apply": "適用",
        "wizard_skip": "スキップ",
        "error_no_model_selected": "ローカルモデルが選択されていません。",
        "error_no_sdxl_model_selected": "SDXLモデルが選択されていません。",
        "dialog_model_downloaded": "モデルのダウンロードが完了しました:\n{path}",
        "task_downloading_model": "{name}をダウンロード中...",
        "task_downloading_model_progress": "{name}をダウンロード中: {percent}%",
        "task_downloading_model_bytes": "{name}をダウンロード中: {mb} MB",
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
        "wizard_body": "Fantasia detected your device and prepared recommended AI settings. Choose local model downloads or enter cloud LLM API keys and models here.",
    }
)


UI_TEXT["ja"].update(
    {
        "settings_label_crashlog_dir": "クラッシュログフォルダ",
        "settings_fetch_cloud_models": "公式モデル一覧取得",
        "error_no_cloud_models_fetched": "{provider} からモデル一覧を取得できませんでした。",
        "dialog_cloud_models_fetched": "{provider} から {count} 件のモデルを取得しました。",
        "task_fetching_cloud_models": "{provider} のモデル一覧を取得中...",
        "wizard_body": "デバイスを検出し、推奨AI設定を準備しました。ローカルモデルのダウンロード、またはクラウドLLMのAPIキーとモデルをここで設定できます。",
    }
)


UI_TEXT["en"].update({"settings_label_log_dir": "Log dir"})
UI_TEXT["ja"].update({"settings_label_log_dir": "ログフォルダ"})


def _ui_text(config_data, key: str) -> str:
    language = getattr(config_data, "language", "ja")
    table = UI_TEXT.get(language, UI_TEXT["ja"])
    return table.get(key, UI_TEXT["en"].get(key, key))


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
        tr_enum("initial_choice", "open_map", language),
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


if __name__ == "__main__":
    main()
