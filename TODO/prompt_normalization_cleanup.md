# Prompt And Normalization Cleanup TODO

Created: 2026-06-22

## Fix Now

- [x] Accept only canonical `tool_judgements` entries in `llm_tool.py`.
- [x] Remove broad normal-tool aliases such as `quest`, `event`, `move`, and `tools`.
- [x] Accept only canonical `tool_judgements` entries in `combat_llm_tool.py`.
- [x] Update local combat fallback payloads from `tools` to `tool_judgements`.
- [x] Stop showing top-level side-effect instructions when a manager uses `tool_judgements`.
- [x] Limit collection response wrapping to declared item keys only.
- [x] Stop auto-filling settlement detail descriptions/facilities from structure.
- [x] Keep trait duplicate prompts on the current `name`/`desc` shape.
- [x] Repair and validate nested traits in `create_initial_character_profile`.
- [x] Remove ignored trait instructions from `npc_detail_generater`.
- [x] Make invalid combat skill effect types fail instead of defaulting to a single attack.

## Later Cleanup Candidates

- [x] Review remaining schema aliases that only exist for old response compatibility.
- [x] Remove unused top-level state-side-effect aggregation paths in `game.py`.
- [x] Make status-effect execution require explicit `effect_id` for LLM tools.
- [x] Review UI-side skill parsing defaults so missing effect type is never treated as attack.
- [x] Remove stale trait fallback branches in the character entry generator UI.
