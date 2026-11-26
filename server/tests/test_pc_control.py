"""Unit and MCP stdio protocol tests for the pc-control server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pc_control_mcp as srv
import realtime_worker as rw

SERVER_DIR = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = SERVER_DIR / "pc_control_mcp.py"
OVERLAY_SCRIPT = SERVER_DIR / "overlay_guard.py"


def test_resolve_coords_screen_and_last_screenshot() -> None:
    srv._LAST_CAPTURE = {
        "screen_left": 0,
        "screen_top": 0,
        "screen_width": 1920,
        "screen_height": 1080,
        "image_width": 1280,
        "image_height": 720,
    }
    assert srv._resolve_coords(640, 360, "last_screenshot") == (960, 540)
    assert srv._resolve_coords(500, 250, "normalized_1000") == (960, 270)
    assert srv._resolve_coords(123, 456, "screen") == (123, 456)
    assert srv._resolve_coords(None, None, "last_screenshot") == (None, None)


def test_find_files_locates_markdown() -> None:
    plugin_root = SERVER_DIR.parent
    raw = srv.find_files(str(plugin_root), pattern="SKILL.md", max_results=10)
    items = json.loads(raw)
    paths = [item["path"] for item in items]
    assert len(paths) == 4
    assert any("pc-desktop-gui" in p for p in paths)


def test_realtime_worker_reports_missing_key_safely(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(rw.Path, "home", lambda: tmp_path)
    # Also ensure plugin-local .env doesn't interfere if absent
    res = rw.run_realtime_task(
        "open notepad",
        guard=srv._GUARD,
        watcher=srv._WATCHER,
        capture_raw_fn=srv._capture_raw_jpeg,
        resolve_coords_fn=srv._resolve_coords,
        focus_fn=srv._focus_win,
        launch_fn=srv.launch_app,
        paste_fn=srv._paste_text,
    )
    assert res["status"] == "missing_api_key"
    assert "GEMINI_API_KEY" in res["message"]


def test_load_gemini_api_key_from_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(rw.Path, "home", lambda: tmp_path)
    (tmp_path / ".env").write_text('GEMINI_API_KEY="test-key-123"\n', encoding="utf-8")
    assert rw.load_gemini_api_key() == "test-key-123"
    assert rw.has_gemini_api_key() is True


def test_mcp_stdio_roundtrip() -> None:
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdin is not None and proc.stdout is not None

    def rpc(payload: dict) -> dict:
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    init_res = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0.3.0"},
            },
        }
    )
    assert "result" in init_res

    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    tools_res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = {t["name"] for t in tools_res["result"]["tools"]}
    expected = {
        "control_session",
        "get_ui_tree",
        "ui_action",
        "realtime_task",
        "take_screenshot",
        "run_gui_sequence",
        "mouse_action",
        "keyboard_action",
        "list_windows",
        "manage_window",
        "launch_app",
        "clipboard",
        "system_overview",
        "list_processes",
        "stop_process",
        "list_services",
        "find_files",
    }
    assert expected.issubset(tool_names)

    seq_res = rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "run_gui_sequence",
                "arguments": {
                    "steps": [{"action": "wait", "ms": 10}],
                    "return_screenshot": False,
                    "auto_lock": False,
                },
            },
        }
    )
    seq_payload = json.loads(seq_res["result"]["content"][0]["text"])
    assert seq_payload["steps"] == ["0: wait 10ms"]

    proc.stdin.close()
    proc.wait(timeout=5)


def test_overlay_guard_lifecycle() -> None:
    proc = subprocess.Popen(
        [sys.executable, str(OVERLAY_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps({"cmd": "start", "timeout": 2}) + "\n")
    proc.stdin.write(json.dumps({"cmd": "stop"}) + "\n")
    proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
    proc.stdin.flush()
    _out, err = proc.communicate(timeout=5)
    assert proc.returncode == 0
    assert err.strip() == ""
