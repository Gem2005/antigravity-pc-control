# MCP Tools Reference

All 14 tools exposed by `pc_control_mcp.py`:

## Control Guard

### `control_session`
Start, stop, or check the animated screen border ring and physical input lock.
- `action`: `"start" | "stop" | "status"`
- `timeout_seconds` (`float`, default `25.0`): Auto-release watchdog timeout.

## Vision & GUI Automation

### `take_screenshot`
Capture the desktop, a specific monitor, or a window.
- `monitor` (`int`, default `1`): `1` primary, `2+` secondary, `0` all monitors.
- `window_title` (`str | null`): Optional title substring or HWND.
- `max_width` (`int`, default `1280`): Downscale width (`0` disables resizing).
- `format` (`"jpeg" | "png"`, default `"jpeg"`): Output image format.
- `quality` (`int`, default `80`): JPEG quality (`30..95`).
- `use_cache_ms` (`int`, default `400`): Reuse background frame if newer than `N` ms (`0` forces a fresh capture).

### `run_gui_sequence`
Execute multiple GUI steps in one MCP call and optionally return the resulting screenshot.
- `steps` (`list[dict]`): Ordered actions:
  - `{"action": "focus_window", "target": "<title or hwnd>"}`
  - `{"action": "launch_app", "target": "<exe or path>", "args": [...]}`
  - `{"action": "click", "x": 600, "y": 400, "coord_space": "last_screenshot", "button": "left", "clicks": 1}`
  - `{"action": "double_click", "x": 600, "y": 400, "coord_space": "last_screenshot"}`
  - `{"action": "right_click", "x": 600, "y": 400, "coord_space": "last_screenshot"}`
  - `{"action": "move", "x": 600, "y": 400, "coord_space": "last_screenshot"}`
  - `{"action": "drag", "x": 100, "y": 100, "end_x": 300, "end_y": 300, "coord_space": "last_screenshot"}`
  - `{"action": "scroll", "scroll_amount": -500, "x": 600, "y": 400, "coord_space": "last_screenshot"}`
  - `{"action": "type", "text": "..."}`
  - `{"action": "paste_text", "text": "..."}` *(Unicode/emoji-safe via clipboard)*
  - `{"action": "press", "key": "enter"}`
  - `{"action": "hotkey", "keys": ["ctrl", "a"]}`
  - `{"action": "wait", "ms": 200}`
- `return_screenshot` (`bool`, default `true`)
- `auto_lock` (`bool`, default `true`)
- `release_after` (`bool`, default `false`)

### `mouse_action` & `keyboard_action`
Single-step cursor and keyboard primitives (prefer `run_gui_sequence` for multi-step flows).

## Windows, Apps & Clipboard

- `list_windows(include_untitled=false)`: Returns visible HWNDs, titles, PIDs, process names, bounds, and minimized/maximized flags.
- `manage_window(action, title_or_hwnd)`: `focus`, `minimize`, `maximize`, `restore`, or `close`.
- `launch_app(target, args=null, working_dir=null)`: Launches an executable, file, or folder non-blockingly.
- `clipboard(action, text=null)`: `get` or `set` clipboard text.

## System Telemetry & Files

- `system_overview()`: CPU %, core counts, RAM, disk partitions, battery status, boot time, and top 10 RAM consumers.
- `list_processes(filter_name=null, sort_by="memory", limit=30)`: Inspect running processes.
- `stop_process(pid, force=false)`: Terminate or kill a process (confirm with user first).
- `list_services(filter_text=null, status="all", limit=60)`: Read-only Windows service listing (`psutil` with `Get-Service` fallback).
- `find_files(root_path, pattern="*", max_results=50, include_dirs=false)`: Recursive glob search under any local path.
