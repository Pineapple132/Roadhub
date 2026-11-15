"""Page "Settings": set prices, costs, income and operation of the company."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import busco
from .busco import CompanyError
from .gui_company import _Page
from .widgets import APP_TITLE

GROUPS = ["Einnahmen", "Kosten", "Preise", "Bus-XP", "Betrieb"]
HINTS = {
    "Einnahmen": "Alle Linien, Ausflüge und Verträge laufen auf diesem Satz. Laufende Verträge werden sofort umgepreist.",
    "Kosten": "Laufende Kosten der Fahrten und des Betriebs.",
    "Preise": "Anschaffungen in Prozent vom Standardpreis.",
    "Bus-XP": "Simulierte Fahrten deiner Fahrer bringen nur wenig Bus-XP. Deine eigenen Fahrten zählt das Spiel selbst.",
    "Betrieb": "Arbeitszeiten, Wartung, Vertragsangebote und Bewerber.",
}


class SettingsPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        self.vars: dict[str, tk.StringVar] = {}
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Einstellungen", style="Head.TLabel").pack(side="left")
        ttk.Button(top, text="Alles auf Standard", command=self.reset).pack(side="right")
        ttk.Button(top, text="Übernehmen", style="Accent.TButton", command=self.apply).pack(side="right", padx=8)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, pady=(8, 0))
        self.canvas = tk.Canvas(outer, highlightthickness=0, bg=ttk.Style().lookup("TFrame", "background") or "#14161a")
        bar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self._build()
        self.refresh()

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _build(self) -> None:
        # company values from the settings (not from TUNABLES)
        self.extra = {
            "Einnahmen": [("profit_multiplier", "Gewinnfaktor auf alle Einnahmen", 0.1, 5.0, 0.1, "×")],
            "Bus-XP": [("xp_per_trip", "Bus-XP pro Fahrt (Obergrenze)", 0, 1000, 5, "XP")],
        }
        firm = ttk.LabelFrame(self.body, text="Firma", padding=10)
        firm.pack(fill="x", pady=(0, 10), padx=(0, 8))
        ttk.Label(firm, text="Name der Firma").grid(row=0, column=0, sticky="w", pady=3)
        self.name_var = tk.StringVar()
        ttk.Entry(firm, textvariable=self.name_var, width=34).grid(row=0, column=1, padx=10, sticky="w")
        firm.columnconfigure(0, weight=1)
        for group in GROUPS:
            box = ttk.LabelFrame(self.body, text=group, padding=10)
            box.pack(fill="x", pady=(0, 10), padx=(0, 8))
            ttk.Label(box, text=HINTS[group], style="Muted.TLabel", wraplength=820, justify="left").grid(
                row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
            row = 1
            if group == "Betrieb":
                self.respect_var = tk.BooleanVar(value=True)
                ttk.Checkbutton(
                    box, text="An Zeiten halten: Fahrer lenken nur bis zur Höchstfahrzeit, dann ruht der Bus bis zum Morgen",
                    variable=self.respect_var).grid(row=row, column=0, columnspan=4, sticky="w", pady=3)
                row += 1
            entries = [(k, lab, lo, hi, st, unit, d) for k, g, lab, d, lo, hi, st, unit in busco.TUNABLES if g == group]
            entries = [(k, lab, lo, hi, st, unit, None) for k, lab, lo, hi, st, unit in self.extra.get(group, [])] + entries
            for key, label, lo, hi, step, unit, default in entries:
                ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=3)
                var = tk.StringVar()
                self.vars[key] = var
                ttk.Spinbox(box, from_=lo, to=hi, increment=step, width=10, textvariable=var).grid(
                    row=row, column=1, padx=10)
                ttk.Label(box, text=unit).grid(row=row, column=2, sticky="w")
                if default is not None:
                    ttk.Label(box, text=f"Standard: {default:g}", style="Muted.TLabel").grid(
                        row=row, column=3, sticky="w", padx=14)
                row += 1
            box.columnconfigure(0, weight=1)

    def refresh(self) -> None:
        c = self.company
        if c is None:
            return
        values = dict(busco.TUNE_DEFAULTS)
        values.update(c.settings.tuning)
        for key, var in self.vars.items():
            if key in values:
                var.set(f"{values[key]:g}")
        self.name_var.set(c.name)
        self.vars["profit_multiplier"].set(f"{c.settings.profit_multiplier:g}")
        self.vars["xp_per_trip"].set(str(c.settings.xp_per_trip))
        self.respect_var.set(c.settings.respect_hours)

    def apply(self) -> None:
        c = self.company
        if c is None:
            messagebox.showinfo(APP_TITLE, "Lade erst einen Spielstand, damit es eine Firma gibt.")
            return
        try:
            tune = {k: float(self.vars[k].get().replace(",", ".")) for k in busco.TUNE_DEFAULTS}
            mult = float(self.vars["profit_multiplier"].get().replace(",", "."))
            xp = int(float(self.vars["xp_per_trip"].get().replace(",", ".")))
            c.set_name(self.name_var.get())
            c.set_tuning(tune)
            c.set_settings(profit_multiplier=mult, xp_per_trip=xp, respect_hours=self.respect_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Bitte überall Zahlen eintragen.")
            return
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.shell.company_changed()
        self.shell._set_status("Einstellungen übernommen. Laufende Verträge sind neu bepreist.")

    def reset(self) -> None:
        c = self.company
        if c is None:
            return
        if not messagebox.askyesno(APP_TITLE, "Alle Werte dieser Seite auf Standard zurücksetzen?"):
            return
        c.set_tuning({})
        c.set_settings(profit_multiplier=1.0, xp_per_trip=busco.XP_PER_TRIP_MAX, respect_hours=True)
        self.shell.company_changed()
