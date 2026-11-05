"""CLI consent boundary only; real Tk runtime runs separately on a desktop."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest


def test_driver_requires_disposable_desktop_before_any_tk_or_clipboard(monkeypatch):
    calls = []
    tk = ModuleType('tkinter')
    tk.Tk = lambda *args, **kwargs: calls.append('Tk')
    ttk = ModuleType('tkinter.ttk')
    tk.ttk = ttk
    monkeypatch.setitem(sys.modules, 'tkinter', tk)
    monkeypatch.setitem(sys.modules, 'tkinter.ttk', ttk)
    path = Path(__file__).resolve().parents[1] / 'scripts_sdk/check_window_prompt_runtime.py'
    spec = importlib.util.spec_from_file_location('gui_runtime_policy', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not calls  # Import itself must not create a desktop or clipboard.
    with pytest.raises(SystemExit) as error:
        module.main([])
    assert error.value.code == 2
    assert not calls
