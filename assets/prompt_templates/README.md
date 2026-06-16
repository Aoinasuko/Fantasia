# Fantasia Prompt Templates

`base.json` applies lightweight prompt overlays without editing Python code.

Supported keys:

- `system_prefix` / `system_suffix`
- `user_prefix` / `user_suffix`
- `schema_instruction`
- `schema_instruction_prefix` / `schema_instruction_suffix`
- `prepend_messages` / `append_messages`

Per-manager files can be placed at `managers/<manager_name>.json`.
