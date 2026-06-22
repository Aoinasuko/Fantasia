from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AppConfig
from .paths import BIN_DIR, LOG_DIR, ROOT, resolve_model_path


class LlmError(RuntimeError):
    pass


@dataclass
class LlmResult:
    content: Any
    backend: str
    request_params: dict[str, Any] | None = None


class BaseLlmBackend:
    name = "base"

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        raise NotImplementedError

    def stop(self) -> None:
        pass


LOCAL_LLAMA_BACKENDS = {
    "llama_cpp_completion_cpu": "cpu",
    "llama_cpp_completion_vulkan": "vulkan",
    "llama_cpp_completion_cuda": "cuda",
    "llama_cpp_completion": "cuda",
}

CLOUD_LLM_BACKENDS = {
    "cloud_openai": "openai",
    "cloud_chatgpt": "openai",
    "cloud_xai": "xai",
    "cloud_gemini": "gemini",
}


class FixtureLlmBackend(BaseLlmBackend):
    name = "fixture_llm"

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if manager_name == "create_world_overview":
            content: Any = {
                "world_name": "硝子森の辺境",
                "overview": "古い森と鉱山跡に囲まれた小さな辺境。霧の夜だけ、忘れられた道が現れる。",
                "structure_description": "宿場町を中心に、森、鉱山跡、古い祠がゆるく接続している。",
                "structure": {
                    "settlements": [{"name": "灯守りの宿", "role": "starting_location"}],
                    "regions": ["硝子森", "錆びた鉱山跡", "雨音の祠"],
                },
                "starting_location": "灯守りの宿",
            }
            content["locations"] = [
                {"name": str(content.get("starting_location") or "開始地点"), "kind": "settlement", "danger": 0, "description": "霧深い森の入口にある宿場町。"},
                {"name": "月影の森", "kind": "wilderness", "danger": 1, "description": "町の外に広がる静かな森。"},
            ]
            content["connections"] = [{"from": str(content.get("starting_location") or "開始地点"), "to": "月影の森", "hours": 2}]
        elif manager_name == "create_world_location_batch":
            content = {
                "batch_summary": "Fixture batch locations.",
                "locations": [
                    {"name": "古い祠", "kind": "landmark", "danger": 2, "description": "森の奥に残る小さな祠。"},
                    {"name": "湿った洞穴", "kind": "dungeon", "danger": 3, "description": "祠の裏手に開いた浅い洞穴。"},
                    {"name": "苔むした丘", "kind": "wilderness", "danger": 2, "description": "古い道標が埋もれたなだらかな丘。"},
                ],
                "connections": [
                    {"from": "月影の森", "to": "古い祠", "hours": 2},
                    {"from": "古い祠", "to": "湿った洞穴", "hours": 2},
                    {"from": "月影の森", "to": "苔むした丘", "hours": 2},
                ],
            }
            try:
                fixture_context = json.loads(user_text)
            except Exception:
                fixture_context = {}
            batch_index = int(fixture_context.get("batch_index") or 1) if isinstance(fixture_context, dict) else 1
            anchors = fixture_context.get("anchor_names") if isinstance(fixture_context, dict) else []
            anchor = str(anchors[0]) if isinstance(anchors, list) and anchors else "月影の森"
            base = batch_index * 10
            names = [f"ルミナール街道{base + 1}", f"セラフィル原野{base + 2}", f"ノクスディア迷宮{base + 3}"]
            content = {
                "batch_summary": f"Fixture batch {batch_index}.",
                "locations": [
                    {"name": names[0], "kind": "landmark", "danger": min(50, batch_index * 5), "description": "街道沿いの目印になる場所。"},
                    {"name": names[1], "kind": "wilderness", "danger": min(50, batch_index * 5 + 4), "description": "周辺地形に合わせて広がる森。"},
                    {"name": names[2], "kind": "dungeon", "danger": min(50, batch_index * 5 + 8), "description": "探索対象になる小さな洞窟。"},
                ],
                "connections": [
                    {"from": anchor, "to": names[0], "hours": 2},
                    {"from": names[0], "to": names[1], "hours": 2},
                    {"from": names[1], "to": names[2], "hours": 2},
                ],
            }
        elif manager_name == "create_world_theme":
            content = {
                "world_name": "霧灯りの辺境",
                "overview": "霧深い森と古い鉱山跡に囲まれた辺境。失われた灯火の伝承が旅人を奥地へ導く。",
                "structure_description": "街道、森、鉱山、遺跡が霧の外側へ広がる小さな幻想世界。",
                "structure": {
                    "themes": ["霧", "古代鉱山", "失われた灯火"],
                    "generation_mode": "local_skeleton_llm_descriptions",
                },
                "final_destination_concept": "世界の外縁に眠る、灯火を封じた古代遺跡",
                "opening": "あなたは最初の街の入り口に立ち、霧の向こうへ続く道を見ている。",
            }
            try:
                fixture_context = json.loads(user_text)
            except Exception:
                fixture_context = {}
            requested = str(fixture_context.get("requested_world_name") or "").strip() if isinstance(fixture_context, dict) else ""
            if requested:
                content["world_name"] = requested
        elif manager_name == "local_world_settlement_describer":
            try:
                fixture_context = json.loads(user_text)
            except Exception:
                fixture_context = {}
            slots = fixture_context.get("slots") if isinstance(fixture_context, dict) else []
            names = ["灯守りの街", "霧橋の村", "銀苔の村", "風見の町", "灰鐘の村"]
            content = {
                "summary": "Fixture settlement descriptions.",
                "settlements": [
                    {
                        "slot_id": str(slot.get("slot_id") or f"loc_{index:03d}"),
                        "name": names[index % len(names)],
                        "description": "霧の辺境にある拠点。外へ続く入り口と旅人の噂があり、夜には灯火が道標になる。",
                    }
                    for index, slot in enumerate(slots if isinstance(slots, list) else [])
                    if isinstance(slot, dict)
                ],
            }
        elif manager_name == "local_world_single_location_describer":
            try:
                fixture_context = json.loads(user_text)
            except Exception:
                fixture_context = {}
            slots = fixture_context.get("slots") if isinstance(fixture_context, dict) else []
            label_by_subtype = {
                "road": "白石の街道",
                "crossroad": "霧分かれの辻",
                "coast": "青鳴りの海岸",
                "river": "月映しの川辺",
                "plain": "銀穂の平原",
                "landmark": "古い祈り石",
                "wilderness": "雨待ちの野",
            }
            locations = []
            for index, slot in enumerate(slots if isinstance(slots, list) else []):
                if not isinstance(slot, dict):
                    continue
                subtype = str(slot.get("subtype") or "location")
                base = label_by_subtype.get(subtype, "名もなき道標")
                locations.append(
                    {
                        "slot_id": str(slot.get("slot_id") or f"loc_{index:03d}"),
                        "name": f"{base}{index + 1}",
                        "description": "霧の流れと古い道標が残る、旅人が足を止める小さな場所。",
                    }
                )
            content = {"summary": "Fixture single-node descriptions.", "locations": locations}
        elif manager_name == "local_world_dungeon_location_describer":
            try:
                fixture_context = json.loads(user_text)
            except Exception:
                fixture_context = {}
            slots = fixture_context.get("slots") if isinstance(fixture_context, dict) else []
            slot = slots[0] if isinstance(slots, list) and slots and isinstance(slots[0], dict) else {}
            subtype = str(slot.get("subtype") or "dungeon")
            label_by_subtype = {
                "forest": "黒枝の森",
                "mountain": "鳴石山",
                "ruin": "眠り灯の遺跡",
                "cave": "滴りの洞窟",
                "mine": "沈黙鉱山",
                "final_destination": "最果ての灯火殿",
            }
            subnodes = []
            for raw in fixture_context.get("subnodes_to_name", []) if isinstance(fixture_context, dict) else []:
                if not isinstance(raw, dict):
                    continue
                node_id = str(raw.get("id") or "")
                subnodes.append(
                    {
                        "id": node_id,
                        "name": f"{node_id}の間",
                        "kind": str(raw.get("kind") or "room"),
                        "description": "ローカル生成された構造に沿って名付けられた内部地点。",
                    }
                )
            content = {
                "summary": "Fixture dungeon description.",
                "location": {
                    "slot_id": str(slot.get("slot_id") or "loc_000"),
                    "name": label_by_subtype.get(subtype, "霧奥の迷宮"),
                    "description": "霧の奥に沈む探索地。複数の入口と曲がりくねった内部通路が、古い伝承の中心へ続いている。",
                    "subnodes": subnodes,
                },
            }
        elif manager_name == "dungeon_subnode_generator":
            content = {
                "summary": "Fixture dungeon layout with branches and varied rooms.",
                "nodes": [
                    {"id": "entrance", "name": "入口", "kind": "entrance", "description": "外と内部をつなぐ出入口。"},
                    {"id": "ore_vein", "name": "青鉄鉱の広間", "kind": "ore_vein", "description": "壁に青い鉱石が走る広間。"},
                    {"id": "herb_grove", "name": "光苔の薬草群生地", "kind": "herb_grove", "description": "薬草と光苔が群生する湿った空間。"},
                    {"id": "treasure_room", "name": "古い宝箱の間", "kind": "treasure_room", "description": "古びた宝箱が鎮座する小部屋。"},
                    {"id": "monster_nest", "name": "魔物の巣", "kind": "monster_nest", "description": "爪痕と獣臭が残る危険な巣穴。"},
                    {"id": "deepest", "name": "最奥部", "kind": "deepest", "description": "ダンジョンの中核に近い場所。"},
                ],
                "edges": [
                    {"from": "entrance", "to": "ore_vein"},
                    {"from": "ore_vein", "to": "herb_grove"},
                    {"from": "herb_grove", "to": "deepest"},
                    {"from": "ore_vein", "to": "treasure_room"},
                    {"from": "treasure_room", "to": "monster_nest"},
                    {"from": "monster_nest", "to": "deepest"},
                ],
            }
        elif manager_name == "craft_item_generator":
            content = {
                "narration": "選んだ素材を丁寧に加工し、旅で使える品へ仕上げた。",
                "item": {
                    "name": "試作クラフト品",
                    "category": "tool",
                    "description": "素材を組み合わせて作った簡素な道具。",
                    "quantity": 1,
                    "value": 20,
                    "rarity": "common",
                },
            }
        elif manager_name == "check_world_content_violation":
            content = {
                "content_violation": False,
                "reason": "世界設定として処理可能です。",
                "message": "この内容で世界生成を続行できます。",
                "suggested_revision": "",
            }
        elif manager_name == "check_illegal_content":
            content = {
                "content_violation": False,
                "reason": "プレイヤー入力として処理可能です。",
                "message": "この行動を通常のナレーションへ渡せます。",
                "suggested_action": "",
            }
        elif manager_name == "input_gatekeeper":
            action = _extract_action(user_text) or user_text
            impossible = (
                "50000" in action
                or "instant kill" in action.lower()
                or "impossible miracle" in action.lower()
            )
            content = {
                "content_violation": False,
                "action_possible": not impossible,
                "reason": "The action is implausible in the current world state." if impossible else "The action can proceed.",
                "message": "That cannot be done from the current situation." if impossible else "The action can proceed.",
                "suggested_action": "" if not impossible else "Choose an action grounded in the current scene.",
            }
        elif manager_name == "check_action_feasibility":
            action = _extract_action(user_text) or user_text
            impossible = (
                "50000" in action
                or "超現象" in action
                or "いきなり死" in action
                or "突然死" in action
                or "instant kill" in action.lower()
            )
            content = {
                "action_possible": not impossible,
                "reason": (
                    "因果や手段なしに大金や敵の死亡を発生させる入力です。"
                    if impossible
                    else "現在の状況で試みることはできます。"
                ),
                "message": (
                    "そのようなことはできない。世界内の手段や因果に沿った行動を選んでください。"
                    if impossible
                    else "この行動は通常進行へ渡せます。"
                ),
                "suggested_action": "" if not impossible else "周囲を調べ、実際に使える手段を探す",
            }
        elif manager_name == "create_story":
            content = {
                "world_situation": "霧の夜だけ開く古い道をめぐり、宿場町では失踪者の噂が広がっている。",
                "flow": [
                    {"phase": "導入", "goal": "宿場町で赤い印の意味を探る"},
                    {"phase": "探索", "goal": "硝子森に残る雨夜の道を追う"},
                    {"phase": "対決", "goal": "錆びた鉱山跡の鐘の正体を暴く"},
                ],
                "current_rumor": "錆びた鉱山跡から、雨の夜だけ鐘の音が聞こえるらしい。",
                "story_quests": [
                    {
                        "name": "雨夜の赤い印",
                        "overview": "古びた地図の赤い印が示す場所を調べる。",
                        "neighboring_settlement": "灯守りの宿",
                    },
                    {
                        "name": "鉱山跡の鐘",
                        "overview": "夜ごと鳴る鐘の音と失踪者の関係を追う。",
                        "neighboring_settlement": "灯守りの宿",
                    },
                ],
            }
        elif manager_name == "create_settlement_detail":
            content = {
                "settlement_structure_description": "灯守りの宿を中心に、掲示板、馬小屋、古井戸、小さな礼拝所が中庭を囲んでいる。",
                "atmosphere": "雨音とランタンの温かさが混ざるが、旅人たちはみな森の方角を避けている。",
                "settlement_structure": {
                    "core": "灯守りの宿",
                    "spots": ["掲示板", "馬小屋", "古井戸", "小さな礼拝所"],
                },
                "facilities": [
                    {
                        "name": "冒険者ギルド",
                        "type": "guild",
                        "description": "依頼掲示板と受付がある小さなギルド。",
                        "npc_name": "ミラ",
                        "npc_role": "ギルド受付",
                    },
                    {
                        "name": "馬小屋",
                        "type": "stable",
                        "description": "旅人の荷馬と古い馬具が並ぶ厩舎。",
                        "npc_name": "ヨハン",
                        "npc_role": "馬丁",
                    },
                    {
                        "name": "雨打ちの鍛冶場",
                        "type": "blacksmith",
                        "description": "雨に濡れた街道装備を直すため、夜遅くまで炉の火が落ちない鍛冶屋。",
                        "npc_name": "ガルド",
                        "npc_role": "鍛冶職人",
                        "npc_gender": "male",
                        "npc_age": "middle-aged",
                        "npc_look": "soot-stained leather apron, muscular arms, iron-gray beard",
                        "npc_personality": "blunt, dependable, proud of sturdy work",
                    },
                    {
                        "name": "白露の薬棚",
                        "type": "apothecary",
                        "description": "森で採れた薬草と旅人向けの傷薬を小瓶に分けて並べる薬屋。",
                        "npc_name": "リゼ",
                        "npc_role": "薬師",
                        "npc_gender": "female",
                        "npc_age": "early 30s",
                        "npc_look": "green cloak, herb-stained gloves, careful measuring tools at her belt",
                        "npc_personality": "observant, gentle, cautious about rare herbs",
                    },
                    {
                        "name": "灯り箱の雑貨店",
                        "type": "general_store",
                        "description": "ランタン油、縄、保存食など旅の細かな必需品を木箱ごとに整えた雑貨店。",
                        "npc_name": "ノラン",
                        "npc_role": "雑貨店主",
                        "npc_gender": "male",
                        "npc_age": "late 40s",
                        "npc_look": "round spectacles, patched vest, ink-stained fingers",
                        "npc_personality": "talkative, practical, remembers every traveler's order",
                    },
                ],
                "residents": [
                    {
                        "name": "ミラ",
                        "role": "宿の主人",
                        "description": "古い道の噂を知る寡黙な主人。",
                    },
                    {
                        "name": "ヨハン",
                        "role": "馬丁",
                        "description": "失踪した隊商の最後の目撃者。",
                    },
                ],
                "adventurers": [
                    {
                        "name": "セオ",
                        "role": "斥候",
                        "description": "硝子森から戻ったばかりの旅人。",
                    }
                ],
            }
        elif manager_name == "settlement_quest_generator":
            content = {
                "quests": [
                    {
                        "name": "消えた隊商",
                        "quest_type": "investigate",
                        "overview": "最後に灯守りの宿を出た隊商の足取りを追う。",
                        "neighboring_settlement": "灯守りの宿",
                        "destination_hint": {
                            "location_kind": "wilderness",
                            "anchor_kind": "road",
                            "objective_subnode_name": "隊商の痕跡",
                            "objective_description": "街道近くの森に残された車輪跡と破れた荷布。",
                        },
                        "choices": ["掲示板を確認する", "馬丁に話を聞く"],
                    },
                    {
                        "name": "古井戸の光",
                        "quest_type": "investigate",
                        "overview": "雨の夜に古井戸の底で揺れる青い光を調べる。",
                        "neighboring_settlement": "灯守りの宿",
                        "destination_hint": {
                            "location_kind": "dungeon",
                            "anchor_kind": "road",
                            "objective_subnode_name": "青い光の源",
                            "objective_description": "井戸の地下通路の奥で揺れる青白い光。",
                        },
                        "choices": ["古井戸を覗く", "礼拝所で話を聞く"],
                    },
                ]
            }
        elif manager_name == "facility_request_evaluator":
            content = {
                "allowed": True,
                "narration": "通りを少し進むと、その施設の看板が見えてきた。中には担当者がいて、すぐに話を聞けそうだ。",
                "facility": {
                    "name": "鍛冶屋",
                    "type": "blacksmith",
                    "description": "武具の修理と売買を行う小さな鍛冶場。",
                },
                "npc": {
                    "name": "炉番のレナ",
                    "role": "鍛冶職人",
                    "personality": "口数は少ないが、仕事には誠実。",
                },
                "choices": ["炉番のレナに話しかける", "品物を見る", "移動する"],
            }
        elif manager_name == "home_construction_evaluator":
            unusable = any(word in user_text for word in ("食料", "飲料", "紙切れ", "花"))
            content = {
                "usable": not unusable,
                "reason": "fixture home construction material check",
                "narration": (
                    "その品は家の建材としては頼りなく、建築には使えなかった。"
                    if unusable
                    else "あなたは素材を加工し、家の骨組みと作業家具を少しずつ整えた。"
                ),
                "furniture_level_gain": 0 if unusable else 2,
                "consume_item": not unusable,
            }
        elif manager_name == "quest_starter":
            quest_name = _extract_quest_name(user_text) or "消えた隊商"
            if "救難" in quest_name:
                content = {
                    "quest_name": quest_name,
                    "objective": "地下門の奥から聞こえる声の主を探す。",
                    "location": "灯守りの宿の外れ",
                    "narration": "霧の中で始まった突発依頼だ。地下門の奥から、弱い声があなたの名を知らないまま助けを求めている。",
                    "choices": ["地下門へ入る", "声に返事をする", "宿へ戻って助けを呼ぶ"],
                }
            else:
                content = {
                    "quest_name": quest_name,
                    "objective": "隊商が最後に通った道を調べる。",
                    "location": "灯守りの宿",
                    "destination_location": "灯守りの宿近くの森",
                    "objective_subnode_name": "隊商の痕跡",
                    "narration": "掲示板の依頼札は雨で滲んでいる。隊商は三日前、硝子森へ向かったまま戻っていない。",
                    "choices": ["掲示板を読む", "馬丁に話を聞く", "灯守りの宿近くの森へ向かう"],
                }
        elif manager_name == "field_event_evaluator":
            action = _extract_action(user_text) or "周辺を探索する"
            if "神殿" in action and ("女神" in action or "ボス" in action or "守護者" in action or "ダンジョン" in action):
                content = {
                    "event_occurred": True,
                    "narration": f"あなたが「{action}」と願うように進むと、霧の奥に快楽の神殿が輪郭を現した。内部からは強い気配が漂い、奥へ続く通路が闇に沈んでいる。",
                    "location": "快楽の神殿",
                    "discovered_location": {
                        "name": "快楽の神殿",
                        "kind": "dungeon",
                        "description": "快楽の女神が最奥で待つと噂される、甘い香の漂う神殿型ダンジョン。",
                        "danger": 5,
                    },
                    "boss_npc": {
                        "name": "快楽の女神",
                        "role": "神殿のボス",
                        "description": "快楽の神殿の最奥で侵入者を待ち受ける女神。",
                        "personality": "微笑みながら試練を与え、退く者には興味を失う。",
                        "look": "幻想的な神殿の光をまとった女神。",
                        "image_generation_prompt": ["fantasy dungeon boss", "goddess in pleasure temple", "final chamber"],
                        "hostile": True,
                    },
                    "choices": ["神殿へ入る", "周囲を調べる", "いったん離れる"],
                }
            else:
                content = {
                    "event_occurred": True,
                    "narration": f"あなたが「{action}」と動いた瞬間、霧の向こうから助けを求める声が聞こえた。足元の苔が崩れ、隠されていた地下門が姿を現す。",
                    "location": "灯守りの宿の外れ",
                    "event": {
                        "name": "霧中の救難声",
                        "kind": "wild_quest",
                        "summary": "探索中に発生した未登録の突発クエスト。",
                    },
                    "discovered_location": {
                        "name": "雨裂きの地下門",
                        "kind": "dungeon",
                        "description": "硝子森の斜面に隠れていた古い地下入口。奥から弱い声が響いている。",
                        "area": "硝子森",
                    },
                    "quest": {
                        "name": "霧中の救難声",
                        "overview": "地下門の奥から聞こえる声の主を探す。",
                        "neighboring_settlement": "灯守りの宿",
                        "choices": ["地下門へ入る", "声に返事をする", "宿へ戻って助けを呼ぶ"],
                    },
                    "choices": ["地下門へ近づく", "声に返事をする", "宿へ戻る"],
                }
        elif manager_name == "quest_objective_npc_designer":
            role_match = re.search(r'"objective_role"\s*:\s*"([^"]+)"', user_text)
            objective_role = role_match.group(1) if role_match else ""
            if objective_role == "blocker":
                content = {
                    "name": "森蔦の拘束者",
                    "display_alias": "さらった者",
                    "role_label": "妨害者",
                    "description": "依頼の目的地に潜み、救出対象の退路を塞ぐ魔物。",
                    "personality": "獲物を逃がさず、侵入者には敵意を見せる。",
                    "look": "暗い森に溶ける緑黒い体と、絡みつく蔦のような腕を持つ。",
                    "species": "魔物",
                    "category": "quest_objective",
                    "hostile": True,
                    "image_prompt": "fantasy monster, forest captor, vine-like arms",
                    "aliases": ["拘束者", "妨害者"],
                }
            else:
                content = {
                    "name": "攫われた娘",
                    "display_alias": "町娘",
                    "role_label": "救出対象",
                    "description": "依頼主が探している救出対象。恐怖で震えているが、帰還を望んでいる。",
                    "personality": "怯えているが、助けを求める意志は残っている。",
                    "look": "旅装の乱れた若い町娘。",
                    "species": "人間",
                    "category": "quest_objective",
                    "hostile": False,
                    "image_prompt": "fantasy rescued town girl, anxious expression",
                    "aliases": ["救出対象", "町娘"],
                }
        elif manager_name == "danger_subnode_monster_generator":
            content = {
                "name": "苔牙の狼",
                "role": "危険地帯の徘徊魔物",
                "category": "wild_encounter",
                "description": "暗い森や洞窟の湿った気配に引き寄せられた、苔むした牙を持つ狼型の魔物。",
                "gender": "none",
                "age": "adult",
                "look": "moss-covered dark fur, long fangs, low predatory stance",
                "personality": "territorial, aggressive toward intruders",
                "traits": [{"name": "不意打ち", "description": "初めて足を踏み入れた相手へ素早く襲いかかる。"}],
                "image_generation_prompt": ["fantasy RPG monster", "moss wolf", "dangerous dungeon"],
                "npc_template_id": "wolf",
                "hostile": True,
                "reason": "Fixture dangerous subnode monster.",
            }
        elif manager_name == "quest_referee_with_free_action":
            action = _extract_action(user_text) or "手がかりを探す"
            quest_name = _extract_quest_name(user_text)
            if "霧中の救難声" in quest_name:
                content = {
                    "narration": f"あなたの行動「{action}」を受け、地下門の奥から短い返事が戻った。声の主は水音のする部屋に閉じ込められているらしい。",
                    "location": "灯守りの宿の外れ",
                    "quest_progress": "救助対象が地下門の奥にいると分かった。",
                    "event": {
                        "name": "地下門からの返答",
                        "result": "次の調査地点が地下門内部に定まった。",
                    },
                    "finished": False,
                    "choices": ["地下門へ入る", "ロープを準備する", "宿へ戻って助けを呼ぶ"],
                }
            else:
                content = {
                    "narration": f"あなたの行動「{action}」により、隊商が赤い印の道を通った痕跡が見つかった。",
                    "location": "灯守りの宿",
                    "quest_progress": "赤い印の道が次の調査地点になった。",
                    "event": {
                        "name": "赤い印の道",
                        "result": "硝子森へ向かう理由が明確になった。",
                    },
                    "finished": False,
                    "choices": ["硝子森へ向かう", "宿で準備する"],
                }
        elif manager_name == "quest_referee_event_resolve":
            quest_name = _extract_quest_name(user_text)
            if "霧中の救難声" in quest_name:
                content = {
                    "narration": "返答は途切れたが、地下門の石段に濡れた足跡が残っている。奥へ進めば救助に間に合うかもしれない。",
                    "location": "灯守りの宿の外れ",
                    "quest_update": {
                        "progress": "地下門内部へ入る理由が明確になった。",
                        "next_objective": "地下門の水音がする部屋を探す。",
                    },
                    "finished": False,
                    "choices": ["地下門へ入る", "灯りを用意する", "助けを呼びに戻る"],
                }
            else:
                content = {
                    "narration": "赤い印の道は、古びた地図と隊商の轍の両方に残っている。次の目的地は硝子森だ。",
                    "location": "灯守りの宿",
                    "quest_update": {
                        "progress": "硝子森へ向かう手がかりを得た。",
                        "next_objective": "硝子森で隊商の痕跡を追う。",
                    },
                    "finished": False,
                    "choices": ["硝子森へ向かう", "宿の主人に報告する"],
                }
        elif manager_name == "quest_procurement_checker":
            match = re.search(r'"item_uuid"\s*:\s*"([^"]+)"', user_text)
            item_match = re.search(r'"name"\s*:\s*"([^"]+)"', user_text)
            content = {
                "accepted": bool(match),
                "item_uuid": match.group(1) if match else "",
                "item_name": item_match.group(1) if item_match else "",
                "reason": "fixture procurement check",
            }
        elif manager_name == "master_ai_facilitator":
            action = _extract_action(user_text) or "状況を見る"
            if any(word in action for word in ("ゲームオーバー", "死ぬ", "破滅する")):
                content = {
                    "content_violation": False,
                    "think": "プレイヤー行動の結果が確定的な冒険終了に至る。",
                    "narration": "あなたの選択は取り返しのつかない結末を招き、冒険はそこで途切れた。",
                    "process": [{"step": "ゲームオーバー判定", "result": "確定的な冒険終了"}],
                    "finished": True,
                    "game_over": True,
                    "game_over_reason": "プレイヤー行動の結果が確定的なゲームオーバーになったため。",
                    "choices": ["ゲームオーバー"],
                }
            elif any(word in action for word in ("数日", "三日", "3日", "滞在", "長く休む")):
                content = {
                    "content_violation": False,
                    "think": "長い時間を過ごす行動として扱う。",
                    "narration": "あなたはしばらく腰を落ち着け、数日を準備と休息に費やした。",
                    "process": [{"step": "時間経過", "result": "長期滞在として72時間進める"}],
                    "finished": False,
                    "long_time_passage_hours": 72,
                    "time_reason": "長期滞在",
                    "choices": ["周囲を見る", "出発する"],
                }
            else:
                no_recipients = "整理" in action or "考える" in action
                content = {
                    "content_violation": False,
                    "think": "現在地、直近ログ、プレイヤー入力を照合し、通常進行として扱う。",
                    "narration": (
                        "あなたは一度足を止め、雨音と宿場のざわめきの中で手がかりを整理した。"
                        if no_recipients
                        else "宿の主人ミラは、赤い印が硝子森へ続く古道を示しているのではないかと低い声で告げた。"
                    ),
                    "process": [
                        {"step": "入力解釈", "result": f"プレイヤー行動「{action}」を通常進行として処理する"},
                        {
                            "step": "進行更新",
                            "result": "次の行動候補を会話、掲示板確認、探索に整理する",
                        },
                    ],
                    "finished": False,
                    "location": "灯守りの宿",
                    "recipients": [] if no_recipients else ["ミラ"],
                    "new_npc_requests": (
                        [
                            {
                                "role": "巡回薬師",
                                "reason": "状況整理の中で、雨夜の古道に詳しい通りすがりのNPCが必要になった。",
                                "location": "灯守りの宿",
                            }
                        ]
                        if no_recipients
                        else []
                    ),
                    "choices": ["赤い印について聞く", "掲示板を見る", "周辺を探索する"],
                }
        elif manager_name == "master_ai_process_summarizer":
            content = {
                "summary": "ミラは赤い印が硝子森へ続く古道を示す可能性を伝えた。",
                "recipients": ["ミラ"],
                "process_summary": {
                    "topic": "赤い印の相談",
                    "state": "NPCから古道の手がかりを得た",
                },
                "memory_updates": [
                    {"target": "ミラ", "memory": "プレイヤーに赤い印と硝子森の古道の関係を示唆した"}
                ],
            }
        elif manager_name == "master_ai_process_summarizer_with_no_recipients":
            content = {
                "summary": "プレイヤーは直近の手がかりを整理し、赤い印と探索先の関係を再確認した。",
                "process_summary": {
                    "topic": "自己整理",
                    "state": "次に追う候補が会話、掲示板、探索にまとまった",
                },
                "memory_updates": [],
                "no_recipients_reason": "NPCや外部対象へ渡す情報がないため。",
            }
        elif manager_name == "master_ai_npc_generater":
            content = {
                "reason": "探索の進行で雨夜の古道に詳しいNPCが必要になったため。",
                "npcs": [
                    {
                        "name": "レナ",
                        "category": "traveler",
                        "description": "雨の夜に灯守りの宿へ立ち寄った巡回薬師。硝子森の古道と湿地の薬草に詳しい。",
                        "personality": "警戒心は強いが、相手が無謀でなければ手がかりを分ける。",
                        "look": "濡れた旅外套、薬草袋、小さな銀の鈴、泥のついた革靴。",
                        "occupation": "巡回薬師",
                        "archetype": "cautious_helper",
                        "skills": [
                            {
                                "name": "薬草鑑定",
                                "desc": "周辺の薬草や毒草を見分け、必要に応じて手当てする。",
                                "usesp": 3,
                                "power": 2,
                                "ability": "wis",
                                "element": "nature",
                                "type": ["heal_single"],
                            }
                        ],
                        "aliases": ["薬師", "巡回薬師"],
                    }
                ],
            }
        elif manager_name == "npc_detail_generater":
            name = _extract_character_name(user_text) or "レナ"
            content = {
                "name": name,
                "talk_style": "短く慎重に話し、危険を感じると質問で相手を試す。",
                "archetype": "cautious_helper",
                "behavior_policy": "困っている相手には助言するが、無謀な戦闘や略奪には加担しない。",
                "conversation_topics": ["薬草", "雨夜の道", "行方不明の旅人"],
                "skills": [
                    {
                        "name": "雨避けの処方",
                        "desc": "雨で悪化する傷を一時的に和らげる。",
                        "usesp": 2,
                        "power": 1,
                        "ability": "wis",
                        "element": "water",
                        "type": ["heal_single"],
                    }
                ],
                "memory_updates": [{"target": name, "memory": "プレイヤーと初対面。まだ警戒している。"}],
                "relationship": {"trust": 0, "stance": "watchful"},
            }
        elif manager_name == "conversation_starter":
            speaker = _extract_conversation_speaker(user_text) or "ミラ"
            content = {
                "speaker": speaker,
                "topic": "赤い印",
                "mood": "警戒しつつ協力的",
                "location": "灯守りの宿",
                "narration": f"{speaker}は周囲の客に聞こえないよう声を落とし、赤い印のことなら少し知っていると告げた。",
                "finished": False,
                "choices": ["赤い印について聞く", "失踪者について聞く", "会話を終える"],
            }
        elif manager_name == "conversation_facilitator":
            speaker = _extract_conversation_speaker(user_text) or "ミラ"
            action = _extract_action(user_text) or "赤い印について聞く"
            finished = "終える" in action or "別れ" in action or "離れる" in action
            content = {
                "speaker": speaker,
                "topic": "赤い印",
                "location": "灯守りの宿",
                "narration": (
                    f"{speaker}は小さくうなずき、これ以上は雨が止んでから話そうと会話を締めた。"
                    if finished
                    else f"{speaker}は、あなたの問い「{action}」に答え、赤い印は雨夜だけ現れる古道の目印だと語った。"
                ),
                "relationship_change": {"trust": 1, "reason": "落ち着いて会話した"},
                "finished": finished,
                "choices": ["古道について聞く", "協力を頼む", "会話を終える"] if not finished else ["掲示板を見る", "周辺を探索する"],
            }
        elif manager_name == "conversation_resolver":
            speaker = _extract_conversation_speaker(user_text) or "ミラ"
            content = {
                "speaker": speaker,
                "summary": f"{speaker}から、赤い印と雨夜の古道が関係しているという情報を得た。",
                "location": "灯守りの宿",
                "narration": f"{speaker}は地図を畳み、雨が強まる前に動くなら今だと静かに告げた。",
                "relationship_change": {"trust": 1},
                "memory_updates": [
                    {"target": speaker, "memory": "プレイヤーに赤い印と雨夜の古道の関係を共有した"}
                ],
                "finished": True,
                "choices": ["掲示板を見る", "周辺を探索する", "宿の外へ出る"],
            }
        elif manager_name == "encounter_target_resolver":
            action = _extract_action(user_text)
            target = _extract_fixture_encounter_target(action) or _extract_fixture_encounter_target(user_text) or "未知の魔物"
            is_tentacle = "触手" in target or "tentacle" in target.lower()
            content = {
                "target_name": target,
                "opponent_type": "character",
                "category": "tentacle_monster" if is_tentacle else "wild_encounter",
                "description": (
                    "水辺や暗がりに潜む、粘液をまとった触手状の魔物。"
                    if is_tentacle
                    else f"直近の文脈から戦闘相手として推定された{target}。"
                ),
                "traits": (
                    [{"name": "絡みつく触手", "description": "多数の触手で相手の動きを封じる。"}]
                    if is_tentacle
                    else [{"name": "警戒", "description": "不用意に近づいた相手へ反応する。"}]
                ),
                "image_generation_prompt": (
                    ["tentacle monster", "slimy tendrils", "fantasy RPG monster"]
                    if is_tentacle
                    else ["fantasy RPG monster", target]
                ),
                "confidence": 90 if target != "未知の魔物" else 30,
                "reason": "プレイヤー行動と一時コンテキストログから戦闘対象を推定した。",
            }
        elif manager_name == "hostile_npc_encounter_evaluator":
            target = _extract_fixture_visible_enemy(user_text) or "敵対者"
            content = {
                "narration": f"{target}があなたの気配に気づき、身構えた。",
                "combat_started": False,
                "opponent_name": target,
                "stance": "watching",
                "choices": ["距離を取る", "武器を構える", "声をかける"],
                "reason": "Fixture hostile encounter response.",
            }
        elif manager_name == "combat_transition_detector":
            text = user_text.casefold()
            started = any(word in text for word in ("襲い掛", "襲いかか", "攻撃してき", "飛びかか", "attacks", "attack"))
            target = _extract_fixture_visible_enemy(user_text) or _extract_fixture_encounter_target(user_text) or ""
            content = {
                "combat_started": started,
                "opponent_name": target,
                "narration": f"{target or '敵'}との戦闘が始まった。" if started else "",
                "reason": "Fixture combat transition detector.",
            }
        elif manager_name == "context_reference_resolver":
            action = _extract_action(user_text)
            target_type, target_name = _extract_fixture_context_reference(user_text, action)
            content = {
                "target_type": target_type,
                "target_name": target_name,
                "resolved_action": action.replace("あの人", target_name).replace("その人", target_name).replace("その依頼", target_name),
                "confidence": 80 if target_name else 20,
                "reason": "fixture: プレイヤー行動と一時コンテキストログから曖昧参照を推定した。",
            }
        elif manager_name == "combat_player_action":
            payload = _extract_fixture_payload(user_text)
            action = str(payload.get("action") or "").strip() or _extract_action(user_text) or "身構える"
            surrendering = any(word in action for word in ("降伏", "降参", "無抵抗", "抵抗しない", "武器を捨て", "両手", "surrender", "nonresistance"))
            content = {
                "intent": "surrender" if surrendering else "free_action",
                "narration": (
                    "あなたは無抵抗の姿勢を保ち、相手の反応を待った。"
                    if surrendering
                    else f"あなたは戦闘中に「{action}」を試み、相手の出方をうかがった。"
                ),
                "choices": ["相手の反応を待つ", "事情を説明する"] if surrendering else ["攻撃", "スキル", "行動", "逃走"],
                "tool_judgements": [
                    {
                        "name": "player_surrender",
                        "confidence": 1.0 if surrendering else 0.0,
                        "arguments": {"reason": "fixture combat player action"},
                        "reason": "fixture surrender classification.",
                    }
                ],
            }
        elif manager_name == "combat_enemy_action":
            payload = _extract_fixture_payload(user_text)
            surrender_required = bool(payload.get("player_surrender_resolution_required"))
            content = {
                "action_type": "free_action" if surrender_required else "attack",
                "attack_name": "" if surrender_required else "攻撃",
                "element": "" if surrender_required else "physical",
                "narration": "相手はあなたの無抵抗を見て、攻撃を止めた。" if surrender_required else "相手は短く間合いを詰め、反撃の姿勢を取った。",
                "choices": ["攻撃", "スキル", "行動", "逃走"],
                "reason": "fixture enemy action.",
                "tool_judgements": [
                    {
                        "name": "accept_player_surrender",
                        "confidence": 1.0 if surrender_required else 0.0,
                        "arguments": {"reason": "fixture accepts player surrender"},
                        "reason": "fixture surrender response.",
                    }
                ],
            }
        elif manager_name == "combat_log_narrator":
            payload = _extract_fixture_payload(user_text)
            event = str(payload.get("event") or "combat")
            actor = str(payload.get("actor") or "攻撃者")
            target = str(payload.get("target") or "相手")
            skill_payload = payload.get("skill") if isinstance(payload.get("skill"), dict) else {}
            action = str(payload.get("action") or skill_payload.get("name") or "行動")
            if "miss" in event:
                narration = f"{actor}の{action}は{target}にかわされた。"
            elif event == "skill":
                narration = f"{actor}は{action}を使い、戦況を動かした。"
            else:
                narration = f"{actor}の{action}が{target}に命中した。"
            content = {"narration": narration}
        elif manager_name == "create_initial_character_profile":
            name = _extract_character_name(user_text) or "Mira"
            role = _extract_character_role(user_text) or "innkeeper"
            content = {
                "name": name,
                "gender": "female",
                "age": "late 30s",
                "role": role,
                "category": "resident",
                "backstory": f"{name} is a local fixture character who knows the roads around the starting inn.",
                "personality": "Calm, observant, and willing to help cautious travelers.",
                "ability": {
                    "name": "Rain Road Memory",
                    "description": "Reads changes in rain, sound, and road mud to predict danger.",
                },
                "look": f"{name} wears practical travel clothes, a dark apron, and a small lantern charm.",
                "image_generation_prompt": [
                    "fantasy RPG character",
                    f"{name}",
                    "rainy frontier inn",
                    "lantern accessory",
                    "anime illustration",
                    "detailed outfit",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, extra fingers",
                "traits": [
                    {
                        "name": "Watchful",
                        "description": "Notices danger before most people do.",
                        "severity": 2,
                        "power": 2,
                        "strength_level": 2,
                        "effect": "Provides hints before risky travel or negotiation.",
                    }
                ],
                "skills": [
                    {
                        "name": "Lantern Signal",
                        "desc": "Uses a lantern flash to guide allies or distract threats.",
                        "usesp": 3,
                        "power": 2,
                        "ability": "wis",
                        "element": "none",
                        "type": ["effect_ally_party"],
                    }
                ],
            }
        elif manager_name == "create_character":
            name = _extract_character_name(user_text) or "ミラ"
            role = _extract_character_role(user_text) or "宿の主人"
            content = {
                "name": name,
                "gender": "女性" if name in {"ミラ"} else "男性",
                "age": "30代後半" if name == "ミラ" else "20代後半",
                "role": role,
                "category": "resident" if "主人" in role or "馬丁" in role else "adventurer",
                "backstory": f"{name}は灯守りの宿で多くの旅人を見てきた。雨夜の古道にまつわる噂を断片的に知っている。",
                "personality": "慎重で観察眼が鋭く、敵意を見せない相手にはまず事情を聞こうとする。",
                "ability": {
                    "name": "雨夜の勘",
                    "description": "霧や雨音の変化から、古道や危険の兆しを読み取る。",
                },
            }
        elif manager_name == "create_look":
            name = _extract_character_name(user_text) or "ミラ"
            content = {
                "category": "human",
                "look": f"{name}は旅装に馴染む落ち着いた服をまとい、雨除けの外套と小さなランタン飾りを身につけている。",
                "image_generation_prompt": [
                    "fantasy RPG character",
                    f"{name}",
                    "rainy frontier inn",
                    "lantern accessory",
                    "anime illustration",
                    "detailed outfit",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, extra fingers",
            }
        elif manager_name == "create_trait":
            content = {
                "traits": [
                    {
                        "name": "慎重",
                        "description": "相手が降伏や交渉を選んだ場合、すぐ攻撃せず状況を見る。",
                        "severity": "medium",
                        "effect": "敵対/会話/戦闘のNPC判断で攻撃以外の選択が起きやすい。",
                    },
                    {
                        "name": "噂に敏い",
                        "description": "宿場や旅人の噂から次の手がかりを拾える。",
                        "severity": "medium",
                        "effect": "探索前の会話でヒントを出せる。",
                    },
                ]
            }
        elif manager_name == "create_skill":
            content = {
                "skills": [
                    {
                        "name": "三連突き",
                        "desc": "鋭い突きを三度続けて放つ。",
                        "usesp": 3,
                        "power": 2,
                        "ability": "dex",
                        "element": "physical",
                        "type": ["damage_hp_single", "damage_hp_single", "damage_hp_single"],
                    },
                    {
                        "name": "雨音読み",
                        "desc": "雨や霧の変化から危険の接近を察して身をかわす。",
                        "usesp": 2,
                        "power": 1,
                        "ability": "dex",
                        "element": "wind",
                        "type": ["effect_self"],
                    },
                ]
            }
        elif manager_name == "narrator_initial":
            content = {
                "narration": "雨音の奥で、宿の主人があなたに古びた地図を差し出した。地図の端には、まだインクの乾いていない赤い印がある。",
                "location": "灯守りの宿",
                "choices": ["移動する", "宿の主人に話しかける", "宿の外へ出る"],
            }
        elif manager_name == "character_image_creator":
            name = _extract_character_name(user_text) or "ミラ"
            content = {
                "prompt": [
                    "masterpiece",
                    "best quality",
                    "anime fantasy RPG character",
                    name,
                    "single character",
                    "full body",
                    "standing pose",
                    "isolated cutout",
                    "pure white background",
                    "no scenery",
                    "no background objects",
                    "detailed outfit",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, extra fingers, bad hands, background objects, wall, pillar",
            }
        elif manager_name == "monster_image_creator":
            name = _extract_monster_name(user_text) or "硝子森の影"
            content = {
                "prompt": [
                    "masterpiece",
                    "best quality",
                    "fantasy RPG monster",
                    name,
                    "single creature",
                    "full body",
                    "misty shadow beast",
                    "isolated cutout",
                    "pure white background",
                    "no scenery",
                    "no background objects",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, cropped, extra limbs, background objects, wall, pillar",
            }
        elif manager_name == "background_image_creator":
            content = {
                "prompt": [
                    "SDXL fantasy RPG background",
                    "misty frontier inn",
                    "glass forest",
                    "warm lantern light",
                    "painterly",
                ]
            }
        elif manager_name == "cg_image_creator":
            content = {
                "prompt": [
                    "fantasy RPG event CG",
                    "single cinematic scene illustration",
                    "match the latest story narration",
                    "visible established characters",
                    "dramatic but story-accurate composition",
                    "no UI, no text, no speech bubbles",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, UI, speech bubble, unrelated characters",
            }
        else:
            action = _extract_action(user_text) or "周囲を見る"
            content = {
                "narration": f"あなたは「{action}」を試みた。霧の向こうで小さな灯りが揺れ、次の手掛かりが見える。",
                "location": "灯守りの宿",
                "choices": ["灯りへ近づく", "宿へ戻る"],
            }
        content = _fixture_intent_tool_response(manager_name, content)
        return LlmResult(content=content, backend=self.name)


def _fixture_intent_tool_response(manager_name: str, content: Any) -> Any:
    if not isinstance(content, dict):
        return content
    if manager_name not in {
        "master_ai_facilitator",
        "field_event_evaluator",
        "quest_starter",
        "quest_referee_with_free_action",
        "quest_referee_event_resolve",
        "conversation_starter",
        "conversation_facilitator",
        "conversation_resolver",
    }:
        return content

    tool_judgements: list[dict[str, Any]] = []

    def add_tool(name: str, arguments: Any) -> None:
        if arguments in (None, "", [], {}):
            return
        tool_judgements.append(
            {
                "name": name,
                "confidence": 1.0,
                "arguments": arguments if isinstance(arguments, dict) else {"value": arguments},
                "reason": "fixture-converted side effect",
            }
        )

    if content.get("location"):
        add_tool("move_player", {"location": content.get("location")})
    if content.get("quest_progress"):
        add_tool("quest_progress", {"progress": content.get("quest_progress")})
    if content.get("quest_update"):
        add_tool("quest_update", {"quest_update": content.get("quest_update")})
    if content.get("event"):
        add_tool("quest_event", {"event": content.get("event")})
    if content.get("discovered_location"):
        add_tool("discover_location", {"location": content.get("discovered_location")})
    if content.get("quest"):
        add_tool("generate_quest", {"quest": content.get("quest")})
    if content.get("quests"):
        add_tool("generate_quest", {"quests": content.get("quests")})
    if content.get("npcs"):
        add_tool("spawn_npc", {"npcs": content.get("npcs")})
    if content.get("enemies") or content.get("opponents"):
        add_tool("spawn_enemy", {"enemies": content.get("enemies") or content.get("opponents")})
    if content.get("boss_npc"):
        add_tool("spawn_boss", {"boss_npc": content.get("boss_npc")})
    if content.get("new_npc_requests"):
        add_tool("request_npc_generation", {"requests": content.get("new_npc_requests")})
    if content.get("item_add"):
        add_tool("item_add", {"item_add": content.get("item_add")})
    if content.get("item_remove"):
        add_tool("item_remove", {"item_remove": content.get("item_remove")})
    if content.get("item_equip"):
        add_tool("item_equip", {"item_equip": content.get("item_equip")})
    if content.get("item_unequip"):
        add_tool("item_unequip", {"item_unequip": content.get("item_unequip")})
    if content.get("relationship_change"):
        add_tool("npc_change_relationship", {"relationship_change": content.get("relationship_change")})
    if content.get("memory_updates"):
        add_tool("npc_update_memory", {"memory_updates": content.get("memory_updates")})
    if content.get("game_over"):
        add_tool(
            "game_over",
            {
                "game_over": content.get("game_over"),
                "game_over_reason": content.get("game_over_reason") or content.get("reason") or "",
                "game_over_narration": content.get("game_over_narration") or content.get("narration") or "",
            },
        )
    time_args: dict[str, Any] = {}
    for key in (
        "time_passed_hours",
        "time_passed_days",
        "advance_time_hours",
        "long_time_passage_hours",
        "time_skip_hours",
        "spend_time_hours",
        "time_reason",
    ):
        if key in content:
            time_args[key] = content[key]
    if time_args:
        add_tool("time_passage", time_args)

    hunger_args: dict[str, Any] = {}
    for key in (
        "hunger_delta",
        "player_hunger_delta",
    ):
        if key in content:
            hunger_args[key] = content[key]
    if hunger_args:
        add_tool("hunger_delta", hunger_args)

    gold_args: dict[str, Any] = {}
    for key in (
        "gold_delta",
        "receive_gold",
        "gain_gold",
        "spend_gold",
        "pay_gold",
    ):
        if key in content:
            gold_args[key] = content[key]
    if gold_args:
        add_tool("gold_delta", gold_args)

    exp_args: dict[str, Any] = {}
    for key in (
        "player_exp_delta",
        "exp_delta",
        "exp",
        "xp",
        "target",
        "target_name",
        "character_name",
        "npc_name",
        "target_uuid",
    ):
        if key in content:
            exp_args[key] = content[key]
    if exp_args:
        add_tool("exp_delta", exp_args)

    sanitized: dict[str, Any] = {
        "intent": content.get("intent") or {"kind": manager_name, "summary": str(content.get("think") or content.get("summary") or "")},
        "narration": str(content.get("narration") or content.get("text") or content.get("message") or ""),
        "choices": list(content.get("choices") or []),
        "tool_judgements": tool_judgements,
    }
    for key in (
        "content_violation",
        "think",
        "process",
        "finished",
        "speaker",
        "topic",
        "mood",
        "quest_name",
        "objective",
        "destination_location",
        "objective_subnode_name",
        "summary",
        "recipients",
        "reason",
        "message",
        "event_occurred",
    ):
        if key in content:
            sanitized[key] = content[key]
    return sanitized


class LlamaCppCompletionBackend(BaseLlmBackend):
    name = "llama_cpp_completion"

    def __init__(self, config: AppConfig, backend_name: str, runtime_kind: str) -> None:
        self.config = config
        self.name = backend_name
        self.runtime_kind = runtime_kind
        self.process: subprocess.Popen[str] | None = None
        self.log_handle = None
        self.log_path: Path | None = None
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        self._ensure_started()
        if not self.health_check():
            self.restart("health check failed before request")
        prompt = self._apply_template(messages)
        request_params = _completion_params(self.config, manager_name, max_tokens)
        payload = _llama_completion_payload(prompt, request_params, max_tokens)
        try:
            data = _post_json(f"{self.base_url}/completion", payload, timeout=180)
        except Exception:
            self.restart("completion request failed")
            data = _post_json(f"{self.base_url}/completion", payload, timeout=180)
        content = data.get("content") if isinstance(data, dict) else data
        parsed = _try_parse_json(content)
        return LlmResult(content=parsed, backend=self.name, request_params=_loggable_request_params(payload))

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self._write_log_line("stopping llama-server")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._write_log_line("terminate timed out; killing llama-server")
                self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self.process = None
        self._close_log_handle()

    def restart(self, reason: str) -> None:
        self._write_log_line(f"restart requested: {reason}")
        self.stop()
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._ensure_started()

    def health_check(self) -> bool:
        if not self.process or self.process.poll() is not None:
            return False
        try:
            _get_json(f"{self.base_url}/v1/models", timeout=3)
            return True
        except Exception as exc:
            self._write_log_line(f"health check failed: {exc}")
            return False

    def _ensure_started(self) -> None:
        if self.process and self.process.poll() is None and self.health_check():
            return

        self.stop()
        exe = self._server_path()
        model = _resolve_model_path(self.config.local_llm.get("model_path", ""))
        if not exe.exists():
            raise LlmError(f"llama-server.exe not found: {exe}")
        if not model.exists():
            raise LlmError(f"GGUF model not found: {model}")

        params = self._server_params()
        command = [str(exe), "--model", str(model), "--port", str(self.port)]
        command.extend(_split_params(params))
        env = os.environ.copy()
        self._open_log_handle(command)
        self._write_log_line(f"starting {self.name} on {self.base_url}")
        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 120
        while time.time() < deadline:
            if self.process and self.process.poll() is not None:
                raise LlmError(
                    "llama-server exited before becoming ready"
                    + (f"\nlog={self.log_path}\n{_tail_file(self.log_path)}" if self.log_path else "")
                )
            try:
                _get_json(f"{self.base_url}/v1/models", timeout=2)
                self._write_log_line("llama-server is ready")
                return
            except Exception as exc:
                self._write_log_line(f"waiting for health endpoint: {exc}")
                time.sleep(1)
        raise LlmError(
            "llama-server did not become ready in time"
            + (f"\nlog={self.log_path}\n{_tail_file(self.log_path)}" if self.log_path else "")
        )

    def _apply_template(self, messages: list[dict[str, str]]) -> str:
        payload = {"messages": messages, "add_generation_prompt": True, "enable_thinking": False}
        try:
            data = _post_json(f"{self.base_url}/apply-template", payload, timeout=30)
        except Exception:
            payload.pop("enable_thinking", None)
            data = _post_json(f"{self.base_url}/apply-template", payload, timeout=30)
        if isinstance(data, str):
            return data
        for key in ("prompt", "content", "result"):
            if isinstance(data, dict) and isinstance(data.get(key), str):
                return data[key]
        return json.dumps(messages, ensure_ascii=False)

    def _server_path(self) -> Path:
        local_llm = self.config.local_llm
        server_paths = local_llm.get("server_paths")
        if isinstance(server_paths, dict) and server_paths.get(self.runtime_kind):
            return _resolve_path(str(server_paths[self.runtime_kind]))
        explicit_key = f"{self.runtime_kind}_server_path"
        if local_llm.get(explicit_key):
            return _resolve_path(str(local_llm[explicit_key]))
        if local_llm.get("server_path"):
            return _resolve_path(str(local_llm["server_path"]))
        defaults = {
            "cpu": BIN_DIR / "llama" / "llama-server.exe",
            "vulkan": BIN_DIR / "llama" / "llama-server.exe",
            "cuda": BIN_DIR / "llama-cuda" / "llama-server.exe",
        }
        return _resolve_path(defaults[self.runtime_kind])

    def _server_params(self) -> str:
        params = self.config.server_parameters
        raw = (
            params.get(self.name)
            or params.get(f"llama_cpp_completion_{self.runtime_kind}")
            or params.get("llama_cpp_completion")
            or ""
        )
        return _apply_context_size(raw, self.config.llm_context_size)

    def _open_log_handle(self, command: list[str]) -> None:
        self._close_log_handle()
        folder = LOG_DIR / "llama-server"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = folder / f"{timestamp}-{self.name}.log"
        self.log_handle = self.log_path.open("a", encoding="utf-8", errors="replace")
        self._write_log_line("command: " + _quote_command(command))

    def _write_log_line(self, message: str) -> None:
        if not self.log_handle:
            return
        self.log_handle.write(f"[fantasia {datetime.now().isoformat(timespec='seconds')}] {message}\n")
        self.log_handle.flush()

    def _close_log_handle(self) -> None:
        if self.log_handle:
            try:
                self.log_handle.close()
            except OSError:
                pass
        self.log_handle = None


class OpenAiResponsesBackend(BaseLlmBackend):
    name = "cloud_openai"

    def __init__(self, config: AppConfig, backend_name: str = "cloud_openai") -> None:
        self.config = config
        self.name = backend_name
        self.provider = "openai"
        self.model = _cloud_model(config, self.provider, "gpt-5.1-mini")
        self.base_url = _cloud_base_url(config, self.provider, "https://api.openai.com/v1").rstrip("/")
        self.timeout = _cloud_timeout(config)

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        request_params = _completion_params(self.config, manager_name, max_tokens)
        payload = {
            "model": self.model,
            "input": _openai_responses_input(messages),
            "max_output_tokens": _param_int(request_params, ("max_output_tokens", "max_tokens", "n_predict"), max_tokens),
        }
        _copy_params(payload, request_params, ("temperature", "top_p", "top_logprobs", "truncation"))
        data = _post_json_with_headers(
            f"{self.base_url}/responses",
            payload,
            _bearer_headers(_cloud_api_key(self.config, self.provider)),
            timeout=self.timeout,
        )
        text = _openai_response_text(data)
        return LlmResult(content=_try_parse_json(text), backend=f"{self.name}:{self.model}", request_params=_loggable_request_params(payload))


class OpenAiCompatibleChatBackend(BaseLlmBackend):
    name = "cloud_xai"

    def __init__(self, config: AppConfig, backend_name: str, provider: str) -> None:
        self.config = config
        self.name = backend_name
        self.provider = provider
        default_model = "grok-4.3" if provider == "xai" else "gpt-5.1-mini"
        default_url = "https://api.x.ai/v1" if provider == "xai" else "https://api.openai.com/v1"
        self.model = _cloud_model(config, provider, default_model)
        self.base_url = _cloud_base_url(config, provider, default_url).rstrip("/")
        self.timeout = _cloud_timeout(config)

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        request_params = _completion_params(self.config, manager_name, max_tokens)
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": _param_int(request_params, ("max_tokens", "n_predict"), max_tokens),
            "temperature": float(request_params.get("temperature", _cloud_value(self.config, self.provider, "temperature", 0.9))),
            "top_p": float(request_params.get("top_p", _cloud_value(self.config, self.provider, "top_p", 0.9))),
        }
        _copy_params(payload, request_params, ("presence_penalty", "frequency_penalty", "stop"))
        data = _post_json_with_headers(
            f"{self.base_url}/chat/completions",
            payload,
            _bearer_headers(_cloud_api_key(self.config, self.provider)),
            timeout=self.timeout,
        )
        text = _chat_completion_text(data)
        return LlmResult(content=_try_parse_json(text), backend=f"{self.name}:{self.model}", request_params=_loggable_request_params(payload))


class GeminiGenerateContentBackend(BaseLlmBackend):
    name = "cloud_gemini"

    def __init__(self, config: AppConfig, backend_name: str = "cloud_gemini") -> None:
        self.config = config
        self.name = backend_name
        self.provider = "gemini"
        self.model = _cloud_model(config, self.provider, "gemini-2.5-flash")
        self.base_url = _cloud_base_url(config, self.provider, "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.timeout = _cloud_timeout(config)

    def chat(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> LlmResult:
        request_params = _completion_params(self.config, manager_name, max_tokens)
        payload = _gemini_payload(messages, max_tokens, self.config, request_params)
        data = _post_json_with_headers(
            f"{self.base_url}/models/{self.model}:generateContent",
            payload,
            {
                "Content-Type": "application/json",
                "x-goog-api-key": _cloud_api_key(self.config, self.provider),
            },
            timeout=self.timeout,
        )
        text = _gemini_response_text(data)
        return LlmResult(content=_try_parse_json(text), backend=f"{self.name}:{self.model}", request_params=payload.get("generationConfig", {}))


def create_llm_backend(config: AppConfig) -> BaseLlmBackend:
    backend = config.llm_backend
    if backend in LOCAL_LLAMA_BACKENDS:
        return LlamaCppCompletionBackend(config, backend, LOCAL_LLAMA_BACKENDS[backend])
    if backend in {"cloud_openai", "cloud_chatgpt"}:
        return OpenAiResponsesBackend(config, backend)
    if backend == "cloud_xai":
        return OpenAiCompatibleChatBackend(config, backend, "xai")
    if backend == "cloud_gemini":
        return GeminiGenerateContentBackend(config, backend)
    if backend in CLOUD_LLM_BACKENDS:
        provider = CLOUD_LLM_BACKENDS[backend]
        if provider == "gemini":
            return GeminiGenerateContentBackend(config, backend)
        if provider == "openai":
            return OpenAiResponsesBackend(config, backend)
        return OpenAiCompatibleChatBackend(config, backend, provider)
    raise LlmError(
        "Unknown LLM backend: "
        f"{backend}. Expected one of: {', '.join(sorted(set(LOCAL_LLAMA_BACKENDS) | set(CLOUD_LLM_BACKENDS)))}"
    )


def _cloud_provider_config(config: AppConfig, provider: str) -> dict[str, Any]:
    value = config.cloud_llm.get(provider)
    return value if isinstance(value, dict) else {}


def _cloud_value(config: AppConfig, provider: str, key: str, default: Any = "") -> Any:
    provider_config = _cloud_provider_config(config, provider)
    if key in provider_config:
        return provider_config[key]
    value = config.cloud_llm.get(key)
    if isinstance(value, dict):
        return value.get(provider, default)
    if value not in (None, ""):
        return value
    return default


def _cloud_model(config: AppConfig, provider: str, default: str) -> str:
    return str(_cloud_value(config, provider, "model", default))


def _cloud_base_url(config: AppConfig, provider: str, default: str) -> str:
    return str(_cloud_value(config, provider, "base_url", default))


def _cloud_timeout(config: AppConfig) -> int:
    return int(config.cloud_llm.get("timeout_sec", 180))


def _cloud_api_key(config: AppConfig, provider: str) -> str:
    default_env = {
        "openai": "OPENAI_API_KEY",
        "xai": "XAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }[provider]
    env_name = str(_cloud_value(config, provider, "api_key_env", default_env))
    env_setting = config.environment_setting
    candidates = [
        env_setting.get(env_name),
        env_setting.get(env_name.lower()),
        env_setting.get(f"{provider}_api_key"),
        os.environ.get(env_name),
    ]
    api_key = next((str(value).strip() for value in candidates if str(value or "").strip()), "")
    if not api_key:
        raise LlmError(f"{provider} API key is not configured. Set {env_name} or environment_setting.{provider}_api_key.")
    return api_key


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}


def _completion_params(config: AppConfig, manager_name: str, fallback_max_tokens: int) -> dict[str, Any]:
    raw = config.completion_parameters
    result: dict[str, Any] = {}
    default = raw.get("default") if isinstance(raw, dict) else {}
    if isinstance(default, dict):
        result.update(default)
    managers = raw.get("managers") if isinstance(raw, dict) else {}
    manager_params = managers.get(manager_name) if isinstance(managers, dict) else {}
    if isinstance(manager_params, dict):
        result.update(manager_params)
    if "max_tokens" not in result and "n_predict" not in result and "max_output_tokens" not in result:
        result["max_tokens"] = fallback_max_tokens
    return {key: value for key, value in result.items() if value is not None}


def _llama_completion_payload(prompt: str, params: dict[str, Any], fallback_max_tokens: int) -> dict[str, Any]:
    payload = dict(params)
    max_tokens = _param_int(payload, ("n_predict", "max_tokens", "max_output_tokens"), fallback_max_tokens)
    payload.pop("max_tokens", None)
    payload.pop("max_output_tokens", None)
    payload["n_predict"] = max_tokens
    payload["prompt"] = prompt
    payload.setdefault("temperature", 0.9)
    payload.setdefault("top_p", 0.9)
    payload.setdefault("cache_prompt", True)
    return payload


def _loggable_request_params(params: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in params.items():
        if key in _LARGE_REQUEST_KEYS:
            result[f"{key}_chars"] = _text_size(value)
            preview = _preview_text(value)
            if preview:
                result[f"{key}_preview"] = preview
            continue
        result[key] = value
    return result


def _text_size(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    return len(json.dumps(value, ensure_ascii=False))


def _preview_text(value: Any, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if not text:
        return ""
    return text[:limit] + ("... [truncated]" if len(text) > limit else "")


_LARGE_REQUEST_KEYS = {"prompt", "input", "messages", "contents", "systemInstruction"}


def _param_int(params: dict[str, Any], names: tuple[str, ...], fallback: int) -> int:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return int(fallback)


def _copy_params(target: dict[str, Any], source: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def _openai_responses_input(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        if role == "system":
            role = "developer"
        result.append({"role": role, "content": str(message.get("content") or "")})
    return result


def _openai_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data)
    if isinstance(data.get("output_text"), str):
        return str(data["output_text"])
    parts: list[str] = []
    for item in data.get("output", []) if isinstance(data.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts) if parts else json.dumps(data, ensure_ascii=False)


def _chat_completion_text(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return str(message["content"])
            if isinstance(first.get("text"), str):
                return str(first["text"])
    return json.dumps(data, ensure_ascii=False)


def _gemini_payload(
    messages: list[dict[str, str]],
    max_tokens: int,
    config: AppConfig,
    request_params: dict[str, Any],
) -> dict[str, Any]:
    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        text = str(message.get("content") or "")
        if role == "system":
            system_parts.append({"text": text})
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": _param_int(request_params, ("max_output_tokens", "max_tokens", "n_predict"), max_tokens),
            "temperature": float(request_params.get("temperature", _cloud_value(config, "gemini", "temperature", 0.9))),
            "topP": float(request_params.get("top_p", _cloud_value(config, "gemini", "top_p", 0.9))),
        },
    }
    if request_params.get("top_k") is not None:
        payload["generationConfig"]["topK"] = int(request_params["top_k"])
    if request_params.get("stop"):
        payload["generationConfig"]["stopSequences"] = request_params["stop"]
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def _gemini_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data)
    parts: list[str] = []
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []) if isinstance(content.get("parts"), list) else []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(str(part["text"]))
    return "\n".join(parts) if parts else json.dumps(data, ensure_ascii=False)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _resolve_model_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    return resolve_model_path(str(value or ""), "text")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _split_params(params: str) -> list[str]:
    return shlex.split(params) if params.strip() else []


def _apply_context_size(params: str, context_size: int) -> str:
    tokens = _split_params(params)
    cleaned: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in _CTX_SIZE_FLAGS:
            skip_next = True
            continue
        if any(token.startswith(f"{flag}=") for flag in _CTX_SIZE_FLAGS if flag.startswith("--")):
            continue
        cleaned.append(token)
    cleaned.extend(["--ctx-size", str(max(1024, int(context_size)))])
    return shlex.join(cleaned)


_CTX_SIZE_FLAGS = {"--ctx-size", "--ctx_size", "--context-size", "-c"}


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> Any:
    return _post_json_with_headers(url, payload, {"Content-Type": "application/json"}, timeout)


def _post_json_with_headers(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LlmError(f"{url} returned HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc


def _get_json(url: str, timeout: int) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _quote_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def _tail_file(path: Path | None, lines: int = 80) -> str:
    if not path or not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def _try_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    for candidate in (text, _extract_json_payload(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {"text": value}


def _extract_json_payload(text: str) -> str:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return text[index : index + end]
    return ""


def _extract_fixture_payload(text: str) -> dict[str, Any]:
    parsed = _try_parse_json(_extract_json_payload(text))
    return parsed if isinstance(parsed, dict) else {}


def _extract_action(user_text: str) -> str:
    marker = "プレイヤー行動:"
    if marker in user_text:
        return user_text.rsplit(marker, 1)[-1].splitlines()[0].strip()
    return user_text.strip()


def _extract_quest_name(user_text: str) -> str:
    marker = "クエスト名:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""


def _extract_conversation_speaker(user_text: str) -> str:
    marker = "会話相手:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""


def _extract_referee_target(user_text: str) -> str:
    marker = "対象:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    marker = "敵対者:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""


def _extract_fixture_encounter_target(text: str) -> str:
    source = str(text or "").strip()
    patterns = (
        r"([^\s、。,.「」『』（）()\[\]{}:：]{1,30})(?:と|との)(?:戦い|戦闘|バトル|決闘)(?:を)?(?:始め|開始|する|行う)?",
        r"([^\s、。,.「」『』（）()\[\]{}:：]{1,30})(?:に|へ|を)(?:攻撃|斬|撃|殴|刺|襲)",
        r"(?:不意打ち|奇襲|先制攻撃|先制)(?:で|に|から)?([^\s、。,.「」『』（）()\[\]{}:：]{1,30})(?:を|に|へ)",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            value = str(match.group(1) or "").strip("「」[] ")
            if value:
                return value
    return ""


def _extract_fixture_visible_enemy(text: str) -> str:
    source = str(text or "")
    parsed = _try_parse_json(_extract_json_payload(source))
    if isinstance(parsed, dict):
        context = parsed.get("arrival_context") or parsed.get("context") or {}
        if isinstance(context, dict):
            hostile_npcs = context.get("hostile_npcs")
            if isinstance(hostile_npcs, list):
                for item in hostile_npcs:
                    if isinstance(item, dict):
                        name = str(item.get("name") or "").strip()
                        if name:
                            return name
    for key in ("name", "opponent_name", "target_name"):
        match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', source)
        if match:
            return match.group(1)
    return ""


def _extract_fixture_context_reference(user_text: str, action: str) -> tuple[str, str]:
    allowed = _extract_fixture_allowed_types(user_text)
    source = str(user_text or "")
    if "quest" in allowed:
        for name in ("消えた隊商", "古井戸の光", "霧中の救難声"):
            if name in source:
                return "quest", name
    if "character" in allowed:
        for name in ("ミラ", "レナ", "ヨハン", "ガストン", "エリン", "マルタ"):
            if name in source:
                return "character", name
        match = re.search(r'"visible_characters"\s*:\s*\[[\s\S]*?"name"\s*:\s*"([^"]+)"', source)
        if match:
            return "character", match.group(1)
            if "character" in allowed or "monster" in allowed:
                target = _extract_fixture_encounter_target(action) or _extract_fixture_encounter_target(source)
                if target:
                    return "character", target
    if "location" in allowed:
        match = re.search(r'"current_location"\s*:\s*"([^"]+)"', source)
        if match and any(word in action for word in ("そこ", "その場所", "さっきの場所", "戻る")):
            return "location", match.group(1)
    return "unknown", ""


def _extract_fixture_allowed_types(user_text: str) -> set[str]:
    marker = "許可対象種別:"
    if marker not in user_text:
        return {"character", "monster", "location", "quest", "facility", "item", "action", "unknown"}
    line = user_text.split(marker, 1)[-1].splitlines()[0].strip()
    try:
        parsed = json.loads(line)
    except Exception:
        parsed = []
    if isinstance(parsed, list):
        return {str(item).strip().casefold() for item in parsed if str(item).strip()}
    return {str(parsed).strip().casefold()} if str(parsed).strip() else {"unknown"}


def _extract_character_name(user_text: str) -> str:
    marker = "キャラクター名:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    marker = "対象キャラクター:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""


def _extract_character_role(user_text: str) -> str:
    marker = "役割:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""


def _extract_monster_name(user_text: str) -> str:
    marker = "モンスター名:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    marker = "対象モンスター:"
    if marker in user_text:
        return user_text.split(marker, 1)[-1].splitlines()[0].strip()
    return ""

