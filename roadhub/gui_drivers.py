"""Seite „Fahrer“: einstellen, weiterbilden, Bussen zuweisen."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import busco
from .busco import SKILLS, BusCompany, CompanyError, Driver, city_name, eur
from .gui_company import _Page
from .widgets import APP_TITLE, Dialog, fill_tree, make_tree


def bar(level: int) -> str:
    return f"{level} / {busco.MAX_SKILL}"


class DriversPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Fahrer einstellen …", style="Accent.TButton", command=self.hire).pack(side="left")
        ttk.Button(top, text="Weiterbilden …", command=self.train).pack(side="left", padx=8)
        ttk.Button(top, text="Bus zuweisen …", command=self.assign).pack(side="left")
        ttk.Button(top, text="Entlassen", command=self.fire).pack(side="right")
        wrap, self.tree = make_tree(
            self,
            [("id", "Nr.", 36, "center"), ("name", "Name", 135, "w"), ("rank", "Rang", 70, "w"),
             ("bus", "Bus", 46, "center"), ("eco", "Öko", 56, "center"), ("punctual", "Pünktlich", 76, "center"),
             ("service", "Service", 62, "center"), ("safety", "Sicherheit", 78, "center"),
             ("km", "km", 64, "e"), ("wage", "Lohn / h", 78, "e"), ("state", "Status", 180, "w")],
            height=11,
        )
        wrap.pack(fill="both", expand=True, pady=10)
        ttk.Label(
            self, style="Muted.TLabel", wraplength=900, justify="left",
            text=(
                "Öko-Fahrweise spart Diesel, Pünktlichkeit verkürzt Fahrten und verringert Verspätungen, "
                "Fahrgast-Service füllt die Busse besser und Sicherheit schont den Bus und verhindert Pannen. "
                f"Jede Stufe (bis {busco.MAX_SKILL}) macht den Fahrer teurer. Während einer Weiterbildung "
                "steht sein Bus. Neue Bewerber gibt es jede Spielwoche."
            ),
        ).pack(fill="x")
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        rows = []
        if c is not None:
            for d in sorted(c.drivers.values(), key=lambda x: x.id):
                if d.training:
                    left = max(0, d.training_until - c.now)
                    state = f"Schulung: {SKILLS[d.training]} ({left // busco.DAY + (1 if left % busco.DAY else 0)} T.)"
                elif d.bus_id is None:
                    state = "frei"
                else:
                    state = "im Einsatz"
                rows.append((str(d.id), (d.id, d.name, d.rank, f"#{d.bus_id}" if d.bus_id else "–",
                                         bar(d.eco), bar(d.punctual), bar(d.service), bar(d.safety),
                                         busco.num(d.km), f"{d.wage:.1f}".replace(".", ",") + " €", state)))
        fill_tree(self.tree, rows)

    def _selected(self) -> Driver | None:
        c = self.company
        sel = self.tree.selection()
        if c is None or not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst einen Fahrer auswählen.")
            return None
        return c.drivers.get(int(sel[0]))

    def hire(self) -> None:
        if self.company is None:
            return
        HireDialog(self, self.company).popup()
        self.shell.company_changed()

    def train(self) -> None:
        d = self._selected()
        if d is None:
            return
        TrainDialog(self, self.company, d).popup()
        self.shell.company_changed()

    def assign(self) -> None:
        d = self._selected()
        if d is None:
            return
        AssignDriverDialog(self, self.company, driver=d).popup()
        self.shell.company_changed()

    def fire(self) -> None:
        d = self._selected()
        if d is None:
            return
        if not messagebox.askokcancel(APP_TITLE, f"{d.name} wirklich entlassen?"):
            return
        self.company.fire(d.id)
        self.shell.company_changed()


class HireDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany) -> None:
        super().__init__(master, "Fahrer einstellen", "Einstellen")
        self.company = company
        ttk.Label(self.body, style="Muted.TLabel",
                  text=f"Bewerber dieser Woche  ·  Kasse: {eur(company.cash)}").pack(anchor="w", pady=(0, 6))
        wrap, self.tree = make_tree(
            self.body,
            [("name", "Name", 160, "w"), ("eco", "Öko", 56, "center"), ("punctual", "Pünktlich", 76, "center"),
             ("service", "Service", 62, "center"), ("safety", "Sicherheit", 78, "center"),
             ("wage", "Lohn / h", 80, "e"), ("fee", "Vermittlung", 100, "e")],
            height=8,
        )
        wrap.pack(fill="both", expand=True)
        rows = []
        for c in company.candidates():
            rows.append((c.key, (c.name, bar(c.eco), bar(c.punctual), bar(c.service), bar(c.safety),
                                 f"{c.wage:.1f}".replace(".", ",") + " €", eur(c.fee))))
        fill_tree(self.tree, rows)
        if not rows:
            ttk.Label(self.body, text="Diese Woche gibt es keine Bewerber mehr.", style="Muted.TLabel").pack(pady=6)

    def on_ok(self) -> bool:
        sel = self.tree.selection()
        if not sel:
            self.error("Bitte einen Bewerber auswählen.")
            return False
        try:
            self.company.hire(sel[0])
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True


class TrainDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, driver: Driver) -> None:
        super().__init__(master, f"Weiterbildung: {driver.name}", "Anmelden")
        self.company, self.driver = company, driver
        ttk.Label(self.body, style="Muted.TLabel",
                  text=f"Dauer {busco.TRAINING_DAYS} Tage, der Bus des Fahrers steht in dieser Zeit.  ·  "
                       f"Kasse: {eur(company.cash)}").pack(anchor="w", pady=(0, 8))
        self.var = tk.StringVar()
        for key, label in SKILLS.items():
            level = getattr(driver, key)
            if level >= busco.MAX_SKILL:
                text = f"{label}   Stufe {level}   (Höchststufe)"
                state = "disabled"
            else:
                text = f"{label}   Stufe {level}  -  nächste Stufe {level + 1} für {eur(company.training_cost(driver, key))}"
                state = "normal"
            ttk.Radiobutton(self.body, text=text, value=key, variable=self.var, state=state).pack(anchor="w", pady=3)
        if driver.training:
            ttk.Label(self.body, style="Muted.TLabel",
                      text=f"Achtung: {driver.name} ist schon in einer Weiterbildung.").pack(anchor="w", pady=(8, 0))

    def on_ok(self) -> bool:
        if not self.var.get():
            self.error("Bitte einen Skill auswählen.")
            return False
        try:
            self.company.train(self.driver.id, self.var.get())
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True


class AssignDriverDialog(Dialog):
    """Entweder zu einem Bus den Fahrer wählen (bus=...) oder zu einem Fahrer den Bus (driver=...)."""

    def __init__(self, master: tk.Misc, company: BusCompany, bus=None, driver: Driver | None = None) -> None:
        title = f"Fahrer für Bus #{bus.id}" if bus is not None else f"Bus für {driver.name}"
        super().__init__(master, title, "Zuweisen")
        self.company, self.bus, self.driver = company, bus, driver
        if bus is not None:
            cols = [("name", "Fahrer", 170, "w"), ("skills", "Öko / Pünktl. / Service / Sicherh.", 200, "center"),
                    ("now", "Aktuell", 90, "center")]
            rows = [("none", ("(keiner)", "", ""))]
            for d in sorted(company.drivers.values(), key=lambda x: x.id):
                rows.append((str(d.id), (d.name, f"{d.eco} / {d.punctual} / {d.service} / {d.safety}",
                                         company.driver_bus_label(d))))
        else:
            cols = [("name", "Bus", 230, "w"), ("line", "Linie", 190, "w"), ("now", "Fahrer", 120, "w")]
            rows = [("none", ("(keiner)", "", ""))]
            for b in sorted(company.buses.values(), key=lambda x: x.id):
                line = company.line_label(b)
                current = company.drivers[b.driver].name if b.driver in company.drivers else "–"
                rows.append((str(b.id), (f"Bus #{b.id} · {company.model(b.model).label.split(' · ')[0]}", line, current)))
        wrap, self.tree = make_tree(self.body, cols, height=10)
        wrap.pack(fill="both", expand=True)
        fill_tree(self.tree, rows)

    def on_ok(self) -> bool:
        sel = self.tree.selection()
        if not sel:
            self.error("Bitte eine Zeile auswählen.")
            return False
        try:
            if self.bus is not None:
                if sel[0] == "none":
                    if self.bus.driver in self.company.drivers:
                        self.company.assign_driver(self.bus.driver, None)
                else:
                    self.company.assign_driver(int(sel[0]), self.bus.id)
            else:
                self.company.assign_driver(self.driver.id, None if sel[0] == "none" else int(sel[0]))
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True
