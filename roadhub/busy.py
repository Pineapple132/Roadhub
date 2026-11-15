"""Loading feedback for all buttons: while a click is being processed, the window shows the hourglass cursor
and "Bitte warten …" (Please wait …) in the status bar. If the click opens a dialog, the display is paused meanwhile."""
from __future__ import annotations

import functools
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BUSY_TEXT = "Bitte warten …"

_app = None
_depth = 0
_paused = 0
_prev_text = ""
_installed = False


def _status_is_busy() -> bool:
    from . import i18n
    try:
        return str(_app.status.cget("text")) == i18n.tr(BUSY_TEXT)
    except (tk.TclError, AttributeError):
        return False


def _show() -> None:
    global _prev_text
    try:
        if not _status_is_busy():
            _prev_text = str(_app.status.cget("text"))
        _app.config(cursor="watch")
        _app.status.config(text=BUSY_TEXT)
        _app.update_idletasks()
    except (tk.TclError, AttributeError):
        pass


def _hide() -> None:
    try:
        _app.config(cursor="")
        if _status_is_busy():
            _app.status.config(text=_prev_text)
        _app.update_idletasks()
    except (tk.TclError, AttributeError):
        pass


def begin() -> None:
    global _depth
    _depth += 1
    if _depth == 1 and not _paused:
        _show()


def end() -> None:
    global _depth
    _depth = max(0, _depth - 1)
    if _depth == 0:
        _hide()


def _pause() -> None:
    global _paused
    _paused += 1
    if _depth and _paused == 1:
        _hide()


def _resume() -> None:
    global _paused
    _paused = max(0, _paused - 1)
    if _depth and not _paused:
        _show()


def run(func, *args, **kwargs):
    begin()
    try:
        return func(*args, **kwargs)
    finally:
        end()


def _wrap_command(command):
    if not callable(command) or getattr(command, "_busy_wrapped", False):
        return command

    @functools.wraps(command)
    def wrapper(*a, **k):
        return run(command, *a, **k)

    wrapper._busy_wrapped = True  # type: ignore[attr-defined]
    return wrapper


def _paused_call(func):
    @functools.wraps(func)
    def wrapper(*a, **k):
        _pause()
        try:
            return func(*a, **k)
        finally:
            _resume()
    return wrapper


def install(app) -> None:
    """Must be called after i18n.install(). The hooks are set once per process."""
    global _app, _installed
    _app = app
    if _installed:
        return
    _installed = True

    orig_init = ttk.Button.__init__

    def button_init(self, master=None, **kw):
        if "command" in kw:
            kw["command"] = _wrap_command(kw["command"])
        orig_init(self, master, **kw)

    ttk.Button.__init__ = button_init

    orig_wait = tk.Misc.wait_window
    tk.Misc.wait_window = _paused_call(orig_wait)

    for mod, names in (
        (messagebox, ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                      "askretrycancel", "askquestion", "askyesnocancel")),
        (filedialog, ("askopenfilename", "asksaveasfilename", "askdirectory")),
    ):
        for name in names:
            if hasattr(mod, name):
                setattr(mod, name, _paused_call(getattr(mod, name)))
