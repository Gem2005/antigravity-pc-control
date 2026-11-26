# Changelog

All notable changes to **PC Control** are documented in this file.

## [0.2.0] - 2026-11-26

### Added
- `run_gui_sequence` MCP tool for single-turn batched GUI automation with optional post-action screenshot.
- `control_session` MCP tool and `server/overlay_guard.py` providing:
  - Animated multi-color glowing border ring around the primary monitor.
  - Physical keyboard/mouse lock via Win32 low-level hooks (`WH_KEYBOARD_LL`, `WH_MOUSE_LL`) while passing injected automation events through.
  - Top-center interrupt warning pill (`Gemini has control of your PC • To stop, press Ctrl+C`).
  - Immediate `Ctrl+C` emergency abort (`ABORTED_BY_USER`) and `25s` watchdog auto-release.
- `_ScreenWatcher` background JPEG frame buffer (`1280px`) with `use_cache_ms` support in `take_screenshot`.
- Repository documentation (`README.md`, `docs/`, `CONTRIBUTING.md`, `LICENSE`), unit/stdio tests (`server/tests/test_pc_control.py`), and GitHub Actions CI (`.github/workflows/ci.yml`).

### Changed
- Switched `take_screenshot` default format from `PNG (optimize=True)` to fast `JPEG` (`quality=80`, `max_width=1280`).
- Reduced `pyautogui.PAUSE` to `0.01s` and eliminated unnecessary cursor movement animation delays.
- Updated `mcp_config.json` to launch portably via `uv --directory server run pc_control_mcp.py`.
- Updated `pc-desktop-gui` skill and `rules/AGENTS.md` for batched sequences and `Ctrl+C` interrupt handling.

## [0.1.0] - 2026-11-26

### Added
- Initial `pc-control` Antigravity plugin with 12-tool Windows MCP server (`pc_control_mcp.py`).
- Four Windows skills (`pc-desktop-gui`, `pc-diagnostics`, `pc-network-power`, `pc-maintenance`) with PowerShell diagnostic helpers.
- Tiered safety rules in `rules/AGENTS.md`.
