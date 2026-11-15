"""Page "Map": Europe with cities, sights, garages and moving buses."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

from . import busco, mapdata, theme
from .busco import CompanyError, city_name, eur
from .gui_company import AssignRouteDialog, BuildGarageDialog, BuyBusDialog, _Page
from .gui_routes import RouteDialog
from .widgets import APP_TITLE

LAT_SCALE = math.cos(math.radians(53))     # longitude is compressed so that Europe does not look distorted
HOME = (14.0, 54.0, 11.5)                  # centre (longitude, latitude) and start zoom (pixels per degree of latitude)
LAND = "#252c30"
LAND_EDGE = "#3d4850"
SEA = "#11161a"
SIGHT = "#6fb7e8"
BUS_COLOR = "#ffffff"
ROUTE_COLOR = "#8a5a12"


class MapPage(_Page):
    def __init__(self, parent: tk.Misc, shell) -> None:
        super().__init__(parent, shell)
        self.cx, self.cy, self.zoom = HOME[0], HOME[1], HOME[2]
        self.selected: tuple[str, str] | None = None        # ("city" | "sight" | "bus", key)
        self._drag: tuple[int, int] | None = None
        self._moved = False
        self._first_draw = True

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        self.show_sights = tk.BooleanVar(value=True)
        self.show_routes = tk.BooleanVar(value=True)
        self.show_names = tk.BooleanVar(value=True)
        for text, var in (("Sehenswürdigkeiten", self.show_sights), ("Linien", self.show_routes),
                          ("Städtenamen", self.show_names)):
            ttk.Checkbutton(bar, text=text, variable=var, command=self.redraw).pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="Ganz Europa", style="Small.TButton", command=self.reset_view).pack(side="right")
        ttk.Button(bar, text="Zu meinen Garagen", style="Small.TButton", command=self.fit_garages).pack(
            side="right", padx=6)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=SEA, highlightthickness=1, highlightbackground=theme.BORDER)
        self.canvas.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(body, style="Card.TFrame", width=270, padding=12)
        side.pack(side="right", fill="y", padx=(10, 0))
        side.pack_propagate(False)
        self.title = ttk.Label(side, text="Karte", style="CardAccent.TLabel", wraplength=240)
        self.title.pack(anchor="w")
        self.info = ttk.Label(side, text="", style="CardCaption.TLabel", wraplength=240, justify="left")
        self.info.pack(anchor="w", pady=(6, 10))
        self.actions = ttk.Frame(side, style="Card.TFrame")
        self.actions.pack(fill="x")
        ttk.Label(
            side, style="CardCaption.TLabel", wraplength=240, justify="left",
            text=("Ziehen verschiebt die Karte, das Mausrad zoomt. Klick auf eine Stadt: Garage bauen. "
                  "Klick auf einen Bus: Details.\n\nOrange = Garage, weiß = Bus, blau = Sehenswürdigkeit."),
        ).pack(side="bottom", anchor="w")

        c = self.canvas
        c.bind("<Configure>", lambda e: self._on_resize())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.25))
        c.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 0.8))

    # ---- Coordinates --------------------------------------------------------
    def to_screen(self, lat: float, lon: float) -> tuple[float, float]:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (w / 2 + (lon - self.cx) * LAT_SCALE * self.zoom, h / 2 - (lat - self.cy) * self.zoom)

    def from_screen(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (self.cy - (y - h / 2) / self.zoom, self.cx + (x - w / 2) / (LAT_SCALE * self.zoom))

    def _fit(self, lat0: float, lat1: float, lon0: float, lon1: float) -> None:
        w, h = max(200, self.canvas.winfo_width()), max(200, self.canvas.winfo_height())
        self.cx, self.cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        self.zoom = min(h / max(0.5, lat1 - lat0), w / (max(0.5, lon1 - lon0) * LAT_SCALE)) * 0.92
        self.redraw()

    def reset_view(self) -> None:
        self._fit(35.0, 71.5, -24.0, 40.0)

    def fit_garages(self) -> None:
        c = self.company
        pts = [mapdata.coords(city) for city in (c.garages if c else {})]
        pts = [p for p in pts if p]
        if not pts:
            messagebox.showinfo(APP_TITLE, "Du hast noch keine Garage. Klick eine Stadt an und bau eine.")
            return
        lat0, lat1 = min(p[0] for p in pts) - 2, max(p[0] for p in pts) + 2
        lon0, lon1 = min(p[1] for p in pts) - 3, max(p[1] for p in pts) + 3
        self._fit(lat0, lat1, lon0, lon1)

    def _on_resize(self) -> None:
        if self._first_draw and self.canvas.winfo_width() > 100:
            self._first_draw = False
            self.reset_view()
        else:
            self.redraw()

    # ---- Mouse ---------------------------------------------------------------
    def _press(self, e) -> None:
        self._drag, self._moved = (e.x, e.y), False

    def _motion(self, e) -> None:
        if self._drag is None:
            return
        dx, dy = e.x - self._drag[0], e.y - self._drag[1]
        if abs(dx) + abs(dy) > 3:
            self._moved = True
        self._drag = (e.x, e.y)
        self.cx -= dx / (LAT_SCALE * self.zoom)
        self.cy += dy / self.zoom
        self.redraw()

    def _release(self, e) -> None:
        if not self._moved:
            self._click(e.x, e.y)
        self._drag = None

    def _wheel(self, e) -> None:
        self._zoom_at(e.x, e.y, 1.25 if e.delta > 0 else 0.8)

    def _zoom_at(self, x: float, y: float, factor: float) -> None:
        lat, lon = self.from_screen(x, y)
        self.zoom = max(4.0, min(400.0, self.zoom * factor))
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.cx = lon - (x - w / 2) / (LAT_SCALE * self.zoom)
        self.cy = lat + (y - h / 2) / self.zoom
        self.redraw()

    # ---- Drawing -----------------------------------------------------------
    def refresh(self) -> None:
        self.redraw()

    def redraw(self) -> None:
        c = self.canvas
        if c.winfo_width() < 50:
            return
        c.delete("all")
        for ring in mapdata.shapes():
            pts: list[float] = []
            for lon, lat in ring:
                x, y = self.to_screen(lat, lon)
                pts += [x, y]
            if len(pts) >= 6:
                c.create_polygon(pts, fill=LAND, outline=LAND_EDGE)
        company = self.company
        garages = company.garages if company else {}
        if company and self.show_routes.get():
            self._draw_routes(company)
        names = self.show_names.get()
        labelled_zoom = self.zoom >= 22
        playable = set(company.catalog.cities()) if company else set()
        for key, (lat, lon) in mapdata.CITY_COORDS.items():
            x, y = self.to_screen(lat, lon)
            if not (-20 < x < c.winfo_width() + 20 and -20 < y < c.winfo_height() + 20):
                continue
            if key in garages:
                r = 7
                c.create_oval(x - r, y - r, x + r, y + r, fill=theme.ACCENT, outline=theme.ON_ACCENT, width=2)
                if names:
                    c.create_text(x + 10, y, text=city_name(key), anchor="w", fill=theme.ACCENT,
                                  font=("TkDefaultFont", 9, "bold"))
            else:
                r = 3 if key in playable or not company else 2
                c.create_oval(x - r, y - r, x + r, y + r, fill="#aab4ba", outline="")
                if names and (labelled_zoom or self.selected == ("city", key)):
                    c.create_text(x + 6, y, text=city_name(key), anchor="w", fill=theme.MUTED,
                                  font=("TkDefaultFont", 8))
        if self.show_sights.get():
            for key, (lat, lon) in mapdata.SIGHT_COORDS.items():
                x, y = self.to_screen(lat, lon)
                if not (-20 < x < c.winfo_width() + 20 and -20 < y < c.winfo_height() + 20):
                    continue
                x, y = x + 4, y - 4
                c.create_polygon(x, y - 5, x + 5, y, x, y + 5, x - 5, y, fill=SIGHT, outline=SEA)
                if names and (self.zoom >= 40 or self.selected == ("sight", key)):
                    c.create_text(x + 8, y, text=mapdata.sight_label(key), anchor="w", fill=SIGHT,
                                  font=("TkDefaultFont", 8))
        if self.selected and self.selected[0] in ("city", "sight"):
            pos = mapdata.coords(self.selected[1])
            if pos:
                x, y = self.to_screen(*pos)
                c.create_oval(x - 11, y - 11, x + 11, y + 11, outline=theme.TEXT, width=2)
        self.draw_buses()

    def _draw_routes(self, company) -> None:
        c = self.canvas
        drawn: set[tuple[str, str]] = set()
        for bus in company.buses.values():
            stops = company.bus_stops(bus)
            for x, y in zip(stops, stops[1:]):
                if (x, y) in drawn or (y, x) in drawn:
                    continue
                drawn.add((x, y))
                a, b = mapdata.coords(x), mapdata.coords(y)
                if a and b:
                    (x0, y0), (x1, y1) = self.to_screen(*a), self.to_screen(*b)
                    c.create_line(x0, y0, x1, y1, fill=ROUTE_COLOR, dash=(4, 3))

    def draw_buses(self) -> None:
        c = self.canvas
        c.delete("bus")
        company = self.company
        if company is None:
            return
        for bus in company.buses.values():
            start, end, frac, status = company.bus_state(bus)
            a, b = mapdata.coords(start), mapdata.coords(end)
            if not a or not b:
                continue
            lat, lon = a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac
            x, y = self.to_screen(lat, lon)
            moving = status == "unterwegs"
            if not moving:           # parked buses next to the city so the garage stays clickable
                x, y = x + 9, y + 8
            r = 5 if moving else 3
            c.create_rectangle(x - r, y - r, x + r, y + r, fill=BUS_COLOR if moving else "#9aa3a8",
                               outline=theme.ACCENT if self.selected == ("bus", str(bus.id)) else SEA,
                               width=2, tags="bus")

    # ---- Click --------------------------------------------------------------
    def _click(self, x: float, y: float) -> None:
        company = self.company
        best: tuple[float, tuple[str, str]] | None = None

        def consider(dist: float, item: tuple[str, str], limit: float = 11) -> None:
            nonlocal best
            if dist <= limit and (best is None or dist < best[0]):
                best = (dist, item)

        if company:
            for bus in company.buses.values():
                start, end, frac, status = company.bus_state(bus)
                a, b = mapdata.coords(start), mapdata.coords(end)
                if a and b and status == "unterwegs":
                    bx, by = self.to_screen(a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)
                    consider(math.hypot(bx - x, by - y) - 2, ("bus", str(bus.id)))
        for key, (lat, lon) in mapdata.CITY_COORDS.items():
            cx_, cy_ = self.to_screen(lat, lon)
            consider(math.hypot(cx_ - x, cy_ - y), ("city", key))
        if self.show_sights.get():
            for key, (lat, lon) in mapdata.SIGHT_COORDS.items():
                sx, sy = self.to_screen(lat, lon)
                consider(math.hypot(sx + 4 - x, sy - 4 - y), ("sight", key), 9)
        self.selected = best[1] if best else None
        self.show_selection()
        self.redraw()

    # ---- Sidebar ---------------------------------------------------------
    def _clear_actions(self) -> None:
        for w in self.actions.winfo_children():
            w.destroy()

    def _button(self, text: str, command, accent: bool = False) -> None:
        ttk.Button(self.actions, text=text, command=command,
                   style="Accent.TButton" if accent else "TButton").pack(fill="x", pady=3)

    def show_selection(self, buttons: bool = True) -> None:
        if buttons:
            self._clear_actions()
        company = self.company
        sel = self.selected
        if sel is None or company is None:
            self.title.config(text="Karte")
            self.info.config(text="Wähle eine Stadt, eine Sehenswürdigkeit oder einen Bus." if company else
                                  "Lade einen Spielstand, um eine Busfirma zu starten.")
            return
        kind, key = sel
        if kind == "city":
            self.title.config(text=city_name(key))
            garage = company.garages.get(key)
            dests = company.catalog.destinations(key)
            sights = [d for d in dests if d[0].startswith("viewpoints.")]
            lines = [f"{len(dests) - len(sights)} Linien und {len(sights)} Sehenswürdigkeiten ab hier."]
            if key not in company.catalog.cities():
                lines = ["Hier kennt dein Save keine Linien, eine Garage ist nicht möglich."]
            if garage:
                buses = company.garage_buses(key)
                lines.insert(0, f"Garage: {busco.GARAGE_SIZES[garage.size]['label']}\n"
                                f"Busse: {len(buses)} / {garage.capacity}\nUnterhalt: {eur(garage.upkeep)} / Tag")
            self.info.config(text="\n".join(lines))
            if not buttons:
                return
            if garage:
                self._button("Bus kaufen …", lambda: self._buy(key), True)
                self._button("Route von hier anlegen …", lambda: self._new_route(start=key))
                self._button("Garage ausbauen", lambda: self._upgrade(key))
            elif key in company.catalog.cities():
                self._button("Garage hier bauen …", lambda: self._build(key), True)
        elif kind == "sight":
            self.title.config(text=mapdata.sight_label(key))
            homes = [city for city, g in company.garages.items() if any(d[0] == key for d in company.catalog.destinations(city))]
            self.info.config(text=("Sehenswürdigkeit. Touristenfahrten gibt es ab diesen deiner Garagen: "
                                   + (", ".join(city_name(h) for h in homes) if homes else "keine (noch keine Garage mit Strecke hierhin).")
                                   + "\n\nWeise einem Bus diese Fahrt auf der Seite „Busse“ zu."))
            if buttons and company.garages:
                self._button("Ausflug dorthin anlegen …", lambda: self._new_route(stop=key), True)
        else:
            bus = company.buses.get(int(key))
            if bus is None:
                return
            self.title.config(text=f"Bus #{bus.id}")
            start, end, frac, status = company.bus_state(bus)
            driver = company.drivers.get(bus.driver) if bus.driver else None
            where = (f"unterwegs {city_name(start)} – {city_name(end)} ({frac * 100:.0f} %)"
                     if status == "unterwegs" else f"{status} in {city_name(start)}")
            line = company.line_label(bus) if company.bus_stops(bus) else "keine Linie"
            self.info.config(text=(f"{company.model(bus.model).label}\nGarage: {city_name(bus.home)}\n"
                                   f"Linie: {line}\nFahrer: {driver.name if driver else 'keiner'}\n{where}\n"
                                   f"Zustand: {bus.condition:.0f} %  ·  Fahrten: {bus.trips}\n"
                                   f"Gewinn: {eur(bus.revenue - bus.costs)}"))
            if buttons:
                self._button("Linie zuweisen …", lambda: self._route(bus))

    def _after(self) -> None:
        self.shell.company_changed()
        self.show_selection()
        self.redraw()

    def _build(self, city: str) -> None:
        BuildGarageDialog(self, self.company, preset=city).popup()
        self._after()

    def _upgrade(self, city: str) -> None:
        c = self.company
        g = c.garages[city]
        idx = busco.SIZE_ORDER.index(g.size)
        if idx + 1 >= len(busco.SIZE_ORDER):
            messagebox.showinfo(APP_TITLE, "Die Garage hat schon die höchste Stufe.")
            return
        new = busco.SIZE_ORDER[idx + 1]
        price = busco.GARAGE_SIZES[new]["price"] - busco.GARAGE_SIZES[g.size]["price"]
        if not messagebox.askokcancel(APP_TITLE, f"{city_name(city)} auf „{busco.GARAGE_SIZES[new]['label']}“ "
                                                 f"ausbauen?\nKosten: {eur(price)}"):
            return
        try:
            c.upgrade_garage(city)
        except CompanyError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self._after()

    def _new_route(self, start: str | None = None, stop: str | None = None) -> None:
        c = self.company
        if stop and not start:      # nearest garage as the start
            target = mapdata.coords(stop)
            near = [(busco._haversine(mapdata.coords(g), target), g) for g in c.garages if mapdata.coords(g)]
            start = min(near)[1] if near and target else None
        RouteDialog(self, c, preset_start=start, preset_stop=stop).popup()
        self._after()

    def _buy(self, city: str) -> None:
        BuyBusDialog(self, self.company, preset=city).popup()
        self._after()

    def _route(self, bus) -> None:
        AssignRouteDialog(self, self.company, bus).popup()
        self._after()

    # ---- Animation ------------------------------------------------------------
    def tick(self) -> None:
        self.draw_buses()
        if self.selected and self.selected[0] == "bus":
            self.show_selection(buttons=False)
