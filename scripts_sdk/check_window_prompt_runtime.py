"""Exercise the real Tk dialog on an isolated display with synthetic input only.

Requires --disposable-desktop: this uses the REAL GLOBAL OS CLIPBOARD with
synthetic strings. Never run on a user's desktop. On Linux, DISPLAY must point
at a disposable X server. No account flow is invoked; this is not an
authentication or financial integration.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitteam_sdk.account_check import window_prompt

# Hosted Windows clipboard/focus cold starts may exceed the previous 5 seconds.
# Each case remains bounded; the workflow's job timeout is the hard outer bound.
CASE_TIMEOUT_SECONDS = 30 if sys.platform == "win32" else 5


def checkpoint(root):
    """Observe a cooperative watchdog after nested Tk event processing."""
    check = getattr(root, "_sdk_driver_checkpoint", None)
    if check is not None:
        check()


def widgets(root):
    children = root.winfo_children()[0].winfo_children()
    entry = next(item for item in children if isinstance(item, ttk.Entry))
    buttons = {item.cget("text"): item for item in children if isinstance(item, ttk.Button)}
    labels = [item for item in children if isinstance(item, ttk.Label)]
    return entry, buttons, labels, children


def clipboard(root, value):
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()
    checkpoint(root)
    actual = root.clipboard_get()
    assert actual == value, f"Synthetic clipboard mismatch: expected_length={len(value)}, actual_length={len(actual)}"


def keyboard(root, entry, sequence):
    # Windows focus transfer is asynchronous. Process WM_SETFOCUS before
    # delivering the synthetic key, then queue it through the real Tk bindings.
    entry.focus_force()
    root.update()
    checkpoint(root)
    assert root.focus_get() is entry, "Synthetic key target did not receive focus"
    entry.event_generate(sequence, when="tail")
    root.update()
    checkpoint(root)


def expect_text(root, entry, value):
    actual = entry.get()
    assert actual == value, (f"Synthetic entry mismatch: expected_length={len(value)}, "
                             f"actual_length={len(actual)}, focused={root.focus_get() is entry}")


def secret_controls(root):
    entry, buttons, labels, children = widgets(root)
    assert str(buttons["Продолжить"].cget("state")) == "disabled"
    clipboard(root, " synthetic password ")
    keyboard(root, entry, "<Control-KeyPress-v>")
    expect_text(root, entry, " synthetic password ")
    assert any(item.cget("text") == "Введено символов: 20" for item in labels)
    assert str(buttons["Продолжить"].cget("state")) == "normal"
    toggle = next(item for item in children if isinstance(item, ttk.Checkbutton))
    assert entry.cget("show") == "*"
    toggle.invoke()
    assert entry.cget("show") == ""
    toggle.invoke()
    assert entry.cget("show") == "*"
    buttons["Очистить"].invoke()
    assert entry.get() == ""
    assert str(buttons["Продолжить"].cget("state")) == "disabled"
    assert any(item.cget("text") == "Поле пустое" for item in labels)
    entry.insert(0, "replace me")
    entry.selection_range(0, tk.END)
    clipboard(root, "synthetic replacement")
    keyboard(root, entry, "<Shift-Insert>")
    expect_text(root, entry, "synthetic replacement")
    buttons["Продолжить"].invoke()


def email_controls(root):
    entry, buttons, _, children = widgets(root)
    assert entry.cget("show") == ""
    assert not any(isinstance(item, ttk.Checkbutton) for item in children)
    clipboard(root, " synthetic@example.invalid ")
    buttons["Вставить"].invoke()
    assert entry.get() == "synthetic@example.invalid"
    buttons["Продолжить"].invoke()


def code_controls(value):
    def drive(root):
        entry, buttons, labels, _ = widgets(root)
        assert entry.cget("show") == "*"
        clipboard(root, value)
        buttons["Вставить"].invoke()
        assert entry.get() == value
        assert any(item.cget("text") == f"Введено символов: {len(value)}" for item in labels)
        keyboard(root, entry, "<Return>")
    return drive


def empty_clipboard(root):
    entry, buttons, labels, _ = widgets(root)
    root.clipboard_clear()
    buttons["Вставить"].invoke()
    assert entry.get() == ""
    assert str(buttons["Продолжить"].cget("state")) == "disabled"
    assert any("В буфере нет текста" in item.cget("text") for item in labels)
    buttons["Отмена"].invoke()


def cancel(root):
    entry, buttons, _, _ = widgets(root)
    entry.insert(0, "synthetic discarded")
    buttons["Отмена"].invoke()


def run_case(label, driver, expected):
    original = tk.Tk
    errors = []
    roots = []

    def factory(*args, **kwargs):
        root = original(*args, **kwargs)
        roots.append(root)
        destroy = root.destroy
        active = False
        closed = False
        expired = None

        def check_deadline():
            if expired is not None:
                raise expired

        root._sdk_driver_checkpoint = check_deadline

        def clear_and_destroy():
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                # Timed focus/watchdog callbacks must not outlive this dialog
                # and surface as Tcl errors in the next synthetic mainloop.
                for callback in root.tk.call("after", "info"):
                    root.after_cancel(callback)
                root.clipboard_clear()
            finally:
                destroy()

        root.destroy = clear_and_destroy

        def drive():
            nonlocal active
            active = True
            try:
                check_deadline()
                driver(root)
                check_deadline()
            except BaseException as error:
                if not errors:
                    errors.append(error)
            finally:
                active = False
                if errors:
                    root.destroy()

        def timeout():
            nonlocal expired
            if closed or expired is not None:
                return
            expired = AssertionError("Synthetic GUI driver did not close dialog")
            errors.append(expired)
            # root.update() can dispatch this callback inside the driver. Do
            # not destroy Tcl under its live clipboard/focus stack: its next
            # checkpoint raises the deadline, then drive's finally closes once.
            if not active:
                root.destroy()

        root.after(150, drive)
        root.after(CASE_TIMEOUT_SECONDS * 1000, timeout)
        return root

    try:
        with patch.object(tk, "Tk", factory):
            try:
                actual = asyncio.run(window_prompt(label))
            except asyncio.CancelledError:
                actual = None
    finally:
        for root in roots:
            try:
                if root.winfo_exists():
                    root.destroy()
            except tk.TclError:
                pass  # The production dialog already destroyed its interpreter.
    if errors:
        raise errors[0]
    assert actual == expected


def forbidden_http(*args, **kwargs):
    raise AssertionError("GUI runtime check must not create an HTTP client")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable-desktop", action="store_true",
                        help="Acknowledge this is an isolated desktop; global clipboard will be changed")
    if not parser.parse_args(argv).disposable_desktop:
        parser.error("--disposable-desktop is required before any Tk or clipboard access")
    cases = [
        ("password-controls", "BitTeam password (hidden): ", secret_controls, "synthetic replacement"),
        ("email-paste", "BitTeam email (hidden): ", email_controls, "synthetic@example.invalid"),
        ("totp-input", "Google 2FA code - 6 digits (hidden): ", code_controls("012345"), "012345"),
        ("device-code-input", "Device code from email or Telegram - 4 digits (hidden): ", code_controls("0123"), "0123"),
        ("empty-clipboard", "BitTeam password (hidden): ", empty_clipboard, None),
        ("cancel", "BitTeam password (hidden): ", cancel, None),
    ]
    with patch.object(aiohttp, "ClientSession", forbidden_http):
        for _, label, driver, expected in cases:
            run_case(label, driver, expected)
    print(json.dumps({"check": "real-tk-synthetic-dialog", "tk": tk.TkVersion,
                      "case_timeout_seconds": CASE_TIMEOUT_SECONDS,
                      "passed": [name for name, *_ in cases],
                      "account_flow": "not invoked"}))


if __name__ == "__main__":
    main()
