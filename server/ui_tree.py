"""Windows UI Automation (UIA) inspection and element-action helpers."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Literal

import pyautogui
import uiautomation as auto

INTERACTIVE_TYPES = {
    "ButtonControl",
    "EditControl",
    "DocumentControl",
    "MenuItemControl",
    "ListItemControl",
    "TabItemControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "ComboBoxControl",
    "HyperlinkControl",
    "TreeItemControl",
    "SliderControl",
    "SplitButtonControl",
    "ToggleSwitchControl",
}


def _resolve_root_control(window_title: str | None) -> tuple[Any, dict[str, Any]]:
    if window_title:
        q = window_title.strip().lower()
        root = auto.GetRootControl()
        for child in root.GetChildren():
            try:
                name = (child.Name or "").strip()
                handle = getattr(child, "NativeWindowHandle", 0)
                if (q.isdigit() and int(q) == handle) or (q in name.lower()):
                    r = child.BoundingRectangle
                    return child, {
                        "title": name,
                        "hwnd": int(handle or 0),
                        "rect": {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom},
                    }
            except Exception:
                continue
        raise ValueError(f"No UIA top-level window matched '{window_title}'.")

    fg = auto.GetForegroundControl()
    # Walk up to top-level window if possible
    cur = fg
    root_handle = auto.GetRootControl().NativeWindowHandle
    while cur is not None:
        try:
            parent = cur.GetParentControl()
            if parent is None or parent.NativeWindowHandle == root_handle:
                break
            cur = parent
        except Exception:
            break
    target = cur or fg
    r = target.BoundingRectangle
    return target, {
        "title": (target.Name or "").strip(),
        "hwnd": int(getattr(target, "NativeWindowHandle", 0) or 0),
        "rect": {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom},
    }


def inspect_ui_tree(
    window_title: str | None = None,
    max_depth: int = 5,
    max_elements: int = 120,
    interactive_only: bool = True,
) -> dict[str, Any]:
    """Read interactive or named controls from a Windows UIA tree without screenshots."""
    depth_cap = max(1, min(max_depth, 10))
    elem_cap = max(1, min(max_elements, 250))

    with auto.UIAutomationInitializerInThread():
        root_ctrl, win_info = _resolve_root_control(window_title)
        elements: list[dict[str, Any]] = []
        queue: deque[tuple[Any, int]] = deque([(root_ctrl, 0)])

        while queue and len(elements) < elem_cap:
            ctrl, depth = queue.popleft()
            if depth > depth_cap:
                continue

            try:
                if depth > 0:
                    ctype = ctrl.ControlTypeName or ""
                    name = (ctrl.Name or "").strip()
                    aid = (ctrl.AutomationId or "").strip()
                    rect = ctrl.BoundingRectangle
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    visible = w > 0 and h > 0 and not ctrl.IsOffscreen

                    keep = visible and (
                        (not interactive_only and (name or aid or ctype in INTERACTIVE_TYPES))
                        or (interactive_only and ctype in INTERACTIVE_TYPES and (name or aid))
                    )
                    if keep:
                        val_snippet = ""
                        try:
                            vp = ctrl.GetValuePattern()
                            if vp:
                                val_snippet = (vp.Value or "")[:80]
                        except Exception:
                            pass
                        elements.append(
                            {
                                "index": len(elements),
                                "name": name[:120],
                                "control_type": ctype.removesuffix("Control"),
                                "automation_id": aid[:80],
                                "cx": rect.left + w // 2,
                                "cy": rect.top + h // 2,
                                "rect": {"left": rect.left, "top": r_top(rect), "w": w, "h": h},
                                "enabled": bool(ctrl.IsEnabled),
                                **({"value": val_snippet} if val_snippet else {}),
                            }
                        )
            except Exception:
                pass

            if depth < depth_cap:
                try:
                    for ch in ctrl.GetChildren():
                        queue.append((ch, depth + 1))
                except Exception:
                    pass

        return {"window": win_info, "count": len(elements), "elements": elements}


def r_top(rect: Any) -> int:
    return int(rect.top)


def _match_element(
    root_ctrl: Any,
    name: str | None,
    automation_id: str | None,
    control_type: str | None,
    exact: bool,
    max_depth: int = 8,
) -> tuple[Any, dict[str, Any]]:
    q_name = name.strip().lower() if name else None
    q_aid = automation_id.strip().lower() if automation_id else None
    q_ctype = control_type.strip().lower().removesuffix("control") if control_type else None

    queue: deque[tuple[Any, int]] = deque([(root_ctrl, 0)])
    while queue:
        ctrl, depth = queue.popleft()
        if depth > max_depth:
            continue

        try:
            if depth > 0:
                c_name = (ctrl.Name or "").strip()
                c_aid = (ctrl.AutomationId or "").strip()
                c_ctype = (ctrl.ControlTypeName or "").removesuffix("Control")
                rect = ctrl.BoundingRectangle
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                visible = w > 0 and h > 0 and not ctrl.IsOffscreen

                if visible:
                    ok = True
                    if q_name is not None:
                        c_low = c_name.lower()
                        ok = ok and ((c_low == q_name) if exact else (q_name in c_low))
                    if q_aid is not None:
                        ok = ok and (c_aid.lower() == q_aid if exact else q_aid in c_aid.lower())
                    if q_ctype is not None:
                        ok = ok and (c_ctype.lower() == q_ctype)

                    if ok:
                        meta = {
                            "name": c_name,
                            "control_type": c_ctype,
                            "automation_id": c_aid,
                            "cx": rect.left + w // 2,
                            "cy": rect.top + h // 2,
                        }
                        return ctrl, meta
        except Exception:
            pass

        if depth < max_depth:
            try:
                for ch in ctrl.GetChildren():
                    queue.append((ch, depth + 1))
            except Exception:
                pass

    raise ValueError(
        f"No visible UI element matched (name={name!r}, automation_id={automation_id!r}, control_type={control_type!r})."
    )


def perform_ui_action(
    action: Literal["click", "double_click", "right_click", "set_text", "focus"],
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    window_title: str | None = None,
    text: str | None = None,
    exact: bool = False,
    paste_fn: Any = None,
) -> dict[str, Any]:
    """Locate a UI Automation control and interact with it directly without screenshots."""
    if not any([name, automation_id, control_type]):
        raise ValueError("Provide at least one of name, automation_id, or control_type.")

    with auto.UIAutomationInitializerInThread():
        root_ctrl, win_info = _resolve_root_control(window_title)
        ctrl, meta = _match_element(root_ctrl, name, automation_id, control_type, exact=exact)
        cx, cy = meta["cx"], meta["cy"]

        if action == "focus":
            try:
                ctrl.SetFocus()
            except Exception:
                pyautogui.click(cx, cy)
            return {"action": "focus", "window": win_info["title"], "element": meta}

        if action == "click":
            pyautogui.click(cx, cy)
            return {"action": "click", "window": win_info["title"], "element": meta}

        if action == "double_click":
            pyautogui.doubleClick(cx, cy)
            return {"action": "double_click", "window": win_info["title"], "element": meta}

        if action == "right_click":
            pyautogui.rightClick(cx, cy)
            return {"action": "right_click", "window": win_info["title"], "element": meta}

        if action == "set_text":
            if text is None:
                raise ValueError("set_text requires text.")
            pyautogui.click(cx, cy)
            time.sleep(0.04)
            try:
                vp = ctrl.GetValuePattern()
                if vp is not None and not vp.IsReadOnly:
                    vp.SetValue(text)
                    return {
                        "action": "set_text",
                        "method": "ValuePattern",
                        "window": win_info["title"],
                        "element": meta,
                        "chars": len(text),
                    }
            except Exception:
                pass
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.02)
            if paste_fn is not None:
                paste_fn(text)
            else:
                pyautogui.write(text)
            return {
                "action": "set_text",
                "method": "paste_text",
                "window": win_info["title"],
                "element": meta,
                "chars": len(text),
            }

        raise ValueError(f"Unsupported UI action: {action}")
