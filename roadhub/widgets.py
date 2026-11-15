"""Kleine gemeinsame Bausteine für die Oberfläche."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import theme

APP_TITLE = "Roadhub"


class Dialog(tk.Toplevel):
    """Modaler Dialog im Programmdesign. Unterklassen füllen self.body und überschreiben on_ok()."""

    def __init__(self, master: tk.Misc, title: str, ok_text: str = "OK") -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=theme.BG)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill="both", expand=True)
        self._buttons = ttk.Frame(self, padding=(16, 0, 16, 14))
        self._buttons.pack(fill="x")
        ttk.Button(self._buttons, text="Abbrechen", command=self.destroy).pack(side="right")
        self.ok_btn = ttk.Button(self._buttons, text=ok_text, style="Accent.TButton", command=self._ok)
        self.ok_btn.pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())

    def on_ok(self) -> bool:  # pragma: no cover - von Unterklassen überschrieben
        return True

    def _ok(self) -> None:
        if self.on_ok():
            self.destroy()

    def error(self, text: str) -> None:
        messagebox.showerror(APP_TITLE, text, parent=self)

    def popup(self) -> None:
        """Mittig über dem Hauptfenster anzeigen und auf das Schließen warten."""
        self.update_idletasks()
        root = self.master.winfo_toplevel()
        x = root.winfo_rootx() + max(0, (root.winfo_width() - self.winfo_reqwidth()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.wait_window()


def card(parent: tk.Misc, caption: str, accent: bool = False) -> tuple[ttk.Frame, tk.StringVar]:
    """Kleine Kennzahl-Karte: Überschrift + großer Wert."""
    frame = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
    ttk.Label(frame, text=caption, style="CardCaption.TLabel").pack(anchor="w")
    var = tk.StringVar(value="–")
    ttk.Label(frame, textvariable=var, style="CardAccent.TLabel" if accent else "CardValue.TLabel").pack(
        anchor="w"
    )
    return frame, var


def make_tree(parent: tk.Misc, columns: list[tuple[str, str, int, str]], height: int = 12):
    """columns: (id, Überschrift, Breite, Ausrichtung). Gibt (Frame, Treeview) zurück."""
    wrap = ttk.Frame(parent)
    ids = [c[0] for c in columns]
    tree = ttk.Treeview(wrap, columns=ids, show="headings", selectmode="browse", height=height)
    for cid, title, width, anchor in columns:
        tree.heading(cid, text=title)
        tree.column(cid, width=width, anchor=anchor)
    tree.tag_configure("even", background=theme.ROW_A)
    tree.tag_configure("odd", background=theme.ROW_B)
    scroll = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return wrap, tree


def fill_tree(tree: ttk.Treeview, rows: list[tuple[str, tuple]]) -> None:
    """rows: (iid, Werte). Behält die Auswahl, wenn es die Zeile noch gibt."""
    selected = tree.selection()
    tree.delete(*tree.get_children())
    for i, (iid, values) in enumerate(rows):
        tree.insert("", "end", iid=iid, values=values, tags=("odd" if i % 2 else "even",))
    if selected and tree.exists(selected[0]):
        tree.selection_set(selected[0])
