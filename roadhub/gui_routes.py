"""Page "Own routes": create your own lines and excursion trips."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import mapdata
from .busco import MAX_ROUTE_STOPS, BusCompany, CompanyError, city_name
from .gui_company import _Page
from .widgets import APP_TITLE, Dialog, fill_tree, make_tree

KINDS = {"Linie (Städte)": "line", "Ausflug (Sehenswürdigkeiten)": "excursion"}


def fmt_min(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d} h"


class RoutesPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Neue Route …", style="Accent.TButton", command=self.new).pack(side="left")
        ttk.Button(top, text="Löschen", command=self.delete).pack(side="right")
        wrap, self.tree = make_tree(
            self,
            [("name", "Name", 170, "w"), ("kind", "Art", 80, "w"), ("route", "Strecke", 380, "w"),
             ("km", "km (einfach)", 90, "e"), ("time", "Fahrzeit", 80, "e"), ("buses", "Busse", 56, "center")],
            height=12,
        )
        wrap.pack(fill="both", expand=True, pady=10)
        ttk.Label(
            self, style="Muted.TLabel", wraplength=900, justify="left",
            text=(
                "Eigene Routen bestehen aus 2 bis 6 Haltestellen, die erste ist die Garagenstadt. Der Bus pendelt "
                "auf der Strecke hin und zurück. Bei Ausflugsfahrten sind Sehenswürdigkeiten dabei, sie zahlen "
                "mehr pro Fahrgast, vor allem am Wochenende. Zugewiesen wird die Route auf der Seite „Busse“ "
                "(Linie zuweisen). Kilometer und Fahrzeit kommen aus bekannten Strecken in deinem Save, sonst aus "
                "der Luftlinie geschätzt; du kannst sie im Dialog ändern."
            ),
        ).pack(fill="x")
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        rows = []
        if c is not None:
            for r in sorted(c.routes.values(), key=lambda x: x.id):
                km = mins = 0
                for x, y in zip(r.stops, r.stops[1:]):
                    leg = c.catalog.routes.get((x, y))
                    if leg:
                        km, mins = km + leg[0], mins + leg[1]
                used = sum(1 for b in c.buses.values() if b.route_id == r.id)
                rows.append((str(r.id), (r.name, "Ausflug" if r.kind == "excursion" else "Linie",
                                         " – ".join(city_name(s) for s in r.stops), km, fmt_min(mins), used)))
        fill_tree(self.tree, rows)

    def new(self) -> None:
        c = self.company
        if c is None:
            return
        if not c.garages:
            messagebox.showinfo(APP_TITLE, "Bau zuerst eine Garage, in deren Stadt die Route beginnt.")
            return
        RouteDialog(self, c).popup()
        self.shell.company_changed()

    def delete(self) -> None:
        c = self.company
        sel = self.tree.selection()
        if c is None or not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst eine Route auswählen.")
            return
        try:
            c.delete_route(int(sel[0]))
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.shell.company_changed()


class RouteDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, preset_start: str | None = None,
                 preset_stop: str | None = None) -> None:
        super().__init__(master, "Neue Route", "Anlegen")
        self.company = company
        cities = set(company.catalog.cities()) | set(mapdata.CITY_COORDS)
        sights = set(company.catalog.sights()) | set(mapdata.SIGHT_COORDS)
        self.keys = {city_name(k): k for k in sorted(cities | sights)}
        self.names = sorted(self.keys)
        self.starts = {city_name(k): k for k in sorted(company.garages)}
        b = self.body
        ttk.Label(b, text="Name").grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar()
        ttk.Entry(b, textvariable=self.name_var, width=34).grid(row=0, column=1, columnspan=3, sticky="w", padx=8)
        ttk.Label(b, text="Art").grid(row=1, column=0, sticky="w", pady=4)
        self.kind = ttk.Combobox(b, state="readonly", width=32, values=list(KINDS))
        self.kind.current(0)
        self.kind.grid(row=1, column=1, columnspan=3, sticky="w", padx=8)
        ttk.Label(b, text="Start (Garage)").grid(row=2, column=0, sticky="w", pady=4)
        self.start = ttk.Combobox(b, state="readonly", width=32, values=list(self.starts))
        self.start.grid(row=2, column=1, columnspan=3, sticky="w", padx=8)
        first = next((n for n, k in self.starts.items() if k == preset_start), next(iter(self.starts)))
        self.start.set(first)
        self.start.bind("<<ComboboxSelected>>", lambda e: self._restart())

        ttk.Separator(b).grid(row=3, column=0, columnspan=5, sticky="we", pady=8)
        for col, text in ((1, "Haltestelle"), (2, "km"), (3, "Minuten")):
            ttk.Label(b, text=text, style="Muted.TLabel").grid(row=4, column=col, sticky="w", padx=8)
        self.rows: list[dict] = []
        for i in range(MAX_ROUTE_STOPS - 1):
            r = 5 + i
            ttk.Label(b, text=f"{i + 2}.").grid(row=r, column=0, sticky="w", pady=3)
            var, km, mins = tk.StringVar(), tk.StringVar(), tk.StringVar()
            combo = ttk.Combobox(b, textvariable=var, values=self.names, width=32)
            combo.grid(row=r, column=1, sticky="w", padx=8)
            ttk.Entry(b, textvariable=km, width=7).grid(row=r, column=2, sticky="w", padx=8)
            ttk.Entry(b, textvariable=mins, width=8).grid(row=r, column=3, sticky="w", padx=8)
            note = ttk.Label(b, text="", style="Muted.TLabel")
            note.grid(row=r, column=4, sticky="w")
            row = {"var": var, "km": km, "min": mins, "note": note, "combo": combo, "auto": ""}
            self.rows.append(row)
            combo.bind("<<ComboboxSelected>>", lambda e, i=i: self._picked(i))
            combo.bind("<FocusOut>", lambda e, i=i: self._picked(i, soft=True))
            combo.bind("<KeyRelease>", lambda e, i=i: self._filter(e, i))
            km.trace_add("write", lambda *_: self._summarize())
            mins.trace_add("write", lambda *_: self._summarize())
        self.summary = ttk.Label(b, text="", style="Muted.TLabel")
        self.summary.grid(row=5 + MAX_ROUTE_STOPS, column=0, columnspan=5, sticky="w", pady=(10, 0))
        if preset_stop and preset_stop in self.keys.values():
            self.rows[0]["var"].set(city_name(preset_stop))
            if preset_stop.startswith("viewpoints."):
                self.kind.current(1)
            self._picked(0)
            self.name_var.set(f"Ausflug {city_name(preset_stop).replace('Aussicht: ', '')}"
                              if preset_stop.startswith("viewpoints.") else "")
        ttk.Label(
            b, style="Muted.TLabel", wraplength=620, justify="left",
            text=("Der Bus fährt Start, Halt 2, Halt 3 … und wieder zurück. Tipp: Für eine Ausflugsfahrt nimm als "
                  "Halt eine Sehenswürdigkeit (zu erkennen an „Aussicht:“). Leere Zeilen am Ende zählen nicht."),
        ).grid(row=6 + MAX_ROUTE_STOPS, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def _restart(self) -> None:
        for i in range(len(self.rows)):
            if self.rows[i]["var"].get().strip():
                self._picked(i)

    def _filter(self, event, index: int) -> None:
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        typed = self.rows[index]["var"].get().strip().lower()
        values = [n for n in self.names if typed in n.lower()] if typed else self.names
        if self.kind.get().startswith("Ausflug"):
            values = sorted(values, key=lambda n: not n.startswith("Aussicht"))
        self.rows[index]["combo"]["values"] = values

    def _previous(self, index: int) -> str | None:
        for j in range(index - 1, -1, -1):
            key = self.keys.get(self.rows[j]["var"].get().strip())
            if key:
                return key
        return self.starts.get(self.start.get())

    def _picked(self, index: int, soft: bool = False) -> None:
        row = self.rows[index]
        key = self.keys.get(row["var"].get().strip())
        prev = self._previous(index)
        if key is None or prev is None:
            row["note"].config(text="")
            return
        if soft and row["auto"] == f"{prev}>{key}":
            return
        try:
            km, minutes = self.company.catalog.estimate_leg(prev, key)
            known = (prev, key) in self.company.catalog.routes
            row["km"].set(str(km))
            row["min"].set(str(minutes))
            row["note"].config(text="bekannt" if known else "geschätzt")
        except CompanyError:
            row["note"].config(text="bitte selbst eintragen")
        row["auto"] = f"{prev}>{key}"

    def _summarize(self) -> None:
        km = mins = 0
        for row in self.rows:
            if row["var"].get().strip():
                try:
                    km += int(row["km"].get())
                    mins += int(row["min"].get())
                except ValueError:
                    pass
        self.summary.config(text=f"Einfache Strecke: {km} km, {fmt_min(mins)}")

    def on_ok(self) -> bool:
        start = self.starts.get(self.start.get())
        if start is None:
            self.error("Bitte eine Start-Garage wählen.")
            return False
        stops, legs = [start], []
        for i, row in enumerate(self.rows):
            text = row["var"].get().strip()
            if not text:
                if any(r["var"].get().strip() for r in self.rows[i + 1:]):
                    self.error("Zwischen den Haltestellen darf keine leere Zeile sein.")
                    return False
                continue
            key = self.keys.get(text)
            if key is None:
                self.error(f"„{text}“ kenne ich nicht. Bitte aus der Liste wählen.")
                return False
            try:
                legs.append((int(row["km"].get()), int(row["min"].get())))
            except ValueError:
                self.error(f"Bitte km und Minuten für {text} als ganze Zahlen eintragen.")
                return False
            stops.append(key)
        try:
            self.company.create_route(self.name_var.get(), stops, KINDS[self.kind.get()], legs)
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True
