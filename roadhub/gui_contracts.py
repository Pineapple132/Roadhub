"""Page "Contracts": fixed trips like the line jobs in ETS2, with a timetable and pay per trip."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import busco
from .busco import BusCompany, CompanyError, city_name, eur
from .gui_company import _Page
from .widgets import APP_TITLE, Dialog, fill_tree, make_tree

STATUS_LABELS = {"running": "läuft", "completed": "abgeschlossen", "cancelled": "abgebrochen"}


def clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def fmt_min(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d} h"


class ContractsPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Angebote dieser Woche", style="Head.TLabel").pack(side="left")
        ttk.Button(head, text="Annehmen …", style="Accent.TButton", command=self.accept).pack(side="right")
        wrap, self.offers = make_tree(
            self,
            [("name", "Strecke", 270, "w"), ("km", "km", 56, "e"), ("time", "Fahrzeit", 70, "e"),
             ("dep", "Abfahrt", 60, "center"), ("period", "alle", 56, "center"), ("runs", "Fahrten", 56, "center"),
             ("pay", "je Fahrt", 90, "e"), ("sum", "Summe", 100, "e")],
            height=6,
        )
        wrap.pack(fill="x", pady=(4, 10))
        head2 = ttk.Frame(self)
        head2.pack(fill="x")
        ttk.Label(head2, text="Meine Verträge", style="Head.TLabel").pack(side="left")
        ttk.Button(head2, text="Abbrechen …", command=self.cancel).pack(side="right")
        wrap2, self.mine = make_tree(
            self,
            [("name", "Strecke", 250, "w"), ("bus", "Bus", 50, "center"), ("done", "Gefahren", 70, "center"),
             ("missed", "Verpasst", 66, "center"), ("next", "Nächste Abfahrt", 140, "w"),
             ("earned", "Verdient", 100, "e"), ("state", "Status", 100, "w")],
            height=7,
        )
        wrap2.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Label(
            self, style="Muted.TLabel", wraplength=900, justify="left",
            text=(
                "Verträge sind feste Fahrten wie die Linienaufträge in ETS2: Der Bus startet zur festen Uhrzeit "
                "in seiner Garagenstadt, fährt die Haltestellen ab und kommt leer zurück. Du bekommst einen "
                f"festen Betrag je Fahrt und {int(busco.CONTRACT_BONUS * 100)} % Bonus, wenn alle Fahrten klappen. "
                "Verpasste Fahrten (kein Fahrer, Weiterbildung) kosten Ruf, ein Abbruch eine Vertragsstrafe. "
                "Angebote gibt es ab deinen Garagenstädten und wechseln jede Spielwoche."
            ),
        ).pack(fill="x")
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        offers, mine = [], []
        if c is not None:
            for o in c.contract_offers():
                offers.append((o.key, (o.name, o.total_km, fmt_min(o.total_minutes), clock(o.dep),
                                       "Tag" if o.period == 1 else f"{o.period} Tage", o.runs,
                                       eur(o.pay_per_run), eur(o.pay_per_run * o.runs))))
            for ct in sorted(c.contracts.values(), key=lambda x: (x.status != "running", -x.id))[:25]:
                nxt = (c.fmt_time(ct.departures[ct.next_idx])
                       if ct.status == "running" and ct.next_idx < len(ct.departures) else "–")
                mine.append((str(ct.id), (ct.name, f"#{ct.bus_id}", f"{ct.done} / {len(ct.departures)}", ct.missed,
                                          nxt, eur(ct.earned), STATUS_LABELS.get(ct.status, ct.status))))
        fill_tree(self.offers, offers)
        fill_tree(self.mine, mine)

    def accept(self) -> None:
        c = self.company
        sel = self.offers.selection()
        if c is None:
            return
        if not c.garages:
            messagebox.showinfo(APP_TITLE, "Bau zuerst eine Garage. Angebote gibt es ab deinen Garagenstädten.")
            return
        if not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst ein Angebot auswählen.")
            return
        offer = next((o for o in c.contract_offers() if o.key == sel[0]), None)
        if offer is None:
            return
        AcceptDialog(self, c, offer).popup()
        self.shell.company_changed()

    def cancel(self) -> None:
        c = self.company
        sel = self.mine.selection()
        if c is None or not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst einen Vertrag auswählen.")
            return
        ct = c.contracts.get(int(sel[0]))
        if ct is None or ct.status != "running":
            messagebox.showinfo(APP_TITLE, "Dieser Vertrag läuft nicht mehr.")
            return
        remaining = len(ct.departures) - ct.next_idx
        fee = round(busco.CONTRACT_CANCEL_FEE * remaining * ct.pay_per_run)
        if not messagebox.askokcancel(APP_TITLE, f"Vertrag „{ct.name}“ abbrechen?\nVertragsstrafe: {eur(fee)}, "
                                                 "außerdem sinkt dein Ruf."):
            return
        try:
            c.cancel_contract(ct.id)
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.shell.company_changed()


class AcceptDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, offer) -> None:
        super().__init__(master, "Vertrag annehmen", "Annehmen")
        self.company, self.offer = company, offer
        ttk.Label(self.body, text=offer.name, style="Head.TLabel").pack(anchor="w")
        ttk.Label(
            self.body, style="Muted.TLabel", justify="left",
            text=(f"{offer.total_km} km einfach, {fmt_min(offer.total_minutes)}, Abfahrt {clock(offer.dep)} Uhr, "
                  f"{offer.runs} Fahrten à {eur(offer.pay_per_run)}.\nDer Bus muss in {city_name(offer.start)} "
                  "stationiert sein und einen Fahrer haben."),
        ).pack(anchor="w", pady=(4, 8))
        wrap, self.tree = make_tree(
            self.body, [("bus", "Bus", 230, "w"), ("driver", "Fahrer", 140, "w"), ("now", "Gerade", 160, "w")], height=6)
        wrap.pack(fill="both", expand=True)
        rows = []
        for b in sorted(company.buses.values(), key=lambda x: x.id):
            if b.home != offer.start or b.contract_id in company.contracts:
                continue
            drv = company.drivers.get(b.driver) if b.driver else None
            rows.append((str(b.id), (f"Bus #{b.id} · {company.model(b.model).label.split(' · ')[0]}",
                                     drv.name if drv else "– kein Fahrer –", company.line_label(b))))
        fill_tree(self.tree, rows)
        if not rows:
            ttk.Label(self.body, style="Muted.TLabel",
                      text=f"Du hast keinen freien Bus in {city_name(offer.start)}.").pack(pady=6)

    def on_ok(self) -> bool:
        sel = self.tree.selection()
        if not sel:
            self.error("Bitte einen Bus auswählen.")
            return False
        try:
            self.company.accept_contract(self.offer.key, int(sel[0]))
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True
