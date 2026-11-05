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


@pytest.mark.parametrize('nested', [False, True])
def test_watchdog_nested_in_driver_update_does_not_destroy_interpreter_mid_callback(monkeypatch, nested):
    """Replay the Windows trace deterministically, without a display/clipboard."""
    import asyncio
    tk = ModuleType('tkinter')
    ttk = ModuleType('tkinter.ttk')
    tk.ttk = ttk
    tk.TclError = type('TclError', (Exception,), {})
    instances = []
    class Root:
        def __init__(self):
            self.callbacks = {}
            self.destroy_calls = self.clipboard_reads = 0
            self.tk = self
            self.value = ''
            instances.append(self)
        def after(self, delay, callback): self.callbacks[delay] = callback
        def after_cancel(self, callback): pass
        def call(self, *args): return ()
        def clipboard_clear(self): self.value = ''
        def clipboard_append(self, value): self.value = value
        def clipboard_get(self):
            self.clipboard_reads += 1
            if self.destroy_calls: raise tk.TclError('Interpreter destroyed during driver')
            return self.value
        def update(self):
            # Dispatch the deadline reentrantly, exactly where real Tk did.
            self.callbacks[max(self.callbacks)]()
        def destroy(self): self.destroy_calls += 1
        def winfo_exists(self): return not self.destroy_calls
    tk.Tk = Root
    monkeypatch.setitem(sys.modules, 'tkinter', tk)
    monkeypatch.setitem(sys.modules, 'tkinter.ttk', ttk)
    path = Path(__file__).resolve().parents[1] / 'scripts_sdk/check_window_prompt_runtime.py'
    spec = importlib.util.spec_from_file_location('gui_watchdog_policy', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async def prompt(*args, **kwargs):
        root = tk.Tk()
        root.callbacks[150 if nested else max(root.callbacks)]()
        raise asyncio.CancelledError()
    monkeypatch.setattr(module, 'window_prompt', prompt)
    def driver(root): module.clipboard(root, 'synthetic')
    with pytest.raises(AssertionError, match='Synthetic GUI driver did not close dialog'):
        module.run_case('synthetic', driver, None)
    assert instances[0].destroy_calls == 1
    assert instances[0].clipboard_reads == 0
