"""Language switching. The texts in the program are German (they are the catalog keys); for other languages there is a catalog
(i18n_*.py): German text → translation. Dynamic texts are in the catalog with {} as placeholders
(e.g. "Bus #{} warten?"). Translation happens in one place: when texts are set in tkinter widgets,
dialogs and tables. Whatever is not in the catalog stays German."""

from __future__ import annotations

import json
import os
import re
import tkinter as tk
from tkinter import messagebox, ttk

# order of the columns in the catalog (after German)
LANGUAGES = [("de", "Deutsch"), ("en", "English"), ("ru", "Русский"), ("tr", "Türkçe"), ("pl", "Polski")]
CATALOG_ORDER = ["en", "ru", "tr", "pl"]

_lang = "de"
_exact: dict[str, str] = {}
_templates: list[tuple[re.Pattern, str]] = []
_reverse: dict[str, str] = {}
_cache: dict[str, str] = {}
_installed = False


def settings_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ets2_save_tool", "ui.json")


def _read_ui() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def ui_get(key: str, default=None):
    """Reads a value from the UI file (language, tours already seen)."""
    return _read_ui().get(key, default)


def ui_set(**values) -> None:
    data = _read_ui()
    data.update(values)
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def has_saved_language() -> bool:
    return os.environ.get("ETS2_LANG", "") in dict(LANGUAGES) or ui_get("language") in dict(LANGUAGES)


def load_saved_language() -> str:
    forced = os.environ.get("ETS2_LANG", "")
    if forced in dict(LANGUAGES):
        return forced
    code = ui_get("language", "de")
    return code if code in dict(LANGUAGES) else "de"


def save_language(code: str) -> None:
    ui_set(language=code)


def language() -> str:
    return _lang


def _catalog() -> dict[str, tuple]:
    from . import i18n_data
    return i18n_data.CATALOG


def set_language(code: str) -> None:
    """Sets the language and builds the lookup tables."""
    global _lang
    if code not in dict(LANGUAGES):
        code = "de"
    _lang = code
    _exact.clear()
    _templates.clear()
    _reverse.clear()
    _cache.clear()
    if code == "de":
        return
    idx = CATALOG_ORDER.index(code)
    for german, row in _catalog().items():
        text = row[idx] if idx < len(row) and row[idx] else ""
        if not text:
            continue
        if "{}" in german:
            pattern = "^" + re.escape(german).replace(r"\{\}", "(.+?)") + "$"
            _templates.append((re.compile(pattern, re.S), text))
        else:
            _exact[german] = text
            _reverse.setdefault(text, german)
    _templates.sort(key=lambda t: -len(t[0].pattern))      # more specific patterns first


def tr(text):
    """Translates a German text (non-texts and unknown texts stay unchanged)."""
    if _lang == "de" or not isinstance(text, str) or not text:
        return text
    hit = _exact.get(text)
    if hit is not None:
        return hit
    hit = _cache.get(text)
    if hit is not None:
        return hit
    out = text
    for pattern, template in _templates:
        m = pattern.match(text)
        if m:
            groups = [tr(g) for g in m.groups()]
            try:
                out = template.format(*groups) if "{1}" not in template else template.format(None, *groups)
            except (IndexError, KeyError, ValueError):
                out = text
            break
    if len(_cache) < 5000:
        _cache[text] = out
    return out


def source(text):
    """Counterpart of tr: translated text → German original text (for comparisons in the code)."""
    return _reverse.get(text, text) if _lang != "de" and isinstance(text, str) else text


# ---- Hooking into tkinter ------------------------------------------------

def _tr_option(key: str, value):
    if key in ("text", "title", "label") and isinstance(value, str):
        return tr(value)
    if key == "values" and isinstance(value, (list, tuple)):
        return type(value)(tr(v) if isinstance(v, str) else v for v in value) if not isinstance(value, str) else value
    return value


def install() -> None:
    """Hooks the translation into tkinter (once per process)."""
    global _installed
    if _installed:
        return
    _installed = True

    orig_title = tk.Wm.wm_title

    def wm_title(self, string=None):
        return orig_title(self, tr(string))

    tk.Wm.wm_title = wm_title
    tk.Wm.title = wm_title

    orig_options = tk.Misc._options

    def _options(self, cnf, kw=None):
        if kw:
            kw = {k: _tr_option(k, v) for k, v in kw.items()}
        if cnf and isinstance(cnf, dict):
            cnf = {k: _tr_option(k, v) for k, v in cnf.items()}
        return orig_options(self, cnf, kw)

    tk.Misc._options = _options

    orig_ttk_configure = ttk.Widget.configure

    def ttk_configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            cnf = {k: _tr_option(k, v) for k, v in cnf.items()}
        kw = {k: _tr_option(k, v) for k, v in kw.items()}
        return orig_ttk_configure(self, cnf, **kw)

    ttk.Widget.configure = ttk_configure
    ttk.Widget.config = ttk_configure

    orig_set = tk.StringVar.set

    def var_set(self, value):
        return orig_set(self, tr(value))

    tk.StringVar.set = var_set

    orig_get = ttk.Combobox.get

    def combo_get(self):
        return source(orig_get(self))

    ttk.Combobox.get = combo_get

    orig_heading = ttk.Treeview.heading

    def heading(self, column, option=None, **kw):
        if "text" in kw:
            kw["text"] = tr(kw["text"])
        return orig_heading(self, column, option, **kw)

    ttk.Treeview.heading = heading

    orig_insert = ttk.Treeview.insert

    def insert(self, parent, index, iid=None, **kw):
        if "values" in kw and isinstance(kw["values"], (list, tuple)):
            kw["values"] = tuple(tr(v) if isinstance(v, str) else v for v in kw["values"])
        if "text" in kw:
            kw["text"] = tr(kw["text"])
        return orig_insert(self, parent, index, iid, **kw)

    ttk.Treeview.insert = insert

    for name in ("showinfo", "showwarning", "showerror", "askokcancel", "askyesno", "askyesnocancel",
                 "askretrycancel", "askquestion"):
        orig = getattr(messagebox, name)

        def wrapped(title=None, message=None, *a, _orig=orig, **kw):
            return _orig(tr(title), tr(message), *a, **kw)

        setattr(messagebox, name, wrapped)
