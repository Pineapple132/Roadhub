"""Reads the telemetry of ETS2 (read only) and detects the start and end of real trips.

The source is the ets2-telemetry-server by Funbit (HTTP/JSON, default http://127.0.0.1:25555/api/ets2/telemetry).
Without the game there is a demo trip that delivers the same data.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime

DEFAULT_URL = "http://127.0.0.1:25555/api/ets2/telemetry"
DELIVERED_WITHIN_M = 3000      # this close to the destination the end of the job counts as "delivered"


DEFAULT_TIME_SCALE = 19.0      # ETS2: 1 real second = 19 game seconds


@dataclass
class Snapshot:
    connected: bool = False
    paused: bool = False
    speed_kmh: float = 0.0
    income: int = 0                # 0 = no job
    source: str = ""
    dest: str = ""
    cargo: str = ""
    left_m: float = 0.0            # remaining navigation distance in metres
    game_time: str = ""
    demo: bool = False
    vehicle: str = ""
    eta_s: float = 0.0             # estimated travel time to the destination according to navigation (game time, seconds)
    game_s: float = 0.0            # absolute game time in seconds (0 = unknown)
    time_scale: float = 0.0        # according to the server: game seconds per real second (not always reliable)

    @property
    def has_job(self) -> bool:
        # Active = income reported AND navigation running. The income alone is not enough: the plugin
        # does not reset it after the end. Bus lines report no cities and no trailer.
        return self.income > 0 and self.left_m > 0


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_duration(text) -> float:
    """The server sends time spans as a date, e.g. '0001-01-01T02:23:55Z' = 2:23:55 hours."""
    m = re.match(r"\s*(\d+)-(\d+)-(\d+)T(\d+):(\d+):(\d+)", str(text or ""))
    if not m:
        return 0.0
    _, mo, d, h, mi, sec = (int(x) for x in m.groups())
    return ((max(0, mo - 1) * 30 + max(0, d - 1)) * 24 + h) * 3600 + mi * 60 + sec


def parse_game_seconds(text) -> float:
    """'0067-06-04T05:13:00Z' -> seconds since the start of the game (only differences matter)."""
    try:
        return (datetime.fromisoformat(str(text).rstrip("Z")) - datetime(1, 1, 1)).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def parse_funbit(data: dict) -> Snapshot:
    """Converts the JSON response of the telemetry server into a snapshot (missing fields are okay)."""
    game = data.get("game") or {}
    truck = data.get("truck") or {}
    trailer = data.get("trailer") or {}
    job = data.get("job") or {}
    nav = data.get("navigation") or {}
    return Snapshot(
        connected=bool(game.get("connected")),
        paused=bool(game.get("paused")),
        speed_kmh=abs(_num(truck.get("speed"))),
        income=int(_num(job.get("income"))),
        source=str(job.get("sourceCity") or ""),
        dest=str(job.get("destinationCity") or ""),
        cargo=str(trailer.get("name") or job.get("cargo") or ""),
        left_m=_num(nav.get("estimatedDistance")),
        eta_s=parse_duration(nav.get("estimatedTime")),
        game_s=parse_game_seconds(game.get("time")),
        time_scale=_num(game.get("timeScale")),
        game_time=str(game.get("time") or ""),
        vehicle=f"{truck.get('make') or ''} {truck.get('model') or ''}".strip(),
    )


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never use a proxy for the local address


def fetch(url: str, timeout: float = 2.0) -> Snapshot:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json"})
    with _OPENER.open(req, timeout=timeout) as resp:  # noqa: S310 - local URL from the settings
        return parse_funbit(json.loads(resp.read().decode("utf-8", errors="replace")))


def describe_error(exc: Exception) -> str:
    reason = getattr(exc, "reason", None) or exc
    return f"{type(exc).__name__}: {reason}"


class DemoDrive:
    """Simulated trip Hamburg - Copenhagen, sped up so the interface can be tested."""

    TOTAL_KM = 463.0
    RATE = 19.0                    # game seconds per real second

    def __init__(self, income: int = 6240, seconds: float = 40.0, source: str = "Hamburg",
                 dest: str = "Kopenhagen", cargo: str = "Kühlfracht") -> None:
        self.income, self.seconds = income, seconds
        self.source, self.dest, self.cargo = source, dest, cargo
        self.t0 = time.time()

    @property
    def progress(self) -> float:
        return min(1.0, (time.time() - self.t0) / self.seconds)

    def snapshot(self) -> Snapshot:
        p = self.progress
        if p >= 1.0:
            if time.time() - self.t0 - self.seconds < 2.5:   # briefly report "at the destination" so the end counts as a delivery
                return Snapshot(connected=True, demo=True, income=self.income, source=self.source,
                                dest=self.dest, cargo=self.cargo, left_m=500.0)
            return Snapshot(connected=True, demo=True)
        return Snapshot(connected=True, demo=True, game_s=1e9 + (time.time() - self.t0) * self.RATE,
                        time_scale=self.RATE, speed_kmh=78 + 8 * (1 if int(p * 20) % 2 else -1),
                        income=self.income, source=self.source, dest=self.dest, cargo=self.cargo,
                        left_m=max(500.0, self.TOTAL_KM * 1000 * (1 - p)),
                        eta_s=max(60.0, (1 - p) * self.seconds * self.RATE))

    @property
    def finished(self) -> bool:
        return self.progress >= 1.0


@dataclass
class Event:
    kind: str                      # 'started' | 'delivered' | 'cancelled'
    income: int = 0
    source: str = ""
    dest: str = ""
    cargo: str = ""
    km: float = 0.0
    vehicle: str = ""


class TripTracker:
    """Detects the job start and end from the snapshot sequence. A single snapshot without a job is
    not enough (menus, loading screens), so two in a row without a job are required."""

    def __init__(self) -> None:
        self.active = False
        self.income = 0
        self.source = self.dest = self.cargo = self.vehicle = ""
        self.total_m = 0.0
        self.left_m = 0.0
        self.last_left_m = 0.0
        self.eta_s = 0.0
        self.time_scale = 0.0
        self._samples: deque = deque()          # (real time, game time) without pauses
        self._misses = 0
        self._arrival: float | None = None      # stable arrival (real time, monotonic) like in Google Maps
        self._now = 0.0
        self._stale_income = 0          # income of the most recently finished job (stays in the plugin)

    @property
    def progress(self) -> float:
        if self.total_m <= 0:
            return 0.0
        return max(0.0, min(1.0, 1 - self.left_m / self.total_m))

    @property
    def rate(self) -> float:
        """Game seconds per real second: measured, otherwise the ETS2 default (19:1)."""
        if len(self._samples) >= 2:
            (t0, g0), (t1, g1) = self._samples[0], self._samples[-1]
            if t1 - t0 >= 30 and g1 > g0:
                return (g1 - g0) / (t1 - t0)
        return DEFAULT_TIME_SCALE

    @property
    def real_eta_s(self) -> float | None:
        """Real seconds to the destination. The arrival is fixed and only moves slowly when it clearly deviates."""
        if self._arrival is None:
            return None
        return max(0.0, self._arrival - self._now)

    def _stabilize(self, snap: Snapshot, now: float) -> None:
        last = self._now if self._now else now
        self._now = now
        if self._arrival is None:
            if snap.paused or self.eta_s <= 0:
                return
            self._arrival = now + self.eta_s / self.rate
            return
        if snap.paused:
            self._arrival += now - last              # pause: real time runs, the trip does not
            return
        if self.eta_s <= 0:
            return
        raw = now + self.eta_s / self.rate
        diff = raw - self._arrival
        remaining = max(0.0, self._arrival - now)
        if abs(diff) > max(120.0, 0.08 * remaining):       # only adjust on a noticeable deviation
            self._arrival += diff * min(1.0, 0.03 * (now - last))

    @property
    def km_total(self) -> float:
        return self.total_m / 1000

    def update(self, snap: Snapshot, now: float | None = None) -> list[Event]:
        if not snap.connected:
            self._samples.clear()
            return []                       # no connection says nothing about the job
        now = time.monotonic() if now is None else now
        if snap.paused or snap.game_s <= 0:
            self._samples.clear()           # game time does not advance during the pause
        else:
            self._samples.append((now, snap.game_s))
            while self._samples and now - self._samples[0][0] > 300:
                self._samples.popleft()
        if snap.time_scale > 0:
            self.time_scale = snap.time_scale
        events: list[Event] = []
        if snap.income != self._stale_income:
            self._stale_income = 0       # new or deleted job: lift the lock
        if snap.has_job and snap.income == self._stale_income:
            return events                # remainder of the old job, no new trip
        if snap.has_job:
            self._misses = 0
            if snap.vehicle:
                self.vehicle = snap.vehicle
            if not self.active or (snap.dest, snap.income) != (self.dest, self.income):
                if self.active:
                    events.append(self._end("cancelled"))
                self.active = True
                self.income, self.source, self.dest, self.cargo = snap.income, snap.source, snap.dest, snap.cargo
                self.total_m = self.left_m = self.last_left_m = 0.0
                self._arrival, self._now = None, 0.0
                events.append(Event("started", self.income, self.source, self.dest, self.cargo, 0.0, self.vehicle))
            if snap.cargo:
                self.cargo = snap.cargo
            self.eta_s = snap.eta_s
            self._stabilize(snap, now)
            if snap.left_m > 0:
                self.left_m = snap.left_m
                self.last_left_m = snap.left_m
                self.total_m = max(self.total_m, snap.left_m)
        elif self.active and not snap.paused:
            self._misses += 1
            if self._misses >= 2:
                near = 0 < self.last_left_m <= DELIVERED_WITHIN_M
                events.append(self._end("delivered" if near else "cancelled"))
        return events

    def force_end(self, kind: str) -> Event | None:
        """Ends a trip by hand ('delivered' or 'cancelled')."""
        if not self.active:
            return None
        return self._end(kind)

    def _end(self, kind: str) -> Event:
        ev = Event(kind, self.income, self.source, self.dest, self.cargo, self.km_total, self.vehicle)
        self._stale_income = self.income
        self.active = False
        self._misses = 0
        self.total_m = self.left_m = self.last_left_m = self.eta_s = 0.0
        self._arrival, self._now = None, 0.0
        return ev


class TelemetryClient:
    """Polls the telemetry in a background thread so the interface never hangs."""

    def __init__(self) -> None:
        self.url = DEFAULT_URL
        self.snapshot = Snapshot()
        self.error = ""
        self.enabled = False
        self.demo: DemoDrive | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.demo is not None:
                self.snapshot = self.demo.snapshot()
                self.error = ""
            elif self.enabled:
                try:
                    self.snapshot = fetch(self.url)
                    self.error = ""
                except Exception as exc:  # noqa: BLE001 - connection errors are normal while ETS2 is off
                    self.snapshot = Snapshot()
                    self.error = describe_error(exc)
            else:
                self.snapshot = Snapshot()
            self._stop.wait(1.0 if self.demo is None else 0.5)

    def start_demo(self, **kw) -> None:
        self.demo = DemoDrive(**kw)

    def stop_demo(self) -> None:
        self.demo = None

    def close(self) -> None:
        self._stop.set()
