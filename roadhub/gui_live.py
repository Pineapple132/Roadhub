"""Live trip: cockpit with the current ETS2 trip on the left and the company on the right, then the trip report."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import telemetry, theme
from .busco import eur, route_label
from .overlay import fmt_clock
from .gui_company import _Page
from .widgets import APP_TITLE, card


class LivePage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        self.report: dict | None = None
        self._loading = False

        head = ttk.Frame(self)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=14, height=14, bg=theme.BG, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=theme.MUTED, outline="")
        self.status = ttk.Label(head, text="Keine Fahrt", style="Head.TLabel")
        self.status.pack(side="left")
        self.save_lbl = ttk.Label(head, text="", style="Muted.TLabel")
        self.save_lbl.pack(side="left", padx=(18, 0))
        self.toggle_btn = ttk.Button(head, text="Letzten Fahrtbericht anzeigen", command=self._toggle)
        self.toggle_btn.pack(side="right")

        box = ttk.LabelFrame(self, text="Telemetrie", padding=(12, 8))
        box.pack(fill="x", pady=(10, 8))
        self.use_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="Echte Fahrten aus ETS2 verfolgen", variable=self.use_var,
                        command=self._changed).grid(row=0, column=0, sticky="w")
        ttk.Button(box, text="Demo-Fahrt starten", command=self._demo).grid(row=0, column=3, padx=(18, 0))
        self.overlay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="Overlay im Spiel anzeigen", variable=self.overlay_var,
                        command=self._overlay_changed).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Button(box, text="Verbindung testen", command=self._test).grid(row=1, column=3, padx=(18, 0), pady=(6, 0))
        ttk.Label(box, text="Adresse").grid(row=1, column=0, sticky="e", pady=(6, 0))
        self.url_var = tk.StringVar(value=telemetry.DEFAULT_URL)
        url = ttk.Entry(box, textvariable=self.url_var, width=52)
        url.grid(row=1, column=1, columnspan=2, sticky="w", padx=6, pady=(6, 0))
        url.bind("<FocusOut>", lambda e: self._changed())
        url.bind("<Return>", lambda e: self._changed())
        self.hint = ttk.Label(
            box, style="Muted.TLabel", wraplength=900, justify="left",
            text=("Dafür läuft der ets2-telemetry-server von Funbit (Plugin im ETS2-Ordner bin/win_x64/plugins). "
                  "Firma und ETS2 teilen sich ein Konto: Käufe in diesem Tool gehen von deinem ETS2-Geld ab, der Verdienst "
                  "deiner Fahrten ist ohnehin schon dein Geld. Beim Beenden von ETS2 wird nur die Änderung durch die "
                  "Firma in den Spielstand geschrieben. Die Telemetrie liest nur, ins laufende Spiel "
                  "wird nichts geschrieben."))
        self.hint.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.stage = ttk.Frame(self)
        self.stage.pack(fill="both", expand=True)
        self._build_live()
        self._build_report()
        self._show_live()

    # ---- Layout ---------------------------------------------------------------
    def _build_live(self) -> None:
        self.live = ttk.Frame(self.stage)
        self.live.columnconfigure(0, weight=3, uniform="c")
        self.live.columnconfigure(1, weight=2, uniform="c")
        left = ttk.Frame(self.live, style="Card.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(left, text="DEINE FAHRT", style="CardCaption.TLabel").pack(anchor="w")
        self.job_var = tk.StringVar(value="Gerade kein Auftrag")
        ttk.Label(left, textvariable=self.job_var, style="CardValue.TLabel").pack(anchor="w", pady=(2, 10))
        self.bar = tk.Canvas(left, height=14, bg=theme.FIELD, highlightthickness=0)
        self.bar.pack(fill="x")
        self.bar.bind("<Configure>", lambda e: self._draw_bar())
        ends = ttk.Frame(left, style="Card.TFrame")
        ends.pack(fill="x", pady=(4, 12))
        self.from_var, self.km_var, self.to_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(ends, textvariable=self.from_var, style="CardCaption.TLabel").pack(side="left")
        ttk.Label(ends, textvariable=self.to_var, style="CardCaption.TLabel").pack(side="right")
        ttk.Label(ends, textvariable=self.km_var, style="CardCaption.TLabel").pack()
        row = ttk.Frame(left, style="Card.TFrame")
        row.pack(fill="x")
        self.v: dict[str, tk.StringVar] = {}
        for i, (key, cap) in enumerate((("speed", "TEMPO"), ("eta", "NOCH"), ("time", "ANKUNFT"),
                                        ("income", "AUFTRAG"))):
            c, var = card(row, cap, key == "income")
            c.grid(row=0, column=i, sticky="nsew", padx=(0, 8))
            row.columnconfigure(i, weight=1, uniform="m")
            self.v[key] = var
        self._progress = 0.0
        foot = ttk.Frame(left, style="Card.TFrame")
        foot.pack(fill="x", pady=(12, 0))
        self.eta_note = ttk.Label(foot, text="", style="Card.TLabel")
        self.eta_note.pack(side="left")
        self.end_btn = ttk.Button(foot, text="Fahrt beenden …", command=self.shell.end_trip_manually)
        self.end_btn.pack(side="right")

        right = ttk.Frame(self.live, style="Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="DEINE BUSFIRMA, LIVE", style="CardCaption.TLabel").pack(anchor="w")
        self.firm_var = tk.StringVar(value="+ 0 €")
        ttk.Label(right, textvariable=self.firm_var, style="CardAccent.TLabel").pack(anchor="w", pady=(2, 8))
        self.f: dict[str, tk.StringVar] = {}
        for key, cap in (("buses", "Busse unterwegs"), ("pax", "Fahrgäste seit Start"),
                         ("trips", "Fahrten seit Start"), ("contract", "Verträge"), ("rep", "Ruf"),
                         ("share", "Verdienst aufs Konto")):
            line = ttk.Frame(right, style="Card.TFrame")
            line.pack(fill="x", pady=2)
            ttk.Label(line, text=cap, style="CardCaption.TLabel").pack(side="left")
            var = tk.StringVar(value="–")
            ttk.Label(line, textvariable=var, style="Card.TLabel").pack(side="right")
            self.f[key] = var

    def _build_report(self) -> None:
        self.rep = ttk.Frame(self.stage, style="Card.TFrame", padding=16)
        self.rep_title = tk.StringVar(value="Noch keine Fahrt abgeliefert")
        ttk.Label(self.rep, textvariable=self.rep_title, style="CardValue.TLabel").pack(anchor="w")
        self.rep_sub = tk.StringVar()
        ttk.Label(self.rep, textvariable=self.rep_sub, style="CardCaption.TLabel").pack(anchor="w", pady=(0, 10))
        self.rep_rows = ttk.Frame(self.rep, style="Card.TFrame")
        self.rep_rows.pack(fill="x")
        self.rep_btn = ttk.Button(self.rep, text="Weiter", style="Accent.TButton", command=self._show_live)
        self.rep_btn.pack(anchor="e", pady=(14, 0))

    # ---- Settings --------------------------------------------------------
    def refresh(self) -> None:
        c = self.company
        self._loading = True
        if c is not None:
            self.use_var.set(c.settings.use_telemetry)
            self.url_var.set(c.settings.telemetry_url)
            self.overlay_var.set(c.settings.overlay_on)
        self._loading = False

    def _changed(self) -> None:
        c = self.company
        if c is None or self._loading:
            return
        try:
            c.set_settings(use_telemetry=self.use_var.get(),
                           telemetry_url=self.url_var.get(),
                           follow_game=True if self.use_var.get() else None)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(exc))
            self.refresh()
            return
        self.shell.save_company()
        self.shell.overview.refresh()

    def _overlay_changed(self) -> None:
        c = self.company
        if c is None or self._loading:
            return
        c.settings.overlay_on = bool(self.overlay_var.get())
        self.shell.save_company()
        self.shell.sync_overlay()

    def _test(self) -> None:
        try:
            snap = telemetry.fetch(self.url_var.get().strip() or telemetry.DEFAULT_URL)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Der Telemetrie-Server antwortet nicht:\n{telemetry.describe_error(exc)}\n\n"
                                 "Läuft Ets2Telemetry.exe, und stimmt die Adresse?")
            return
        if snap.connected:
            messagebox.showinfo(APP_TITLE, "Verbunden: Der Server meldet, dass ETS2 läuft."
                                + (f"\nAuftrag: {snap.source} nach {snap.dest}, {snap.income} €." if snap.has_job else ""))
        else:
            messagebox.showinfo(APP_TITLE, "Der Server antwortet, meldet aber, dass ETS2 nicht verbunden ist. "
                                "Das Plugin im Spiel ist dann nicht geladen (siehe README).")

    def _demo(self) -> None:
        if self.company is None:
            messagebox.showinfo(APP_TITLE, "Lege zuerst eine Busfirma an.")
            return
        if self.shell.tracker.active:
            return
        self.shell.telemetry.start_demo()
        self._show_live()

    # ---- Display --------------------------------------------------------------
    def _show_live(self) -> None:
        self.rep.pack_forget()
        self.live.pack(fill="both", expand=True)
        self.toggle_btn.config(text="Letzten Fahrtbericht anzeigen")

    def _show_report(self, report: dict | None = None) -> None:
        report = report or (self.company.trip_log[-1] if self.company and self.company.trip_log else None)
        if report is None:
            messagebox.showinfo(APP_TITLE, "Es wurde noch keine Fahrt abgeliefert.")
            return
        self.live.pack_forget()
        self.rep.pack(fill="x", anchor="n")
        self.toggle_btn.config(text="Zurück zur Fahrt")
        self.rep_title.set("Fahrt abgeliefert: " + route_label(report["source"], report["dest"], report.get("vehicle", "")))
        self.rep_sub.set(f"{report['cargo'] or 'Fracht'} · {report['km']} km · "
                         f"Firmen-Fahrten in der Zeit: {report['trips']} · Fahrgäste: {report['pax']} · "
                         f"Bus-XP: + {report['xp']}")
        for w in self.rep_rows.winfo_children():
            w.destroy()
        rows = [
            ("Auftrag (laut Spiel, schon auf deinem Konto)", eur(report["income"]), False),
            ("Firma hat verdient", "+ " + eur(report["revenue"]), False),
            ("Firma hat ausgegeben", "- " + eur(report["costs"]), False),
            ("Firma: Ergebnis dieser Fahrt", ("+ " if report["profit"] >= 0 else "- ") + eur(abs(report["profit"])), True),
            ("Konto jetzt (geschätzt)", eur(report["cash_after"]), True),
        ]
        for i, (a, b, bold) in enumerate(rows):
            style = "CardValue.TLabel" if bold else "Card.TLabel"
            ttk.Label(self.rep_rows, text=a, style=style).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Label(self.rep_rows, text=b, style=style).grid(row=i, column=1, sticky="e", padx=(40, 0))
        self.rep_rows.columnconfigure(0, weight=1)

    def _toggle(self) -> None:
        if self.rep.winfo_ismapped():
            self._show_live()
        else:
            self._show_report()

    def _draw_bar(self) -> None:
        self.bar.delete("all")
        w = max(self.bar.winfo_width(), 10)
        self.bar.create_rectangle(0, 0, w * self._progress, 14, fill=theme.ACCENT, outline="")

    def show(self, snap: telemetry.Snapshot, tracker: telemetry.TripTracker, demo: bool) -> None:
        c = self.company
        mtime = self.shell.last_save_mtime
        if mtime:
            minutes = max(0, int((time.time() - mtime) // 60))
            self.save_lbl.config(text=f"Letzter Save: vor {minutes} Min ({time.strftime('%H:%M', time.localtime(mtime))})")
        if not snap.connected:
            err = self.shell.telemetry.error
            color = theme.MUTED
            text = ("Nicht mit ETS2 verbunden" + (f" ({err})" if err else " (Server meldet: Spiel nicht verbunden)")
                    if self.use_var.get() else "Telemetrie aus")
        elif tracker.active:
            color, text = theme.ACCENT, "Fahrt läuft" + (" (Demo)" if demo else "")
        else:
            color, text = "#5fb760", "Verbunden, kein Auftrag" + (" (Demo)" if demo else "")
        self.dot.itemconfig(self.dot_id, fill=color)
        self.status.config(text=text)
        if tracker.active:
            self.job_var.set(route_label(tracker.source, tracker.dest, tracker.vehicle)
                             + (f" · {tracker.cargo}" if tracker.cargo else ""))
            self._progress = tracker.progress
            self.from_var.set(tracker.source or "Start")
            self.to_var.set(tracker.dest or "Ziel")
            self.km_var.set(f"{max(0, (tracker.total_m - tracker.left_m) / 1000):.0f} von {tracker.km_total:.0f} km")
            self.v["speed"].set(f"{snap.speed_kmh:.0f} km/h")
            self.v["eta"].set(f"{tracker.left_m / 1000:.0f} km")
            real = tracker.real_eta_s
            self.v["time"].set(fmt_clock(real).replace(" Uhr", "") if real else "–")
            self.eta_note.config(text=f"Ankunft in {int(round(real / 60))} Min (Echtzeit)" if real else
                                 "Ankunftszeit unbekannt: die Telemetrie liefert keine Fahrzeit")
            self.v["income"].set(eur(tracker.income))
        else:
            self.job_var.set("Gerade kein Auftrag")
            self._progress = 0.0
            self.from_var.set("")
            self.to_var.set("")
            self.km_var.set("")
            for key in self.v:
                self.v[key].set("–")
            self.eta_note.config(text="")
        self.end_btn.config(state="normal" if tracker.active else "disabled")
        self._draw_bar()
        if c is None:
            return
        d = c.trip_delta()
        self.firm_var.set(("+ " if d["revenue"] - d["costs"] >= 0 else "- ") + eur(abs(d["revenue"] - d["costs"])))
        self.f["buses"].set(f"{c.active_buses()} von {len(c.buses)}")
        self.f["pax"].set(busco_num(d["pax"]))
        self.f["trips"].set(str(d["trips"]))
        active = [k for k in c.contracts.values() if k.status == "running"]
        self.f["contract"].set(f"{len(active)} laufend" if active else "keine")
        self.f["rep"].set(f"{c.reputation * 100:.0f} %")
        self.f["share"].set("+ " + eur(tracker.income) if tracker.active else "–")

    def delivered(self, report: dict) -> None:
        self._show_report(report)


def busco_num(n) -> str:
    from .busco import num
    return num(n)
