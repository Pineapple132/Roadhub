"""Seite „Bus-Aufträge“: Linienangebote an den Haltestellen im Save bearbeiten."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import buslines, editor, mapdata, sii  # noqa: F401  (mapdata registriert die Sehenswürdigkeits-Namen)
from .buslines import Leg, LineSpec, MAX_TARGETS, pretty_stop, stop_label
from .widgets import APP_TITLE, Dialog, fill_tree, make_tree

TYPE_LABELS = {"regular": "Linie (regular)", "tourist": "Touristik (tourist)"}
TYPE_SHORT = {"regular": "Linie", "tourist": "Touristik"}


def fmt_minutes(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d} h"


def fmt_clock(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def parse_clock(text: str) -> int:
    text = text.strip().replace(".", ":")
    try:
        if ":" in text:
            h, m = text.split(":", 1)
            hours, minutes = int(h), int(m)
        else:
            hours, minutes = int(text), 0
    except ValueError:
        raise sii.SiiError("Die Abfahrtszeit bitte als HH:MM eingeben, z. B. 08:30.") from None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise sii.SiiError("Die Abfahrtszeit muss zwischen 00:00 und 23:59 liegen.")
    return hours * 60 + minutes


class BusLinesPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, app) -> None:
        super().__init__(parent, padding=12)
        self.app = app
        self._cache: list[buslines.LineOffer] | None = None

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(bar, textvariable=self.filter_var, width=28).pack(side="left", padx=8)
        self.show_empty = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="leere Slots anzeigen", variable=self.show_empty,
                        command=self.refresh).pack(side="left", padx=10)
        self.edit_btn = ttk.Button(bar, text="Linie bearbeiten …", style="Accent.TButton",
                                   command=self.edit, state="disabled")
        self.edit_btn.pack(side="right")

        wrap, self.tree = make_tree(
            self,
            [("start", "Start", 150, "w"), ("slot", "Slot", 44, "center"), ("typ", "Typ", 80, "w"),
             ("route", "Strecke", 300, "w"), ("bus", "Bus", 130, "w"), ("km", "km", 60, "e"),
             ("dauer", "Fahrzeit", 80, "e"), ("ab", "Abfahrt", 60, "center"), ("rest", "läuft ab (h)", 90, "e")],
            height=16,
        )
        wrap.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_btn())
        ttk.Label(
            self,
            style="Muted.TLabel",
            wraplength=940,
            justify="left",
            text=(
                "Du überschreibst einen vorhandenen Linien-Slot einer Haltestelle: Strecke mit bis zu "
                f"{MAX_TARGETS} Zielen, Busmodell, Abfahrtszeit und Gültigkeit. Kilometer und Fahrzeit "
                "werden aus bekannten Etappen deines Saves vorbelegt, sonst geschätzt."
            ),
        ).pack(fill="x")

    # ---- Daten ------------------------------------------------------------
    def offers(self) -> list[buslines.LineOffer]:
        if self.app.doc is None:
            return []
        if self._cache is None:
            self._cache = buslines.list_line_offers(self.app.doc)
        return self._cache

    def invalidate(self) -> None:
        self._cache = None

    def refresh(self) -> None:
        doc = self.app.doc
        rows = []
        if doc is not None:
            try:
                now = editor.game_time(doc)
            except sii.SiiError:
                now = 0
            needle = self.filter_var.get().strip().lower()
            for o in self.offers():
                if o.is_empty and not self.show_empty.get():
                    continue
                exp = editor._safe_int(o.expiration)
                if o.is_empty:
                    values = (o.start_name and pretty_stop(o.start_name), o.slot, "", "(leer)", "", "", "", "", "")
                else:
                    route = " – ".join([pretty_stop(o.start_name)] + [pretty_stop(t) for t in o.targets])
                    values = (pretty_stop(o.start_name), o.slot, TYPE_SHORT.get(o.line_type, o.line_type), route,
                              o.bus_name, o.total_km, fmt_minutes(o.total_minutes), fmt_clock(o.departure),
                              round((exp - now) / 60, 1) if exp else "")
                if needle and needle not in " ".join(str(v) for v in values).lower():
                    continue
                rows.append((f"{o.stop_unit}|{o.slot}", values))
        fill_tree(self.tree, rows)
        self._update_btn()

    def _update_btn(self) -> None:
        self.edit_btn.config(state="normal" if self.tree.selection() else "disabled")

    def edit(self) -> None:
        sel = self.tree.selection()
        if not sel or self.app.doc is None:
            return
        unit, slot = sel[0].rsplit("|", 1)
        for o in self.offers():
            if o.stop_unit == unit and o.slot == int(slot):
                if LineDialog(self, self.app, o).run():
                    self.invalidate()
                    self.app.lines_applied()
                return


class LineDialog(Dialog):
    def __init__(self, master: tk.Misc, app, offer: buslines.LineOffer) -> None:
        super().__init__(master, "Linie bearbeiten", "Übernehmen")
        self.app, self.offer = app, offer
        self.saved = False
        doc = app.doc
        all_offers = master.offers()  # type: ignore[attr-defined]
        self.known = buslines.known_legs(all_offers)
        self.stop_keys = buslines.list_stop_targets(doc)
        self.stop_names = {pretty_stop(k): k for k in self.stop_keys}
        self.start_key = stop_label(offer.stop_unit)
        models = buslines.list_bus_models(all_offers)

        b = self.body
        ttk.Label(b, text=f"Start: {pretty_stop(self.start_key)}   ·   Slot {offer.slot}",
                  style="Head.TLabel").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))

        ttk.Label(b, text="Typ").grid(row=1, column=0, sticky="w", pady=4)
        self.type_box = ttk.Combobox(b, state="readonly", width=22, values=list(TYPE_LABELS.values()))
        self.type_box.set(TYPE_LABELS.get(offer.line_type, TYPE_LABELS["regular"]))
        self.type_box.grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(b, text="Busmodell").grid(row=1, column=2, sticky="w", padx=(18, 0))
        self.model_var = tk.StringVar(value=offer.bus_name if not offer.is_empty else (models[0] if models else ""))
        ttk.Combobox(b, textvariable=self.model_var, values=models, width=28).grid(
            row=1, column=3, columnspan=3, sticky="w", padx=8)

        ttk.Label(b, text="Abfahrt (HH:MM)").grid(row=2, column=0, sticky="w", pady=4)
        self.dep_var = tk.StringVar(value=fmt_clock(offer.departure if not offer.is_empty else 480))
        ttk.Entry(b, textvariable=self.dep_var, width=8).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(b, text="Gültig (Stunden)").grid(row=2, column=2, sticky="w", padx=(18, 0))
        self.hours_var = tk.StringVar(value=str(self._current_hours()))
        ttk.Spinbox(b, from_=1, to=720, width=7, textvariable=self.hours_var).grid(row=2, column=3, sticky="w", padx=8)

        ttk.Separator(b).grid(row=3, column=0, columnspan=6, sticky="we", pady=10)
        for col, text in enumerate(["Halt", "Ziel", "", "km", "Minuten", ""], start=0):
            if text:
                ttk.Label(b, text=text, style="Muted.TLabel").grid(row=4, column=col, sticky="w", padx=4)

        self.rows: list[dict] = []
        prefill = [] if offer.is_empty else list(zip(offer.targets, offer.legs))
        for i in range(MAX_TARGETS):
            r = 5 + i
            ttk.Label(b, text=f"{i + 1}.").grid(row=r, column=0, sticky="w", pady=3)
            target_var = tk.StringVar()
            combo = ttk.Combobox(b, textvariable=target_var, values=sorted(self.stop_names), width=30)
            combo.grid(row=r, column=1, columnspan=2, sticky="w", padx=4)
            km_var, min_var = tk.StringVar(), tk.StringVar()
            ttk.Entry(b, textvariable=km_var, width=7).grid(row=r, column=3, sticky="w", padx=4)
            ttk.Entry(b, textvariable=min_var, width=8).grid(row=r, column=4, sticky="w", padx=4)
            note = ttk.Label(b, text="", style="Muted.TLabel")
            note.grid(row=r, column=5, sticky="w", padx=4)
            row = {"target": target_var, "km": km_var, "min": min_var, "note": note, "leg": None, "combo": combo}
            self.rows.append(row)
            if i < len(prefill):
                key, leg = prefill[i]
                target_var.set(pretty_stop(key))
                km_var.set(str(leg.km))
                min_var.set(str(leg.minutes))
                row["leg"] = leg
            combo.bind("<<ComboboxSelected>>", lambda e, i=i: self._target_picked(i))
            combo.bind("<FocusOut>", lambda e, i=i: self._target_picked(i, soft=True))
            combo.bind("<KeyRelease>", lambda e, i=i: self._filter_combo(e, i))
            km_var.trace_add("write", lambda *_, i=i: self._km_changed(i))

        bar = ttk.Frame(b)
        bar.grid(row=5 + MAX_TARGETS, column=0, columnspan=6, sticky="we", pady=(10, 0))
        ttk.Button(bar, text="Zeile leeren", style="Small.TButton", command=self._clear_last).pack(side="left")
        self.summary = ttk.Label(bar, text="", style="Muted.TLabel")
        self.summary.pack(side="right")
        ttk.Label(
            b, style="Muted.TLabel", wraplength=640, justify="left",
            text=("Leere Zeilen am Ende werden ignoriert. Bei bekannten Etappen kommen km und Minuten aus dem "
                  "Save, bei neuen Etappen trägst du die Kilometer ein und die Minuten werden geschätzt."),
        ).grid(row=6 + MAX_TARGETS, column=0, columnspan=6, sticky="w", pady=(8, 0))
        self._summarize()

    # ---- Hilfen -------------------------------------------------------------
    def _current_hours(self) -> int:
        if self.offer.is_empty:
            return 24
        try:
            now = editor.game_time(self.app.doc)
            exp = editor._safe_int(self.offer.expiration)
            return max(1, min(720, round((exp - now) / 60))) if exp else 24
        except sii.SiiError:
            return 24

    def _previous(self, index: int) -> str:
        for j in range(index - 1, -1, -1):
            key = self.stop_names.get(self.rows[j]["target"].get().strip())
            if key:
                return key
        return self.start_key

    def _filter_combo(self, event, index: int) -> None:
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        row = self.rows[index]
        typed = row["target"].get().strip().lower()
        names = sorted(self.stop_names)
        row["combo"]["values"] = [n for n in names if typed in n.lower()] if typed else names

    def _target_picked(self, index: int, soft: bool = False) -> None:
        row = self.rows[index]
        key = self.stop_names.get(row["target"].get().strip())
        if key is None:
            row["leg"] = None
            row["note"].config(text="")
            self._summarize()
            return
        prev = self._previous(index)
        leg = self.known.get((prev, key)) or self.known.get((key, prev))
        if leg is not None:
            if row["leg"] is leg and soft:
                return
            row["leg"] = leg
            row["km"].set(str(leg.km))
            row["min"].set(str(leg.minutes))
            row["note"].config(text="aus Save")
        else:
            row["leg"] = None
            row["note"].config(text="geschätzt")
            if not row["km"].get().strip():
                row["km"].set("100")
            self._km_changed(index)
        self._summarize()

    def _km_changed(self, index: int) -> None:
        row = self.rows[index]
        if row["note"].cget("text") != "geschätzt":
            return
        try:
            km = int(row["km"].get())
        except ValueError:
            return
        if km > 0:
            row["min"].set(str(buslines.estimate_leg(km, self.known).minutes))
        self._summarize()

    def _clear_last(self) -> None:
        for row in reversed(self.rows):
            if row["target"].get().strip():
                row["target"].set("")
                row["km"].set("")
                row["min"].set("")
                row["note"].config(text="")
                row["leg"] = None
                break
        self._summarize()

    def _summarize(self) -> None:
        km = minutes = 0
        for row in self.rows:
            if row["target"].get().strip():
                try:
                    km += int(row["km"].get())
                    minutes += int(row["min"].get())
                except ValueError:
                    pass
        self.summary.config(text=f"Gesamt: {km} km, {fmt_minutes(minutes)}")

    def _collect(self) -> LineSpec:
        targets: list[str] = []
        legs: list[Leg] = []
        previous = self.start_key
        for i, row in enumerate(self.rows):
            text = row["target"].get().strip()
            if not text:
                if any(r["target"].get().strip() for r in self.rows[i + 1:]):
                    raise sii.SiiError("Zwischen den Zielen darf keine leere Zeile sein.")
                continue
            key = self.stop_names.get(text)
            if key is None:
                raise sii.SiiError(f"„{text}“ ist keine Haltestelle aus deinem Save. Bitte aus der Liste wählen.")
            try:
                km, minutes = int(row["km"].get()), int(row["min"].get())
            except ValueError:
                raise sii.SiiError(f"Bitte km und Minuten für {text} als ganze Zahlen eintragen.") from None
            template = row["leg"] or buslines.estimate_leg(km, self.known)
            ratio = template.base_minutes / template.minutes if template.minutes else 0.8
            legs.append(Leg(km, minutes, max(1, round(minutes * ratio)), template.ferry_minutes if row["leg"] else 0))
            targets.append(key)
            previous = key
        if not targets:
            raise sii.SiiError("Bitte mindestens ein Ziel eintragen.")
        line_type = next((k for k, v in TYPE_LABELS.items() if v == self.type_box.get()), "regular")
        try:
            hours = int(self.hours_var.get())
        except ValueError:
            raise sii.SiiError("Die Gültigkeit bitte als ganze Stunden eintragen.") from None
        return LineSpec(self.offer.stop_unit, self.offer.slot, line_type, targets, legs,
                        self.model_var.get().strip(), parse_clock(self.dep_var.get()), hours)

    def on_ok(self) -> bool:
        try:
            buslines.apply_line(self.app.doc, self._collect())
        except sii.SiiError as exc:
            self.error(str(exc))
            return False
        self.saved = True
        return True

    def run(self) -> bool:
        self.popup()
        return self.saved
