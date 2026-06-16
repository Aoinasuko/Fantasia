# Fantasia TODO

Created: 2026-06-16

## P2: Distribution And Operations

- [x] Select runtime binary profile during build and asset sync.
- [x] Exclude duplicate CPU/Vulkan binaries from the default CUDA distribution.
- [x] Add crashlog capture for unhandled exceptions, Tk callback exceptions, and thread exceptions.
- [x] Show crashlogs from the Generation Logs screen.
- [ ] Add license collection for bundled runtime binaries and fonts.
- [ ] Add log rotation settings for generation logs and server logs.
- [ ] Add a clean release packaging script.

## P2: Device And Setup

- [x] Detect startup device capability.
- [x] Add first-run setup wizard.
- [x] Auto-select backend from detected GPU capability.
- [x] Keep model sync opt-in and safe by default.
- [ ] Add model download progress persistence after app restart.
- [ ] Add clearer recovery UI for missing model downloads.

## P2: Tests

- [x] Add save smoke test.
- [x] Add encoding check.
- [x] Add runtime asset check.
- [ ] Add unit tests for `--check-assets`.
- [ ] Add manager schema regression tests.
- [ ] Add save/load migration tests for current Fantasia save version only.
- [ ] Add minimal CUDA image generation smoke script.
- [ ] Add llama.cpp CUDA device detection smoke script.
