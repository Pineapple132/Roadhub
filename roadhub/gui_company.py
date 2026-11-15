"""Pages of the bus company: overview (fast-forward), garages and buses."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import busco, theme
from .busco import BusCompany, CompanyError, city_name, eur
from .widgets import APP_TITLE, Dialog, card, fill_tree, make_tree

SPEEDS = [
    ("1 Stunde pro Sekunde", 60),
    ("6 Stunden pro Sekunde", 360),
    ("1 Tag pro Sekunde", 1440),
    ("3 Tage pro Sekunde", 4320),
    ("7 Tage pro Sekunde", 10080),
]
GAME_SPEEDS = [
    ("wie ETS2 (1:19)", 19 / 60),
    ("1 Stunde pro Minute", 1),
    ("1 Stunde pro 20 Sekunden", 3),
    ("1 Tag pro Minute", 24),
    ("1 Tag pro 10 Sekunden", 144),
]
TICK_MS = 100


class _Page(ttk.Frame):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, padding=16)
        self.shell = shell

    @property
    def company(self) -> BusCompany | None:
        return self.shell.company

    def refresh(self) -> None:  # pragma: no cover
        pass


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------

class OverviewPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        self.running = False
        self._carry = 0.0
        self._last_save_tick = 0
        self._tick_count = 0

        # placeholder while there is no company
        self.empty = ttk.Frame(self)
        ttk.Label(self.empty, text="Noch keine Busfirma", style="Head.TLabel").pack(anchor="w")
        ttk.Label(
            self.empty,
            style="Muted.TLabel",
            wraplength=640,
            justify="left",
            text=(
                f"Eine Firma gründen kostet {eur(busco.FOUNDING_COST)} von deinem ETS2-Konto. Erst wenn du so viel "
                "Geld im Spiel hast, kannst du gründen. Strecken und Busmodelle kommen aus deinem Spielstand."
            ),
        ).pack(anchor="w", pady=(6, 12))
        name_row = ttk.Frame(self.empty)
        name_row.pack(anchor="w", pady=(0, 10))
        ttk.Label(name_row, text="Name der Firma").pack(side="left", padx=(0, 10))
        self.name_var = tk.StringVar(value="Meine Busfirma")
        ttk.Entry(name_row, textvariable=self.name_var, width=32).pack(side="left")
        self.found_info = ttk.Label(self.empty, text="", style="Muted.TLabel", wraplength=640, justify="left")
        self.found_info.pack(anchor="w", pady=(0, 12))
        self.found_btn = ttk.Button(self.empty, text=f"Firma gründen ({eur(busco.FOUNDING_COST)})",
                                    style="Accent.TButton", command=shell._create_company)
        self.found_btn.pack(anchor="w")
        ttk.Button(self.empty, text="Spielstand wählen …", command=shell.choose_save).pack(anchor="w", pady=(10, 0))

        self.main = ttk.Frame(self)
        self._build_main()
        self.refresh()

    # ---- Layout -----------------------------------------------------------
    def _build_main(self) -> None:
        m = self.main
        grid = ttk.Frame(m)
        grid.pack(fill="x")
        self.vars: dict[str, tk.StringVar] = {}
        specs = [
            ("cash", "ETS2-KONTO", True), ("time", "ZEIT", False), ("buses", "BUSSE (AKTIV / GESAMT)", False),
            ("rep", "RUF", False), ("yday", "GEWINN GESTERN", False), ("avg", "Ø GEWINN 7 TAGE", False),
            ("xp", "VERDIENTE BUS-XP", False), ("paid", "NOCH NICHT IM SPIELSTAND", False),
        ]
        for i, (key, caption, accent) in enumerate(specs):
            frame, var = card(grid, caption, accent)
            frame.grid(row=i // 4, column=i % 4, sticky="nsew", padx=(0, 8), pady=(0, 8))
            self.vars[key] = var
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="k")

        ctrl = ttk.LabelFrame(m, text="Zeitraffer", padding=(12, 8))
        ctrl.pack(fill="x", pady=(4, 0))
        self.ctrl_frame = ctrl
        self.run_btn = ttk.Button(ctrl, text="Start", style="Accent.TButton", width=9, command=self.toggle_run)
        self.run_btn.grid(row=0, column=0, padx=(0, 10))
        self.speed = ttk.Combobox(ctrl, state="readonly", width=24, values=[s[0] for s in SPEEDS])
        self.speed.current(2)
        self.speed.grid(row=0, column=1, padx=(0, 18))
        for col, (text, minutes) in enumerate([("+ 1 Tag", 1440), ("+ 7 Tage", 7 * 1440), ("+ 30 Tage", 30 * 1440)], start=2):
            ttk.Button(ctrl, text=text, command=lambda mn=minutes: self.jump(mn)).grid(row=0, column=col, padx=3)
        ttk.Separator(ctrl, orient="vertical").grid(row=0, column=5, sticky="ns", padx=14)
        ttk.Label(ctrl, text="Einnahmen-Faktor").grid(row=0, column=6, padx=(0, 6))
        self.mult_var = tk.StringVar(value="1.0")
        self.mult = ttk.Spinbox(ctrl, from_=0.1, to=5.0, increment=0.1, width=6, textvariable=self.mult_var,
                                command=self._settings_changed)
        self.mult.grid(row=0, column=7)
        self.mult.bind("<FocusOut>", lambda e: self._settings_changed())
        self.mult.bind("<Return>", lambda e: self._settings_changed())
        second = ttk.Frame(ctrl)
        second.grid(row=1, column=0, columnspan=11, sticky="w", pady=(8, 0))
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(second, text="Wartung automatisch", variable=self.auto_var,
                        command=self._settings_changed).pack(side="left")
        ttk.Label(second, text="Bus-XP pro Fahrt (max)").pack(side="left", padx=(24, 6))
        self.xp_var = tk.StringVar(value="20")
        xp_spin = ttk.Spinbox(second, from_=0, to=1000, increment=5, width=5, textvariable=self.xp_var,
                              command=self._settings_changed)
        xp_spin.pack(side="left")
        xp_spin.bind("<FocusOut>", lambda e: self._settings_changed())
        xp_spin.bind("<Return>", lambda e: self._settings_changed())

        game = ttk.LabelFrame(m, text="Mit ETS2 mitlaufen", padding=(12, 8))
        game.pack(fill="x", pady=(8, 0))
        self.game_frame = game
        self.follow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(game, text="Firma nur verdienen lassen, solange ETS2 läuft", variable=self.follow_var,
                        command=self._settings_changed).grid(row=0, column=0, sticky="w")
        ttk.Label(game, text="Tempo").grid(row=0, column=1, padx=(18, 6))
        self.game_speed = ttk.Combobox(game, state="readonly", width=24, values=[g[0] for g in GAME_SPEEDS])
        self.game_speed.current(0)
        self.game_speed.grid(row=0, column=2)
        self.game_speed.bind("<<ComboboxSelected>>", lambda e: self._settings_changed())
        self.autopay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(game, text="Beim Beenden von ETS2 die Änderungen automatisch in den neuesten Spielstand schreiben",
                        variable=self.autopay_var, command=self._settings_changed).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(game, text="Mit Spielstand abgleichen", command=lambda: self.shell.sync_account(False)).grid(
            row=1, column=3, columnspan=2, padx=(18, 0), pady=(6, 0))
        self.game_state = ttk.Label(game, text="", style="Muted.TLabel")
        self.game_state.grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))

        lower = ttk.Frame(m)
        lower.pack(fill="both", expand=True, pady=(10, 0))
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)

        chart_box = ttk.LabelFrame(lower, text="Gewinn der letzten 14 Tage", padding=8)
        chart_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.canvas = tk.Canvas(chart_box, height=170, bg=theme.PANEL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_chart())

        log_box = ttk.LabelFrame(lower, text="Ereignisse", padding=8)
        log_box.grid(row=0, column=1, sticky="nsew")
        wrap, self.log_tree = make_tree(
            log_box, [("t", "Zeit", 110, "w"), ("text", "Ereignis", 260, "w")], height=7
        )
        wrap.pack(fill="both", expand=True)

        bottom = ttk.Frame(m)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Auf ETS2 übertragen …", style="Accent.TButton",
                   command=self.shell.start_payout).pack(side="left")
        ttk.Button(bottom, text="Neue Firma …", command=self.shell.new_company).pack(side="right")

    # ---- Controls --------------------------------------------------------
    def _speed_minutes(self) -> int:
        return SPEEDS[max(0, self.speed.current())][1]

    def toggle_run(self) -> None:
        if self.company is None:
            return
        self.running = not self.running
        self.run_btn.config(text="Pause" if self.running else "Start")
        if not self.running:
            self.shell.save_company()

    def jump(self, minutes: int) -> None:
        company = self.company
        if company is None:
            return
        company.advance(minutes)
        self.shell.company_changed()

    def _settings_changed(self) -> None:
        company = self.company
        if company is None:
            return
        try:
            company.set_settings(
                float(self.mult_var.get().replace(",", ".")), self.auto_var.get(),
                follow_game=self.follow_var.get(), auto_payout=self.autopay_var.get(),
                xp_per_trip=int(self.xp_var.get().strip() or "0"),
                game_speed=GAME_SPEEDS[max(0, self.game_speed.current())][1])
        except (CompanyError, ValueError) as exc:
            messagebox.showerror(APP_TITLE, str(exc) if isinstance(exc, CompanyError)
                                 else "Bitte Faktor (0,1 bis 5) und Reserve als Zahlen eingeben.")
            self.mult_var.set(str(company.settings.profit_multiplier))
            return
        self._sync_mode()
        self.shell.save_company()

    def _sync_mode(self) -> None:
        company = self.company
        follow = bool(company and company.settings.follow_game)
        self.run_btn.config(state="disabled" if follow else "normal")
        if follow:
            self.running = False
            self.run_btn.config(text="Start")
        self.update_game_state()

    def update_game_state(self) -> None:
        company = self.company
        if company is None or not company.settings.follow_game:
            self.game_state.config(text="Der Zeitraffer läuft nur, wenn du ihn selbst startest.")
        elif self.shell.game_running:
            self.game_state.config(text="ETS2 läuft: Die Firma verdient jetzt.")
        else:
            self.game_state.config(text="ETS2 läuft nicht: Die Firma pausiert.")

    def _effective(self) -> tuple[bool, int]:
        """(running?, simulation minutes per real second)"""
        company = self.company
        if company is not None and company.settings.follow_game:
            return self.shell.game_running, company.settings.game_speed
        return self.running, self._speed_minutes()

    def tick(self) -> None:
        """Called by the main window every 100 ms."""
        company = self.company
        if company is None:
            return
        active, per_second = self._effective()
        if not active:
            return
        self._carry += per_second * TICK_MS / 1000
        whole = int(self._carry)
        if whole >= 1:
            self._carry -= whole
            company.advance(whole)
            self._tick_count += 1
            self.refresh_values()
            self.shell.refresh_chips()
            if self._tick_count % 20 == 0:
                self.shell.refresh_company_pages()
            if self._tick_count % 300 == 0:
                self.shell.save_company()

    # ---- Display ------------------------------------------------------------
    def refresh(self) -> None:
        company = self.company
        if company is None:
            self.main.pack_forget()
            self.empty.pack(fill="x")
            money = self.shell.account_money()
            if money is None:
                self.found_info.config(text="Lade zuerst einen Spielstand.")
                self.found_btn.config(state="disabled")
            elif money < busco.FOUNDING_COST:
                self.found_info.config(text=f"Dein ETS2-Konto: {eur(money)}. Dir fehlen noch "
                                            f"{eur(busco.FOUNDING_COST - money)}.")
                self.found_btn.config(state="disabled")
            else:
                self.found_info.config(text=f"Dein ETS2-Konto: {eur(money)}. Du kannst gründen.")
                self.found_btn.config(state="normal")
            return
        self.empty.pack_forget()
        self.main.pack(fill="both", expand=True)
        self.mult_var.set(f"{company.settings.profit_multiplier:.1f}")
        self.auto_var.set(company.settings.auto_service)
        self.follow_var.set(company.settings.follow_game)
        self.autopay_var.set(company.settings.auto_payout)
        self.xp_var.set(str(company.settings.xp_per_trip))
        speeds = [g[1] for g in GAME_SPEEDS]
        match = min(range(len(speeds)), key=lambda i: abs(speeds[i] - company.settings.game_speed))
        self.game_speed.current(match)
        self._sync_mode()
        self.refresh_values()

    def refresh_values(self) -> None:
        c = self.company
        if c is None:
            return
        day = c.now // busco.DAY
        profits = c.recent_profits(7)
        yesterday = c.ledger.get(day - 1)
        self.vars["cash"].set(eur(c.cash))
        self.vars["time"].set(c.fmt_time())
        self.vars["buses"].set(f"{c.active_buses()} / {len(c.buses)}")
        self.vars["rep"].set(f"{c.reputation * 100:.0f} %")
        self.vars["yday"].set(eur(yesterday["revenue"] - yesterday["costs"]) if yesterday else "–")
        full_days = [p for d, p in profits if d < day]
        self.vars["avg"].set(eur(sum(full_days) / len(full_days)) if full_days else "–")
        self.vars["xp"].set(f"{busco.num(c.xp_pending)} XP")
        self.vars["paid"].set(("+ " if c.firm_delta() >= 0 else "- ") + eur(abs(c.firm_delta())))
        self._draw_chart()
        rows = []
        for i, (t, text) in enumerate(reversed(c.log[-12:])):
            rows.append((f"l{i}", (c.fmt_time(t), text)))
        fill_tree(self.log_tree, rows)

    def _draw_chart(self) -> None:
        cv = self.canvas
        cv.delete("all")
        c = self.company
        w, h = cv.winfo_width(), cv.winfo_height()
        if c is None or w < 60 or h < 60:
            return
        data = c.recent_profits(14)
        left, right, top, bottom = 52, 10, 10, 24
        peak = max([abs(v) for _, v in data] + [1.0])
        has_neg = any(v < 0 for _, v in data)
        zero_y = (top + (h - top - bottom) * (0.62 if has_neg else 1.0))
        scale = (zero_y - top) / peak
        cv.create_line(left, zero_y, w - right, zero_y, fill=theme.BORDER)
        cv.create_text(left - 6, top + 4, text=_short_eur(peak), anchor="e", fill=theme.MUTED, font=("TkDefaultFont", 8))
        cv.create_text(left - 6, zero_y, text="0", anchor="e", fill=theme.MUTED, font=("TkDefaultFont", 8))
        slot = (w - left - right) / max(1, len(data))
        for i, (day, value) in enumerate(data):
            x0 = left + i * slot + slot * 0.18
            x1 = left + (i + 1) * slot - slot * 0.18
            y = zero_y - value * scale
            cv.create_rectangle(x0, min(y, zero_y), x1, max(y, zero_y),
                                fill=theme.ACCENT if value >= 0 else theme.DANGER, outline="")
            cv.create_text((x0 + x1) / 2, h - 10, text=str(day + 1), fill=theme.MUTED, font=("TkDefaultFont", 8))


def _short_eur(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} Mio".replace(".", ",")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f} Tsd"
    return f"{value:.0f}"


# --------------------------------------------------------------------------
# Garages
# --------------------------------------------------------------------------

class GaragesPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="Garage bauen …", style="Accent.TButton", command=self.build).pack(side="left")
        self.upgrade_btn = ttk.Button(bar, text="Ausbauen", command=self.upgrade)
        self.upgrade_btn.pack(side="left", padx=8)
        wrap, self.tree = make_tree(
            self,
            [("city", "Stadt", 200, "w"), ("size", "Größe", 140, "w"), ("buses", "Busse", 70, "center"),
             ("drivers", "Fahrer", 70, "center"), ("profit", "Gewinn gesamt", 120, "e"),
             ("upkeep", "Fixkosten / Tag", 120, "e"), ("routes", "Strecken", 80, "center")],
            height=3,
        )
        wrap.pack(fill="x", pady=(10, 8))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._detail())

        # profitability of the selected garage
        self.detail_title = ttk.Label(self, text="", style="Head.TLabel")
        self.detail_title.pack(anchor="w")
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(4, 6))
        self.stat: dict[str, tk.StringVar] = {}
        cards = [("fill", "AUSLASTUNG"), ("revenue", "EINNAHMEN"), ("costs", "KOSTEN (FAHRTEN)"),
                 ("profit", "GEWINN"), ("per_km", "GEWINN JE KM"), ("per_bus", "GEWINN JE BUS"),
                 ("fixed", "FIXKOSTEN / TAG"), ("trips", "FAHRTEN · KM")]
        for i, (key, label) in enumerate(cards):
            cell = ttk.Frame(grid, style="Card.TFrame", padding=(10, 6))
            cell.grid(row=i // 4, column=i % 4, sticky="nsew", padx=(0 if i % 4 == 0 else 6, 0), pady=(0, 6))
            grid.columnconfigure(i % 4, weight=1)
            ttk.Label(cell, text=label, style="CardCaption.TLabel").pack(anchor="w")
            var = tk.StringVar(value="–")
            self.stat[key] = var
            ttk.Label(cell, textvariable=var, style="CardValue.TLabel").pack(anchor="w")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        bus_wrap, self.bus_tree = make_tree(
            self.nb,
            [("id", "#", 34, "center"), ("model", "Bus", 125, "w"), ("driver", "Fahrer", 105, "w"),
             ("line", "Linie", 140, "w"), ("cond", "Zustand", 74, "center"), ("trips", "Fahrten", 66, "e"),
             ("km", "km", 62, "e"), ("rev", "Einnahmen", 90, "e"), ("profit", "Gewinn", 90, "e"),
             ("state", "Status", 110, "w")], height=5)
        drv_wrap, self.drv_tree = make_tree(
            self.nb,
            [("name", "Fahrer", 150, "w"), ("rank", "Rang", 80, "w"), ("skills", "Öko / Pünktl. / Service / Sicher.", 210, "center"),
             ("wage", "Lohn / Std.", 90, "e"), ("km", "km", 80, "e"), ("bus", "Bus", 60, "center"),
             ("state", "Status", 150, "w")], height=5)
        self.nb.add(bus_wrap, text="  Busse  ")
        self.nb.add(drv_wrap, text="  Fahrer  ")
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        rows = []
        if c is not None:
            for city, g in sorted(c.garages.items()):
                st = c.garage_stats(city)
                rows.append((city, (city_name(city), busco.GARAGE_SIZES[g.size]["label"],
                                    f"{st['buses']} / {g.capacity}", st["drivers"],
                                    ("+ " if st["profit"] >= 0 else "- ") + eur(abs(st["profit"])),
                                    eur(st["fixed_per_day"]), len(c.catalog.destinations(city)))))
        fill_tree(self.tree, rows)
        if rows and not self.tree.selection():
            self.tree.selection_set(rows[0][0])
        self._detail()

    def _detail(self) -> None:
        c = self.company
        sel = self.tree.selection()
        if c is None or not sel or sel[0] not in c.garages:
            self.detail_title.config(text="")
            for var in self.stat.values():
                var.set("–")
            fill_tree(self.bus_tree, [])
            fill_tree(self.drv_tree, [])
            return
        city = sel[0]
        st = c.garage_stats(city)
        self.detail_title.config(text=f"Garage {city_name(city)}")

        def signed(v: float) -> str:
            return ("+ " if v >= 0 else "- ") + eur(abs(v))

        self.stat["fill"].set(f"{st['buses']} / {st['capacity']} Busse · {st['drivers']} Fahrer")
        self.stat["revenue"].set(eur(st["revenue"]))
        self.stat["costs"].set(eur(st["costs"]))
        self.stat["profit"].set(signed(st["profit"]))
        self.stat["per_km"].set(signed(st["profit_per_km"]).replace(" €", " €/km") if st["km"] else "–")
        self.stat["per_bus"].set(signed(st["profit_per_bus"]) if st["buses"] else "–")
        self.stat["fixed"].set(eur(st["fixed_per_day"]))
        self.stat["trips"].set(f"{busco.num(st['trips'])} · {busco.num(st['km'])} km")
        rows = []
        for bus in sorted(c.garage_buses(city), key=lambda b: b.id):
            spec = c.model(bus.model)
            driver = c.drivers.get(bus.driver) if bus.driver else None
            rows.append((str(bus.id), (bus.id, spec.label.split(" · ")[0] + f" ({spec.seats} Pl.)",
                                       driver.name if driver else "–", c.line_label(bus), f"{bus.condition:.0f} %",
                                       bus.trips, busco.num(bus.km), eur(bus.revenue),
                                       signed(bus.revenue - bus.costs), c.bus_status(bus))))
        fill_tree(self.bus_tree, rows)
        rows = []
        for d in sorted(c.garage_drivers(city), key=lambda x: x.name):
            rows.append((str(d.id), (d.name, d.rank, f"{d.eco} / {d.punctual} / {d.service} / {d.safety}",
                                     eur(d.wage), busco.num(d.km), d.bus_id or "–",
                                     f"Schulung: {busco.SKILLS.get(d.training, d.training)}" if d.training else "im Dienst")))
        fill_tree(self.drv_tree, rows)

    def build(self) -> None:
        c = self.company
        if c is None:
            return
        BuildGarageDialog(self, c).popup()
        self.shell.company_changed()

    def upgrade(self) -> None:
        c = self.company
        sel = self.tree.selection()
        if c is None or not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst eine Garage auswählen.")
            return
        city = sel[0]
        g = c.garages[city]
        idx = busco.SIZE_ORDER.index(g.size)
        if idx + 1 >= len(busco.SIZE_ORDER):
            messagebox.showinfo(APP_TITLE, "Die Garage hat schon die höchste Stufe.")
            return
        new = busco.SIZE_ORDER[idx + 1]
        price = busco.GARAGE_SIZES[new]["price"] - busco.GARAGE_SIZES[g.size]["price"]
        if not messagebox.askokcancel(APP_TITLE, f"{city_name(city)} auf „{busco.GARAGE_SIZES[new]['label']}“ ausbauen?\nKosten: {eur(price)}"):
            return
        try:
            c.upgrade_garage(city)
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.shell.company_changed()


class BuildGarageDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, preset: str | None = None) -> None:
        super().__init__(master, "Garage bauen", "Bauen")
        self.company = company
        cities = [c for c in company.catalog.cities() if c not in company.garages]
        self.names = {city_name(c): c for c in cities}
        self.all_names = sorted(self.names)
        ttk.Label(self.body, text="Stadt").grid(row=0, column=0, sticky="w", pady=5)
        self.city_var = tk.StringVar()
        self.city = ttk.Combobox(self.body, textvariable=self.city_var, values=self.all_names, width=34)
        self.city.grid(row=0, column=1, sticky="w", padx=12)
        self.city.bind("<KeyRelease>", self._filter)
        self.city.bind("<<ComboboxSelected>>", lambda e: self._info())
        self.city.bind("<FocusOut>", lambda e: self._info())
        ttk.Label(self.body, text="Größe").grid(row=1, column=0, sticky="nw", pady=5)
        self.size_var = tk.StringVar(value="small")
        box = ttk.Frame(self.body)
        box.grid(row=1, column=1, sticky="w", padx=12)
        for key in busco.SIZE_ORDER:
            spec = busco.GARAGE_SIZES[key]
            ttk.Radiobutton(
                box, value=key, variable=self.size_var,
                text=f"{spec['label']} – {eur(spec['price'])}, Unterhalt {eur(spec['upkeep'])} / Tag",
            ).pack(anchor="w", pady=2)
        self.hint = ttk.Label(self.body, style="Muted.TLabel", text=f"Kasse: {eur(company.cash)}")
        self.hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        if preset and city_name(preset) in self.names:
            self.city_var.set(city_name(preset))
            self._info()

    def _filter(self, event) -> None:
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        typed = self.city_var.get().strip().lower()
        self.city["values"] = [n for n in self.all_names if typed in n.lower()] if typed else self.all_names

    def _info(self) -> None:
        city = self.names.get(self.city_var.get().strip())
        extra = ""
        if city:
            extra = f"   ·   {len(self.company.catalog.destinations(city))} Strecken ab {city_name(city)}"
        self.hint.config(text=f"Kasse: {eur(self.company.cash)}{extra}")

    def on_ok(self) -> bool:
        city = self.names.get(self.city_var.get().strip())
        if city is None:
            self.error("Bitte eine Stadt aus der Liste wählen.")
            return False
        try:
            self.company.build_garage(city, self.size_var.get())
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True


# --------------------------------------------------------------------------
# Buses
# --------------------------------------------------------------------------

class BusesPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="Bus kaufen …", style="Accent.TButton", command=self.buy).pack(side="left")
        ttk.Button(bar, text="Linie zuweisen …", command=self.assign).pack(side="left", padx=8)
        ttk.Button(bar, text="Fahrer zuweisen …", command=self.assign_driver).pack(side="left")
        ttk.Button(bar, text="Wartung", command=self.service).pack(side="left", padx=8)
        ttk.Button(bar, text="Aus Verkehr nehmen", command=self.unassign).pack(side="left")
        ttk.Button(bar, text="Verkaufen", command=self.sell).pack(side="right")
        wrap, self.tree = make_tree(
            self,
            [("id", "Nr.", 40, "center"), ("model", "Modell", 150, "w"), ("home", "Garage", 90, "w"),
             ("line", "Linie", 165, "w"), ("driver", "Fahrer", 115, "w"), ("cond", "Zustand", 70, "center"),
             ("trips", "Fahrten", 58, "center"), ("km", "km", 66, "e"), ("profit", "Gewinn", 90, "e"),
             ("state", "Status", 110, "w")],
            height=14,
        )
        wrap.pack(fill="both", expand=True, pady=10)
        self.hint = ttk.Label(self, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "Kaufe Busse für deine Garagen und weise ihnen eine Strecke ab der Garagenstadt oder eine "
            "Touristenfahrt zu einer Sehenswürdigkeit zu. Jeder Bus braucht einen Fahrer (Menü „Fahrer“)."))
        self.hint.pack(fill="x")
        self.refresh()

    def refresh(self) -> None:
        c = self.company
        rows = []
        if c is not None:
            for bus in sorted(c.buses.values(), key=lambda b: b.id):
                spec = c.model(bus.model)
                driver = c.drivers.get(bus.driver) if bus.driver else None
                state = c.bus_status(bus)
                line = c.line_label(bus)
                rows.append((str(bus.id), (bus.id, spec.label.split(" · ")[0] + f" ({spec.seats} Pl.)",
                                           city_name(bus.home), line, driver.name if driver else "–",
                                           f"{bus.condition:.0f} %", bus.trips,
                                           busco.num(bus.km), eur(bus.revenue - bus.costs), state)))
        fill_tree(self.tree, rows)

    def _selected(self):
        c = self.company
        sel = self.tree.selection()
        if c is None or not sel:
            messagebox.showinfo(APP_TITLE, "Bitte erst einen Bus auswählen.")
            return None
        return c.buses.get(int(sel[0]))

    def buy(self) -> None:
        c = self.company
        if c is None:
            return
        if not c.garages:
            messagebox.showinfo(APP_TITLE, "Bau zuerst eine Garage (Menü „Garagen“).")
            return
        BuyBusDialog(self, c).popup()
        self.shell.company_changed()

    def assign(self) -> None:
        bus = self._selected()
        if bus is None:
            return
        AssignRouteDialog(self, self.company, bus).popup()
        self.shell.company_changed()

    def assign_driver(self) -> None:
        bus = self._selected()
        if bus is None:
            return
        from .gui_drivers import AssignDriverDialog
        AssignDriverDialog(self, self.company, bus=bus).popup()
        self.shell.company_changed()

    def unassign(self) -> None:
        bus = self._selected()
        if bus is None:
            return
        self.company.assign_route(bus.id, None)
        self.shell.company_changed()

    def service(self) -> None:
        bus = self._selected()
        if bus is None:
            return
        cost = round((100 - bus.condition) * busco.SERVICE_COST_PER_POINT)
        if bus.condition >= 99.5:
            messagebox.showinfo(APP_TITLE, "Der Bus ist in einwandfreiem Zustand.")
            return
        if not messagebox.askokcancel(APP_TITLE, f"Bus #{bus.id} warten?\nKosten: {eur(cost)}, der Bus steht dabei {busco.SERVICE_HOURS} Stunden."):
            return
        try:
            self.company.service_bus(bus.id)
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.shell.company_changed()

    def sell(self) -> None:
        bus = self._selected()
        if bus is None:
            return
        spec = self.company.model(bus.model)
        value = round(spec.price * 0.55 * (0.6 + 0.4 * bus.condition / 100))
        if not messagebox.askokcancel(APP_TITLE, f"Bus #{bus.id} für {eur(value)} verkaufen?"):
            return
        self.company.sell_bus(bus.id)
        self.shell.company_changed()


class BuyBusDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, preset: str | None = None) -> None:
        super().__init__(master, "Bus kaufen", "Kaufen")
        self.company = company
        self.cities = {
            f"{city_name(c)}  ({len(company.garage_buses(c))} / {g.capacity})": c
            for c, g in sorted(company.garages.items())
        }
        ttk.Label(self.body, text="Garage").grid(row=0, column=0, sticky="w", pady=5)
        self.garage = ttk.Combobox(self.body, state="readonly", width=38, values=list(self.cities))
        self.garage.grid(row=0, column=1, sticky="w", padx=12)
        preset_idx = next((i for i, c in enumerate(self.cities.values()) if c == preset), 0)
        self.garage.current(preset_idx)
        ttk.Label(self.body, text="Modell").grid(row=1, column=0, sticky="w", pady=5)
        self.models = {
            f"{company.model(m).label}  –  {company.model(m).seats} Plätze  –  {eur(company.model(m).price)}": m
            for m in company.catalog.models
        }
        self.model = ttk.Combobox(self.body, state="readonly", width=70, values=list(self.models))
        self.model.grid(row=1, column=1, sticky="w", padx=12)
        self.model.current(0)
        ttk.Label(self.body, style="Muted.TLabel", text=f"Kasse: {eur(company.cash)}").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def on_ok(self) -> bool:
        try:
            self.company.buy_bus(self.cities[self.garage.get()], self.models[self.model.get()])
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True


class AssignRouteDialog(Dialog):
    def __init__(self, master: tk.Misc, company: BusCompany, bus) -> None:
        super().__init__(master, f"Linie für Bus #{bus.id}", "Zuweisen")
        self.company, self.bus = company, bus
        ttk.Label(
            self.body,
            text=(f"Strecken ab {city_name(bus.home)} und deine eigenen Routen. Die Gewinn-Schätzung gilt für "
                  "dieses Modell und normale Nachfrage."),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(self.body)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._fill())
        ttk.Entry(bar, textvariable=self.filter_var, width=26).pack(side="left", padx=8)
        wrap, self.tree = make_tree(
            self.body,
            [("dest", "Ziel", 200, "w"), ("typ", "Art", 80, "w"), ("km", "km", 70, "e"),
             ("min", "Fahrzeit (Min.)", 110, "e"), ("est", "ca. Gewinn / Fahrt", 140, "e")],
            height=14,
        )
        wrap.pack(fill="both", expand=True, pady=8)
        self.rows = []
        for dest, km, mins in company.catalog.destinations(bus.home):
            est = busco.estimate_trip_profit(bus.model, km, mins, company.settings.profit_multiplier,
                                              tourist=dest.startswith("viewpoints."))
            self.rows.append((dest, km, mins, est))
        self.rows.sort(key=lambda r: -r[3])
        self.custom = []
        for r in company.routes.values():
            if r.stops[0] != bus.home:
                continue
            km = mins = 0
            for x, y in zip(r.stops, r.stops[1:]):
                leg = company.catalog.routes.get((x, y))
                if leg:
                    km, mins = km + leg[0], mins + leg[1]
            self.custom.append((f"route:{r.id}", r.name, "Ausflug" if r.kind == "excursion" else "Eigene Linie", km, mins))
        self._fill()

    def _fill(self) -> None:
        needle = self.filter_var.get().strip().lower()
        rows = [(key, (name, kind, km, mins, "–")) for key, name, kind, km, mins in self.custom
                if needle in name.lower()]
        rows += [(dest, (city_name(dest), "Touristik" if dest.startswith("viewpoints.") else "Linie",
                         km, mins, eur(est)))
                 for dest, km, mins, est in self.rows if needle in city_name(dest).lower()]
        fill_tree(self.tree, rows)

    def on_ok(self) -> bool:
        sel = self.tree.selection()
        if not sel:
            self.error("Bitte ein Ziel auswählen.")
            return False
        try:
            if sel[0].startswith("route:"):
                self.company.assign_custom_route(self.bus.id, int(sel[0].split(":")[1]))
            else:
                self.company.assign_route(self.bus.id, sel[0])
        except CompanyError as exc:
            self.error(str(exc))
            return False
        return True
