"""Small overlay for the running trip: always on top, semi-transparent, movable with the mouse.

It is a separate window above the game. This only works if ETS2 runs in windowed or borderless mode;
in exclusive fullscreen the game hides other windows.
"""

from __future__ import annotations

import tkinter as tk

from datetime import datetime, timedelta

from . import telemetry, theme
from .busco import BusCompany, eur, route_label


def fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d} h"


def fmt_clock(real_seconds: float, now: datetime | None = None) -> str:
    return f"{(now or datetime.now()) + timedelta(seconds=real_seconds):%H:%M} Uhr"


def fmt_arrival(real_seconds: float | None, now: datetime | None = None) -> str:
    """Real arrival time, e.g. '14:52 Uhr (in 48 Min)' (German text)."""
    if real_seconds is None:
        return ""
    clock = (now or datetime.now()) + timedelta(seconds=real_seconds)
    return f"{clock:%H:%M} Uhr (in {int(round(real_seconds / 60))} Min)"


class Overlay(tk.Toplevel):
    WIDTH = 330

    def __init__(self, master: tk.Misc, pos: str = "", on_move=None, on_close=None) -> None:
        super().__init__(master)
        self.on_move, self.on_close = on_move, on_close
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.88)
        except tk.TclError:
            pass
        self.configure(bg=theme.BORDER)
        inner = tk.Frame(self, bg=theme.PANEL)
        inner.pack(padx=1, pady=1, fill="both", expand=True)
        font = ("Segoe UI", 10)
        big = ("Segoe UI", 12, "bold")
        self.title_var, self.line_var, self.firm_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.title_lbl = tk.Label(inner, textvariable=self.title_var, bg=theme.PANEL, fg=theme.ACCENT, font=big,
                                  anchor="w")
        self.title_lbl.pack(fill="x", padx=10, pady=(8, 2))
        self.bar = tk.Canvas(inner, width=self.WIDTH - 20, height=8, bg=theme.FIELD, highlightthickness=0)
        self.bar.pack(padx=10)
        tk.Label(inner, textvariable=self.line_var, bg=theme.PANEL, fg=theme.TEXT, font=font, anchor="w").pack(
            fill="x", padx=10, pady=(6, 0))
        tk.Label(inner, textvariable=self.firm_var, bg=theme.PANEL, fg=theme.MUTED, font=font, anchor="w").pack(
            fill="x", padx=10, pady=(0, 8))
        self._progress = 0.0
        for widget in (self, inner, *inner.winfo_children()):
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<ButtonRelease-1>", self._release)
            widget.bind("<Button-3>", self._close)
        self.geometry(self._clamp(pos))
        self._dx = self._dy = 0

    def _clamp(self, pos: str) -> str:
        try:
            x, y = (int(v) for v in pos.split(","))
        except ValueError:
            x, y = 40, 40
        w, h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(max(-w, x), w * 2)          # allow several monitors, but not off into nowhere
        y = min(max(-h, y), h * 2)
        return f"+{x}+{y}"

    def _press(self, event) -> None:
        self._dx, self._dy = event.x_root - self.winfo_x(), event.y_root - self.winfo_y()

    def _drag(self, event) -> None:
        self.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _release(self, _event) -> None:
        if self.on_move:
            self.on_move(f"{self.winfo_x()},{self.winfo_y()}")

    def _close(self, _event) -> None:
        if self.on_close:
            self.on_close()

    def update_trip(self, snap: telemetry.Snapshot, tracker: telemetry.TripTracker,
                    company: BusCompany | None) -> None:
        if tracker.active:
            self.title_var.set(route_label(tracker.source, tracker.dest, tracker.vehicle))
            self._progress = tracker.progress
            arrival = fmt_arrival(tracker.real_eta_s)
            self.line_var.set(f"noch {tracker.left_m / 1000:.0f} km"
                              + (f" · Ankunft {arrival}" if arrival else "") + f" · {snap.speed_kmh:.0f} km/h")
            firm = ""
            if company is not None:
                d = company.trip_delta()
                firm = f" · Firma {d['revenue'] - d['costs']:+,.0f} €".replace(",", ".")
            self.firm_var.set(f"Auftrag {eur(tracker.income)}" + firm)
        else:
            self.title_var.set("Keine Fahrt" if snap.connected else "Nicht verbunden")
            self._progress = 0.0
            self.line_var.set("")
            self.firm_var.set("Rechtsklick schließt das Overlay")
        self.bar.delete("all")
        self.bar.create_rectangle(0, 0, (self.WIDTH - 20) * self._progress, 8, fill=theme.ACCENT, outline="")
