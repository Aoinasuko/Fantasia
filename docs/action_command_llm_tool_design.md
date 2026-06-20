# ActionCommand / LLM Tool Refactor Design

## 2026-06-20 Implementation Note
- Quest destination movement is executed only when `ActionCommandType.QUEST_GO_TO_DESTINATION` is passed into quest resolution.
- `quest_report`, `quest_objective_action`, and `quest_abandon` must not move the player even when LLM `location`, `narration`, or `choices` mention the quest destination.
- Quest `choices` are display-only. They must not be used as evidence for movement, quest reporting, reward grants, combat start, or quest completion.
- `quest_referee_with_free_action` receives `action_command_type` in the prompt so the LLM can keep non-movement quest actions at the current location.

## 2026-06-20 Intent / Tool JSON Migration Note
- Normal action, field event, quest, and conversation managers now express game-state changes through top-level `tools[]`.
- Display fields such as `narration` and `choices` are intentionally ignored for movement, combat start, item changes, quest progress, NPC generation, and world-state side effects.
- `llm_tool.py` owns tool parsing, normalization, and common side-effect dispatch. `GameEngine` should read side-effect payloads through `tool_effect_payload(...)` or the specific tool helpers.
- Top-level legacy side-effect keys such as `location`, `quest_progress`, `quest_update`, `event`, `relationship_change`, `memory_updates`, `new_npc_requests`, `discovered_location`, `boss_npc`, and reward/status fields are no longer part of these manager schemas.
- Fixture LLM responses are converted to the new intent/tool shape before validation so local tests exercise the same contract.

## 2026-06-20 Progress Tool Split Note
- Do not use `progress_effects` as an LLM tool.
- Use `gold_delta`, `hunger_delta`, `exp_delta`, `time_passage`, and `game_over` as separate tools.
- `exp_delta` may include `target`, `target_name`, `npc_name`, or `target_uuid`; omitted targets apply to the player.
- Equipment HP/SP regeneration is not an LLM tool. It is applied mechanically once per elapsed hour and once per combat turn.

## 目的

選択肢や自由入力の自然文から、ゲーム側の副作用を直接推測しない構造へ移行する。

今後の基本方針は以下。

- プレイヤー入力は `player_action.py` の `ActionCommand` として分類する。
- LLM応答に含まれる状態更新は `llm_tool.py` の `LlmToolName` として扱う。
- narration や choices は表示用であり、移動・報酬・戦闘開始などの副作用の根拠にしない。
- 副作用を起こす場合は、型付きコマンドまたは型付きツールを経由する。

## player_action.py

`src/fantasia/player_action.py` は、選択肢および自由入力の受付と、行動時ルーティングの入口を持つ。

主要定義:

- `PlayerInputType`
  - `choice`
  - `free_action`
- `ActionCommandType`
  - `quest_start`
  - `quest_report`
  - `quest_go_to_destination`
  - `quest_objective_action`
  - `quest_abandon`
  - `conversation_start`
  - `conversation_continue`
  - `skill`
  - `master_ai`
  - `attack`
  - `craft`
  - `facility`
  - その他、既存ルートに対応する型
- `ActionCommand`
  - 実際に選ばれた処理を表す型付きコマンド。
  - `world_data.history` に `manager=player_action` として記録される。
- `resolve_player_input(...)`
  - 既存 `GameEngine._resolve_player_input` の実処理を担当する。
  - 現段階では既存順序を維持しつつ、どのルートに入ったかを `ActionCommand` で記録する。
  - 探索・調査・鍵開け・宝箱の罠解除は専用 `ActionCommandType` にせず、行動文として処理する。
  - スキル使用だけは `skill` として記録する。

## llm_tool.py

`src/fantasia/llm_tool.py` は、LLMが返す副作用フィールドの適用を集約する。

主要定義:

- `LlmToolName`
  - `status_effects`
  - `hp_effects`
  - `sp_effects`
  - `gold_delta`
  - `hunger_delta`
  - `exp_delta`
  - `time_passage`
  - `game_over`
  - `npc_change_relationship`
  - `npc_move`
  - `npc_join_party`
  - `npc_remove_party`
  - `npc_dead`
  - `npc_capture_player`
  - `npc_update_memory`
  - `npc_update_description`
  - `world_home_construction`
  - `world_mainnode_reveal`
  - `world_subnode_reveal`
  - `crime_risk`
  - `item_add`
  - `item_remove`
  - `item_equip`
  - `item_unequip`
  - `visual_intent`
  - `movement_status`
  - `npc_action`
- `LlmToolCall`
  - LLM応答から適用するツール呼び出し。
- `LlmToolResult`
  - ツール適用結果。
- `apply_common_response_tools(...)`
  - master_ai など通常行動で共通利用する副作用適用手順。
- `apply_npc_action_tool(...)`
  - NPCの `flee` / `surrender` を処理する戦闘用ツール。

現段階では、状態更新の実体は既存の `GameEngine._apply_response_*` メソッドを呼ぶ。
次段階で、個別ツールの実装を `llm_tool.py` 側へ移していく。

## 現在の接続

- `GameEngine._resolve_player_input(...)`
  - `player_action.resolve_player_input(...)` に委譲する。
- `GameEngine._resolve_master_ai_turn(...)`
  - LLM副作用を `llm_tool.apply_common_response_tools(...)` 経由で適用する。
- `GameEngine._apply_npc_action_tool(...)`
  - `llm_tool.apply_npc_action_tool(...)` に委譲する。

## 次の移行ステップ

1. クエスト中の `ActionCommandType` は旧 `quest_turn` を使わず、以下のどれかに分ける。
   - `quest_report`: 依頼主・ギルド・受付への報告、報酬受け取り、完了申告。
   - `quest_go_to_destination`: 確定済み目的地・現地・目標地点へ向かう行動。
   - `quest_objective_action`: 救出、討伐、回収、調査、会話、鍵開けなどクエスト目標を進める行動。
   - `quest_abandon`: 撤退、破棄、諦める行動。

2. クエスト中の移動副作用を明示型に限定する。
   - `report` 系コマンドでは目的地名が文中に含まれていても移動しない。
   - `go_to_destination` 系コマンドだけが目的地移動を試みる。

3. LLMの choices を表示専用にする。
   - 将来的には選択肢ごとに `command_id` を持たせる。
   - 表示文から移動・報告・戦闘開始を再推測しない。

4. `llm_tool.py` に個別ツール実装を順次移す。
   - 報酬
   - NPC移動
   - map reveal
   - status effect
   - HP/SP/時間/経験値

5. LLMプロンプトを「副作用JSON」ではなく「intent/tool JSON」へ寄せる。
   - `narration` は描写。
   - `choices` は表示。
   - `tools` または `command` が副作用。

## 禁止事項

- narration 内の地名だけでプレイヤーを移動させない。
- choices の表示文だけで副作用を確定しない。
- クエスト報告と目的地移動を同じ曖昧な自然文判定で処理しない。
- LLMにゲーム状態の最終決定権を渡さない。

## 判断基準

新しい行動やLLM応答を追加する時は、以下の順で考える。

1. これはプレイヤー入力のルーティングか。
   - そうなら `ActionCommandType` を追加する。
2. これはLLM応答による状態更新か。
   - そうなら `LlmToolName` を追加する。
3. これは表示だけか。
   - そうなら narration / choices に留める。
