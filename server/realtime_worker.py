"""Local real-time Gemini Vision + UIA micro-agent worker for pc-control."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pyautogui
from google import genai
from google.genai import types

from ui_tree import inspect_ui_tree, perform_ui_action

SYSTEM_PROMPT = """You are a fast real-time Windows desktop micro-agent.
Given the user's goal, the current Windows UI Automation element tree, and an optional desktop screenshot,
output JSON with the immediate next action(s) to take.

Prefer UI element actions (ui_click, ui_set_text) over raw screen coordinates whenever an element appears in the UI tree.
If using raw coordinates (click, double_click), read coordinates in the screenshot image space (image_width x image_height) — they will be mapped automatically.

Return strictly valid JSON matching this schema:
{
  "done": boolean,
  "need_user_help": boolean,
  "note": string,
  "actions": [
    // Supported actions:
    // {"action": "ui_click", "name": "...", "control_type": "...", "automation_id": "..."}
    // {"action": "ui_set_text", "name": "...", "text": "...", "control_type": "..."}
    // {"action": "click", "x": 500, "y": 300}
    // {"action": "double_click", "x": 500, "y": 300}
    // {"action": "paste_text", "text": "..."}
    // {"action": "press", "key": "enter"}
    // {"action": "hotkey", "keys": ["ctrl", "l"]}
    // {"action": "focus_window", "target": "..."}
    // {"action": "launch_app", "target": "notepad.exe"}
    // {"action": "wait", "ms": 250}
  ]
}

Safety:
- Never interact with passwords, banking/payment prompts, CAPTCHAs, or UAC dialogs; set need_user_help=true instead.
- Set done=true once the goal is visibly completed."""


def load_gemini_api_key() -> str | None:
    """Safely load GEMINI_API_KEY from environment or ~/.env without logging its value."""
    val = os.environ.get("GEMINI_API_KEY", "").strip()
    if val:
        return val

    candidates = [
        Path.home() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    cleaned = v.strip().strip('"').strip("'")
                    if cleaned:
                        return cleaned
        except Exception:
            continue
    return None


def has_gemini_api_key() -> bool:
    return bool(load_gemini_api_key())


def run_realtime_task(
    goal: str,
    max_steps: int = 12,
    model: str = "gemini-2.5-flash",
    window_title: str | None = None,
    include_screenshot: bool = True,
    *,
    guard: Any,
    watcher: Any,
    capture_raw_fn: Any,
    resolve_coords_fn: Any,
    focus_fn: Any,
    launch_fn: Any,
    paste_fn: Any,
) -> dict[str, Any]:
    """Execute a goal in a tight local Vision/UIA -> Gemini Flash -> Action loop."""
    api_key = load_gemini_api_key()
    if not api_key:
        return {
            "status": "missing_api_key",
            "message": (
                "GEMINI_API_KEY is not set. Add GEMINI_API_KEY=<your-key> to ~/.env "
                "(or your system environment variables) to enable the local real-time worker."
            ),
        }

    client = genai.Client(api_key=api_key)
    step_cap = max(1, min(max_steps, 30))
    history_log: list[dict[str, Any]] = []
    final_status = "max_steps_reached"
    final_note = ""

    guard.clear_abort()
    guard.start(timeout=30.0)
    watcher.touch()

    try:
        for step_idx in range(1, step_cap + 1):
            guard.raise_if_aborted()
            guard.heartbeat(timeout=30.0)

            try:
                ui_snapshot = inspect_ui_tree(
                    window_title=window_title,
                    max_depth=5,
                    max_elements=90,
                    interactive_only=True,
                )
            except Exception as exc:
                ui_snapshot = {"error": str(exc), "elements": []}

            parts: list[Any] = [
                (
                    f"Goal: {goal}\n"
                    f"Step: {step_idx}/{step_cap}\n"
                    f"Recent actions: {json.dumps(history_log[-4:])}\n"
                    f"Active UI tree: {json.dumps(ui_snapshot)}"
                )
            ]

            if include_screenshot:
                img_bytes, meta_dict = capture_raw_fn(max_width=1024, quality=70)
                parts[0] += f"\nScreenshot meta: {json.dumps(meta_dict)}"
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

            resp = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            plan = json.loads(resp.text or "{}")
            note = str(plan.get("note", ""))
            actions = list(plan.get("actions") or [])

            executed: list[str] = []
            for act in actions:
                guard.raise_if_aborted()
                guard.heartbeat(timeout=30.0)
                op = act.get("action")

                if op == "ui_click":
                    res = perform_ui_action(
                        "click",
                        name=act.get("name"),
                        automation_id=act.get("automation_id"),
                        control_type=act.get("control_type"),
                        window_title=window_title,
                    )
                    executed.append(f"ui_click:{res['element']['name']}")
                elif op == "ui_set_text":
                    res = perform_ui_action(
                        "set_text",
                        name=act.get("name"),
                        automation_id=act.get("automation_id"),
                        control_type=act.get("control_type"),
                        window_title=window_title,
                        text=str(act.get("text", "")),
                        paste_fn=paste_fn,
                    )
                    executed.append(f"ui_set_text:{res['element']['name']}")
                elif op in ("click", "double_click"):
                    sx, sy = resolve_coords_fn(act.get("x"), act.get("y"), "last_screenshot")
                    if op == "click":
                        pyautogui.click(sx, sy)
                    else:
                        pyautogui.doubleClick(sx, sy)
                    executed.append(f"{op}:({sx},{sy})")
                elif op == "paste_text":
                    paste_fn(str(act.get("text", "")))
                    executed.append("paste_text")
                elif op == "type":
                    pyautogui.write(str(act.get("text", "")))
                    executed.append("type")
                elif op == "press":
                    k = str(act.get("key") or act.get("text"))
                    pyautogui.press(k)
                    executed.append(f"press:{k}")
                elif op == "hotkey":
                    ks = list(act.get("keys") or [])
                    pyautogui.hotkey(*ks)
                    executed.append(f"hotkey:{'+'.join(ks)}")
                elif op == "focus_window":
                    executed.append(focus_fn(str(act["target"])))
                    time.sleep(0.12)
                elif op == "launch_app":
                    launch_fn(str(act["target"]), act.get("args"), act.get("working_dir"))
                    executed.append(f"launch:{act['target']}")
                    time.sleep(0.25)
                elif op == "wait":
                    ms = max(0, min(int(act.get("ms", 150)), 3000))
                    time.sleep(ms / 1000.0)
                    executed.append(f"wait:{ms}ms")

            history_log.append({"step": step_idx, "note": note, "executed": executed})
            final_note = note

            if plan.get("need_user_help"):
                final_status = "need_user_help"
                break
            if plan.get("done"):
                final_status = "completed"
                break
            time.sleep(0.08)
    finally:
        guard.stop()

    return {
        "status": final_status,
        "model": model,
        "steps_taken": len(history_log),
        "note": final_note,
        "history": history_log,
    }
