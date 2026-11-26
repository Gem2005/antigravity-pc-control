# MCP Tools Reference

All 17 tools exposed by `pc_control_mcp.py`:

## Control Guard

### `control_session`
Start, stop, or inspect the animated screen border ring, physical input lock, and whether `GEMINI_API_KEY` is configured.
- `action`: `"start" | "stop" | "status"`
- `timeout_seconds` (`float`, default `25.0`): Auto-release watchdog timeout.

## Windows UI Automation (No Screenshots)

### `get_ui_tree`
Inspect live UI Automation controls in the active foreground window or a matched window.
- `window_title` (`str | null`): Optional title substring or HWND (defaults to active foreground window).
- `max_depth` (`int`, default `5`): Tree traversal depth (`1..10`).
- `max_elements` (`int`, default `120`): Element cap (`1..250`).
- `interactive_only` (`bool`, default `true`): Filter to interactive control types (`Button`, `Edit`, `MenuItem`, `ListItem`, `TabItem`, etc.).

### `ui_action`
Interact directly with a matched Windows UI element without taking a screenshot.
- `action`: `"click" | "double_click" | "right_click" | "set_text" | "focus"`
- `name`, `automation_id`, `control_type`: Element matchers.
- `window_title` (`str | null`): Target window (defaults to foreground).
- `text` (`str | null`): Text for `set_text` (uses `ValuePattern` with `paste_text` fallback).
- `exact` (`bool`, default `false`)
- `auto_lock` (`bool`, default `true`)

## Local Real-Time Worker

### `realtime_task`
Run a tight local `UI Tree + JPEG Screenshot -> Gemini Flash -> Action` loop inside the MCP server (requires `GEMINI_API_KEY` in env or `~/.env`).
- `goal` (`str`): Natural-language desktop goal.
- `max_steps` (`int`, default `12`): Maximum iterations (`1..30`).
- `model` (`str`, default `"gemini-2.5-flash"`): Gemini model ID.
- `window_title` (`str | null`): Optional target window scope for UIA inspection.
- `include_screenshot` (`bool`, default `true`)

## Vision & Batched GUI Automation

### `take_screenshot`
Capture the desktop, a monitor, or a window (`jpeg` default, `use_cache_ms=400`).

### `run_gui_sequence`
Execute multiple GUI steps (`focus_window`, `launch_app`, `click`, `double_click`, `right_click`, `move`, `drag`, `scroll`, `type`, `paste_text`, `press`, `hotkey`, `wait`) in one MCP call and optionally return the updated screenshot.

### `mouse_action` & `keyboard_action`
Single-step cursor and keyboard primitives (prefer `ui_action` or `run_gui_sequence`).

## Windows, Apps & Clipboard

- `list_windows(include_untitled=false)`
- `manage_window(action, title_or_hwnd)` — `focus`, `minimize`, `maximize`, `restore`, `close`
- `launch_app(target, args=null, working_dir=null)`
- `clipboard(action, text=null)` — `get` or `set`

## System Telemetry & Files

- `system_overview()`
- `list_processes(filter_name=null, sort_by="memory", limit=30)`
- `stop_process(pid, force=false)`
- `list_services(filter_text=null, status="all", limit=60)`
- `find_files(root_path, pattern="*", max_results=50, include_dirs=false)`
