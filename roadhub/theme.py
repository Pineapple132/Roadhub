"""Dark design with orange accents, inspired by the menus of Euro Truck Simulator 2.

Only colours and shapes – no logos or graphics from the game.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#15181a"            # window background
PANEL = "#1e2326"         # header, cards
PANEL_RAISED = "#2a3135"  # tabs, headings
FIELD = "#0f1214"         # input fields
BORDER = "#3a4348"
TEXT = "#ececec"
MUTED = "#98a2a8"
ACCENT = "#f7a021"        # ETS-style orange
ACCENT_HOVER = "#ffb84a"
ON_ACCENT = "#17120a"
BTN = "#2f373c"
BTN_HOVER = "#3b454b"
DISABLED_FG = "#6b757a"
ROW_A = "#1a1e21"
ROW_B = "#20262a"
DANGER = "#e8624f"

_FONT_CANDIDATES = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans", "Liberation Sans"]


def pick_font_family(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for name in _FONT_CANDIDATES:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def apply(root: tk.Tk) -> dict[str, tuple]:
    """Sets the theme and returns named fonts."""
    family = pick_font_family(root)
    fonts = {
        "base": (family, 10),
        "bold": (family, 10, "bold"),
        "small": (family, 9),
        "head": (family, 11, "bold"),
        "title": (family, 18, "bold"),
        "chip": (family, 15, "bold"),
    }
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name).configure(family=family, size=10)
        except tk.TclError:
            pass

    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)

    # drop-down lists of the comboboxes
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)
    root.option_add("*TCombobox*Listbox.font", fonts["base"])
    root.option_add("*Text.background", FIELD)
    root.option_add("*Text.foreground", TEXT)

    style.configure(
        ".",
        background=BG,
        foreground=TEXT,
        fieldbackground=FIELD,
        bordercolor=BORDER,
        lightcolor=PANEL_RAISED,
        darkcolor=PANEL_RAISED,
        troughcolor=FIELD,
        focuscolor=ACCENT,
        insertcolor=TEXT,
        selectbackground=ACCENT,
        selectforeground=ON_ACCENT,
        font=fonts["base"],
    )
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Accent.TFrame", background=ACCENT)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=fonts["small"])
    style.configure("Title.TLabel", background=PANEL, foreground=ACCENT, font=fonts["title"])
    style.configure("Chip.TLabel", background=PANEL, foreground=ACCENT, font=fonts["chip"])
    style.configure("Head.TLabel", background=BG, foreground=ACCENT, font=fonts["head"])

    style.configure(
        "TLabelframe", background=BG, bordercolor=BORDER, relief="solid", borderwidth=1
    )
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=fonts["bold"])

    # tabs
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=[0, 6, 0, 0])
    style.configure(
        "TNotebook.Tab",
        background=PANEL_RAISED,
        foreground=TEXT,
        padding=[22, 9],
        borderwidth=0,
        font=fonts["bold"],
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", ACCENT), ("active", BTN_HOVER)],
        foreground=[("selected", ON_ACCENT)],
    )

    # buttons
    style.configure(
        "TButton",
        background=BTN,
        foreground=TEXT,
        bordercolor=BORDER,
        padding=[14, 7],
        focusthickness=1,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", BTN_HOVER), ("active", BTN_HOVER)],
        foreground=[("disabled", DISABLED_FG)],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=ON_ACCENT,
        bordercolor=ACCENT,
        padding=[18, 8],
        font=fonts["bold"],
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", "#5a4a2a"), ("pressed", ACCENT_HOVER), ("active", ACCENT_HOVER)],
        foreground=[("disabled", "#8a7c60")],
        bordercolor=[("disabled", "#5a4a2a")],
    )
    style.configure("Small.TButton", padding=[8, 3], font=fonts["small"])

    # sidebar
    style.configure(
        "Nav.TButton", background=PANEL, foreground=TEXT, bordercolor=PANEL, relief="flat",
        padding=[20, 10], anchor="w", font=fonts["base"],
    )
    style.map(
        "Nav.TButton",
        background=[("active", PANEL_RAISED)],
        bordercolor=[("active", PANEL_RAISED), ("focus", PANEL)],
    )
    style.configure(
        "NavActive.TButton", background=ACCENT, foreground=ON_ACCENT, bordercolor=ACCENT,
        relief="flat", padding=[20, 10], anchor="w", font=fonts["bold"],
    )
    style.map("NavActive.TButton", background=[("active", ACCENT_HOVER)], bordercolor=[("focus", ACCENT)])
    style.configure(
        "NavSub.TButton", background=PANEL, foreground=MUTED, bordercolor=PANEL, relief="flat",
        padding=[38, 8], anchor="w", font=fonts["base"],
    )
    style.map(
        "NavSub.TButton",
        background=[("active", PANEL_RAISED)],
        foreground=[("active", TEXT)],
        bordercolor=[("active", PANEL_RAISED), ("focus", PANEL)],
    )
    style.configure(
        "NavSubActive.TButton", background=ACCENT, foreground=ON_ACCENT, bordercolor=ACCENT,
        relief="flat", padding=[38, 8], anchor="w", font=fonts["bold"],
    )
    style.map("NavSubActive.TButton", background=[("active", ACCENT_HOVER)], bordercolor=[("focus", ACCENT)])
    style.configure("NavHead.TLabel", background=PANEL, foreground=MUTED, font=fonts["small"])

    # notebook without visible tabs (the sidebar selects the page)
    style.layout("Hidden.TNotebook.Tab", [])
    style.configure("Hidden.TNotebook", background=BG, borderwidth=0, tabmargins=0)

    # KPI cards
    style.configure("Card.TFrame", background=PANEL)
    style.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=fonts["base"])
    style.configure("CardCaption.TLabel", background=PANEL, foreground=MUTED, font=fonts["small"])
    style.configure("CardValue.TLabel", background=PANEL, foreground=TEXT, font=fonts["chip"])
    style.configure("CardAccent.TLabel", background=PANEL, foreground=ACCENT, font=fonts["chip"])

    # input fields
    for name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(
            name,
            fieldbackground=FIELD,
            foreground=TEXT,
            bordercolor=BORDER,
            insertcolor=TEXT,
            padding=[6, 4],
            arrowcolor=TEXT,
        )
        style.map(
            name,
            fieldbackground=[("disabled", PANEL), ("readonly", FIELD)],
            foreground=[("disabled", DISABLED_FG)],
            bordercolor=[("focus", ACCENT)],
            arrowcolor=[("disabled", DISABLED_FG)],
        )
    style.configure("TCombobox", background=BTN)
    style.configure("TSpinbox", background=BTN)
    style.map(
        "TCombobox",
        selectbackground=[("!focus", FIELD)],
        selectforeground=[("!focus", TEXT)],
    )

    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=FIELD)
    style.map(
        "TCheckbutton",
        background=[("active", BG)],
        indicatorbackground=[("selected", ACCENT)],
        indicatorforeground=[("selected", ON_ACCENT)],
    )

    # table
    style.configure(
        "Treeview",
        background=ROW_A,
        fieldbackground=ROW_A,
        foreground=TEXT,
        rowheight=27,
        borderwidth=0,
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", ON_ACCENT)],
    )
    style.configure(
        "Treeview.Heading",
        background=PANEL_RAISED,
        foreground=ACCENT,
        relief="flat",
        padding=[8, 7],
        font=fonts["bold"],
    )
    style.map("Treeview.Heading", background=[("active", BTN_HOVER)])

    style.configure(
        "Vertical.TScrollbar",
        background=BTN,
        troughcolor=FIELD,
        bordercolor=BG,
        arrowcolor=TEXT,
    )
    style.map("Vertical.TScrollbar", background=[("active", BTN_HOVER)])
    return fonts


def format_int(value: str | int | None) -> str:
    """12345678 -> '12.345.678' (German notation)."""
    try:
        return f"{int(str(value).strip()):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "–"
