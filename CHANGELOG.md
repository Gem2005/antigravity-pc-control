# Changelog

All notable changes to **PC Control** are documented in this file.

## [0.3.0] - 2026-11-26

### Added
- **Windows UI Automation (`server/ui_tree.py`)**: `get_ui_tree` and `ui_action` MCP tools for ~30–60ms element inspection, clicking, focusing, and text entry without screenshots.
- **Multi-Agent `pc-operator` Subagent (`agents/pc-operator.md`)**: Dedicated subagent definition for fast `Model="flash"` GUI execution.
- **Local Real-Time Worker (`server/realtime_worker.py`)**: `realtime_task` MCP tool running a tight local Vision+UIA loop via `google-genai` when `GEMINI_API_KEY` is configured in the environment or `~/.env`.
- `control_session(action="status")` now reports `has_gemini_api_key` safely without exposing secrets.
- Unit tests for `realtime_worker` key loading and 17-tool MCP schema verification.

## [0.2.0] - 2026-11-26

### Added
- `run_gui_sequence` MCP tool for single-turn batched GUI automation with optional post-action screenshot.
- `control_session` MCP tool and `server/overlay_guard.py` (animated border ring, Win32 low-level input lock, interrupt banner, `Ctrl+C` abort, and `25s` watchdog).
- `_ScreenWatcher` background JPEG frame buffer (`1280px`) with `use_cache_ms` support in `take_screenshot`.
- Repository documentation, MIT license, and initial `pytest` suite.

## [0.1.0] - 2026-11-26

### Added
- Initial `pc-control` Antigravity plugin with 12-tool Windows MCP server and 4 Windows skills (`pc-desktop-gui`, `pc-diagnostics`, `pc-network-power`, `pc-maintenance`).
