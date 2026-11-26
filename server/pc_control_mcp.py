"""Local Windows PC-Control MCP Server for Antigravity.

Provides fast desktop vision (with background screen-watcher cache),
batched real-time GUI automation, Win32 overlay ring + physical input lock
with Ctrl+C abort, window management, application launching, clipboard access,
system telemetry, process/service inspection, and user file search.
"""

from __future__ import annotations

import atexit
import ctypes
import ctypes.wintypes as wintypes
import fnmatch
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Literal

# Enable Per-Monitor DPI awareness before importing mss/pyautogui so screen
# capture pixels and Win32/pyautogui mouse coordinates match 1:1 on Windows.
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import mss
import psutil
import pyautogui
import pyperclip
from mcp.server.mcpserver import Image, MCPServer
from mcp.types import CallToolResult, TextContent
from PIL import Image as PILImage

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01

mcp = MCPServer("pc-control")

# Tracks the most recent screenshot geometry for image-space coordinate mapping.
_LAST_CAPTURE: dict[str, int] | None = None

# Win32 constants and bindings
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
WM_CLOSE = 0x0010
CREATE_NO_WINDOW = 0x08000000

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
if user32 is not None:
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL


class _GuardClient:
    """Manages the overlay_guard.py border-ring + input-lock child process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self.active = False
        self.aborted = False
        self._overlay_path = Path(__file__).with_name("overlay_guard.py")
        atexit.register(self.shutdown)

    def _ensure_proc(self) -> subprocess.Popen[str] | None:
        if sys.platform != "win32" or not self._overlay_path.exists():
            return None
        if self._proc is not None and self._proc.poll() is None:
            return self._proc

        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(
            [sys.executable, str(self._overlay_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=flags,
        )
        threading.Thread(target=self._read_events, args=(self._proc,), daemon=True).start()
        return self._proc

    def _read_events(self, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                if evt.get("event") == "aborted":
                    with self._lock:
                        self.active = False
                        self.aborted = True
            except Exception:
                continue

    def _send(self, payload: dict[str, Any]) -> None:
        with self._lock:
            proc = self._ensure_proc()
            if proc is None or proc.stdin is None:
                return
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except Exception:
                self._proc = None

    def start(self, timeout: float = 25.0) -> None:
        with self._lock:
            self.aborted = False
            self.active = True
        self._send({"cmd": "start", "timeout": timeout})

    def heartbeat(self, timeout: float = 25.0) -> None:
        with self._lock:
            if self.aborted:
                return
            self.active = True
        self._send({"cmd": "heartbeat", "timeout": timeout})

    def stop(self) -> None:
        with self._lock:
            self.active = False
        self._send({"cmd": "stop"})

    def clear_abort(self) -> None:
        with self._lock:
            self.aborted = False

    def raise_if_aborted(self) -> None:
        with self._lock:
            if self.aborted:
                self.aborted = False
                raise RuntimeError("ABORTED_BY_USER: Control was stopped because Ctrl+C was pressed.")

    def shutdown(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self.active = False
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    proc.stdin.flush()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass


class _ScreenWatcher:
    """Background screen-share buffer keeping a fresh 1280px JPEG ready in memory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_touch = 0.0
        self._frame_bytes: bytes | None = None
        self._frame_ts = 0.0
        self._frame_meta: dict[str, int] | None = None

    def touch(self) -> None:
        with self._lock:
            self._last_touch = time.monotonic()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        try:
            with mss.MSS() as sct:
                while time.monotonic() - self._last_touch < 30.0:
                    try:
                        region = sct.monitors[1]
                        raw = sct.grab(region)
                        img = PILImage.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                        sw, sh = img.size
                        if sw > 1280:
                            img = img.resize((1280, max(1, round(sh * 1280 / sw))), PILImage.Resampling.BILINEAR)
                        iw, ih = img.size
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=78)
                        meta = {
                            "screen_left": int(region["left"]),
                            "screen_top": int(region["top"]),
                            "screen_width": int(sw),
                            "screen_height": int(sh),
                            "image_width": int(iw),
                            "image_height": int(ih),
                        }
                        with self._lock:
                            self._frame_bytes = buf.getvalue()
                            self._frame_meta = meta
                            self._frame_ts = time.monotonic()
                    except Exception:
                        time.sleep(0.5)
                    time.sleep(0.35)
        except Exception:
            pass

    def get_if_fresh(self, max_age_ms: int) -> tuple[bytes, dict[str, int]] | None:
        if max_age_ms <= 0:
            return None
        with self._lock:
            if self._frame_bytes is None or self._frame_meta is None:
                return None
            if (time.monotonic() - self._frame_ts) * 1000.0 <= max_age_ms:
                return self._frame_bytes, dict(self._frame_meta)
            return None


_GUARD = _GuardClient()
_WATCHER = _ScreenWatcher()


def _get_window_rect(hwnd: int) -> dict[str, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "left": rect.left,
        "top": rect.top,
        "right": rect.right,
        "bottom": rect.bottom,
        "width": max(0, rect.right - rect.left),
        "height": max(0, rect.bottom - rect.top),
    }


def _enumerate_windows(include_untitled: bool = False) -> list[dict[str, Any]]:
    if user32 is None:
        return []

    windows: list[dict[str, Any]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

        if not title and not include_untitled:
            return True

        rect = _get_window_rect(hwnd)
        if rect["width"] <= 0 or rect["height"] <= 0:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = ""
        try:
            proc_name = psutil.Process(pid.value).name()
        except Exception:
            pass

        windows.append(
            {
                "hwnd": int(hwnd),
                "title": title,
                "pid": int(pid.value),
                "process": proc_name,
                "rect": rect,
                "minimized": bool(user32.IsIconic(hwnd)),
                "maximized": bool(user32.IsZoomed(hwnd)),
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return windows


def _find_window(title_or_hwnd: str) -> dict[str, Any] | None:
    windows = _enumerate_windows(include_untitled=True)
    query = title_or_hwnd.strip()
    if query.isdigit():
        target_hwnd = int(query)
        for win in windows:
            if win["hwnd"] == target_hwnd:
                return win

    query_lower = query.lower()
    exact = [w for w in windows if w["title"].lower() == query_lower]
    if exact:
        return exact[0]
    partial = [w for w in windows if query_lower in w["title"].lower()]
    return partial[0] if partial else None


def _resolve_coords(
    x: int | None,
    y: int | None,
    coord_space: Literal["screen", "last_screenshot", "normalized_1000"],
) -> tuple[int | None, int | None]:
    if x is None or y is None:
        return None, None

    if coord_space == "screen":
        return int(x), int(y)

    if coord_space == "last_screenshot":
        if _LAST_CAPTURE is None:
            raise ValueError(
                "No prior screenshot recorded; call take_screenshot first or use coord_space='screen'."
            )
        sx = _LAST_CAPTURE["screen_left"] + round(
            x * (_LAST_CAPTURE["screen_width"] / _LAST_CAPTURE["image_width"])
        )
        sy = _LAST_CAPTURE["screen_top"] + round(
            y * (_LAST_CAPTURE["screen_height"] / _LAST_CAPTURE["image_height"])
        )
        return sx, sy

    if coord_space == "normalized_1000":
        if _LAST_CAPTURE is not None:
            sx = _LAST_CAPTURE["screen_left"] + round((x / 1000.0) * _LAST_CAPTURE["screen_width"])
            sy = _LAST_CAPTURE["screen_top"] + round((y / 1000.0) * _LAST_CAPTURE["screen_height"])
            return sx, sy
        sw, sh = pyautogui.size()
        return round((x / 1000.0) * sw), round((y / 1000.0) * sh)

    raise ValueError(f"Unsupported coord_space: {coord_space}")


def _capture_image_content(
    monitor: int = 1,
    window_title: str | None = None,
    max_width: int = 1280,
    fmt: Literal["jpeg", "png"] = "jpeg",
    quality: int = 80,
    use_cache_ms: int = 0,
) -> tuple[Any, str]:
    global _LAST_CAPTURE
    _WATCHER.touch()

    if (
        use_cache_ms > 0
        and monitor == 1
        and window_title is None
        and max_width == 1280
        and fmt == "jpeg"
    ):
        cached = _WATCHER.get_if_fresh(use_cache_ms)
        if cached is not None:
            data, meta = cached
            _LAST_CAPTURE = meta
            meta_json = json.dumps({"captured": "monitor:1", "cached": True, **meta})
            return Image(data=data, format="jpeg").to_image_content(), meta_json

    with mss.MSS() as sct:
        if window_title:
            win = _find_window(window_title)
            if win is None:
                raise ValueError(f"No visible window matched '{window_title}'.")
            rect = win["rect"]
            region = {
                "left": rect["left"],
                "top": rect["top"],
                "width": rect["width"],
                "height": rect["height"],
            }
        else:
            if monitor < 0 or monitor >= len(sct.monitors):
                raise ValueError(
                    f"Monitor index {monitor} out of range (0..{len(sct.monitors) - 1})."
                )
            region = sct.monitors[monitor]

        raw = sct.grab(region)
        img = PILImage.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    screen_w, screen_h = img.size
    if max_width > 0 and screen_w > max_width:
        ratio = max_width / float(screen_w)
        new_h = max(1, round(screen_h * ratio))
        img = img.resize((max_width, new_h), PILImage.Resampling.BILINEAR)

    img_w, img_h = img.size
    _LAST_CAPTURE = {
        "screen_left": int(region["left"]),
        "screen_top": int(region["top"]),
        "screen_width": int(screen_w),
        "screen_height": int(screen_h),
        "image_width": int(img_w),
        "image_height": int(img_h),
    }

    buf = io.BytesIO()
    if fmt == "jpeg":
        img.save(buf, format="JPEG", quality=max(30, min(quality, 95)))
    else:
        img.save(buf, format="PNG")

    metadata = json.dumps(
        {
            "captured": window_title or f"monitor:{monitor}",
            "cached": False,
            **_LAST_CAPTURE,
            "tip": "Pass coord_space='last_screenshot' when clicking coordinates read from this image.",
        }
    )
    return Image(data=buf.getvalue(), format=fmt).to_image_content(), metadata


def _focus_win(title_or_hwnd: str) -> str:
    if user32 is None:
        raise RuntimeError("Window management is only supported on Windows.")
    win = _find_window(title_or_hwnd)
    if win is None:
        raise ValueError(f"No visible window matched '{title_or_hwnd}'.")
    hwnd = win["hwnd"]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    pyautogui.press("alt")
    user32.SetForegroundWindow(hwnd)
    return f"Focused '{win['title']}' (hwnd={hwnd})"


def _paste_text(text: str) -> str:
    previous = ""
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = ""
    pyperclip.copy(text)
    time.sleep(0.03)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.04)
    try:
        pyperclip.copy(previous)
    except Exception:
        pass
    return f"Pasted {len(text)} chars"


@mcp.tool()
def control_session(
    action: Literal["start", "stop", "status"],
    timeout_seconds: float = 25.0,
) -> str:
    """Start, stop, or inspect the Gemini PC-control border ring and physical input lock.

    When started, displays an animated border ring around the screen, blocks physical
    human mouse/keyboard input (while letting Gemini's automated actions pass through),
    shows a 'Gemini has control of your PC — to stop, press Ctrl+C' banner if interrupted,
    and automatically releases on Ctrl+C or timeout.
    """
    if action == "start":
        _GUARD.start(timeout=timeout_seconds)
        _WATCHER.touch()
        return json.dumps(
            {
                "active": True,
                "timeout_seconds": timeout_seconds,
                "stop_hotkey": "Ctrl+C",
            }
        )
    if action == "stop":
        _GUARD.stop()
        return json.dumps({"active": False})
    if action == "status":
        return json.dumps({"active": _GUARD.active, "aborted": _GUARD.aborted})
    raise ValueError(f"Unsupported action: {action}")


@mcp.tool()
def take_screenshot(
    monitor: int = 1,
    window_title: str | None = None,
    max_width: int = 1280,
    format: Literal["jpeg", "png"] = "jpeg",
    quality: int = 80,
    use_cache_ms: int = 400,
) -> CallToolResult:
    """Capture a fast screenshot of the Windows desktop, a monitor, or a specific window.

    Args:
        monitor: 1 for primary monitor (default), 2+ for secondary monitors, 0 for all monitors combined.
        window_title: Optional window title substring or HWND to capture just that window.
        max_width: Resize image width down to at most this many pixels (0 disables resizing).
        format: 'jpeg' (fast default) or 'png'.
        quality: JPEG quality (30..95).
        use_cache_ms: Reuse background screen-share frame if newer than this many milliseconds (0 forces fresh grab).
    """
    img_content, metadata = _capture_image_content(
        monitor=monitor,
        window_title=window_title,
        max_width=max_width,
        fmt=format,
        quality=quality,
        use_cache_ms=use_cache_ms,
    )
    return CallToolResult(content=[img_content, TextContent(type="text", text=metadata)])


@mcp.tool()
def run_gui_sequence(
    steps: list[dict[str, Any]],
    return_screenshot: bool = True,
    auto_lock: bool = True,
    release_after: bool = False,
) -> CallToolResult:
    """Execute a multi-step GUI workflow in a single fast call and optionally return the updated screenshot.

    Each item in `steps` is a dict with an `action` key:
      - {"action": "focus_window", "target": "<title or hwnd>"}
      - {"action": "launch_app", "target": "<exe or path>", "args": [...]}
      - {"action": "click", "x": 600, "y": 400, "coord_space": "last_screenshot", "button": "left", "clicks": 1}
      - {"action": "double_click", "x": 600, "y": 400, "coord_space": "last_screenshot"}
      - {"action": "right_click", "x": 600, "y": 400, "coord_space": "last_screenshot"}
      - {"action": "move", "x": 600, "y": 400, "coord_space": "last_screenshot"}
      - {"action": "drag", "x": 100, "y": 100, "end_x": 300, "end_y": 300, "coord_space": "last_screenshot"}
      - {"action": "scroll", "scroll_amount": -500, "x": 600, "y": 400, "coord_space": "last_screenshot"}
      - {"action": "type", "text": "..."}
      - {"action": "paste_text", "text": "..."}
      - {"action": "press", "key": "enter"}
      - {"action": "hotkey", "keys": ["ctrl", "a"]}
      - {"action": "wait", "ms": 200}
    """
    _GUARD.clear_abort()
    if auto_lock:
        _GUARD.start(timeout=25.0)
    _WATCHER.touch()

    log: list[str] = []
    try:
        for idx, step in enumerate(steps):
            _GUARD.raise_if_aborted()
            _GUARD.heartbeat(timeout=25.0)
            op = step.get("action")
            cs = step.get("coord_space", "last_screenshot")

            if op == "focus_window":
                log.append(f"{idx}: {_focus_win(str(step['target']))}")
                time.sleep(0.12)
            elif op == "launch_app":
                res = launch_app(str(step["target"]), step.get("args"), step.get("working_dir"))
                log.append(f"{idx}: launch {res}")
                time.sleep(0.25)
            elif op in ("click", "double_click", "right_click", "move", "drag", "scroll"):
                sx, sy = _resolve_coords(step.get("x"), step.get("y"), cs)
                if op == "move":
                    pyautogui.moveTo(sx, sy, duration=0.0)
                    log.append(f"{idx}: move ({sx},{sy})")
                elif op == "click":
                    btn = step.get("button", "left")
                    clk = int(step.get("clicks", 1))
                    if sx is not None and sy is not None:
                        pyautogui.click(sx, sy, clicks=clk, button=btn)
                    else:
                        pyautogui.click(clicks=clk, button=btn)
                    log.append(f"{idx}: click ({sx},{sy})")
                elif op == "double_click":
                    pyautogui.doubleClick(sx, sy, button=step.get("button", "left"))
                    log.append(f"{idx}: double_click ({sx},{sy})")
                elif op == "right_click":
                    pyautogui.rightClick(sx, sy)
                    log.append(f"{idx}: right_click ({sx},{sy})")
                elif op == "drag":
                    ex, ey = _resolve_coords(step.get("end_x"), step.get("end_y"), cs)
                    pyautogui.moveTo(sx, sy, duration=0.0)
                    pyautogui.dragTo(ex, ey, duration=0.15, button=step.get("button", "left"))
                    log.append(f"{idx}: drag ({sx},{sy})->({ex},{ey})")
                elif op == "scroll":
                    amt = int(step.get("scroll_amount", 0))
                    if sx is not None and sy is not None:
                        pyautogui.scroll(amt, x=sx, y=sy)
                    else:
                        pyautogui.scroll(amt)
                    log.append(f"{idx}: scroll {amt}")
            elif op == "type":
                txt = str(step["text"])
                pyautogui.write(txt, interval=float(step.get("interval", 0.0)))
                log.append(f"{idx}: type {len(txt)} chars")
            elif op == "paste_text":
                log.append(f"{idx}: {_paste_text(str(step['text']))}")
            elif op == "press":
                k = str(step.get("key") or step.get("text"))
                pyautogui.press(k)
                log.append(f"{idx}: press {k}")
            elif op == "hotkey":
                ks = list(step["keys"])
                pyautogui.hotkey(*ks)
                log.append(f"{idx}: hotkey {'+'.join(ks)}")
            elif op == "wait":
                ms = max(0, min(int(step.get("ms", 100)), 5000))
                time.sleep(ms / 1000.0)
                log.append(f"{idx}: wait {ms}ms")
            else:
                raise ValueError(f"Unknown sequence action at step {idx}: {op}")
    finally:
        if release_after:
            _GUARD.stop()

    contents: list[Any] = [TextContent(type="text", text=json.dumps({"steps": log}))]
    if return_screenshot:
        time.sleep(0.12)
        img_content, meta = _capture_image_content(use_cache_ms=0)
        contents.append(img_content)
        contents.append(TextContent(type="text", text=meta))
    return CallToolResult(content=contents)


@mcp.tool()
def mouse_action(
    action: Literal["move", "click", "double_click", "right_click", "drag", "scroll"],
    x: int | None = None,
    y: int | None = None,
    button: Literal["left", "right", "middle"] = "left",
    clicks: int = 1,
    end_x: int | None = None,
    end_y: int | None = None,
    scroll_amount: int = 0,
    coord_space: Literal["screen", "last_screenshot", "normalized_1000"] = "screen",
) -> str:
    """Perform a single mouse action on the Windows desktop. Prefer run_gui_sequence for multi-step flows."""
    _GUARD.raise_if_aborted()
    _GUARD.heartbeat(timeout=20.0)
    sx, sy = _resolve_coords(x, y, coord_space)

    if action == "move":
        if sx is None or sy is None:
            raise ValueError("move requires x and y.")
        pyautogui.moveTo(sx, sy, duration=0.0)
        return f"Moved cursor to ({sx}, {sy})."

    if action == "click":
        if sx is not None and sy is not None:
            pyautogui.click(sx, sy, clicks=clicks, button=button)
            return f"Clicked {button} x{clicks} at ({sx}, {sy})."
        pyautogui.click(clicks=clicks, button=button)
        return f"Clicked {button} x{clicks} at current position."

    if action == "double_click":
        if sx is not None and sy is not None:
            pyautogui.doubleClick(sx, sy, button=button)
            return f"Double-clicked {button} at ({sx}, {sy})."
        pyautogui.doubleClick(button=button)
        return f"Double-clicked {button} at current position."

    if action == "right_click":
        if sx is not None and sy is not None:
            pyautogui.rightClick(sx, sy)
            return f"Right-clicked at ({sx}, {sy})."
        pyautogui.rightClick()
        return "Right-clicked at current position."

    if action == "drag":
        ex, ey = _resolve_coords(end_x, end_y, coord_space)
        if sx is None or sy is None or ex is None or ey is None:
            raise ValueError("drag requires x, y, end_x, and end_y.")
        pyautogui.moveTo(sx, sy, duration=0.0)
        pyautogui.dragTo(ex, ey, duration=0.15, button=button)
        return f"Dragged {button} from ({sx}, {sy}) to ({ex}, {ey})."

    if action == "scroll":
        if sx is not None and sy is not None:
            pyautogui.scroll(scroll_amount, x=sx, y=sy)
            return f"Scrolled {scroll_amount} at ({sx}, {sy})."
        pyautogui.scroll(scroll_amount)
        return f"Scrolled {scroll_amount} at current position."

    raise ValueError(f"Unsupported mouse action: {action}")


@mcp.tool()
def keyboard_action(
    action: Literal["type", "paste_text", "press", "hotkey"],
    text: str | None = None,
    keys: list[str] | None = None,
    interval: float = 0.0,
) -> str:
    """Send keyboard input or hotkeys to the active Windows application. Prefer run_gui_sequence for multi-step flows."""
    _GUARD.raise_if_aborted()
    _GUARD.heartbeat(timeout=20.0)

    if action == "type":
        if text is None:
            raise ValueError("type requires text.")
        pyautogui.write(text, interval=interval)
        return f"Typed {len(text)} characters."

    if action == "paste_text":
        if text is None:
            raise ValueError("paste_text requires text.")
        return _paste_text(text)

    if action == "press":
        key = text or (keys[0] if keys else None)
        if not key:
            raise ValueError("press requires text (or keys[0]) naming the key.")
        pyautogui.press(key)
        return f"Pressed key '{key}'."

    if action == "hotkey":
        if not keys:
            raise ValueError("hotkey requires a non-empty keys list.")
        pyautogui.hotkey(*keys)
        return f"Triggered hotkey {' + '.join(keys)}."

    raise ValueError(f"Unsupported keyboard action: {action}")


@mcp.tool()
def list_windows(include_untitled: bool = False) -> str:
    """List visible Windows application windows with their HWND, title, PID, process name, and bounds."""
    return json.dumps(_enumerate_windows(include_untitled=include_untitled), indent=2)


@mcp.tool()
def manage_window(
    action: Literal["focus", "minimize", "maximize", "restore", "close"],
    title_or_hwnd: str,
) -> str:
    """Focus, minimize, maximize, restore, or close a Windows application window."""
    if user32 is None:
        raise RuntimeError("Window management is only supported on Windows.")

    win = _find_window(title_or_hwnd)
    if win is None:
        raise ValueError(f"No visible window matched '{title_or_hwnd}'.")

    hwnd = win["hwnd"]
    if action == "focus":
        return _focus_win(title_or_hwnd)

    if action == "minimize":
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return f"Minimized window '{win['title']}' (hwnd={hwnd})."

    if action == "maximize":
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return f"Maximized window '{win['title']}' (hwnd={hwnd})."

    if action == "restore":
        user32.ShowWindow(hwnd, SW_RESTORE)
        return f"Restored window '{win['title']}' (hwnd={hwnd})."

    if action == "close":
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return f"Sent close message to '{win['title']}' (hwnd={hwnd})."

    raise ValueError(f"Unsupported window action: {action}")


@mcp.tool()
def launch_app(
    target: str,
    args: list[str] | None = None,
    working_dir: str | None = None,
) -> str:
    """Launch an application, executable, folder, or file on Windows."""
    if not args and os.path.exists(target) and not target.lower().endswith((".exe", ".bat", ".cmd", ".ps1")):
        os.startfile(target)  # noqa: S606 - intentional user-requested local open
        return f"Opened '{target}'."

    cmd = [target, *(args or [])]
    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=working_dir or None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return json.dumps({"launched": cmd, "pid": proc.pid})


@mcp.tool()
def clipboard(
    action: Literal["get", "set"],
    text: str | None = None,
) -> str:
    """Read or write the Windows clipboard text."""
    if action == "get":
        return pyperclip.paste()
    if action == "set":
        if text is None:
            raise ValueError("set requires text.")
        pyperclip.copy(text)
        return f"Copied {len(text)} characters to clipboard."
    raise ValueError(f"Unsupported clipboard action: {action}")


@mcp.tool()
def system_overview() -> str:
    """Return a snapshot of CPU, RAM, disks, battery, uptime, and top resource-using processes."""
    vm = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=0.2)
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(
                {
                    "drive": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "used_percent": usage.percent,
                }
            )
        except Exception:
            continue

    battery = None
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            battery = {
                "percent": round(bat.percent, 1),
                "power_plugged": bool(bat.power_plugged),
                "secs_left": bat.secsleft,
            }
    except Exception:
        pass

    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem_mb = round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024**2), 1)
            procs.append({"pid": p.info["pid"], "name": p.info["name"], "ram_mb": mem_mb})
        except Exception:
            continue
    top_ram = sorted(procs, key=lambda x: x["ram_mb"], reverse=True)[:10]

    payload = {
        "cpu_percent": cpu_pct,
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "ram_used_gb": round(vm.used / (1024**3), 2),
        "ram_percent": vm.percent,
        "disks": disks,
        "battery": battery,
        "boot_time_epoch": int(psutil.boot_time()),
        "top_ram_processes": top_ram,
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def list_processes(
    filter_name: str | None = None,
    sort_by: Literal["memory", "cpu", "name"] = "memory",
    limit: int = 30,
) -> str:
    """List running Windows processes sorted by memory, CPU, or name."""
    items = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            name = p.info["name"] or ""
            if filter_name and filter_name.lower() not in name.lower():
                continue
            mem_mb = round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024**2), 1)
            items.append(
                {
                    "pid": p.info["pid"],
                    "name": name,
                    "ram_mb": mem_mb,
                    "cpu_percent": p.info["cpu_percent"],
                    "status": p.info["status"],
                }
            )
        except Exception:
            continue

    key_fn = {
        "memory": lambda x: x["ram_mb"],
        "cpu": lambda x: x["cpu_percent"] or 0.0,
        "name": lambda x: x["name"].lower(),
    }[sort_by]
    items.sort(key=key_fn, reverse=(sort_by != "name"))
    return json.dumps(items[: max(1, min(limit, 200))], indent=2)


@mcp.tool()
def stop_process(pid: int, force: bool = False) -> str:
    """Terminate or kill a Windows process by PID. Confirm with the user before calling."""
    proc = psutil.Process(pid)
    name = proc.name()
    if force:
        proc.kill()
        return f"Killed process '{name}' (PID {pid})."
    proc.terminate()
    return f"Sent terminate signal to '{name}' (PID {pid})."


@mcp.tool()
def list_services(
    filter_text: str | None = None,
    status: Literal["all", "running", "stopped"] = "all",
    limit: int = 60,
) -> str:
    """Inspect Windows services by name/display name and status (read-only)."""
    if sys.platform != "win32":
        return "[]"

    cap = max(1, min(limit, 300))
    needle = filter_text.lower() if filter_text else None
    results = []

    try:
        for svc in psutil.win_service_iter():
            try:
                info = svc.as_dict()
                svc_status = (info.get("status") or "").lower()
                if status != "all" and svc_status != status:
                    continue
                haystack = f"{info.get('name', '')} {info.get('display_name', '')}".lower()
                if needle and needle not in haystack:
                    continue
                results.append(
                    {
                        "name": info.get("name"),
                        "display_name": info.get("display_name"),
                        "status": info.get("status"),
                        "start_type": info.get("start_type"),
                    }
                )
            except Exception:
                continue
        return json.dumps(results[:cap], indent=2)
    except PermissionError:
        ps_cmd = (
            "Get-Service | Select-Object Name, DisplayName, "
            "@{N='Status';E={$_.Status.ToString().ToLower()}}, "
            "@{N='StartType';E={$_.StartType.ToString().ToLower()}} | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise PermissionError(
                "Unable to enumerate Windows services in the current security context."
            )
        raw_items = json.loads(proc.stdout)
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        for item in raw_items:
            svc_status = (item.get("Status") or "").lower()
            if status != "all" and svc_status != status:
                continue
            haystack = f"{item.get('Name', '')} {item.get('DisplayName', '')}".lower()
            if needle and needle not in haystack:
                continue
            results.append(
                {
                    "name": item.get("Name"),
                    "display_name": item.get("DisplayName"),
                    "status": svc_status,
                    "start_type": item.get("StartType"),
                }
            )
        return json.dumps(results[:cap], indent=2)


@mcp.tool()
def find_files(
    root_path: str,
    pattern: str = "*",
    max_results: int = 50,
    include_dirs: bool = False,
) -> str:
    """Search for files or directories under a path on the PC (e.g. Desktop, Documents, Downloads)."""
    root = Path(os.path.expandvars(os.path.expanduser(root_path)))
    if not root.exists():
        raise ValueError(f"Path does not exist: {root}")

    matches: list[dict[str, Any]] = []
    cap = max(1, min(max_results, 200))
    pattern_lower = pattern.lower()

    for dirpath, dirnames, filenames in os.walk(root):
        if include_dirs:
            for d in dirnames:
                if fnmatch.fnmatch(d.lower(), pattern_lower):
                    full = Path(dirpath) / d
                    matches.append({"path": str(full), "type": "dir"})
                    if len(matches) >= cap:
                        return json.dumps(matches, indent=2)

        for f in filenames:
            if fnmatch.fnmatch(f.lower(), pattern_lower):
                full = Path(dirpath) / f
                try:
                    size = full.stat().st_size
                except Exception:
                    size = None
                matches.append({"path": str(full), "type": "file", "size_bytes": size})
                if len(matches) >= cap:
                    return json.dumps(matches, indent=2)

    return json.dumps(matches, indent=2)


if __name__ == "__main__":
    mcp.run()
