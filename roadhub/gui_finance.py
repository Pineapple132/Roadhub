"""Seite „Finanzen“: Einnahmen und Ausgaben der Firma nach Art."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .busco import DAY, EXPENSE_CATS, INCOME_CATS, eur
from .gui_company import _Page
from .widgets import fill_tree, make_tree


class FinancePage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        ttk.Label(self, text="Finanzen", style="Head.TLabel").pack(anchor="w")
        ttk.Label(
            self, style="Muted.TLabel", wraplength=900, justify="left",
            text=("Einnahmen und Ausgaben deiner Firma. „Echte Fahrten“ sind dein Verdienst aus ETS2, der schon im "
                  "Spiel auf dem Konto liegt. Alles andere ist reserviert und wird beim Beenden von ETS2 in den "
                  "Spielstand geschrieben."),
        ).pack(anchor="w", pady=(2, 8))
        wrap, self.tree = make_tree(
            self,
            [("cat", "", 280, "w"), ("today", "Heute", 110, "e"), ("yday", "Gestern", 110, "e"),
             ("week", "7 Tage", 120, "e"), ("all", "Insgesamt", 130, "e")],
            height=18,
        )
        wrap.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        if c is None:
            fill_tree(self.tree, [])
            return
        today = c.now // DAY
        periods = [c.finance_period(today, today), c.finance_period(today - 1, today - 1),
                   c.finance_period(today - 6, today), dict(c.fin_total)]

        def row(iid: str, label: str, values: list[float], sign: str = "") -> tuple[str, tuple]:
            return iid, (label, *[(sign + eur(v)) if v else "–" for v in values])

        rows: list[tuple[str, tuple]] = [("h1", ("EINNAHMEN", "", "", "", ""))]
        for cat in INCOME_CATS:
            rows.append(row("i_" + cat, "   " + cat, [p.get(cat, 0.0) for p in periods], "+ "))
        inc = [sum(p.get(k, 0.0) for k in INCOME_CATS) for p in periods]
        rows.append(row("it", "Einnahmen gesamt", inc, "+ "))
        rows.append(("h2", ("AUSGABEN", "", "", "", "")))
        for cat in EXPENSE_CATS:
            rows.append(row("e_" + cat, "   " + cat, [p.get(cat, 0.0) for p in periods], "- "))
        exp = [sum(p.get(k, 0.0) for k in EXPENSE_CATS) for p in periods]
        rows.append(row("et", "Ausgaben gesamt", exp, "- "))
        net = [i - e for i, e in zip(inc, exp)]
        rows.insert(0, ("net", ("ERGEBNIS", *[("+ " if v >= 0 else "- ") + eur(abs(v)) for v in net])))
        fill_tree(self.tree, rows)
