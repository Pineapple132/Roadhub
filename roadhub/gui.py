"""User interface (tkinter) for Roadhub."""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import busco, busy, editor, gamewatch, i18n, saves, sii, telemetry, theme, tour
from .busco import BusCatalog, BusCompany, CompanyError, eur
from .gui_buslines import BusLinesPage
from .gui_company import TICK_MS, BusesPage, GaragesPage, OverviewPage
from .gui_contracts import ContractsPage
from .gui_drivers import DriversPage
from .gui_finance import FinancePage
from .gui_routes import RoutesPage
from .gui_settings import SettingsPage
from .gui_live import LivePage
from .gui_map import MapPage
from .overlay import Overlay
from .widgets import APP_TITLE, Dialog
URGENCY_LABELS = ["0 – normal", "1 – eilig", "2 – sehr eilig"]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        i18n.set_language(i18n.load_saved_language())
        self.title(APP_TITLE)
        self.geometry("1200x780")
        self.minsize(1000, 640)
        self.fonts = theme.apply(self)
        self.tour: tour.Tour | None = None
        self.skip_tutorial = bool(os.environ.get("ETS2_SKIP_TUTORIAL"))
        if not self.skip_tutorial and not i18n.has_saved_language():
            self.withdraw()                      # first start: choose the language first
            code = tour.choose_first_language(self)
            if code:
                i18n.save_language(code)
                i18n.set_language(code)
            self.deiconify()
        i18n.install()
        busy.install(self)

        self.doc: sii.SiiDocument | None = None
        self.path: str | None = None
        self.jobs_dirty = False
        self.loaded_profile: dict[str, str | None] = {}
        self.profile_vars: dict[str, tk.StringVar] = {}   # all fields (profile + bus)
        self.field_widgets: dict[str, ttk.Widget] = {}
        self.save_entries: list[saves.SaveEntry] = []
        self._sort_state: tuple[str, bool] = ("", False)
        self._offers_cache: list[editor.JobOffer] | None = None
        self.pages: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.current_page = ""
        self.company_path = busco.default_state_path()
        self.company: BusCompany | None = None
        self.game_running = False
        self.telemetry = telemetry.TelemetryClient()
        self.tracker = telemetry.TripTracker()
        self.overlay: Overlay | None = None
        self._save_stamp: tuple | None = None          # (path, modification time) of the newest save game
        self._save_pending_since = 0.0
        self.last_save_mtime = 0.0
        self._load_company()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._startup)
        self.after(1200, self._maybe_start_tour)
        self.after(600, self.sync_account)
        self.after(TICK_MS, self._tick)
        self.after(500, self._poll_game)
        self.after(1000, self._telemetry_tick)
        self.after(3000, self._watch_saves)
        self.after(self.RESCAN_MS, self._periodic_rescan)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self._build_header()

        top = ttk.LabelFrame(self, text="Spielstand", padding=(10, 6))
        top.pack(fill="x", padx=14, pady=(12, 4))
        self.save_bar = top
        self.save_combo = ttk.Combobox(top, state="readonly", width=70)
        self.save_combo.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="we")
        ttk.Button(top, text="Laden", style="Accent.TButton", command=self._load_selected).grid(
            row=0, column=1, padx=4
        )
        ttk.Button(top, text="Neu suchen", command=self._scan_saves).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Datei wählen …", command=self._choose_file).grid(row=0, column=3, padx=(4, 0))
        top.columnconfigure(0, weight=1)

        self.file_label = ttk.Label(self, text="Noch nichts geladen.", style="Muted.TLabel")
        self.file_label.pack(fill="x", padx=16)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
        self.save_btn = ttk.Button(
            bottom, text="Speichern (mit Backup)", style="Accent.TButton", command=self._save,
            state="disabled",
        )
        self.save_btn.pack(side="right")
        self.status = ttk.Label(bottom, text="Bereit.", style="Muted.TLabel")
        self.status.pack(side="left")
        self.payout_btn = ttk.Button(bottom, text="Firmenstand in Spielstand schreiben …", command=self.start_payout)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(6, 0))
        self._build_sidebar(body)
        self.tabs = ttk.Notebook(body, style="Hidden.TNotebook")
        self.tabs.pack(side="left", fill="both", expand=True, padx=(10, 14))

        self.overview = OverviewPage(self.tabs, self)
        self._add_page(self.overview, "overview")
        self.live_page = LivePage(self.tabs, self)
        self._add_page(self.live_page, "live")
        self.map_page = MapPage(self.tabs, self)
        self._add_page(self.map_page, "map")
        self.garages_page = GaragesPage(self.tabs, self)
        self._add_page(self.garages_page, "garages")
        self.buses_page = BusesPage(self.tabs, self)
        self._add_page(self.buses_page, "buses")
        self.drivers_page = DriversPage(self.tabs, self)
        self._add_page(self.drivers_page, "drivers")
        self.routes_page = RoutesPage(self.tabs, self)
        self._add_page(self.routes_page, "routes")
        self.finance_page = FinancePage(self.tabs, self)
        self._add_page(self.finance_page, "finance")
        self.settings_page = SettingsPage(self.tabs, self)
        self._add_page(self.settings_page, "settings")
        self.contracts_page = ContractsPage(self.tabs, self)
        self._add_page(self.contracts_page, "contracts")
        self._build_profile_tab()
        self._build_jobs_tab()
        self._build_bus_tab()
        self.buslines_page = BusLinesPage(self.tabs, self)
        self._add_page(self.buslines_page, "buslines")
        self._update_nav()
        self.show_page("overview")

    def _add_page(self, frame: ttk.Frame, key: str) -> None:
        self.tabs.add(frame)
        self.pages[key] = frame

    def _build_sidebar(self, parent: tk.Misc) -> None:
        side = ttk.Frame(parent, style="Panel.TFrame", width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ttk.Label(side, text="BUSFIRMA", style="NavHead.TLabel").pack(anchor="w", padx=20, pady=(16, 4))
        self.firm_nav = [("live", "Live-Fahrt"), ("map", "Karte"), ("garages", "Garagen"),
                         ("buses", "Busse"), ("drivers", "Fahrer"), ("routes", "Eigene Routen"),
                         ("contracts", "Verträge"), ("finance", "Finanzen"), ("settings", "Einstellungen")]
        self._nav_button(side, "overview", "Übersicht", "Nav")
        for key, text in self.firm_nav:
            self._nav_button(side, key, text, "Nav")
        self._nav_spacer = ttk.Frame(side, style="Panel.TFrame", height=14)
        self._nav_spacer.pack()
        self.editor_open = False
        self.editor_toggle = ttk.Button(side, text="▸  Save-Editor", style="Nav.TButton", command=self._toggle_editor)
        self.editor_toggle.pack(fill="x")
        self.editor_box = ttk.Frame(side, style="Panel.TFrame")
        for key, text in (("profile", "Profil"), ("jobs", "Truck-Aufträge"), ("bus", "Bus (XP, Skills)"),
                          ("buslines", "Bus-Aufträge")):
            self._nav_button(self.editor_box, key, text, "NavSub")

    def _update_nav(self) -> None:
        """Without a company there is only the overview (for founding one), all other company pages are hidden."""
        show = self.company is not None
        self.payout_btn.pack_forget()
        if show:
            self.payout_btn.pack(side="right", padx=(0, 10))
        for key, _text in self.firm_nav:
            btn = self.nav_buttons[key]
            btn.pack_forget()
        if show:
            for key, _text in self.firm_nav:
                self.nav_buttons[key].pack(fill="x", before=self._nav_spacer)

    def _nav_button(self, parent: tk.Misc, key: str, text: str, kind: str) -> None:
        btn = ttk.Button(parent, text=text, style=f"{kind}.TButton", command=lambda: self.show_page(key))
        btn.pack(fill="x")
        btn._kind = kind  # type: ignore[attr-defined]
        self.nav_buttons[key] = btn

    def _toggle_editor(self, force: bool | None = None) -> None:
        self.editor_open = (not self.editor_open) if force is None else force
        if self.editor_open:
            self.editor_box.pack(fill="x", after=self.editor_toggle)
        else:
            self.editor_box.pack_forget()
        self.editor_toggle.config(text=("▾  Save-Editor" if self.editor_open else "▸  Save-Editor"))

    def show_page(self, key: str) -> None:
        if self.company is None and key not in ("profile", "jobs", "bus", "buslines"):
            key = "overview"            # without a company there is only the page for founding one
        self.current_page = key
        self.tabs.select(self.pages[key])
        for name, btn in self.nav_buttons.items():
            kind = btn._kind  # type: ignore[attr-defined]
            btn.config(style=f"{kind}Active.TButton" if name == key else f"{kind}.TButton")
        if key in ("profile", "jobs", "bus", "buslines"):
            self._toggle_editor(True)
        self.editor_toggle.config(style="NavActive.TButton" if key in ("profile", "jobs", "bus", "buslines")
                                  and not self.editor_open else "Nav.TButton")
        if key == "buslines":
            self.buslines_page.refresh()
        if key == "live":
            self.live_page.refresh()
        self.refresh_company_pages()
        if self.tour is not None:
            self.tour.page_shown(key)

    # ---- Tutorial ----
    @staticmethod
    def _upper(text: str) -> str:
        if i18n.language() == "tr":
            text = text.replace("i", "İ").replace("ı", "I")
        return text.upper()

    def _maybe_start_tour(self) -> None:
        if self.skip_tutorial:
            return
        if self.company is not None:
            if not i18n.ui_get("company_tour_done", False):
                self.start_tour("company")
        elif not i18n.ui_get("tour_done", False):
            self.start_tour("intro")

    def _tutorial_clicked(self) -> None:
        if self.company is None:
            self.start_tour("intro")
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Einführung (Spielstand und Save-Editor)", command=lambda: self.start_tour("intro"))
        menu.add_command(label="Firmenmenü", command=lambda: self.start_tour("company"))
        x = self.tutorial_btn.winfo_rootx()
        y = self.tutorial_btn.winfo_rooty() + self.tutorial_btn.winfo_height()
        menu.tk_popup(x, y)

    def start_tour(self, kind: str) -> None:
        if self.tour is not None and self.tour.active:
            self.tour._close(False)
        steps = tour.company_steps() if kind == "company" else tour.intro_steps()
        flag = "company_tour_done" if kind == "company" else "tour_done"

        def closed(_finished: bool) -> None:
            i18n.ui_set(**{flag: True})
            self.show_page("overview")

        self.tour = tour.Tour(self, steps, closed)
        self.tour.start()

    def _build_header(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame")
        bar.pack(fill="x")
        ttk.Frame(bar, style="Accent.TFrame", width=8).pack(side="left", fill="y")
        left = ttk.Frame(bar, style="Panel.TFrame")
        left.pack(side="left", padx=18, pady=12)
        self.title_var = tk.StringVar(value="ROADHUB")
        ttk.Label(left, textvariable=self.title_var, style="Title.TLabel").pack(anchor="w")
        self.subtitle_var = tk.StringVar(value="Busunternehmen im Zeitraffer  ·  Save-Editor für Truck und Bus")
        ttk.Label(left, textvariable=self.subtitle_var, style="PanelMuted.TLabel").pack(anchor="w")
        right = ttk.Frame(bar, style="Panel.TFrame")
        right.pack(side="right", padx=18, pady=12)
        self.chip_vars = {k: tk.StringVar(value="–") for k in ("money", "xp", "busxp")}
        self.stat_cells: list[ttk.Frame] = []
        for column, (key, caption) in enumerate(
            [("money", "ETS2-KONTO (€)"), ("xp", "XP"), ("busxp", "BUS-XP")]
        ):
            cell = ttk.Frame(right, style="Panel.TFrame")
            cell.grid(row=0, column=column, padx=(22, 0))
            self.stat_cells.append(cell)
            ttk.Label(cell, text=caption, style="PanelMuted.TLabel").pack(anchor="e")
            ttk.Label(cell, textvariable=self.chip_vars[key], style="Chip.TLabel").pack(anchor="e")
        lang_cell = ttk.Frame(right, style="Panel.TFrame")
        lang_cell.grid(row=0, column=3, padx=(26, 0), sticky="n")
        self.lang_cell = lang_cell
        ttk.Label(lang_cell, text="Sprache / Language", style="PanelMuted.TLabel").pack(anchor="e")
        self.lang_box = ttk.Combobox(lang_cell, state="readonly", width=12, values=[n for _c, n in i18n.LANGUAGES])
        self.lang_box.current([c for c, _n in i18n.LANGUAGES].index(i18n.language()))
        self.lang_box.pack(anchor="e", pady=(2, 0))
        self.lang_box.bind("<<ComboboxSelected>>", self._language_chosen)
        help_cell = ttk.Frame(right, style="Panel.TFrame")
        help_cell.grid(row=0, column=4, padx=(10, 0), sticky="n")
        ttk.Label(help_cell, text=" ", style="PanelMuted.TLabel").pack(anchor="e")
        self.tutorial_btn = ttk.Button(help_cell, text="Tutorial", style="Small.TButton", command=self._tutorial_clicked)
        self.tutorial_btn.pack(anchor="e", pady=(2, 0))
        ttk.Frame(self, style="Accent.TFrame", height=3).pack(fill="x")

    def _language_chosen(self, _event=None) -> None:
        code = i18n.LANGUAGES[self.lang_box.current()][0]
        if code == i18n.language():
            return
        i18n.save_language(code)
        i18n.set_language(code)
        if not messagebox.askyesno(
                APP_TITLE, "Die Sprache wird nach einem Neustart des Tools übernommen. Jetzt neu starten?"):
            return
        if not self._confirm_discard():
            return
        self.save_company()
        self.telemetry.close()
        if self.overlay is not None:
            self.overlay.destroy()
        self.destroy()
        import subprocess
        import sys
        try:
            subprocess.Popen([sys.executable] + sys.argv)
        except OSError:
            pass

    # ---- Fields -----------------------------------------------------------
    def _add_field(self, parent, row: int, spec: editor.FieldSpec, kind: str = "entry") -> tk.StringVar:
        ttk.Label(parent, text=spec.label).grid(row=row, column=0, sticky="w", pady=5)
        var = tk.StringVar()
        var.trace_add("write", lambda *_: self._on_var())
        if kind == "spin":
            widget: ttk.Widget = ttk.Spinbox(
                parent, from_=spec.minimum, to=spec.maximum, textvariable=var, width=10, state="disabled"
            )
        else:
            widget = ttk.Entry(parent, textvariable=var, width=22, state="disabled")
        widget.grid(row=row, column=1, sticky="w", padx=14)
        self.profile_vars[spec.key] = var
        self.field_widgets[spec.key] = widget
        return var

    def _on_var(self) -> None:
        self._refresh_title()
        self._refresh_header()

    def _refresh_header(self) -> None:
        def value(key: str) -> str:
            var = self.profile_vars.get(key)
            if self.doc is None or var is None:
                return "–"
            return theme.format_int(var.get())

        self.chip_vars["xp"].set(value("experience_points"))
        self.chip_vars["busxp"].set(value("bus_experience_points"))
        self.refresh_chips()

    def refresh_chips(self) -> None:
        self._update_nav()
        self.title_var.set(self._upper(self.company.name) if self.company is not None else "ROADHUB")
        """Ein Konto: mit Firma der Stand inklusive noch nicht geschriebener Firmenänderungen, sonst der Save."""
        if self.company is not None:
            self.chip_vars["money"].set(eur(self.company.cash))
        else:
            var = self.profile_vars.get("money_account")
            self.chip_vars["money"].set(theme.format_int(var.get()) if self.doc is not None and var else "–")

    def _build_profile_tab(self) -> None:
        frame = ttk.Frame(self.tabs, padding=16)
        self._add_page(frame, "profile")
        by_key = {s.key: s for s in editor.PROFILE_FIELDS}

        box = ttk.LabelFrame(frame, text="Konto und Erfahrung", padding=14)
        box.pack(fill="x")
        self._add_field(box, 0, by_key["money_account"])
        self._add_field(box, 1, by_key["experience_points"])

        skills = ttk.LabelFrame(frame, text="Truck-Skills", padding=14)
        skills.pack(fill="x", pady=(12, 0))
        adr_var = self._add_field(skills, 0, by_key["adr"], kind="spin")
        bar = ttk.Frame(skills)
        bar.grid(row=0, column=2, sticky="w")
        ttk.Button(bar, text="alle (63)", style="Small.TButton", command=lambda: adr_var.set("63")).pack(
            side="left"
        )
        ttk.Button(bar, text="keine (0)", style="Small.TButton", command=lambda: adr_var.set("0")).pack(
            side="left", padx=6
        )
        for row, key in enumerate(("long_dist", "heavy", "fragile", "urgent", "mechanical"), start=1):
            var = self._add_field(skills, row, by_key[key], kind="spin")
            ttk.Button(
                skills, text="max (6)", style="Small.TButton", command=lambda v=var: v.set("6")
            ).grid(row=row, column=2, sticky="w")

        ttk.Label(
            frame,
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
            text=(
                "Der Kontostand ist der interne Euro-Wert. Bei anderen Währungen (z. B. Pfund oder "
                "Franken) rechnet das Spiel die Anzeige um. Skills reichen von 0 bis 6, ADR ist eine "
                "Bitmaske (0 bis 63). Mit „Speichern“ unten werden alle Änderungen aller Reiter geschrieben."
            ),
        ).pack(fill="x", pady=(14, 0))

    def _build_jobs_tab(self) -> None:
        frame = ttk.Frame(self.tabs, padding=12)
        self._add_page(frame, "jobs")

        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._fill_jobs())
        ttk.Entry(bar, textvariable=self.filter_var, width=28).pack(side="left", padx=8)
        self.show_empty_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="leere Slots anzeigen", variable=self.show_empty_var, command=self._fill_jobs
        ).pack(side="left", padx=10)
        self.edit_btn = ttk.Button(
            bar, text="Auftrag bearbeiten …", style="Accent.TButton", command=self._edit_selected,
            state="disabled",
        )
        self.edit_btn.pack(side="right")

        cols = ("start", "slot", "ziel", "fracht", "km", "dringlich", "rest")
        heads = {
            "start": ("Start", 210),
            "slot": ("Slot", 50),
            "ziel": ("Ziel", 210),
            "fracht": ("Fracht", 160),
            "km": ("km", 64),
            "dringlich": ("Dringlichkeit", 100),
            "rest": ("läuft ab in (h)", 110),
        }
        wrap = ttk.Frame(frame)
        wrap.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            title, width = heads[c]
            self.tree.heading(c, text=title, command=lambda c=c: self._sort_by(c))
            self.tree.column(c, width=width, anchor="w" if c in ("start", "ziel", "fracht") else "center")
        self.tree.tag_configure("even", background=theme.ROW_A)
        self.tree.tag_configure("odd", background=theme.ROW_B)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_edit_btn())

        ttk.Label(
            frame,
            style="Muted.TLabel",
            wraplength=940,
            justify="left",
            text=(
                "Du überschreibst einen vorhandenen Auftrags-Slot einer Firma. Fracht und Anhänger "
                "kommen aus Kombinationen, die schon in deinem Save vorkommen – so passt beides "
                "zusammen. Die Entfernung bestimmt die Bezahlung."
            ),
        ).pack(fill="x")

    def _build_bus_tab(self) -> None:
        frame = ttk.Frame(self.tabs, padding=16)
        self._add_page(frame, "bus")
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        by_key = {s.key: s for s in editor.BUS_FIELDS}

        left = ttk.Frame(frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(frame)
        right.grid(row=0, column=1, sticky="nsew")

        xp_box = ttk.LabelFrame(left, text="Bus-Erfahrung", padding=14)
        xp_box.pack(fill="x")
        xp_var = self._add_field(xp_box, 0, by_key["bus_experience_points"])
        xp_btns = ttk.Frame(xp_box)
        xp_btns.grid(row=1, column=1, sticky="w", padx=14, pady=(2, 0))
        ttk.Button(xp_btns, text="+ 10.000", style="Small.TButton",
                   command=lambda: self._bump(xp_var, 10_000, 99_999_999)).pack(side="left")
        ttk.Button(xp_btns, text="max", style="Small.TButton",
                   command=lambda: xp_var.set("99999999")).pack(side="left", padx=6)

        skill_box = ttk.LabelFrame(left, text="Bus-Skills", padding=14)
        skill_box.pack(fill="x", pady=(12, 0))
        for row, spec in enumerate(editor.BUS_FIELDS[1:]):
            self._add_field(skill_box, row, spec, kind="spin")
        ttk.Label(
            skill_box,
            style="Muted.TLabel",
            wraplength=460,
            justify="left",
            text=(
                "Die Höchstwerte der Bus-Skills sind dem Tool nicht bekannt, deshalb sind 0 bis 6 "
                "erlaubt. Erhöhe in kleinen Schritten und prüfe im Spiel, ob die Werte passen."
            ),
        ).grid(row=len(editor.BUS_FIELDS), column=0, columnspan=2, sticky="w", pady=(8, 0))

        info_box = ttk.LabelFrame(right, text="Im Save gefunden (nur lesen)", padding=14)
        info_box.pack(fill="x")
        self.bus_info_frame = info_box
        ttk.Label(info_box, text="Noch nichts geladen.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")

    @staticmethod
    def _bump(var: tk.StringVar, step: int, limit: int) -> None:
        try:
            current = int(var.get().strip() or "0")
        except ValueError:
            current = 0
        var.set(str(min(current + step, limit)))

    # ------------------------------------------------------------- helpers
    def _set_status(self, text: str) -> None:
        self.status.config(text=text)
        self.update_idletasks()

    def _profile_changed(self) -> bool:
        for key, var in self.profile_vars.items():
            old = self.loaded_profile.get(key)
            if old is not None and var.get().strip() != old:
                return True
        return False

    @property
    def dirty(self) -> bool:
        return self.doc is not None and (self.jobs_dirty or self._profile_changed())

    def _refresh_title(self) -> None:
        mark = "* " if self.dirty else ""
        self.title(f"{mark}{APP_TITLE}")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        return messagebox.askyesno(
            APP_TITLE, "Es gibt ungespeicherte Änderungen. Wirklich verwerfen?", icon="warning"
        )

    def _on_close(self) -> None:
        if self._confirm_discard():
            self.save_company()
            self.telemetry.close()
            if self.overlay is not None:
                self.overlay.destroy()
            self.destroy()

    # ------------------------------------------------------- Save selection
    def _scan_saves(self, quiet: bool = False) -> None:
        selected = self.save_entries[self.save_combo.current()].path if (
            quiet and self.save_entries and self.save_combo.current() >= 0) else None
        self.save_entries = []
        for root in saves.candidate_roots():
            self.save_entries += saves.list_saves(root)
        self.save_entries.sort(key=lambda e: e.mtime, reverse=True)
        labels = [
            f"{e.profile}  –  {e.folder}  –  {time.strftime('%d.%m.%Y %H:%M', time.localtime(e.mtime))}"
            for e in self.save_entries
        ]
        self.save_combo["values"] = labels
        if labels and quiet:
            idx = next((i for i, e in enumerate(self.save_entries) if e.path == selected), 0)
            self.save_combo.current(idx)
        elif labels:
            self.save_combo.current(0)
            self._set_status(f"{len(labels)} Spielstände gefunden. Der neueste ist vorausgewählt.")
        else:
            self.save_combo.set("")
            self._set_status("Keine Spielstände gefunden – nutze „Datei wählen …“.")

    def _load_selected(self) -> None:
        idx = self.save_combo.current()
        if idx < 0 or idx >= len(self.save_entries):
            messagebox.showinfo(APP_TITLE, "Bitte erst einen Spielstand auswählen.")
            return
        self.load_path(self.save_entries[idx].path)

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="game.sii auswählen",
            filetypes=[("ETS2-Save", "game.sii"), ("SII-Dateien", "*.sii"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> bool:
        if not self._confirm_discard():
            return False
        self.config(cursor="watch")
        self._set_status("Lade …")
        try:
            doc = sii.load(path)
            if doc.first("economy") is None or doc.first("bank") is None:
                raise sii.SiiError(
                    "Das sieht nicht nach einem Spielstand (game.sii) aus. "
                    "Info-Dateien (info.sii) oder Profil-Dateien lassen sich hier nicht bearbeiten."
                )
        except sii.SiiError as exc:
            self.config(cursor="")
            self._set_status("Laden fehlgeschlagen.")
            messagebox.showerror(APP_TITLE, str(exc))
            return False
        finally:
            self.config(cursor="")

        self.doc, self.path, self.jobs_dirty = doc, path, False
        self._offers_cache = None
        self.file_label.config(text=path)
        self._populate()
        self.save_btn.config(state="normal")
        self._set_status("Geladen.")
        self._refresh_title()
        if self.company is None:
            self.overview.refresh()
            self._set_status(f"Geladen. Für die Busfirma brauchst du {eur(busco.FOUNDING_COST)} auf dem ETS2-Konto.")
        else:
            try:
                money = editor.read_values(doc, editor.ALL_FIELDS).get("money_account")
                if money is not None:                    # base = save, open company changes stay reserved
                    self.company.sync_to_game(editor.parse_int(money, "Kontostand"), os.path.getmtime(path))
                    self.company_changed()
                added = self.company.catalog.merge(BusCatalog.from_doc(doc))
                if added:
                    self.company_changed()
                    self._set_status(f"Geladen. {added} neue Strecken für die Busfirma übernommen.")
            except (CompanyError, sii.SiiError):
                pass
        return True

    # ----------------------------------------------------------- Display
    def _populate(self) -> None:
        assert self.doc is not None
        self.loaded_profile = editor.read_values(self.doc, editor.ALL_FIELDS)
        for spec in editor.ALL_FIELDS:
            val = self.loaded_profile.get(spec.key)
            widget = self.field_widgets[spec.key]
            widget.config(state="normal")
            self.profile_vars[spec.key].set(val if val is not None else "")
            if val is None:
                widget.config(state="disabled")
        self._fill_jobs()
        self._fill_bus_info()
        self._refresh_header()
        self.buslines_page.invalidate()
        self.buslines_page.refresh()

    def _all_offers(self) -> list[editor.JobOffer]:
        if self.doc is None:
            return []
        if self._offers_cache is None:
            self._offers_cache = editor.list_offers(self.doc)
        return self._offers_cache

    def _fill_jobs(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if not self.doc:
            return
        try:
            now = editor.game_time(self.doc)
        except sii.SiiError:
            now = 0
        needle = self.filter_var.get().strip().lower()
        rows = []
        show_empty = self.show_empty_var.get()
        for o in self._all_offers():
            if o.is_empty and not show_empty:
                continue
            exp = editor._safe_int(o.values.get("expiration_time"))
            rows.append(
                (
                    o,
                    (
                        editor.pretty_place(o.source_key),
                        o.slot,
                        editor.pretty_place(o.target_key) if o.target_key else "",
                        o.cargo_name if not o.is_empty else "(leer)",
                        o.values.get("shortest_distance_km", "") if not o.is_empty else "",
                        o.values.get("urgency", "") if not o.is_empty else "",
                        round((exp - now) / 60, 1) if exp and not o.is_empty else "",
                    ),
                )
            )
        col, reverse = self._sort_state
        if col:
            cols = ("start", "slot", "ziel", "fracht", "km", "dringlich", "rest")
            ci = cols.index(col)
            rows.sort(key=lambda r: self._sort_key(r[1][ci]), reverse=reverse)
        shown = 0
        for offer, values in rows:
            blob = " ".join(str(v) for v in values).lower()
            if needle and needle not in blob:
                continue
            self.tree.insert(
                "", "end", iid=f"{offer.company_unit}|{offer.slot}", values=values,
                tags=("odd" if shown % 2 else "even",),
            )
            shown += 1
        self._update_edit_btn()

    @staticmethod
    def _sort_key(value):
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (1, str(value).lower())

    def _sort_by(self, col: str) -> None:
        prev_col, prev_rev = self._sort_state
        self._sort_state = (col, (not prev_rev) if prev_col == col else False)
        self._fill_jobs()

    def _fill_bus_info(self) -> None:
        for child in self.bus_info_frame.winfo_children():
            child.destroy()
        info = editor.read_bus_info(self.doc) if self.doc else {}
        if not info:
            ttk.Label(self.bus_info_frame, text="Keine Bus-Daten im Save.", style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            return
        for row, (key, value) in enumerate(info.items()):
            ttk.Label(self.bus_info_frame, text=key, style="Muted.TLabel", wraplength=230).grid(
                row=row, column=0, sticky="w", pady=3
            )
            ttk.Label(self.bus_info_frame, text=theme.format_int(value)).grid(
                row=row, column=1, sticky="e", padx=(18, 0)
            )

    def _update_edit_btn(self) -> None:
        self.edit_btn.config(state="normal" if self.tree.selection() else "disabled")

    # ------------------------------------------------------------ Jobs
    def _selected_offer(self) -> editor.JobOffer | None:
        sel = self.tree.selection()
        if not sel or not self.doc:
            return None
        unit, slot = sel[0].rsplit("|", 1)
        for o in self._all_offers():
            if o.company_unit == unit and o.slot == int(slot):
                return o
        return None

    def _edit_selected(self) -> None:
        offer = self._selected_offer()
        if offer is None:
            return
        JobDialog(self, offer)

    def job_applied(self) -> None:
        self.jobs_dirty = True
        self._offers_cache = None
        self._fill_jobs()
        self._refresh_title()
        self._set_status("Auftrag geändert (noch nicht gespeichert).")

    def lines_applied(self) -> None:
        self.jobs_dirty = True
        self.buslines_page.invalidate()
        self.buslines_page.refresh()
        self._refresh_title()
        self._set_status("Bus-Auftrag geändert (noch nicht gespeichert).")

    # ------------------------------------------------------------ Bus company
    def _load_company(self) -> None:
        if os.path.exists(self.company_path):
            try:
                self.company = BusCompany.load(self.company_path)
            except CompanyError as exc:
                self.after(300, lambda: messagebox.showwarning(
                    APP_TITLE, f"{exc}\n\nEs wird eine neue Firma angelegt, sobald du einen Spielstand lädst."))

    def save_company(self) -> None:
        if self.company is None:
            return
        try:
            self.company.save(self.company_path)
        except OSError as exc:
            self._set_status(f"Firmenstand konnte nicht gespeichert werden: {exc}")

    def refresh_company_pages(self) -> None:
        self.refresh_chips()
        for page in (self.overview, self.live_page, self.garages_page, self.buses_page, self.drivers_page,
                     self.routes_page, self.contracts_page, self.finance_page,
                     self.settings_page):
            page.refresh()
        if self.current_page == "map":
            self.map_page.refresh()

    def company_changed(self) -> None:
        self.save_company()
        self.refresh_company_pages()

    def _tick(self) -> None:
        try:
            self.overview.tick()
            self._map_ticks = getattr(self, "_map_ticks", 0) + 1
            if self.current_page == "map" and self._map_ticks % 4 == 0:
                self.map_page.tick()
        finally:
            self.after(TICK_MS, self._tick)

    GAME_POLL_MS = 3000
    SAVE_QUIET_S = 3.0              # the save must not change for this long before I read it
    RESCAN_MS = 5 * 60 * 1000       # re-read the save game list every 5 minutes

    def _watch_saves(self) -> None:
        """Notices when ETS2 saves (new or changed save) and then reloads."""
        try:
            entry = gamewatch.newest_save()
            stamp = (entry.path, entry.mtime) if entry else None
            if self._save_stamp is None:
                self._save_stamp = stamp                 # initial state, no event
                if entry:
                    self.last_save_mtime = entry.mtime
            elif stamp != self._save_stamp:
                self._save_stamp = stamp
                self._save_pending_since = time.time()   # file is still changing: wait a moment
            elif self._save_pending_since and time.time() - self._save_pending_since >= self.SAVE_QUIET_S:
                if entry and self._process_new_save(entry):
                    self._save_pending_since = 0.0
                elif entry is None:
                    self._save_pending_since = 0.0
        except Exception as exc:  # noqa: BLE001 - the watcher must never disturb the interface
            self._set_status(f"Save-Überwachung: {exc}")
        finally:
            self.after(3000, self._watch_saves)

    def _process_new_save(self, entry) -> bool:
        """Reads the balance from the new save and reloads the editor if nothing unsaved is in it."""
        c = self.company
        if c is not None:
            try:
                money = gamewatch.read_money(entry.path)
            except (sii.SiiError, OSError):
                return False                              # still being written: next attempt
            if money is not None:
                c.sync_to_game(money, entry.mtime)
                self.company_changed()
        self.last_save_mtime = entry.mtime
        when = time.strftime("%H:%M", time.localtime(entry.mtime))
        if self.doc is not None and self.dirty:
            self._set_status(f"Neuer Save um {when}. Der Editor hat ungespeicherte Änderungen und wurde nicht neu geladen.")
        else:
            if self.load_path(entry.path):
                self._set_status(f"Neuer Save um {when} erkannt und neu geladen.")
        self._scan_saves(quiet=True)
        return True

    def _periodic_rescan(self) -> None:
        try:
            self._scan_saves(quiet=True)
        finally:
            self.after(self.RESCAN_MS, self._periodic_rescan)

    def _poll_game(self) -> None:
        try:
            running = gamewatch.is_game_running()
            snap = self.telemetry.snapshot
            if not running and self.company is not None and self.company.settings.use_telemetry:
                running = snap.connected and not snap.demo
        except Exception:  # noqa: BLE001 - the watcher must never disturb the interface
            running = self.game_running
        was, self.game_running = self.game_running, running
        if was != running:
            self.overview.update_game_state()
            if was and not running:
                self.after(200, self._on_game_closed)
        self.after(self.GAME_POLL_MS, self._poll_game)

    def _telemetry_tick(self) -> None:
        try:
            c = self.company
            tc = self.telemetry
            tc.enabled = bool(c and c.settings.use_telemetry)
            if c is not None:
                tc.url = c.settings.telemetry_url
            snap = tc.snapshot
            if c is not None and snap.demo and not snap.paused:
                c.advance(9)          # the demo trip corresponds to about 6 game hours in 40 seconds
            events = self.tracker.update(snap) if c is not None else []
            for ev in events:
                self._trip_event(c, ev)
            self.live_page.show(snap, self.tracker, snap.demo)
            self.sync_overlay()
            if self.overlay is not None:
                self.overlay.update_trip(snap, self.tracker, c)
            if c is not None and events:
                self.company_changed()
        except Exception as exc:  # noqa: BLE001 - telemetry must never disturb the interface
            self._set_status(f"Telemetrie: {exc}")
        finally:
            self.after(1000, self._telemetry_tick)

    def sync_overlay(self) -> None:
        c = self.company
        want = bool(c and c.settings.overlay_on)
        if want and self.overlay is None:
            def moved(pos: str) -> None:
                if self.company is not None:
                    self.company.settings.overlay_pos = pos
                    self.save_company()

            def closed() -> None:
                if self.company is not None:
                    self.company.settings.overlay_on = False
                    self.save_company()
                self.live_page.refresh()
                self.sync_overlay()

            self.overlay = Overlay(self, c.settings.overlay_pos, on_move=moved, on_close=closed)
        elif not want and self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    def end_trip_manually(self) -> None:
        c = self.company
        if c is None or not self.tracker.active:
            return
        answer = messagebox.askyesnocancel(
            APP_TITLE,
            "Fahrt jetzt beenden?\n\nJa = als abgeliefert verbuchen (der Anteil geht in die Firma)\n"
            "Nein = abbrechen (es geht nichts in die Firma)\nAbbrechen = weiterfahren")
        if answer is None:
            return
        ev = self.tracker.force_end("delivered" if answer else "cancelled")
        if ev is not None:
            self._trip_event(c, ev)
            if self.telemetry.demo is not None:
                self.telemetry.stop_demo()
            self.company_changed()

    def _trip_event(self, c: BusCompany, ev: telemetry.Event) -> None:
        if ev.kind == "started":
            c.begin_trip()
            self._set_status(f"Fahrt gestartet: {busco.route_label(ev.source, ev.dest, ev.vehicle)}.")
        elif ev.kind == "cancelled":
            c.cancel_trip()
            self._set_status("Auftrag abgebrochen oder gewechselt: es geht nichts in die Firma.")
        elif ev.kind == "delivered":
            report = c.complete_trip(ev.income, ev.source, ev.dest, ev.cargo, ev.km, ev.vehicle)
            if self.telemetry.demo is not None and self.telemetry.demo.finished:
                self.telemetry.stop_demo()
            self.live_page.delivered(report)
            self.show_page("live")
            self._set_status("Fahrt abgeliefert, Bericht erstellt.")

    def _on_game_closed(self) -> None:
        c = self.company
        if c is None:
            return
        self.save_company()
        if not c.settings.follow_game and not c.settings.auto_payout:
            return
        if not c.settings.auto_payout:
            return
        self.auto_payout()

    def auto_payout(self) -> None:
        c = self.company
        if c is None:
            return
        euros, xp = gamewatch.payout_amounts(c)
        if euros == 0 and xp == 0:
            self._set_status("ETS2 wurde beendet. Es gibt nichts zu übertragen.")
            return
        entry = gamewatch.newest_save()
        if entry is None:
            messagebox.showwarning(APP_TITLE, "ETS2 wurde beendet, aber ich habe keinen Spielstand gefunden. "
                                   "Die Änderung wartet in der Firma.")
            return
        self.config(cursor="watch")
        self._set_status("ETS2 wurde beendet. Warte auf den letzten Save …")
        self.update_idletasks()
        try:
            gamewatch.wait_until_stable(entry.path)
            result = gamewatch.payout_into_save(c, entry.path)
        except (sii.SiiError, CompanyError, OSError) as exc:
            self.config(cursor="")
            self._set_status("Auszahlung fehlgeschlagen.")
            messagebox.showerror(APP_TITLE, f"Das Übertragen hat nicht geklappt:\n{exc}\n\n"
                                 "Die Änderung bleibt in der Firma.")
            return
        self.config(cursor="")
        self.company_changed()
        note = ""
        if self.path and os.path.abspath(self.path) == os.path.abspath(result.path):
            if self.dirty:
                note = ("\n\nAchtung: Der Save-Editor enthält ungespeicherte Änderungen an diesem Spielstand. "
                        "Lade ihn neu, bevor du speicherst, sonst geht die Auszahlung verloren.")
            else:
                self.jobs_dirty = False
                self.load_path(result.path)
        self._set_status("Auszahlung geschrieben.")
        messagebox.showinfo(
            APP_TITLE,
            f"ETS2 wurde beendet. In den Spielstand\n{entry.profile} – {entry.folder}\nwurden geschrieben:\n\n"
            f"Firma: {'+' if result.euros >= 0 else '-'} {eur(abs(result.euros))} am Konto "
            f"(neuer Kontostand {eur(result.new_money)})\n{busco.num(result.xp)} Bus-XP\n\n"
            f"Backup: {result.backup or '(keins)'}\n{result.info_note}{note}")

    def choose_save(self) -> None:
        self._toggle_editor(True)
        self._choose_file()

    def _create_company(self) -> bool:
        if self.doc is None:
            return False
        try:
            catalog = BusCatalog.from_doc(self.doc)
            if not catalog.routes or not catalog.models:
                raise CompanyError(
                    "Im Spielstand wurden keine Buslinien gefunden. Die Busfirma braucht ein Profil mit "
                    "Coaches-DLC, in dem schon Linienangebote angezeigt wurden.")
        except (CompanyError, sii.SiiError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return False
        start = self.account_money()
        if start is None or start < busco.FOUNDING_COST:
            messagebox.showinfo(
                APP_TITLE, f"Eine Firma gründen kostet {eur(busco.FOUNDING_COST)}. Auf deinem ETS2-Konto sind "
                f"{eur(start or 0)}. Fahr erst weiter, bis du genug hast.")
            return False
        if not messagebox.askokcancel(
                APP_TITLE, f"Firma gründen für {eur(busco.FOUNDING_COST)}?\nDas Geld wird beim Beenden von ETS2 "
                "von deinem Konto abgezogen."):
            return False
        self.company = BusCompany(catalog, start_cash=start, name=self.overview.name_var.get())
        self.company.pay_founding()
        self.company_changed()
        if not self.skip_tutorial and not i18n.ui_get("company_tour_done", False):
            self.after(400, lambda: self.start_tour("company"))
        return True

    def account_money(self) -> int | None:
        """Balance from the loaded save game (None = nothing loaded)."""
        if self.doc is None:
            return None
        value = editor.read_values(self.doc, editor.ALL_FIELDS).get("money_account")
        return None if value is None else editor.parse_int(value, "Kontostand")

    def sync_account(self, quiet: bool = True) -> None:
        """Syncs the company balance with the newest save game (reading is harmless even while ETS2 is running)."""
        c = self.company
        if c is None:
            return
        try:
            money = gamewatch.sync_company(c)
        except Exception:  # noqa: BLE001
            money = None
        if money is None:
            if not quiet:
                messagebox.showinfo(APP_TITLE, "Ich habe keinen Spielstand mit Kontostand gefunden.")
            return
        self.company_changed()
        if not quiet:
            self._set_status(f"Konto mit dem Spielstand abgeglichen: {eur(money)}.")

    def new_company(self) -> None:
        if self.doc is None:
            messagebox.showinfo(APP_TITLE, "Lade erst einen Spielstand, aus dem Strecken und Busmodelle kommen.")
            return
        if self.company is not None and not messagebox.askyesno(
                APP_TITLE, "Die bisherige Firma wird gelöscht (Backup: Datei mit Endung .bak). Neu anfangen?",
                icon="warning"):
            return
        self.overview.running = False
        self.overview.run_btn.config(text="Start")
        self._create_company()

    def _startup(self) -> None:
        self._scan_saves()
        if self.company is None and self.save_entries:
            self.after(50, self._offer_first_save)

    def _offer_first_save(self) -> None:
        if self.doc is None and self.company is None and messagebox.askyesno(
                APP_TITLE, "Für die Busfirma brauche ich Strecken und Busmodelle aus deinem neuesten "
                "Spielstand. Jetzt laden?"):
            self.load_path(self.save_entries[0].path)

    def start_payout(self) -> None:
        c = self.company
        if c is None:
            return
        if self.doc is None:
            messagebox.showinfo(APP_TITLE, "Lade zuerst den Spielstand, in den ausgezahlt werden soll.")
            return
        if self.profile_vars["money_account"].get().strip() == "":
            messagebox.showerror(APP_TITLE, "Im Spielstand wurde kein Kontostand gefunden.")
            return
        euros, xp = gamewatch.payout_amounts(c)
        if euros == 0 and xp == 0:
            messagebox.showinfo(APP_TITLE, "Es gibt nichts zu übertragen.")
            return
        if not messagebox.askokcancel(
                APP_TITLE,
                f"Auf das ETS2-Konto im geladenen Spielstand übertragen:\n\n"
                f"Firma: {'+' if euros >= 0 else '-'} {eur(abs(euros))}\nBus-XP: + {busco.num(xp)}\n\n"
                "Danach wird der Spielstand gespeichert (mit Backup). ETS2 muss geschlossen und die "
                "Steam-Cloud aus sein."):
            return
        money_var = self.profile_vars["money_account"]
        xp_var = self.profile_vars["bus_experience_points"]
        old_money, old_xp = money_var.get(), xp_var.get()
        try:
            money = editor.parse_int(old_money, "Kontostand")
            new_money = max(0, money + euros)
            money_var.set(str(new_money))
            if xp:
                if self.loaded_profile.get("bus_experience_points") is None:
                    raise sii.SiiError("Im Spielstand gibt es keine Bus-Erfahrung. Es wird nur Geld übertragen.")
                xp_var.set(str(min(99_999_999, editor.parse_int(old_xp or "0", "Bus-XP") + xp)))
        except (CompanyError, sii.SiiError) as exc:
            money_var.set(old_money)
            xp_var.set(old_xp)
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if self._save():
            c.mark_written(new_money - money, new_money, xp if self.loaded_profile.get("bus_experience_points") is not None else 0)
            self.company_changed()
        else:
            money_var.set(old_money)
            xp_var.set(old_xp)
            self.refresh_company_pages()

    # ------------------------------------------------------------ Saving
    def _save(self) -> bool:
        if not self.doc or not self.path:
            return False
        values: dict[str, int] = {}
        try:
            for spec in editor.ALL_FIELDS:
                text = self.profile_vars[spec.key].get().strip()
                if self.loaded_profile.get(spec.key) is None or text == "":
                    continue
                values[spec.key] = editor.parse_int(text, spec.label)
            editor.write_profile(self.doc, values)
        except sii.SiiError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return False

        if not messagebox.askokcancel(
            APP_TITLE,
            "Bitte prüfe vor dem Speichern:\n\n"
            "• ETS2 ist geschlossen (oder du bist im Hauptmenü)\n"
            "• Steam-Cloud ist für dein Profil ausgeschaltet\n\n"
            "Vom aktuellen Stand wird automatisch ein Backup angelegt.\n"
            "Der Save wird als Klartext gespeichert, das Spiel liest ihn normal.",
        ):
            return False
        try:
            backup = sii.save(self.doc, self.path, backup=True)
        except sii.SiiError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return False
        self.jobs_dirty = False
        self.loaded_profile = editor.read_values(self.doc, editor.ALL_FIELDS)
        self._refresh_title()
        self._fill_bus_info()
        self.buslines_page.invalidate()
        self.buslines_page.refresh()
        self._set_status("Gespeichert.")

        info_note = ""
        try:
            if editor.sync_info_file(self.path, self.doc):
                info_note = "\n\nDie Anzeige in der Ladeliste (info.sii) wurde angepasst."
        except sii.SiiError as exc:
            info_note = f"\n\nHinweis: info.sii konnte nicht angepasst werden ({exc})."
        try:
            check = editor.read_values(sii.load(self.path), editor.ALL_FIELDS).get("money_account")
            where = os.path.join(os.path.basename(os.path.dirname(os.path.dirname(self.path))),
                                 os.path.basename(os.path.dirname(self.path)))
            verify = f"\n\nKontrolle (aus der Datei gelesen): {check} €\nSpielstand: {where}"
        except (sii.SiiError, OSError):
            verify = ""
        messagebox.showinfo(
            APP_TITLE,
            "Gespeichert.\n\nBackup:\n" + (backup or "(keins)") + info_note + verify +
            "\n\nWichtig: Lade genau diesen Spielstand im Spiel neu (Hauptmenü → Laden). "
            "Ein bereits laufendes Spiel behält sein altes Geld, und sein nächster Autosave überschreibt die Änderung.",
        )
        return True


class JobDialog(tk.Toplevel):
    def __init__(self, app: App, offer: editor.JobOffer) -> None:
        super().__init__(app)
        self.app = app
        self.offer = offer
        self.title("Auftrag bearbeiten")
        self.configure(bg=theme.BG)
        self.transient(app)
        self.resizable(False, False)

        doc = app.doc
        assert doc is not None
        offers = app._all_offers()
        self.destinations = editor.list_destinations(doc)
        self.routes = editor.known_routes(offers)
        self.by_cargo: dict[str, list[editor.CargoTemplate]] = {}
        for tpl in editor.list_templates(offers):
            self.by_cargo.setdefault(tpl.cargo, []).append(tpl)
        self.cargo_names = sorted(self.by_cargo, key=editor.cargo_display_name)
        self.trailer_options: list[editor.CargoTemplate] = []
        if not self.by_cargo:
            messagebox.showerror(APP_TITLE, "Im Save wurden keine Fracht-Vorlagen gefunden.")
            self.destroy()
            return

        pad = {"padx": 10, "pady": 5}
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Start").grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(f, text=f"{editor.pretty_place(offer.source_key)}   (Slot {offer.slot})").grid(
            row=0, column=1, sticky="w", **pad
        )

        ttk.Label(f, text="Ziel").grid(row=1, column=0, sticky="w", **pad)
        self.target_var = tk.StringVar(value=offer.target_key)
        self.target = ttk.Combobox(f, textvariable=self.target_var, values=self.destinations, width=42)
        self.target.grid(row=1, column=1, sticky="w", **pad)
        self.target.bind("<<ComboboxSelected>>", lambda e: self._suggest_route())
        self.target.bind("<FocusOut>", lambda e: self._suggest_route())
        self.target.bind("<KeyRelease>", lambda e: self._filter(e, self.target, self.target_var, self.destinations))

        ttk.Label(f, text="Fracht").grid(row=2, column=0, sticky="w", **pad)
        self.cargo_var = tk.StringVar()
        self.cargo = ttk.Combobox(
            f, textvariable=self.cargo_var, values=[editor.cargo_display_name(c) for c in self.cargo_names], width=42
        )
        self.cargo.grid(row=2, column=1, sticky="w", **pad)
        self.cargo.bind("<<ComboboxSelected>>", lambda e: self._cargo_changed())
        self.cargo.bind("<FocusOut>", lambda e: self._cargo_changed())
        self.cargo.bind(
            "<KeyRelease>",
            lambda e: self._filter(
                e, self.cargo, self.cargo_var, [editor.cargo_display_name(c) for c in self.cargo_names]
            ),
        )

        ttk.Label(f, text="Anhänger").grid(row=3, column=0, sticky="w", **pad)
        self.trailer = ttk.Combobox(f, state="readonly", width=60)
        self.trailer.grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(f, text="Entfernung (km)").grid(row=4, column=0, sticky="w", **pad)
        dist = offer.values.get("shortest_distance_km", "0")
        self.dist_var = tk.StringVar(value=dist if editor._safe_int(dist) > 0 else "500")
        ttk.Spinbox(f, from_=1, to=10000, textvariable=self.dist_var, width=10).grid(
            row=4, column=1, sticky="w", **pad
        )

        ttk.Label(f, text="Dringlichkeit").grid(row=5, column=0, sticky="w", **pad)
        self.urg = ttk.Combobox(f, values=URGENCY_LABELS, state="readonly", width=16)
        self.urg.grid(row=5, column=1, sticky="w", **pad)
        self.urg.current(min(max(editor._safe_int(offer.values.get("urgency")), 0), 2))

        ttk.Label(f, text="Gültig für (Stunden)").grid(row=6, column=0, sticky="w", **pad)
        self.hours_var = tk.StringVar(value=str(self._current_hours()))
        ttk.Spinbox(f, from_=1, to=720, textvariable=self.hours_var, width=10).grid(
            row=6, column=1, sticky="w", **pad
        )

        ttk.Label(f, text="Fährzeit (Min.) / Fährpreis").grid(row=7, column=0, sticky="w", **pad)
        ferry = ttk.Frame(f)
        ferry.grid(row=7, column=1, sticky="w", **pad)
        self.ft_var = tk.StringVar(value=offer.values.get("ferry_time", "0"))
        self.fp_var = tk.StringVar(value=offer.values.get("ferry_price", "0"))
        ttk.Spinbox(ferry, from_=0, to=100000, textvariable=self.ft_var, width=8).pack(side="left")
        ttk.Spinbox(ferry, from_=0, to=100000, textvariable=self.fp_var, width=8).pack(
            side="left", padx=8
        )

        self.hint = ttk.Label(f, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self.hint.grid(row=8, column=0, columnspan=2, sticky="w", **pad)

        btns = ttk.Frame(f)
        btns.grid(row=9, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Übernehmen", style="Accent.TButton", command=self._apply).pack(side="right", padx=8)

        self._preselect_cargo()
        self.grab_set()
        self.target.focus_set()

    # ---- Cargo / trailer ----------------------------------------------
    def _preselect_cargo(self) -> None:
        current = self.offer.template()
        key = (current.cargo, current.trailer_variant, current.trailer_definition, current.units_count)
        cargo = current.cargo if current.cargo in self.by_cargo else self.cargo_names[0]
        self.cargo_var.set(editor.cargo_display_name(cargo))
        self._cargo_changed()
        for i, t in enumerate(self.trailer_options):
            if (t.cargo, t.trailer_variant, t.trailer_definition, t.units_count) == key:
                self.trailer.current(i)
                break

    def _resolve_cargo(self) -> str | None:
        typed = self.cargo_var.get().strip()
        for c in self.cargo_names:
            if editor.cargo_display_name(c) == typed:
                return c
        return None

    def _cargo_changed(self) -> None:
        cargo = self._resolve_cargo()
        if cargo is None:
            return
        options = self.by_cargo[cargo]
        if options == self.trailer_options:
            return
        self.trailer_options = options
        self.trailer["values"] = [
            f"{editor.strip_quotes(t.trailer_definition)}  |  {t.units_count} Einheiten" for t in options
        ]
        self.trailer.current(0)

    @staticmethod
    def _filter(event, combo: ttk.Combobox, var: tk.StringVar, full: list[str]) -> None:
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape"):
            return
        typed = var.get().strip().lower()
        combo["values"] = [v for v in full if typed in v.lower()] if typed else full

    # ---- Rest -------------------------------------------------------------
    def _current_hours(self) -> int:
        try:
            now = editor.game_time(self.app.doc)
            exp = editor._safe_int(self.offer.values.get("expiration_time"))
            hours = round((exp - now) / 60)
            return hours if 1 <= hours <= 720 else 72
        except sii.SiiError:
            return 72

    def _suggest_route(self) -> None:
        target = self.target_var.get().strip()
        src = self.offer.source_key
        known = self.routes.get((src, target)) or self.routes.get((target, src))
        if known:
            dist, ft, fp = known
            self.dist_var.set(str(dist))
            self.ft_var.set(str(ft))
            self.fp_var.set(str(fp))
            self.hint.config(text="Entfernung und Fähre wurden aus einem vorhandenen Auftrag übernommen.")
        else:
            self.hint.config(
                text="Für diese Strecke ist keine Entfernung bekannt – bitte selbst eintragen. "
                "Sie bestimmt die Bezahlung."
            )

    def _apply(self) -> None:
        try:
            if self._resolve_cargo() is None:
                raise sii.SiiError("Bitte eine Fracht aus der Liste wählen.")
            self._cargo_changed()
            if not self.trailer_options:
                raise sii.SiiError("Bitte einen Anhänger wählen.")
            spec = editor.JobSpec(
                company_unit=self.offer.company_unit,
                slot=self.offer.slot,
                target_key=self.target_var.get().strip(),
                template=self.trailer_options[self.trailer.current()],
                distance_km=editor.parse_int(self.dist_var.get(), "Entfernung"),
                urgency=self.urg.current(),
                hours_valid=editor.parse_int(self.hours_var.get(), "Gültigkeit"),
                ferry_time=editor.parse_int(self.ft_var.get(), "Fährzeit"),
                ferry_price=editor.parse_int(self.fp_var.get(), "Fährpreis"),
            )
            editor.apply_job(self.app.doc, spec)
        except sii.SiiError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        self.app.job_applied()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
