from __future__ import annotations

import json
import os
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
                        "overview": "最後に灯守りの宿を出た隊商の足取りを追う。",
                        "neighboring_settlement": "灯守りの宿",
                        "choices": ["掲示板を確認する", "馬丁に話を聞く"],
                    },
                    {
                        "name": "古井戸の光",
                        "overview": "雨の夜に古井戸の底で揺れる青い光を調べる。",
                        "neighboring_settlement": "灯守りの宿",
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
                "choices": ["炉番のレナに話しかける", "品物を見る", "街の地図を見る"],
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
                    "narration": "掲示板の依頼札は雨で滲んでいる。隊商は三日前、硝子森へ向かったまま戻っていない。",
                    "choices": ["掲示板を読む", "馬丁に話を聞く", "硝子森へ向かう"],
                }
        elif manager_name == "field_event_evaluator":
            action = _extract_action(user_text) or "周辺を探索する"
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
        elif manager_name == "master_ai_facilitator":
            action = _extract_action(user_text) or "状況を見る"
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
                                "description": "周辺の薬草や毒草を見分ける。",
                                "skill_type": "support",
                                "effects": [{"name": "治療手がかり", "value": 1}],
                                "sp_cost": 3,
                                "usefulness": "探索と会話で追加情報を出せる。",
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
                        "description": "雨で悪化する状態異常を一時的に和らげる。",
                        "skill_type": "support",
                        "effects": [{"name": "状態異常緩和", "value": 1}],
                        "sp_cost": 2,
                        "usefulness": "探索前の準備や会話イベントに使える。",
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
        elif manager_name == "referee_player_attack_new_new":
            action = _extract_action(user_text) or "攻撃する"
            target = _extract_referee_target(user_text) or "硝子森の影"
            content = {
                "target": target,
                "hit": True,
                "damage": 3,
                "narration": f"あなたの攻撃「{action}」は霧を裂き、{target}の輪郭をわずかに揺らした。",
                "encounter_update": {
                    "opponent_hp_delta": -3,
                    "opponent_status": "wounded",
                    "player_status": "armed",
                },
                "effects": [{"name": "牽制", "duration": 1}],
                "finished": False,
                "choices": ["距離を取る", "追撃する", "降伏する"],
            }
        elif manager_name == "referee_player_any_input_new_new":
            action = _extract_action(user_text) or "様子を見る"
            surrendering = "降伏" in action or "武器を捨て" in action or "両手" in action
            content = {
                "intent": "surrender" if surrendering else "free_action",
                "narration": (
                    "あなたは武器を下ろし、敵意がないことを示した。"
                    if surrendering
                    else f"あなたは戦闘中に「{action}」を試みた。"
                ),
                "encounter_update": (
                    {"player_status": "surrendering", "player_surrendered": True}
                    if surrendering
                    else {"player_status": "acting"}
                ),
                "effects": [],
                "finished": False,
                "content_violation": False,
                "choices": ["両手を上げる", "事情を説明する", "相手の反応を待つ"] if surrendering else ["身構える", "距離を取る", "降伏する"],
            }
        elif manager_name == "referee_npc":
            target = _extract_referee_target(user_text) or "硝子森の影"
            surrendering = (
                '"intent": "surrender"' in user_text
                or '"player_surrendered": true' in user_text
                or '"player_status": "surrendering"' in user_text
            )
            if surrendering:
                content = {
                    "npc_action": "accept_surrender",
                    "intent": "mercy",
                    "target": "Player",
                    "narration": f"{target}はすぐには踏み込まず、あなたが本当に武器を捨てたかを見極めている。",
                    "encounter_update": {
                        "opponent_status": "guarded",
                        "player_status": "surrender_accepted",
                    },
                    "effects": [{"name": "戦闘停止", "duration": 1}],
                    "finished": True,
                    "should_end_encounter": True,
                    "choices": ["事情を説明する", "ゆっくり離れる"],
                }
            else:
                content = {
                    "npc_action": "counterattack",
                    "intent": "self_defense",
                    "target": "Player",
                    "narration": f"{target}は傷ついた輪郭を震わせ、反撃の姿勢を取った。",
                    "encounter_update": {"opponent_status": "hostile", "player_status": "threatened"},
                    "effects": [{"name": "圧迫", "duration": 1}],
                    "finished": False,
                    "should_end_encounter": False,
                    "choices": ["防御する", "距離を取る", "降伏する"],
                }
        elif manager_name == "referee_npc_rewrite":
            target = _extract_referee_target(user_text) or "硝子森の影"
            accepting = (
                '"npc_action": "accept_surrender"' in user_text
                or '"player_status": "surrender_accepted"' in user_text
            )
            content = {
                "npc_action": "accept_surrender" if accepting else "counterattack",
                "narration": (
                    f"{target}は攻撃を止めた。雨音の中、低く唸るだけで、あなたに武器を遠ざけろと促している。"
                    if accepting
                    else f"{target}は霧をまとって踏み込み、あなたを追い払うための一撃を放とうとする。"
                ),
                "encounter_update": (
                    {"opponent_status": "watching", "player_status": "surrender_accepted"}
                    if accepting
                    else {"opponent_status": "attacking", "player_status": "under_attack"}
                ),
                "finished": accepting,
                "rewrite_reason": (
                    "降伏の意思と相手の慎重な性格を反映し、即時攻撃ではなく拘束/警戒に変えた。"
                    if accepting
                    else "相手の敵対状態を自然文として整えた。"
                ),
                "choices": ["事情を説明する", "ゆっくり離れる"] if accepting else ["防御する", "反撃する", "降伏する"],
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
                        "name": "噂の照合",
                        "description": "複数の証言を照らし合わせ、探索先の候補を絞る。",
                        "skill_type": "support",
                        "effects": [{"name": "手がかり発見", "value": 1}],
                        "sp_cost": 3,
                        "usefulness": "会話や探索前の情報収集に役立つ。",
                    },
                    {
                        "name": "雨音読み",
                        "description": "雨や霧の変化から危険の接近を察する。",
                        "skill_type": "passive",
                        "effects": [{"name": "危険察知", "value": 1}],
                        "sp_cost": 0,
                        "usefulness": "フィールドイベントや戦闘前兆の説明に使える。",
                    },
                ]
            }
        elif manager_name == "narrator_initial":
            content = {
                "narration": "雨音の奥で、宿の主人があなたに古びた地図を差し出した。地図の端には、まだインクの乾いていない赤い印がある。",
                "location": "灯守りの宿",
                "choices": ["地図を見る", "宿の主人に話しかける", "宿の外へ出る"],
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
                    "plain light background",
                    "detailed outfit",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, extra fingers, bad hands",
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
                    "plain light background",
                ],
                "negative_prompt": "low quality, blurry, text, watermark, cropped, extra limbs",
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
        return LlmResult(content=content, backend=self.name)


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
