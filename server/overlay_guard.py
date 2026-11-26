"""Win32 Layered Overlay Ring + Low-Level Input Lock Guard for pc-control.

Displays an animated glowing border ring around the primary monitor when Gemini
is controlling the PC, blocks physical human mouse/keyboard events (while allowing
injected automation events through), displays an interrupt warning pill when
physical input is detected, and immediately aborts & releases control on Ctrl+C
or watchdog timeout.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import math
import queue
import sys
import threading
import time
from typing import Any

from PIL import Image, ImageDraw, ImageFont

if sys.platform != "win32":
    raise SystemExit("overlay_guard.py is only supported on Windows.")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Win32 constants
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_MOUSEMOVE = 0x0200
WM_TIMER = 0x0113
WM_QUIT = 0x0012
WM_APP_CMD = 0x8001

LLKHF_INJECTED = 0x00000010
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002
VK_CONTROL = 0x11
VK_C = 0x43


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


# 64-bit safe Win32 signatures
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    wintypes.HDC,
    ctypes.POINTER(POINT),
    wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP

# Gemini palette stops
PALETTE = [
    (66, 133, 244),   # Blue
    (139, 92, 246),   # Purple
    (236, 72, 153),   # Pink
    (6, 182, 212),    # Cyan
]


def _sample_palette(t: float) -> tuple[int, int, int]:
    t = t % 1.0
    n = len(PALETTE)
    pos = t * n
    i0 = int(pos) % n
    i1 = (i0 + 1) % n
    f = pos - int(pos)
    c0, c1 = PALETTE[i0], PALETTE[i1]
    return (
        int(c0[0] + (c1[0] - c0[0]) * f),
        int(c0[1] + (c1[1] - c0[1]) * f),
        int(c0[2] + (c1[2] - c0[2]) * f),
    )


class OverlayGuard:
    def __init__(self) -> None:
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)
        self.border = 14
        self.active = False
        self.deadline = 0.0
        self.banner_until = 0.0
        self.banner_visible = False
        self.last_mouse_pt: tuple[int, int] | None = None
        self.phase = 0.0

        self.cmd_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.main_tid = kernel32.GetCurrentThreadId()
        self.kb_hook: int | None = None
        self.mouse_hook: int | None = None

        self._wndproc = WNDPROC(self._on_wndproc)
        self._kb_proc = HOOKPROC(self._on_kb_hook)
        self._mouse_proc = HOOKPROC(self._on_mouse_hook)

        self.hinst = kernel32.GetModuleHandleW(None)
        self._register_class()
        self.top_hwnd = self._create_overlay_win(0, 0, self.screen_w, self.border)
        self.bottom_hwnd = self._create_overlay_win(
            0, self.screen_h - self.border, self.screen_w, self.border
        )
        self.left_hwnd = self._create_overlay_win(
            0, self.border, self.border, self.screen_h - 2 * self.border
        )
        self.right_hwnd = self._create_overlay_win(
            self.screen_w - self.border,
            self.border,
            self.border,
            self.screen_h - 2 * self.border,
        )
        self.banner_w = 590
        self.banner_h = 56
        bx = max(0, (self.screen_w - self.banner_w) // 2)
        self.banner_hwnd = self._create_overlay_win(bx, 22, self.banner_w, self.banner_h)
        self._render_banner()

    def _on_wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _register_class(self) -> None:
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = self.hinst
        wc.lpszClassName = "GeminiPcControlOverlay"
        user32.RegisterClassExW(ctypes.byref(wc))

    def _create_overlay_win(self, x: int, y: int, w: int, h: int) -> int:
        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )
        return user32.CreateWindowExW(
            ex_style,
            "GeminiPcControlOverlay",
            "",
            WS_POPUP,
            x,
            y,
            w,
            h,
            None,
            None,
            self.hinst,
            None,
        )

    def _push_bitmap(self, hwnd: int, x: int, y: int, img: Image.Image) -> None:
        if not hwnd:
            return
        w, h = img.size
        raw = img.convert("RGBa").tobytes("raw", "BGRa")
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = DIB_RGB_COLORS

        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(
            screen_dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
        )
        if hbmp and bits.value:
            ctypes.memmove(bits.value, raw, len(raw))
            old = gdi32.SelectObject(mem_dc, hbmp)
            pt_dst = POINT(x, y)
            sz = SIZE(w, h)
            pt_src = POINT(0, 0)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            user32.UpdateLayeredWindow(
                hwnd,
                screen_dc,
                ctypes.byref(pt_dst),
                ctypes.byref(sz),
                mem_dc,
                ctypes.byref(pt_src),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )
            gdi32.SelectObject(mem_dc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def _render_banner(self) -> None:
        w, h = self.banner_w, self.banner_h
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(2, 2), (w - 3, h - 3)],
            radius=26,
            fill=(15, 23, 42, 238),
            outline=(96, 165, 250, 240),
            width=2,
        )
        # Gemini 4-point spark icon
        cx, cy, r = 28, h // 2, 10
        draw.polygon(
            [(cx, cy - r), (cx + 4, cy - 4), (cx + r, cy), (cx + 4, cy + 4),
             (cx, cy + r), (cx - 4, cy + 4), (cx - r, cy), (cx - 4, cy - 4)],
            fill=(96, 165, 250, 255),
        )
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
        except Exception:
            font = ImageFont.load_default()
        text = "Gemini has control of your PC  •  To stop, press Ctrl+C"
        draw.text((48, 16), text, font=font, fill=(248, 250, 252, 255))
        bx = max(0, (self.screen_w - w) // 2)
        self._push_bitmap(self.banner_hwnd, bx, 22, img)

    def _render_borders(self) -> None:
        b = self.border
        sw, sh = self.screen_w, self.screen_h
        phase = self.phase

        # Alpha falloff from outer edge inward (0 = outer screen edge)
        falloff = [int(245 * ((1.0 - (d / b)) ** 1.6)) for d in range(b)]

        # Top & Bottom strips (sample every 24px horizontally for fast smooth bands)
        step = 24
        top_img = Image.new("RGBA", (sw, b), (0, 0, 0, 0))
        bot_img = Image.new("RGBA", (sw, b), (0, 0, 0, 0))
        top_draw = ImageDraw.Draw(top_img)
        bot_draw = ImageDraw.Draw(bot_img)

        for x0 in range(0, sw, step):
            x1 = min(sw - 1, x0 + step)
            t_top = phase + (x0 / sw) * 0.35
            t_bot = phase + 0.70 - (x0 / sw) * 0.35
            ct = _sample_palette(t_top)
            cb = _sample_palette(t_bot)
            for d in range(b):
                a = falloff[d]
                top_draw.line([(x0, d), (x1, d)], fill=(ct[0], ct[1], ct[2], a))
                bot_draw.line([(x0, b - 1 - d), (x1, b - 1 - d)], fill=(cb[0], cb[1], cb[2], a))

        self._push_bitmap(self.top_hwnd, 0, 0, top_img)
        self._push_bitmap(self.bottom_hwnd, 0, sh - b, bot_img)

        # Left & Right strips
        side_h = sh - 2 * b
        left_img = Image.new("RGBA", (b, side_h), (0, 0, 0, 0))
        right_img = Image.new("RGBA", (b, side_h), (0, 0, 0, 0))
        left_draw = ImageDraw.Draw(left_img)
        right_draw = ImageDraw.Draw(right_img)

        for y0 in range(0, side_h, step):
            y1 = min(side_h - 1, y0 + step)
            t_right = phase + 0.35 + (y0 / max(1, side_h)) * 0.35
            t_left = phase + 1.0 - (y0 / max(1, side_h)) * 0.30
            cr = _sample_palette(t_right)
            cl = _sample_palette(t_left)
            for d in range(b):
                a = falloff[d]
                left_draw.line([(d, y0), (d, y1)], fill=(cl[0], cl[1], cl[2], a))
                right_draw.line([(b - 1 - d, y0), (b - 1 - d, y1)], fill=(cr[0], cr[1], cr[2], a))

        self._push_bitmap(self.left_hwnd, 0, b, left_img)
        self._push_bitmap(self.right_hwnd, sw - b, b, right_img)

    def _show_borders(self, show: bool) -> None:
        cmd = SW_SHOWNOACTIVATE if show else SW_HIDE
        for hwnd in (self.top_hwnd, self.bottom_hwnd, self.left_hwnd, self.right_hwnd):
            user32.ShowWindow(hwnd, cmd)
            if show:
                user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                )

    def _show_banner(self, show: bool) -> None:
        if show == self.banner_visible:
            return
        self.banner_visible = show
        user32.ShowWindow(self.banner_hwnd, SW_SHOWNOACTIVATE if show else SW_HIDE)
        if show:
            user32.SetWindowPos(
                self.banner_hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )

    def _trigger_interrupt_banner(self) -> None:
        self.banner_until = time.monotonic() + 3.5
        self._show_banner(True)

    def _install_hooks(self) -> None:
        if self.kb_hook is None:
            self.kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, None, 0)
        if self.mouse_hook is None:
            self.mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)

    def _remove_hooks(self) -> None:
        if self.kb_hook is not None:
            user32.UnhookWindowsHookEx(self.kb_hook)
            self.kb_hook = None
        if self.mouse_hook is not None:
            user32.UnhookWindowsHookEx(self.mouse_hook)
            self.mouse_hook = None

    def _on_kb_hook(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode >= 0 and self.active:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(self.kb_hook, ncode, wparam, lparam)

            ctrl_down = (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
            if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN) and kb.vkCode == VK_C and ctrl_down:
                self.stop(aborted=True)
                return 1

            if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._trigger_interrupt_banner()
            return 1
        return user32.CallNextHookEx(self.kb_hook, ncode, wparam, lparam)

    def _on_mouse_hook(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode >= 0 and self.active:
            ms = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if ms.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED):
                return user32.CallNextHookEx(self.mouse_hook, ncode, wparam, lparam)

            if wparam == WM_MOUSEMOVE:
                pt = (ms.pt.x, ms.pt.y)
                if self.last_mouse_pt is None or (
                    abs(pt[0] - self.last_mouse_pt[0]) + abs(pt[1] - self.last_mouse_pt[1]) > 10
                ):
                    self.last_mouse_pt = pt
                    self._trigger_interrupt_banner()
            else:
                self._trigger_interrupt_banner()
            return 1
        return user32.CallNextHookEx(self.mouse_hook, ncode, wparam, lparam)

    def start(self, timeout: float = 25.0) -> None:
        self.deadline = time.monotonic() + max(2.0, min(timeout, 120.0))
        if not self.active:
            self.active = True
            self.last_mouse_pt = None
            self._install_hooks()
            self._render_borders()
            self._show_borders(True)

    def stop(self, aborted: bool = False) -> None:
        was_active = self.active
        self.active = False
        self._remove_hooks()
        self._show_borders(False)
        self._show_banner(False)
        if aborted and was_active:
            sys.stdout.write(json.dumps({"event": "aborted"}) + "\n")
            sys.stdout.flush()

    def _process_commands(self) -> bool:
        while True:
            try:
                cmd = self.cmd_queue.get_nowait()
            except queue.Empty:
                return True
            op = cmd.get("cmd")
            if op == "start" or op == "heartbeat":
                self.start(float(cmd.get("timeout", 25.0)))
            elif op == "stop":
                self.stop(aborted=False)
            elif op == "quit":
                self.stop(aborted=False)
                return False

    def run(self) -> None:
        def stdin_reader() -> None:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.cmd_queue.put(json.loads(line))
                    user32.PostThreadMessageW(self.main_tid, WM_APP_CMD, 0, 0)
                except Exception:
                    continue
            self.cmd_queue.put({"cmd": "quit"})
            user32.PostThreadMessageW(self.main_tid, WM_APP_CMD, 0, 0)

        threading.Thread(target=stdin_reader, daemon=True).start()
        user32.SetTimer(None, 0, 35, None)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP_CMD:
                if not self._process_commands():
                    break
            elif msg.message == WM_TIMER:
                if self.active:
                    now = time.monotonic()
                    if now > self.deadline:
                        self.stop(aborted=False)
                    else:
                        self.phase = (self.phase + 0.025) % 1.0
                        self._render_borders()
                        if self.banner_visible and now > self.banner_until:
                            self._show_banner(False)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self.stop(aborted=False)


if __name__ == "__main__":
    OverlayGuard().run()
