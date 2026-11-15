"""Busfirma: Zustand und Zeitraffer-Simulation (ohne Oberfläche).

Die Strecken und Busmodelle stammen aus dem ETS2-Save (Linienangebote). Alle Preise, Kosten und
Nachfragewerte sind eigene Schätzungen und nur grob an den Bus-Auftragslog eines echten Saves
angelehnt (dort: etwa 15–20 € pro Kilometer bei ~0,17 € pro Fahrgast und Kilometer).

Die Simulation ist deterministisch: Zufall wird pro Fahrt aus (Seed, Bus, Fahrtnummer) abgeleitet,
darum liefert "7 Tage am Stück" dasselbe wie "7 × 1 Tag".
"""

from __future__ import annotations

import time

import heapq
import json
import math
import os
import random
import re
from dataclasses import dataclass, field

from . import buslines, mapdata

STATE_VERSION = 1
DAY = 1440
OPERATING_START = 5 * 60        # frühestens 05:00 Uhr losfahren
TURNAROUND = 30                 # Minuten Pause am Endpunkt
FUEL_PRICE = 1.55               # €/Liter
WAGE_PER_HOUR = 24.0            # Fahrer
MAINTENANCE_PER_KM = 0.11
TOLL_PER_KM = 0.06
INSURANCE_PER_DAY = 55.0
SERVICE_THRESHOLD = 40.0        # automatische Wartung unterhalb dieses Zustands
SERVICE_COST_PER_POINT = 25.0
SERVICE_HOURS = 8
BREAKDOWN_BELOW = 25.0
MAX_DRIVE_HOURS = 9.0            # Lenkzeit pro Fahrer und Tag; danach ruht der Bus bis zum nächsten Morgen
SIM_INCOME_FACTOR = 0.3         # Anteil der Einnahmen aus simulierten Fahrten und Verträgen
XP_PER_KM = 0.1                 # bewusst sehr niedrig: simulierte Fahrten bringen nur wenige XP
XP_PER_TRIP_MAX = 20            # Standard-Obergrenze pro simulierter Fahrt (einstellbar)


def route_label(source: str, dest: str, vehicle: str = "") -> str:
    if source and dest:
        return f"{source} nach {dest}"
    return f"Bus-Linie ({vehicle})" if vehicle else "Fahrt"


def trip_xp(km: float, cap: int = XP_PER_TRIP_MAX) -> int:
    return max(0, min(int(cap), int(km * XP_PER_KM)))
LOG_LIMIT = 300
FARE_BASE = 0.48                # € pro Fahrgast und km (ein Reisebus mit ca. 50 Sitzen kommt so im Schnitt auf ca. 13 € je gefahrenem km)
TOURIST_FARE_FACTOR = 1.0       # Touristenfahrten: gleicher km-Satz, aber Mindestpreis pro Fahrgast und mehr Auslastung am Wochenende
TOURIST_MIN_TICKET = 15.0       # € pro Fahrgast mindestens
TOURIST_DWELL = 90              # Minuten Aufenthalt an der Sehenswürdigkeit statt TURNAROUND
WAGE_PER_SKILL = 1.5            # € pro Stunde Aufschlag je Skill-Stufe
TRAINING_DAYS = 2
TRAINING_COST = 5_000           # × (aktuelle Stufe + 1)
CANDIDATES_PER_WEEK = 8
CONTRACT_RATE_PER_KM = 26.0     # € pro km der Hinfahrt; die Rückfahrt ohne Fahrgäste ist darin enthalten (≈ 13 € je gefahrenem km)
CONTRACT_DAYS = 14
CONTRACT_MAX_ONEWAY_MIN = 660   # längere Strecken schafft ein Bus nicht innerhalb eines Tages hin und zurück
CONTRACT_OFFERS_PER_WEEK = 6
CONTRACT_BONUS = 0.10           # Bonus auf die Summe, wenn alle Fahrten klappen
CONTRACT_CANCEL_FEE = 0.15      # Anteil des restlichen Vertragswerts bei vorzeitigem Abbruch
ROUTE_FACTOR = 1.38             # Straßenkilometer ≈ Luftlinie × Faktor (aus den Strecken im Save)
MAX_ROUTE_STOPS = 6
LEDGER_DAYS = 120

# Finanzen: Kategorien für den Reiter "Finanzen"
INCOME_CATS = ["Linien & Ausflüge", "Verträge (inkl. Bonus)", "Echte Fahrten (schon im Spiel)"]
FOUNDING_COST = 150_000          # so viel ETS2-Geld kostet die Gründung der Firma
EXPENSE_CATS = ["Firmengründung", "Treibstoff", "Fahrerlöhne", "Wartung & Maut", "Werkstatt & Pannen", "Versicherung",
                "Garagenunterhalt", "Käufe (Garagen, Busse)", "Fahrer (Einstellung, Weiterbildung)",
                "Vertragsstrafen"]

MODEL_PRICE_FACTOR = 1.0
_GARAGE_BASE = {
    "klein": (250_000, 120.0),
    "mittel": (600_000, 300.0),
    "gross": (1_300_000, 650.0),
}
GARAGE_SIZES = {
    "klein": {"capacity": 3, "price": 250_000, "upkeep": 120.0, "label": "Klein (3 Busse)"},
    "mittel": {"capacity": 8, "price": 600_000, "upkeep": 300.0, "label": "Mittel (8 Busse)"},
    "gross": {"capacity": 20, "price": 1_300_000, "upkeep": 650.0, "label": "Groß (20 Busse)"},
}
SIZE_ORDER = ["klein", "mittel", "gross"]


# Einstellbare Werte: (Schlüssel, Gruppe, Bezeichnung, Standard, Minimum, Maximum, Schritt, Einheit)
TUNABLES = [
    ("rate_per_km", "Einnahmen", "Verdienst je gefahrenem km (Reisebus mit ca. 50 Sitzen)", 13.0, 1.0, 100.0, 0.5, "€/km"),
    ("tourist_min_ticket", "Einnahmen", "Mindestpreis pro Fahrgast bei Ausflügen", 15.0, 0.0, 500.0, 1.0, "€"),
    ("contract_bonus_pct", "Einnahmen", "Bonus, wenn ein Vertrag ohne verpasste Fahrt endet", 10.0, 0.0, 100.0, 1.0, "%"),
    ("contract_cancel_pct", "Einnahmen", "Strafe beim Vertragsabbruch (Anteil vom Restwert)", 15.0, 0.0, 100.0, 1.0, "%"),
    ("fuel_price", "Kosten", "Spritpreis", 1.55, 0.0, 10.0, 0.05, "€/Liter"),
    ("maintenance_per_km", "Kosten", "Verschleiß und Wartung", 0.11, 0.0, 10.0, 0.01, "€/km"),
    ("toll_per_km", "Kosten", "Maut", 0.06, 0.0, 10.0, 0.01, "€/km"),
    ("insurance_per_day", "Kosten", "Versicherung je Bus", 55.0, 0.0, 5000.0, 5.0, "€/Tag"),
    ("wage_per_hour", "Kosten", "Grundlohn der Fahrer", 24.0, 0.0, 500.0, 1.0, "€/Std."),
    ("wage_per_skill", "Kosten", "Lohnaufschlag je Skill-Stufe", 1.5, 0.0, 100.0, 0.5, "€/Std."),
    ("service_cost_per_point", "Kosten", "Werkstatt je fehlendem Zustandspunkt", 25.0, 0.0, 5000.0, 5.0, "€"),
    ("training_cost", "Kosten", "Weiterbildung (mal Stufe + 1)", 5000.0, 0.0, 1_000_000.0, 500.0, "€"),
    ("garage_price_pct", "Preise", "Garagenpreise", 100.0, 1.0, 1000.0, 5.0, "%"),
    ("garage_upkeep_pct", "Preise", "Garagenunterhalt", 100.0, 0.0, 1000.0, 5.0, "%"),
    ("bus_price_pct", "Preise", "Buspreise", 100.0, 1.0, 1000.0, 5.0, "%"),
    ("max_drive_hours", "Betrieb", "Max. Fahrzeit pro Fahrer und Tag", 9.0, 2.0, 24.0, 0.5, "Std."),
    ("sim_income_pct", "Einnahmen", "Einnahmen simulierter Fahrten und Verträge", 30.0, 5.0, 500.0, 5.0, "%"),
    ("xp_per_km", "Bus-XP", "Bus-XP je km einer simulierten Fahrt", 0.1, 0.0, 10.0, 0.05, "XP/km"),
    ("service_threshold", "Betrieb", "Automatische Wartung unter diesem Zustand", 40.0, 0.0, 99.0, 1.0, "%"),
    ("contract_offers", "Betrieb", "Neue Vertragsangebote pro Woche", 6.0, 1.0, 50.0, 1.0, "Stück"),
    ("candidates", "Betrieb", "Neue Fahrer-Bewerber pro Woche", 8.0, 1.0, 50.0, 1.0, "Stück"),
]
TUNE_DEFAULTS = {t[0]: t[3] for t in TUNABLES}


def apply_tuning(values: dict[str, float] | None = None) -> dict[str, float]:
    """Setzt die Rechenwerte des Moduls. Fehlende Schlüssel nehmen den Standard."""
    global FARE_BASE, CONTRACT_RATE_PER_KM, TOURIST_MIN_TICKET, CONTRACT_BONUS, CONTRACT_CANCEL_FEE, FUEL_PRICE
    global MAINTENANCE_PER_KM, TOLL_PER_KM, INSURANCE_PER_DAY, WAGE_PER_HOUR, WAGE_PER_SKILL
    global SERVICE_COST_PER_POINT, TRAINING_COST, MODEL_PRICE_FACTOR, XP_PER_KM, SERVICE_THRESHOLD
    global CONTRACT_OFFERS_PER_WEEK, CANDIDATES_PER_WEEK, MAX_DRIVE_HOURS, SIM_INCOME_FACTOR
    v = dict(TUNE_DEFAULTS)
    v.update({k: float(x) for k, x in (values or {}).items() if k in TUNE_DEFAULTS})
    FARE_BASE = 0.48 * v["rate_per_km"] / 13.0
    CONTRACT_RATE_PER_KM = 2 * v["rate_per_km"] * v["sim_income_pct"] / 100
    TOURIST_MIN_TICKET = v["tourist_min_ticket"]
    CONTRACT_BONUS = v["contract_bonus_pct"] / 100
    CONTRACT_CANCEL_FEE = v["contract_cancel_pct"] / 100
    FUEL_PRICE = v["fuel_price"]
    MAINTENANCE_PER_KM = v["maintenance_per_km"]
    TOLL_PER_KM = v["toll_per_km"]
    INSURANCE_PER_DAY = v["insurance_per_day"]
    WAGE_PER_HOUR = v["wage_per_hour"]
    WAGE_PER_SKILL = v["wage_per_skill"]
    SERVICE_COST_PER_POINT = v["service_cost_per_point"]
    TRAINING_COST = v["training_cost"]
    MODEL_PRICE_FACTOR = v["bus_price_pct"] / 100
    XP_PER_KM = v["xp_per_km"]
    MAX_DRIVE_HOURS = v["max_drive_hours"]
    SIM_INCOME_FACTOR = v["sim_income_pct"] / 100
    SERVICE_THRESHOLD = v["service_threshold"]
    CONTRACT_OFFERS_PER_WEEK = int(round(v["contract_offers"]))
    CANDIDATES_PER_WEEK = int(round(v["candidates"]))
    for key, (price, upkeep) in _GARAGE_BASE.items():
        GARAGE_SIZES[key]["price"] = int(round(price * v["garage_price_pct"] / 100))
        GARAGE_SIZES[key]["upkeep"] = upkeep * v["garage_upkeep_pct"] / 100
    return v


def clean_name(name: str) -> str:
    name = " ".join(str(name).split())[:40]
    return name or "Meine Busfirma"


def eur(value: float) -> str:
    """12345.6 -> '12.346 €' (deutsche Schreibweise)."""
    return f"{value:,.0f}".replace(",", ".") + " €"


def num(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


class CompanyError(Exception):
    """Fehlermeldung für Nutzer (deutsch)."""


# --------------------------------------------------------------------------
# Katalog (Strecken und Modelle aus dem Save)
# --------------------------------------------------------------------------

@dataclass
class BusCatalog:
    routes: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)   # (von, nach) -> (km, min)
    models: list[str] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)   # Vorlagen aus den Linienangeboten im Save

    @classmethod
    def from_doc(cls, doc) -> "BusCatalog":
        offers = buslines.list_line_offers(doc)
        routes: dict[tuple[str, str], tuple[int, int]] = {}
        for (a, b), leg in buslines.known_legs(offers).items():
            ok_a = a.startswith(("city.", "viewpoints."))
            ok_b = b.startswith(("city.", "viewpoints."))
            both_sights = a.startswith("viewpoints.") and b.startswith("viewpoints.")
            if ok_a and ok_b and not both_sights and a != b and leg.km >= 20 and leg.minutes > 0:
                routes.setdefault((a, b), (leg.km, leg.minutes))
        for (a, b), value in list(routes.items()):
            routes.setdefault((b, a), value)
        pool: list[dict] = []
        seen: set[tuple] = set()
        for o in offers:
            if o.is_empty or o.line_type != "regular":
                continue
            start = buslines.stop_label(o.source)
            stops = [start] + list(o.targets)
            if not all(x.startswith("city.") for x in stops) or len(set(stops)) != len(stops):
                continue
            if any(l.km < 5 or l.minutes <= 0 for l in o.legs):
                continue
            key = tuple(stops)
            if key in seen:
                continue
            seen.add(key)
            pool.append({"stops": stops, "legs": [[l.km, l.minutes] for l in o.legs], "dep": int(o.departure)})
        return cls(routes, buslines.list_bus_models(offers), pool)

    def add_leg(self, a: str, b: str, km: int, minutes: int) -> None:
        self.routes[(a, b)] = (km, minutes)
        self.routes.setdefault((b, a), (km, minutes))

    def estimate_leg(self, a: str, b: str) -> tuple[int, int]:
        """Bekannte Etappe oder Schätzung aus der Luftlinie (km, Minuten)."""
        if (a, b) in self.routes:
            return self.routes[(a, b)]
        pa, pb = mapdata.coords(a), mapdata.coords(b)
        if pa is None or pb is None:
            raise CompanyError("Für diese Orte kenne ich keine Position. Bitte Kilometer und Minuten selbst eintragen.")
        km = max(5, round(_haversine(pa, pb) * ROUTE_FACTOR))
        sample = [m / k for (k, m) in self.routes.values() if k >= 50]
        per_km = sorted(sample)[len(sample) // 2] if sample else 1.0
        return km, max(5, round(km * per_km))

    def cities(self) -> list[str]:
        return sorted({a for a, _ in self.routes if a.startswith("city.")})

    def sights(self) -> list[str]:
        return sorted({b for _, b in self.routes if b.startswith("viewpoints.")})

    def merge(self, other: "BusCatalog") -> int:
        known = {tuple(c["stops"]) for c in self.contracts}
        for c in other.contracts:
            if tuple(c["stops"]) not in known:
                self.contracts.append(c)
        """Übernimmt neue Strecken und Modelle (z. B. aus einem später geladenen Save). Gibt die Zahl neuer Strecken zurück."""
        added = 0
        for key, value in other.routes.items():
            if key not in self.routes:
                self.routes[key] = value
                added += 1
        for model in other.models:
            if model not in self.models:
                self.models.append(model)
        return added

    def destinations(self, city: str) -> list[tuple[str, int, int]]:
        out = [(b, km, mins) for (a, b), (km, mins) in self.routes.items() if a == city]
        return sorted(out, key=lambda r: r[1])

    def route(self, a: str, b: str) -> tuple[int, int]:
        try:
            return self.routes[(a, b)]
        except KeyError:
            raise CompanyError(f"Für {city_name(a)} – {city_name(b)} ist keine Strecke bekannt.") from None

    def hub_factor(self, city: str) -> float:
        """Größere Knotenpunkte (viele Strecken) haben etwas mehr Nachfrage."""
        count = sum(1 for (a, _) in self.routes if a == city)
        return 0.9 + 0.2 * min(1.0, count / 40)

    def to_dict(self) -> dict:
        return {"routes": [[a, b, km, m] for (a, b), (km, m) in sorted(self.routes.items())],
                "models": list(self.models), "contracts": list(self.contracts)}

    @classmethod
    def from_dict(cls, data: dict) -> "BusCatalog":
        routes = {(a, b): (int(km), int(m)) for a, b, km, m in data.get("routes", [])}
        return cls(routes, list(data.get("models", [])), list(data.get("contracts", [])))


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def city_name(city: str) -> str:
    return buslines.pretty_stop(city)


# --------------------------------------------------------------------------
# Busmodelle (aus dem Namen abgeleitet, Werte geschätzt)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelSpec:
    name: str
    label: str
    seats: int
    price: int
    fuel_l100: float
    length_m: float


_SIZE_TOKEN = re.compile(r"^(\d{3})([a-z])(\d)$")
_BRANDS = {"man": "MAN", "daf": "DAF"}


def model_spec(name: str) -> ModelSpec:
    tokens = name.split("_")
    length, kind = 12.5, "h"
    for tok in tokens:
        m = _SIZE_TOKEN.match(tok)
        if m:
            length, kind = int(m.group(1)) / 10, m.group(2)
            break
    hp = 450
    for tok in reversed(tokens):
        if tok.isdigit() and len(tok) == 3 and 300 <= int(tok) <= 700:
            hp = int(tok)
            break
    seats = 82 if kind == "d" else round(length * 3.9)
    price = int(round((120_000 + seats * 2_600 + hp * 200) * MODEL_PRICE_FACTOR / 1000.0) * 1000)
    fuel = round(24 + length * 0.5, 1)
    brand = _BRANDS.get(tokens[0], tokens[0].title())
    series = tokens[1].title() if len(tokens) > 1 else ""
    deck = "Doppeldecker" if kind == "d" else "Reisebus"
    label = f"{brand} {series} · {deck} {str(length).replace('.', ',')} m · {hp} PS"
    return ModelSpec(name, label, seats, price, fuel, length)


# --------------------------------------------------------------------------
# Zustand
# --------------------------------------------------------------------------

@dataclass
class Driver:
    id: int
    name: str
    eco: int = 0
    punctual: int = 0
    service: int = 0
    safety: int = 0
    km: int = 0
    bus_id: int | None = None
    training: str | None = None      # Name des Skills, der gerade trainiert wird
    training_until: int = 0
    hired_at: int = 0

    @property
    def wage(self) -> float:
        return WAGE_PER_HOUR + WAGE_PER_SKILL * (self.eco + self.punctual + self.service + self.safety)

    @property
    def rank(self) -> str:
        return ("Neuling" if self.km < 10_000 else "Erfahren" if self.km < 50_000
                else "Profi" if self.km < 150_000 else "Veteran")


@dataclass
class Candidate:
    key: str
    name: str
    eco: int
    punctual: int
    service: int
    safety: int

    @property
    def fee(self) -> int:
        return 1_500 + 1_200 * (self.eco + self.punctual + self.service + self.safety)

    @property
    def wage(self) -> float:
        return WAGE_PER_HOUR + WAGE_PER_SKILL * (self.eco + self.punctual + self.service + self.safety)


SKILLS = {"eco": "Öko-Fahrweise", "punctual": "Pünktlichkeit", "service": "Fahrgast-Service", "safety": "Sicherheit"}
MAX_SKILL = 5
FIRST_NAMES = ["Jan", "Anna", "Lukas", "Marta", "Pierre", "Sofia", "Mehmet", "Ingrid", "Piotr", "Elena",
               "Hans", "Carla", "Dimitri", "Maja", "Oskar", "Lucia", "Tomas", "Freya", "Marco", "Nora",
               "Andrei", "Ines", "Björn", "Katarina", "Luis", "Petra", "Viktor", "Aino", "Rafael", "Selma"]
LAST_NAMES = ["Müller", "Kowalski", "Dubois", "Rossi", "Nowak", "Svensson", "Garcia", "Jansen", "Novák", "Yilmaz",
              "Larsen", "Costa", "Popescu", "Virtanen", "Horvat", "Fischer", "Moreau", "Bianchi", "Kaya", "Lindgren",
              "Silva", "Wagner", "Petrov", "Hansen", "Ferrari", "Dąbrowski", "Mäkinen", "Álvarez", "Bauer", "Haas"]


@dataclass
class Route:
    id: int
    name: str
    stops: list[str]               # Start (Garagenstadt) zuerst; der Bus pendelt hin und zurück
    kind: str = "linie"            # 'linie' oder 'ausflug'


@dataclass
class Contract:
    id: int
    name: str
    stops: list[str]
    legs: list[list[int]]          # [km, Minuten] je Etappe der Hinfahrt
    pay_per_run: float
    bus_id: int
    departures: list[int]          # alle geplanten Abfahrten (Spielminuten)
    next_idx: int = 0
    done: int = 0
    missed: int = 0
    earned: float = 0.0
    status: str = "läuft"          # läuft, abgeschlossen, abgebrochen

    @property
    def total_km(self) -> int:
        return sum(l[0] for l in self.legs)

    @property
    def total_minutes(self) -> int:
        return sum(l[1] for l in self.legs)


@dataclass
class ContractOffer:
    key: str
    name: str
    stops: list[str]
    legs: list[list[int]]
    dep: int
    pay_per_run: float
    period: int
    runs: int

    @property
    def start(self) -> str:
        return self.stops[0]

    @property
    def total_km(self) -> int:
        return sum(l[0] for l in self.legs)

    @property
    def total_minutes(self) -> int:
        return sum(l[1] for l in self.legs)


@dataclass
class Garage:
    city: str
    size: str

    @property
    def capacity(self) -> int:
        return GARAGE_SIZES[self.size]["capacity"]

    @property
    def upkeep(self) -> float:
        return GARAGE_SIZES[self.size]["upkeep"]


@dataclass
class Bus:
    id: int
    model: str
    home: str                      # Garage (Stadt)
    destination: str | None = None  # Gegenstelle der Linie; None = nicht eingesetzt
    at: str = ""                   # aktueller Endpunkt
    condition: float = 100.0
    next_free: int = 0             # Minute, ab der der Bus wieder abfahren kann
    km: int = 0
    trips: int = 0
    pax: int = 0
    revenue: float = 0.0
    costs: float = 0.0
    driver: int | None = None
    route_id: int | None = None    # eigene Route (sonst: Pendel Garage – destination)
    idx: int = 0                   # Position auf der eigenen Route
    dir: int = 1
    contract_id: int | None = None
    segments: list = field(default_factory=list)   # Vertragsfahrt: [[von, nach, Start, Ende], ...]
    trip_from: str = ""            # letzte Fahrt: Start, Ziel, Abfahrt und Ankunft (Minuten)
    trip_to: str = ""
    trip_start: int = 0
    trip_end: int = 0
    drive_day: int = -1            # Tag, für den drive_min gilt (Lenkzeit-Grenze)
    drive_min: int = 0             # an diesem Tag schon gefahrene Minuten


@dataclass
class Settings:
    profit_multiplier: float = 1.0
    auto_service: bool = True
    follow_game: bool = False      # Firma läuft nur, solange ETS2 läuft
    auto_payout: bool = False      # beim Beenden von ETS2 automatisch in den neuesten Save auszahlen
    reserve: int = 300_000         # Betrag, der bei der Auszahlung in der Kasse bleibt
    game_speed: float = 1.0        # Simulationsminuten pro echter Sekunde (bei follow_game)
    use_telemetry: bool = False    # echte Fahrten per Telemetrie verfolgen und Geld in die Firma geben
    job_share: float = 1.0         # Anteil vom Auftragsverdienst, der in die Firmenkasse geht (1.0 = alles)
    telemetry_url: str = "http://127.0.0.1:25555/api/ets2/telemetry"
    overlay_on: bool = False       # Overlay über dem Spiel anzeigen
    overlay_pos: str = ""          # "x,y" der letzten Position
    respect_hours: bool = True     # An Zeiten halten: Lenkzeit pro Fahrer und Tag begrenzen (MAX_DRIVE_HOURS)
    xp_per_trip: int = XP_PER_TRIP_MAX   # Bus-XP pro simulierter Fahrt (Obergrenze)
    tuning: dict = field(default_factory=dict)   # Abweichungen von den Standardwerten (siehe TUNABLES)


@dataclass
class Report:
    revenue: float = 0.0
    costs: float = 0.0
    trips: int = 0
    km: int = 0
    pax: int = 0

    @property
    def profit(self) -> float:
        return self.revenue - self.costs


class BusCompany:
    def __init__(self, catalog: BusCatalog, start_cash: float = 1_500_000, seed: int = 1,
                 name: str = "Meine Busfirma") -> None:
        self.catalog = catalog
        self.name = clean_name(name)
        self.seed = seed
        self.now = 0                    # Minuten seit Start (Tag 1, Montag 00:00)
        self.cash = float(start_cash)
        self.start_cash = float(start_cash)
        self.garages: dict[str, Garage] = {}
        self.buses: dict[int, Bus] = {}
        self.next_bus_id = 1
        self.reputation = 1.0
        self.settings = Settings()
        self.apply_tuning()
        self.ledger: dict[int, dict[str, float]] = {}
        self.fin: dict[int, dict[str, float]] = {}      # Tag -> Kategorie -> Betrag
        self.fin_total: dict[str, float] = {}
        self.log: list[tuple[int, str]] = []
        self.days_charged = 0
        self.total_paid_out = 0.0
        self.xp_total = 0
        self.xp_pending = 0
        # Ein gemeinsames Konto: cash = geschätzter ETS2-Kontostand. sync_base = Kontostand beim letzten Abgleich
        # mit dem Spielstand, game_earned = Verdienst echter Fahrten seit dann (steckt schon im Spiel).
        self.sync_base = float(start_cash)
        self.game_earned = 0.0
        self.earned_at = 0.0          # Zeitpunkt (Unix) des letzten echten Verdiensts
        self.totals = {"revenue": 0.0, "costs": 0.0, "pax": 0, "trips": 0, "xp": 0}
        self.trip_mark: dict | None = None
        self.trip_log: list[dict] = []
        self.routes: dict[int, Route] = {}
        self.next_route_id = 1
        self.contracts: dict[int, Contract] = {}
        self.next_contract_id = 1
        self.accepted_offers: list[str] = []
        self.drivers: dict[int, Driver] = {}
        self.next_driver_id = 1
        self.hired_keys: list[str] = []

    # ---- Hilfen ---------------------------------------------------------
    def model(self, name: str) -> ModelSpec:
        return model_spec(name)

    def _log(self, text: str, at: int | None = None) -> None:
        self.log.append((self.now if at is None else at, text))
        if len(self.log) > LOG_LIMIT:
            del self.log[: len(self.log) - LOG_LIMIT]

    def _day(self, day: int) -> dict[str, float]:
        entry = self.ledger.setdefault(day, {"revenue": 0.0, "costs": 0.0, "trips": 0, "pax": 0, "km": 0})
        oldest = day - LEDGER_DAYS
        for d in [d for d in self.ledger if d < oldest]:
            del self.ledger[d]
        return entry

    def fmt_time(self, minute: int | None = None) -> str:
        m = self.now if minute is None else minute
        names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        day = m // DAY
        return f"Tag {day + 1} · {names[day % 7]} {(m % DAY) // 60:02d}:{m % 60:02d}"

    def garage_buses(self, city: str) -> list[Bus]:
        return [b for b in self.buses.values() if b.home == city]

    def garage_drivers(self, city: str) -> list[Driver]:
        """Fahrer, die einem Bus dieser Garage zugeteilt sind."""
        out = []
        for bus in self.garage_buses(city):
            driver = self.drivers.get(bus.driver) if bus.driver else None
            if driver is not None:
                out.append(driver)
        return out

    def bus_status(self, bus: Bus) -> str:
        driver = self.drivers.get(bus.driver) if bus.driver else None
        if bus.contract_id in self.contracts:
            return "Vertrag" if driver else "kein Fahrer"
        if not bus.destination:
            return "nicht eingesetzt"
        if driver is None:
            return "kein Fahrer"
        if driver.training:
            return "Fahrer in Schulung"
        if bus.next_free > self.now:
            return "unterwegs bis " + self.fmt_time(bus.next_free).split("· ")[-1]
        return "bereit"

    def garage_stats(self, city: str) -> dict:
        """Wirtschaftlichkeit einer Garage: Summen über alle Busse, die hier stehen."""
        buses = self.garage_buses(city)
        g = self.garages[city]
        revenue = sum(b.revenue for b in buses)
        costs = sum(b.costs for b in buses)
        km = sum(b.km for b in buses)
        drivers = self.garage_drivers(city)
        return {
            "buses": len(buses), "capacity": g.capacity, "drivers": len(drivers),
            "training": sum(1 for d in drivers if d.training),
            "revenue": revenue, "costs": costs, "profit": revenue - costs, "km": km,
            "trips": sum(b.trips for b in buses), "pax": sum(b.pax for b in buses),
            "fixed_per_day": g.upkeep + INSURANCE_PER_DAY * len(buses),
            "profit_per_km": (revenue - costs) / km if km else 0.0,
            "profit_per_bus": (revenue - costs) / len(buses) if buses else 0.0,
            "avg_condition": sum(b.condition for b in buses) / len(buses) if buses else 0.0,
        }

    # ---- Aktionen -------------------------------------------------------
    def _book(self, day: int, cat: str, amount: float) -> None:
        """Bucht Einnahme oder Ausgabe (immer positiv) in die Finanzübersicht."""
        if not amount:
            return
        entry = self.fin.setdefault(day, {})
        entry[cat] = entry.get(cat, 0.0) + amount
        self.fin_total[cat] = self.fin_total.get(cat, 0.0) + amount
        for d in [d for d in self.fin if d < day - LEDGER_DAYS]:
            del self.fin[d]

    def finance_period(self, first_day: int, last_day: int) -> dict[str, float]:
        out: dict[str, float] = {}
        for d, e in self.fin.items():
            if first_day <= d <= last_day:
                for k, v in e.items():
                    out[k] = out.get(k, 0.0) + v
        return out

    def _pay(self, amount: float, what: str, cat: str = "") -> None:
        if amount > self.cash:
            raise CompanyError(
                f"Dafür fehlt Geld: {what} kostet {eur(amount)}, auf deinem Konto sind {eur(self.cash)}."
            )
        self.cash -= amount
        if cat:
            self._book(self.now // DAY, cat, amount)

    def build_garage(self, city: str, size: str = "klein") -> Garage:
        if size not in GARAGE_SIZES:
            raise CompanyError("Unbekannte Garagengröße.")
        if city not in self.catalog.cities():
            raise CompanyError("In dieser Stadt gibt es keine bekannten Linien.")
        if city in self.garages:
            raise CompanyError(f"In {city_name(city)} gibt es schon eine Garage.")
        self._pay(GARAGE_SIZES[size]["price"], "die Garage", "Käufe (Garagen, Busse)")
        garage = self.garages[city] = Garage(city, size)
        self._log(f"Garage in {city_name(city)} gebaut ({GARAGE_SIZES[size]['label']}).")
        return garage

    def upgrade_garage(self, city: str) -> Garage:
        garage = self.garages.get(city)
        if garage is None:
            raise CompanyError("Hier gibt es keine Garage.")
        idx = SIZE_ORDER.index(garage.size)
        if idx + 1 >= len(SIZE_ORDER):
            raise CompanyError("Die Garage hat schon die höchste Stufe.")
        new = SIZE_ORDER[idx + 1]
        self._pay(GARAGE_SIZES[new]["price"] - GARAGE_SIZES[garage.size]["price"], "den Ausbau",
                  "Käufe (Garagen, Busse)")
        garage.size = new
        self._log(f"Garage in {city_name(city)} ausgebaut ({GARAGE_SIZES[new]['label']}).")
        return garage

    def buy_bus(self, city: str, model_name: str) -> Bus:
        garage = self.garages.get(city)
        if garage is None:
            raise CompanyError("Für diese Stadt gibt es noch keine Garage.")
        if model_name not in self.catalog.models:
            raise CompanyError("Dieses Busmodell ist nicht bekannt.")
        if len(self.garage_buses(city)) >= garage.capacity:
            raise CompanyError(f"Die Garage in {city_name(city)} ist voll. Bau sie aus oder nutze eine andere.")
        spec = self.model(model_name)
        self._pay(spec.price, "den Bus", "Käufe (Garagen, Busse)")
        bus = Bus(self.next_bus_id, model_name, city, None, city, 100.0, self.now)
        self.next_bus_id += 1
        self.buses[bus.id] = bus
        self._log(f"Bus #{bus.id} gekauft ({spec.label}) für {city_name(city)}.")
        return bus

    def sell_bus(self, bus_id: int) -> float:
        bus = self._bus(bus_id)
        spec = self.model(bus.model)
        value = round(spec.price * 0.55 * (0.6 + 0.4 * bus.condition / 100))
        self.cash += value
        if bus.driver in self.drivers:
            self.drivers[bus.driver].bus_id = None
        del self.buses[bus_id]
        self._log(f"Bus #{bus_id} für {eur(value)} verkauft.")
        return value

    def _check_free_for_route(self, bus: Bus) -> None:
        if bus.contract_id in self.contracts:
            raise CompanyError("Der Bus fährt gerade einen Vertrag. Schließe oder beende ihn zuerst.")

    def assign_route(self, bus_id: int, destination: str | None) -> None:
        bus = self._bus(bus_id)
        self._check_free_for_route(bus)
        bus.route_id, bus.idx, bus.dir = None, 0, 1
        if destination is None:
            bus.destination = None
            self._log(f"Bus #{bus.id} aus dem Linienverkehr genommen.")
            return
        self.catalog.route(bus.home, destination)  # prüft, ob es die Strecke gibt
        bus.destination = destination
        bus.at = bus.home
        bus.next_free = max(bus.next_free, self.now)
        self._log(f"Bus #{bus.id} fährt jetzt {city_name(bus.home)} – {city_name(destination)}.")

    # ---- Eigene Routen ----------------------------------------------------
    def create_route(self, name: str, stops: list[str], kind: str = "linie",
                     legs: list[tuple[int, int]] | None = None) -> Route:
        """Legt eine eigene Route an. legs = (km, Minuten) je Etappe, sonst bekannt oder geschätzt."""
        name = name.strip()
        if not name:
            raise CompanyError("Bitte der Route einen Namen geben.")
        if any(r.name.lower() == name.lower() for r in self.routes.values()):
            raise CompanyError("Eine Route mit diesem Namen gibt es schon.")
        if kind not in ("linie", "ausflug"):
            raise CompanyError("Die Art muss Linie oder Ausflug sein.")
        if not (2 <= len(stops) <= MAX_ROUTE_STOPS):
            raise CompanyError(f"Eine Route braucht 2 bis {MAX_ROUTE_STOPS} Haltestellen.")
        if not stops[0].startswith("city."):
            raise CompanyError("Die Route muss in einer Stadt beginnen.")
        for x, y in zip(stops, stops[1:]):
            if x == y:
                raise CompanyError("Zwei aufeinanderfolgende Haltestellen dürfen nicht gleich sein.")
        if legs is not None and len(legs) != len(stops) - 1:
            raise CompanyError("Zu jeder Etappe gehören Kilometer und Minuten.")
        planned = []
        for i, (x, y) in enumerate(zip(stops, stops[1:])):
            km, minutes = legs[i] if legs is not None else self.catalog.estimate_leg(x, y)
            if not (1 <= km <= 5000) or minutes < 1:
                raise CompanyError(
                    f"Die Etappe {city_name(x)} – {city_name(y)} braucht 1 bis 5000 km und mindestens 1 Minute.")
            planned.append((x, y, int(km), int(minutes)))
        for x, y, km, minutes in planned:
            self.catalog.add_leg(x, y, km, minutes)
            if legs is not None:
                self.catalog.routes[(y, x)] = (km, minutes)
        route = Route(self.next_route_id, name, list(stops), kind)
        self.next_route_id += 1
        self.routes[route.id] = route
        self._log(f"Route „{name}“ angelegt ({' – '.join(city_name(x) for x in stops)}).")
        return route

    def delete_route(self, route_id: int) -> None:
        route = self.routes.get(route_id)
        if route is None:
            raise CompanyError("Diese Route gibt es nicht.")
        if any(b.route_id == route_id for b in self.buses.values()):
            raise CompanyError("Die Route wird noch von einem Bus gefahren.")
        del self.routes[route_id]
        self._log(f"Route „{route.name}“ gelöscht.")

    def assign_custom_route(self, bus_id: int, route_id: int) -> None:
        bus = self._bus(bus_id)
        self._check_free_for_route(bus)
        route = self.routes.get(route_id)
        if route is None:
            raise CompanyError("Diese Route gibt es nicht.")
        if route.stops[0] != bus.home:
            raise CompanyError(f"Die Route beginnt in {city_name(route.stops[0])}, der Bus gehört aber zur "
                               f"Garage in {city_name(bus.home)}.")
        for x, y in zip(route.stops, route.stops[1:]):
            self.catalog.route(x, y)
        bus.route_id, bus.idx, bus.dir = route.id, 0, 1
        bus.destination = route.stops[-1]
        bus.at = bus.home
        bus.next_free = max(bus.next_free, self.now)
        self._log(f"Bus #{bus.id} fährt jetzt die Route „{route.name}“.")

    def bus_stops(self, bus: Bus) -> list[str]:
        """Haltestellen der Linie eines Busses (für Karte und Anzeige)."""
        if bus.contract_id in self.contracts:
            return list(self.contracts[bus.contract_id].stops)
        if bus.route_id in self.routes:
            return list(self.routes[bus.route_id].stops)
        return [bus.home, bus.destination] if bus.destination else []

    def line_label(self, bus: Bus) -> str:
        if bus.contract_id in self.contracts:
            return f"Vertrag: {self.contracts[bus.contract_id].name}"
        if bus.route_id in self.routes:
            return self.routes[bus.route_id].name
        return f"{city_name(bus.home)} – {city_name(bus.destination)}" if bus.destination else "–"

    # ---- Verträge ------------------------------------------------------------
    def contract_offers(self) -> list[ContractOffer]:
        """Vertragsangebote dieser Woche (aus den Linienangeboten deines Saves, ab deinen Garagenstädten)."""
        week = self.now // (7 * DAY)
        rng = random.Random(f"{self.seed}:contracts:{week}")
        cities = set(self.catalog.cities())
        eligible = [i for i, c in enumerate(self.catalog.contracts)
                    if c["stops"][0] in self.garages and sum(l[1] for l in c["legs"]) <= CONTRACT_MAX_ONEWAY_MIN
                    and all(x in cities for x in c["stops"])]
        picked = sorted(rng.sample(eligible, min(CONTRACT_OFFERS_PER_WEEK, len(eligible))))
        out = []
        for i in picked:
            key = f"{week}:{i}"
            if key in self.accepted_offers:
                continue
            c = self.catalog.contracts[i]
            minutes = sum(l[1] for l in c["legs"])
            km = sum(l[0] for l in c["legs"])
            period = max(1, math.ceil((2 * minutes + 2 * TURNAROUND + 60) / DAY))
            out.append(ContractOffer(key, " – ".join(city_name(x) for x in c["stops"]), list(c["stops"]),
                                     [list(l) for l in c["legs"]], int(c["dep"]) % DAY,
                                     round(km * CONTRACT_RATE_PER_KM), period, math.ceil(CONTRACT_DAYS / period)))
        return out

    def accept_contract(self, key: str, bus_id: int) -> Contract:
        offer = next((o for o in self.contract_offers() if o.key == key), None)
        if offer is None:
            raise CompanyError("Dieses Angebot gibt es nicht mehr.")
        bus = self._bus(bus_id)
        if bus.contract_id in self.contracts:
            raise CompanyError("Dieser Bus fährt schon einen Vertrag.")
        if bus.home != offer.start:
            raise CompanyError(f"Der Vertrag beginnt in {city_name(offer.start)}. Nimm einen Bus aus dieser Garage.")
        if bus.driver not in self.drivers:
            raise CompanyError("Der Bus hat keinen Fahrer.")
        day0 = self.now // DAY + (0 if offer.dep > self.now % DAY + 60 else 1)
        deps = [(day0 + k * offer.period) * DAY + offer.dep for k in range(offer.runs)]
        contract = Contract(self.next_contract_id, offer.name, offer.stops, offer.legs, offer.pay_per_run,
                            bus.id, deps)
        self.next_contract_id += 1
        self.contracts[contract.id] = contract
        self.accepted_offers.append(key)
        self.accepted_offers = self.accepted_offers[-200:]
        bus.contract_id = contract.id
        bus.at = bus.home
        bus.next_free = deps[0]
        self._log(f"Vertrag „{offer.name}“ angenommen: {offer.runs} Fahrten, "
                  f"{eur(offer.pay_per_run)} je Fahrt (Bus #{bus.id}).")
        return contract

    def cancel_contract(self, contract_id: int) -> float:
        contract = self.contracts.get(contract_id)
        if contract is None or contract.status != "läuft":
            raise CompanyError("Dieser Vertrag läuft nicht mehr.")
        remaining = len(contract.departures) - contract.next_idx
        fee = round(CONTRACT_CANCEL_FEE * remaining * contract.pay_per_run)
        self._pay(fee, "die Vertragsstrafe", "Vertragsstrafen")
        self._day(self.now // DAY)["costs"] += fee
        contract.status = "abgebrochen"
        bus = self.buses.get(contract.bus_id)
        if bus is not None and bus.contract_id == contract.id:
            bus.contract_id, bus.segments = None, []
            bus.next_free = max(bus.next_free, self.now)
        self.reputation = max(0.7, self.reputation - 0.03)
        self._log(f"Vertrag „{contract.name}“ abgebrochen (Strafe {eur(fee)}).")
        return fee

    def _contract_step(self, bus: Bus, contract: Contract, report: Report) -> None:
        """Fährt (oder verpasst) die nächste geplante Fahrt des Vertrags."""
        t0 = contract.departures[contract.next_idx]
        driver = self.drivers[bus.driver]
        self._update_training(driver, t0)
        spec = self.model(bus.model)
        rng = random.Random(f"{self.seed}:c{contract.id}:{contract.next_idx}")
        contract.next_idx += 1
        free = t0
        if driver.training:
            contract.missed += 1
            self.reputation = max(0.7, self.reputation - 0.01)
            self._log(f"Vertragsfahrt „{contract.name}“ verpasst: der Fahrer ist in der Weiterbildung.", t0)
        else:
            km = contract.total_km
            delay = rng.randint(10, 45) if rng.random() < 0.15 * (1 - 0.12 * driver.punctual) else 0
            leg_minutes = [max(1, round(l[1] * (1 - 0.01 * driver.punctual))) for l in contract.legs]
            stops = contract.stops
            segments, clock = [], t0
            for i, m in enumerate(leg_minutes):
                end = clock + m + (delay if i == len(leg_minutes) - 1 else 0)
                segments.append([stops[i], stops[i + 1], clock, end])
                clock = end
            clock += TURNAROUND
            for i in range(len(leg_minutes) - 1, -1, -1):
                segments.append([stops[i + 1], stops[i], clock, clock + leg_minutes[i]])
                clock += leg_minutes[i]
            back_end = clock
            revenue = contract.pay_per_run * self.settings.profit_multiplier
            fuel = spec.fuel_l100 * (1 - 0.05 * driver.eco)
            c_fuel = 2 * km * fuel / 100 * FUEL_PRICE
            c_mt = 2 * km * (MAINTENANCE_PER_KM + TOLL_PER_KM)
            c_wage = ((back_end - t0) + 30) / 60 * driver.wage
            costs = c_fuel + c_mt + c_wage
            extra, free = self._maintain(bus, driver, rng, 2 * km, t0, segments[len(leg_minutes) - 1][3], back_end,
                                         f"Vertrag „{contract.name}“")
            costs += extra
            if delay >= 15:
                self.reputation = max(0.7, self.reputation - 0.003)
            else:
                self.reputation = min(1.3, self.reputation + 0.002)
            pax = round(spec.seats * 0.8)
            bus.segments = segments
            bus.at = contract.stops[0]
            bus.km += 2 * km
            bus.trips += 1
            bus.pax += pax
            bus.revenue += revenue
            bus.costs += costs
            driver.km += 2 * km
            self.cash += revenue - costs
            contract.done += 1
            contract.earned += revenue - costs
            xp = trip_xp(km, self.settings.xp_per_trip)
            self.xp_total += xp
            self.xp_pending += xp
            entry = self._day(t0 // DAY)
            entry["revenue"] += revenue
            entry["costs"] += costs
            entry["trips"] += 1
            entry["pax"] += pax
            entry["km"] += 2 * km
            fd = t0 // DAY
            self._book(fd, "Verträge (inkl. Bonus)", revenue)
            self._book(fd, "Treibstoff", c_fuel)
            self._book(fd, "Wartung & Maut", c_mt)
            self._book(fd, "Fahrerlöhne", c_wage)
            self._book(fd, "Werkstatt & Pannen", extra)
            report.revenue += revenue
            report.costs += costs
            report.trips += 1
            report.km += 2 * km
            report.pax += pax
        if contract.next_idx >= len(contract.departures):
            bonus = 0.0
            if contract.missed == 0:
                bonus = round(CONTRACT_BONUS * contract.pay_per_run * contract.done * self.settings.profit_multiplier)
                self.cash += bonus
                contract.earned += bonus
                self._day(t0 // DAY)["revenue"] += bonus
                self._book(t0 // DAY, "Verträge (inkl. Bonus)", bonus)
                report.revenue += bonus
            contract.status = "abgeschlossen"
            bus.contract_id = None
            bus.next_free = max(free, t0)
            self._log(f"Vertrag „{contract.name}“ abgeschlossen: {contract.done} Fahrten, {contract.missed} verpasst"
                      + (f", Bonus {eur(bonus)}." if bonus else "."), t0)
        else:
            bus.next_free = max(contract.departures[contract.next_idx], free)

    def service_bus(self, bus_id: int) -> float:
        bus = self._bus(bus_id)
        if bus.condition >= 99.5:
            raise CompanyError("Der Bus ist in einwandfreiem Zustand.")
        cost = round((100 - bus.condition) * SERVICE_COST_PER_POINT)
        self._pay(cost, "die Wartung", "Werkstatt & Pannen")
        bus.costs += cost
        self._day(self.now // DAY)["costs"] += cost
        bus.condition = 100.0
        bus.next_free = max(bus.next_free, self.now) + SERVICE_HOURS * 60
        self._log(f"Bus #{bus.id} gewartet ({eur(cost)}).")
        return cost

    def _bus(self, bus_id: int) -> Bus:
        try:
            return self.buses[bus_id]
        except KeyError:
            raise CompanyError(f"Bus #{bus_id} gibt es nicht.") from None

    def set_name(self, name: str) -> None:
        self.name = clean_name(name)

    def pay_founding(self) -> None:
        """Gründungskosten vom gemeinsamen Konto (wird beim Beenden von ETS2 in den Save geschrieben)."""
        self.cash -= FOUNDING_COST
        self._book(0, "Firmengründung", FOUNDING_COST)
        self._log(f"Firma gegründet ({eur(FOUNDING_COST)} Gründungskosten).")

    def apply_tuning(self) -> None:
        """Stellt die Rechenwerte auf diese Firma ein und passt laufende Verträge dem aktuellen km-Satz an."""
        apply_tuning(self.settings.tuning)
        for ct in getattr(self, "contracts", {}).values():
            if ct.status == "läuft":
                ct.pay_per_run = round(ct.total_km * CONTRACT_RATE_PER_KM)

    def set_tuning(self, values: dict[str, float]) -> None:
        clean: dict[str, float] = {}
        for key, group, label, default, lo, hi, step, unit in TUNABLES:
            if key not in values:
                continue
            x = float(values[key])
            if not lo <= x <= hi:
                raise CompanyError(f"„{label}“ muss zwischen {lo:g} und {hi:g} {unit} liegen.")
            if abs(x - default) > 1e-9:
                clean[key] = x
        self.settings.tuning = clean
        self.apply_tuning()

    def set_settings(self, profit_multiplier: float | None = None, auto_service: bool | None = None,
                     follow_game: bool | None = None, auto_payout: bool | None = None,
                     reserve: int | None = None, game_speed: int | None = None,
                     use_telemetry: bool | None = None, job_share: float | None = None,
                     xp_per_trip: int | None = None, respect_hours: bool | None = None,
                     telemetry_url: str | None = None) -> None:
        if respect_hours is not None:
            self.settings.respect_hours = bool(respect_hours)
        if use_telemetry is not None:
            self.settings.use_telemetry = bool(use_telemetry)
        if xp_per_trip is not None:
            if not 0 <= xp_per_trip <= 1000:
                raise CompanyError("Die Bus-XP pro Fahrt müssen zwischen 0 und 1000 liegen.")
            self.settings.xp_per_trip = int(xp_per_trip)
        if job_share is not None:
            if not 0 <= job_share <= 1:
                raise CompanyError("Der Anteil muss zwischen 0 und 100 % liegen.")
            self.settings.job_share = float(job_share)
        if telemetry_url is not None and telemetry_url.strip():
            self.settings.telemetry_url = telemetry_url.strip()
        if follow_game is not None:
            self.settings.follow_game = bool(follow_game)
        if auto_payout is not None:
            self.settings.auto_payout = bool(auto_payout)
        if reserve is not None:
            if reserve < 0:
                raise CompanyError("Die Reserve darf nicht negativ sein.")
            self.settings.reserve = int(reserve)
        if game_speed is not None:
            if game_speed <= 0:
                raise CompanyError("Die Geschwindigkeit muss größer als 0 sein.")
            self.settings.game_speed = float(game_speed)
        if profit_multiplier is not None:
            if not (0.1 <= profit_multiplier <= 5.0):
                raise CompanyError("Der Einnahmen-Faktor muss zwischen 0,1 und 5 liegen.")
            self.settings.profit_multiplier = float(profit_multiplier)
        if auto_service is not None:
            self.settings.auto_service = bool(auto_service)

    # ---- Fahrer -----------------------------------------------------------
    def candidates(self) -> list[Candidate]:
        """Bewerber dieser Woche (wechseln jede Spielwoche, schon eingestellte fehlen)."""
        week = self.now // (7 * DAY)
        rng = random.Random(f"{self.seed}:cand:{week}")
        out = []
        for i in range(CANDIDATES_PER_WEEK):
            levels = [rng.choices([0, 1, 2, 3], [50, 30, 15, 5])[0] for _ in SKILLS]
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            key = f"{week}:{i}"
            if key not in self.hired_keys:
                out.append(Candidate(key, name, *levels))
        return out

    def hire(self, key: str) -> Driver:
        cand = next((c for c in self.candidates() if c.key == key), None)
        if cand is None:
            raise CompanyError("Diese Bewerbung ist nicht mehr aktuell.")
        self._pay(cand.fee, "die Einstellung", "Fahrer (Einstellung, Weiterbildung)")
        driver = Driver(self.next_driver_id, cand.name, cand.eco, cand.punctual, cand.service, cand.safety,
                        hired_at=self.now)
        self.next_driver_id += 1
        self.drivers[driver.id] = driver
        self.hired_keys.append(key)
        self.hired_keys = self.hired_keys[-200:]
        self._log(f"{driver.name} eingestellt (Vermittlung {eur(cand.fee)}).")
        return driver

    def _driver(self, driver_id: int) -> Driver:
        try:
            return self.drivers[driver_id]
        except KeyError:
            raise CompanyError(f"Fahrer #{driver_id} gibt es nicht.") from None

    def fire(self, driver_id: int) -> None:
        driver = self._driver(driver_id)
        if driver.bus_id is not None and driver.bus_id in self.buses:
            self.buses[driver.bus_id].driver = None
        del self.drivers[driver_id]
        self._log(f"{driver.name} entlassen.")

    def assign_driver(self, driver_id: int, bus_id: int | None) -> None:
        """Setzt den Fahrer auf einen Bus (None = vom Bus nehmen). Ein Bus hat einen Fahrer."""
        driver = self._driver(driver_id)
        if driver.bus_id is not None and driver.bus_id in self.buses:
            self.buses[driver.bus_id].driver = None
        driver.bus_id = None
        if bus_id is None:
            return
        bus = self._bus(bus_id)
        if bus.driver is not None and bus.driver in self.drivers:
            self.drivers[bus.driver].bus_id = None
        bus.driver = driver.id
        driver.bus_id = bus.id
        bus.next_free = max(bus.next_free, self.now)
        self._log(f"{driver.name} fährt jetzt Bus #{bus.id}.")

    def training_cost(self, driver: Driver, skill: str) -> int:
        return TRAINING_COST * (getattr(driver, skill) + 1)

    def train(self, driver_id: int, skill: str) -> int:
        driver = self._driver(driver_id)
        if skill not in SKILLS:
            raise CompanyError("Unbekannter Skill.")
        self._update_training(driver, self.now)
        if driver.training:
            raise CompanyError(f"{driver.name} ist schon in einer Weiterbildung.")
        if getattr(driver, skill) >= MAX_SKILL:
            raise CompanyError(f"„{SKILLS[skill]}“ hat schon die höchste Stufe ({MAX_SKILL}).")
        cost = self.training_cost(driver, skill)
        self._pay(cost, "die Weiterbildung", "Fahrer (Einstellung, Weiterbildung)")
        driver.training = skill
        driver.training_until = self.now + TRAINING_DAYS * DAY
        self._day(self.now // DAY)["costs"] += cost
        self._log(f"{driver.name} bildet sich weiter: {SKILLS[skill]} ({eur(cost)}, {TRAINING_DAYS} Tage).")
        return cost

    def _update_training(self, driver: Driver, when: int) -> None:
        if driver.training and driver.training_until <= when:
            skill = driver.training
            setattr(driver, skill, min(MAX_SKILL, getattr(driver, skill) + 1))
            driver.training = None
            self._log(f"{driver.name} hat die Weiterbildung „{SKILLS[skill]}“ abgeschlossen "
                      f"(jetzt Stufe {getattr(driver, skill)}).", driver.training_until)

    def driver_bus_label(self, driver: Driver) -> str:
        return f"Bus #{driver.bus_id}" if driver.bus_id is not None else "frei"

    # ---- Position (für die Karte) ------------------------------------------
    def bus_state(self, bus: Bus) -> tuple[str, str, float, str]:
        """(von, nach, Anteil 0..1, Status) – Status: 'unterwegs', 'wartet', 'steht'."""
        for seg in bus.segments:
            if seg[2] <= self.now < seg[3]:
                return seg[0], seg[1], (self.now - seg[2]) / max(1, seg[3] - seg[2]), "unterwegs"
        if bus.trip_end > bus.trip_start and bus.trip_start <= self.now < bus.trip_end:
            frac = (self.now - bus.trip_start) / (bus.trip_end - bus.trip_start)
            return bus.trip_from, bus.trip_to, frac, "unterwegs"
        place = bus.at or bus.home
        active = bus.destination or bus.contract_id in self.contracts
        return place, place, 0.0, "wartet" if active else "steht"

    # ---- Gemeinsames Konto ------------------------------------------------
    def firm_delta(self) -> float:
        """Änderung des ETS2-Kontos durch die Firma (Gewinn, Käufe, Kosten). Verdienst echter Fahrten
        ist schon im Spiel und zählt hier nicht."""
        return self.cash - self.sync_base - self.game_earned

    def sync_to_game(self, money: float, save_mtime: float | None = None) -> None:
        """Gleicht mit dem Kontostand eines Spielstands ab. Noch nicht geschriebene Firmenänderungen bleiben.
        Ist der Save älter als der letzte echte Verdienst, steckt der noch nicht darin: dann bleibt er erhalten."""
        delta = self.firm_delta()
        keep = self.game_earned if (save_mtime is not None and save_mtime < self.earned_at) else 0.0
        self.sync_base = float(money)
        self.game_earned = keep
        self.cash = float(money) + delta + keep

    def reset_to_game(self, money: float) -> None:
        """Konto und Firmen-Datei komplett auf den Stand eines Spielstands setzen (nichts Offenes bleibt)."""
        self.cash = self.sync_base = float(money)
        self.game_earned = 0.0

    def mark_written(self, written: float, new_money: float, xp: int = 0) -> None:
        """Nach erfolgreichem Schreiben in den Spielstand: Firmenänderung (written) gilt als übertragen."""
        self.xp_pending -= xp
        self.total_paid_out += written
        self.cash = float(new_money)
        self.sync_base = float(new_money)
        self.game_earned = 0.0
        self._log(f"{eur(written)} und {num(xp)} XP in den Spielstand übertragen.")

    # ---- Simulation -------------------------------------------------------
    def advance(self, minutes: int) -> Report:
        if minutes <= 0:
            return Report()
        target = self.now + minutes
        report = Report()
        self._miss_without_driver(target)
        heap = [(b.next_free, b.id) for b in self.buses.values()
                if (b.destination or b.contract_id in self.contracts) and b.driver in self.drivers]
        heapq.heapify(heap)
        while heap and heap[0][0] <= target:
            when, bus_id = heapq.heappop(heap)
            bus = self.buses.get(bus_id)
            if bus is None or bus.driver not in self.drivers:
                continue
            contract = self.contracts.get(bus.contract_id) if bus.contract_id is not None else None
            if contract is not None and contract.status == "läuft":
                self._contract_step(bus, contract, report)
                heapq.heappush(heap, (bus.next_free, bus.id))
                continue
            if not bus.destination:
                continue
            driver = self.drivers[bus.driver]
            self._update_training(driver, when)
            if driver.training:                # Fahrer ist in der Weiterbildung: Bus wartet
                bus.next_free = driver.training_until
                heapq.heappush(heap, (bus.next_free, bus.id))
                continue
            allowed = self._operating(when)
            if allowed != when:          # nachts nicht losfahren: auf 05:00 Uhr verschieben
                bus.next_free = allowed
                heapq.heappush(heap, (allowed, bus.id))
                continue
            self._run_trip(bus, report)
            heapq.heappush(heap, (bus.next_free, bus.id))
        self._charge_days(target, report)
        self.now = target
        for driver in self.drivers.values():
            self._update_training(driver, target)
        self.totals["revenue"] += report.revenue
        self.totals["costs"] += report.costs
        self.totals["pax"] += report.pax
        self.totals["trips"] += report.trips
        return report

    # ---- Echte Fahrten (Telemetrie) ------------------------------------------
    def begin_trip(self) -> None:
        """Merkt sich den Firmenstand beim Start einer echten Fahrt."""
        self.trip_mark = {"cash": self.cash, "xp": self.xp_total, **{k: v for k, v in self.totals.items()}}

    def cancel_trip(self) -> None:
        self.trip_mark = None

    def trip_delta(self) -> dict:
        """Was die Firma seit Fahrtbeginn gemacht hat."""
        mark = self.trip_mark or {"revenue": self.totals["revenue"], "costs": self.totals["costs"],
                                  "pax": self.totals["pax"], "trips": self.totals["trips"], "xp": self.xp_total}
        return {
            "revenue": self.totals["revenue"] - mark["revenue"],
            "costs": self.totals["costs"] - mark["costs"],
            "pax": int(self.totals["pax"] - mark["pax"]),
            "trips": int(self.totals["trips"] - mark["trips"]),
            "xp": int(self.xp_total - mark["xp"]),
        }

    def complete_trip(self, income: int, source: str, dest: str, cargo: str, km: float, vehicle: str = "") -> dict:
        """Echte Fahrt abgeliefert: Verdienst aufs gemeinsame Konto, Fahrtbericht anlegen."""
        if income < 0:
            raise CompanyError("Der Auftragsverdienst darf nicht negativ sein.")
        delta = self.trip_delta()
        share = int(income)
        cash_before = self.cash
        self.cash += income              # der Verdienst ist im Spiel schon auf dem Konto
        self.game_earned += income
        self.earned_at = time.time()
        self._book(self.now // DAY, "Echte Fahrten (schon im Spiel)", income)
        report = {
            "when": self.now, "source": source, "dest": dest, "cargo": cargo, "vehicle": vehicle, "km": int(round(km)),
            "income": int(income), "share": share, "revenue": round(delta["revenue"]),
            "costs": round(delta["costs"]), "profit": round(delta["revenue"] - delta["costs"]),
            "pax": delta["pax"], "trips": delta["trips"], "xp": delta["xp"],
            "cash_before": round(cash_before), "cash_after": round(self.cash),
        }
        self.trip_log.append(report)
        del self.trip_log[:-50]
        self.trip_mark = None
        self._log(f"Fahrt {route_label(source, dest, vehicle)}: {eur(income)} verdient, "
                  f"Firmengewinn {eur(report['profit'])}.")
        return report

    def _miss_without_driver(self, target: int) -> None:
        """Vertragsfahrten, für die der Bus keinen Fahrer hat, gelten als verpasst."""
        for contract in self.contracts.values():
            if contract.status != "läuft":
                continue
            bus = self.buses.get(contract.bus_id)
            if bus is not None and bus.driver in self.drivers:
                continue
            while contract.next_idx < len(contract.departures) and contract.departures[contract.next_idx] <= target:
                contract.missed += 1
                contract.next_idx += 1
                self.reputation = max(0.7, self.reputation - 0.01)
                self._log(f"Vertragsfahrt „{contract.name}“ verpasst: der Bus hat keinen Fahrer.",
                          contract.departures[contract.next_idx - 1])
            if contract.next_idx >= len(contract.departures):
                contract.status = "abgeschlossen"
                if bus is not None:
                    bus.contract_id = None
                self._log(f"Vertrag „{contract.name}“ abgeschlossen: {contract.done} Fahrten, {contract.missed} verpasst.")

    def _charge_days(self, target: int, report: Report) -> None:
        while (self.days_charged + 1) * DAY <= target:
            upkeep = sum(g.upkeep for g in self.garages.values())
            cost = upkeep + INSURANCE_PER_DAY * len(self.buses)
            self._book(self.days_charged, "Garagenunterhalt", upkeep)
            self._book(self.days_charged, "Versicherung", INSURANCE_PER_DAY * len(self.buses))
            if cost:
                self.cash -= cost
                self._day(self.days_charged)["costs"] += cost
                report.costs += cost
            self.days_charged += 1

    @staticmethod
    def _operating(minute: int) -> int:
        tod = minute % DAY
        return minute if tod >= OPERATING_START else minute - tod + OPERATING_START

    @staticmethod
    def _demand_base(km: int) -> float:
        if km < 150:
            return 0.80
        if km < 500:
            return 0.72
        if km < 900:
            return 0.62
        return 0.50

    def _maintain(self, bus: Bus, driver: Driver, rng: random.Random, km: int, t0: int, arrival: int,
                  free: int, label: str) -> tuple[float, int]:
        """Verschleiß, Panne oder automatische Wartung. Gibt (Zusatzkosten, neue Freizeit des Busses) zurück."""
        bus.condition = max(0.0, bus.condition - km * 0.008 * (1 - 0.07 * driver.safety))
        extra = 0.0
        if bus.condition < BREAKDOWN_BELOW and rng.random() < 0.10 * (1 - 0.15 * driver.safety):
            repair = rng.randint(1_500, 6_000)
            extra += repair
            free += rng.randint(12, 36) * 60
            self.reputation = max(0.7, self.reputation - 0.02)
            self._log(f"Panne bei Bus #{bus.id} ({label}): {eur(repair)} Reparatur.", t0)
        elif self.settings.auto_service and bus.condition < SERVICE_THRESHOLD:
            cost = round((100 - bus.condition) * SERVICE_COST_PER_POINT)
            extra += cost
            bus.condition = 100.0
            free += SERVICE_HOURS * 60
            self._log(f"Bus #{bus.id} automatisch gewartet ({eur(cost)}).", arrival)
        return extra, free

    def _run_trip(self, bus: Bus, report: Report) -> None:
        t0 = bus.next_free
        custom = self.routes.get(bus.route_id) if bus.route_id is not None else None
        if custom is not None:
            stops, idx, step = custom.stops, bus.idx, bus.dir
            if not (0 <= idx + step < len(stops)):
                step = -step
            a, b = stops[idx], stops[idx + step]
        else:
            a = bus.at or bus.home
            b = bus.destination if a == bus.home else bus.home
        km, minutes = self.catalog.route(a, b)
        spec = self.model(bus.model)
        driver = self.drivers[bus.driver]
        tourist = a.startswith("viewpoints.") or b.startswith("viewpoints.")
        rng = random.Random(f"{self.seed}:{bus.id}:{bus.trips}")

        day, tod = divmod(t0, DAY)
        weekday = day % 7
        hour = tod / 60
        if tourist:      # Ausflügler fahren vor allem am Wochenende und tagsüber
            weekday_factor = {5: 1.3, 6: 1.3, 4: 1.0}.get(weekday, 0.85)
            hour_factor = 1.0 if 8 <= hour < 16 else 0.8
        else:
            weekday_factor = {4: 1.15, 6: 1.15, 5: 1.0}.get(weekday, 0.9)
            hour_factor = 1.1 if (7 <= hour < 10 or 16 <= hour < 19) else (0.75 if hour < 6 or hour >= 22 else 1.0)
        noise = max(0.5, rng.gauss(1.0, 0.12))
        hub = (self.catalog.hub_factor(a) + self.catalog.hub_factor(b)) / 2
        base = 0.70 if tourist else self._demand_base(km)
        load = base * weekday_factor * hour_factor * noise * hub * self.reputation * (1 + 0.03 * driver.service)
        load = min(1.0, max(0.10, load))
        pax = round(spec.seats * load)

        fare = FARE_BASE * (100 / max(km, 100)) ** 0.12
        if tourist:
            ticket = max(TOURIST_MIN_TICKET, km * fare * TOURIST_FARE_FACTOR)
            revenue = pax * ticket * self.settings.profit_multiplier * SIM_INCOME_FACTOR
        else:
            revenue = pax * km * fare * self.settings.profit_multiplier * SIM_INCOME_FACTOR

        late_chance = 0.15 * (1 - 0.12 * driver.punctual)
        delay = rng.randint(10, 45) if rng.random() < late_chance else 0
        drive_minutes = round(minutes * (1 - 0.01 * driver.punctual)) + delay
        fuel_l100 = spec.fuel_l100 * (1 - 0.05 * driver.eco)
        c_fuel = km * fuel_l100 / 100 * FUEL_PRICE
        c_mt = km * (MAINTENANCE_PER_KM + TOLL_PER_KM)
        c_wage = (drive_minutes + 20) / 60 * driver.wage
        costs = c_fuel + c_mt + c_wage

        arrival = t0 + drive_minutes
        free = arrival + (TOURIST_DWELL if tourist else TURNAROUND)

        if delay >= 15:
            self.reputation = max(0.7, self.reputation - 0.003)
        else:
            self.reputation = min(1.3, self.reputation + (0.0008 if tourist else 0.0005))

        extra, free = self._maintain(bus, driver, rng, km, t0, arrival, free, f"{city_name(a)} – {city_name(b)}")
        costs += extra

        day_t0 = t0 // DAY
        if bus.drive_day != day_t0:
            bus.drive_day, bus.drive_min = day_t0, 0
        bus.drive_min += drive_minutes
        if self.settings.respect_hours and bus.drive_min >= MAX_DRIVE_HOURS * 60:           # Lenkzeit erreicht: der Bus ruht bis zum nächsten Morgen
            free = max(free, (day_t0 + 1) * DAY + OPERATING_START)
        free = self._operating(free)

        bus.trip_from, bus.trip_to, bus.trip_start, bus.trip_end = a, b, t0, arrival
        bus.at = b
        if custom is not None:
            bus.idx, bus.dir = idx + step, step
        bus.next_free = free
        bus.km += km
        bus.trips += 1
        bus.pax += pax
        bus.revenue += revenue
        bus.costs += costs
        driver.km += km
        self.cash += revenue - costs
        xp = trip_xp(km, self.settings.xp_per_trip)
        self.xp_total += xp
        self.xp_pending += xp

        entry = self._day(day)
        entry["revenue"] += revenue
        entry["costs"] += costs
        entry["trips"] += 1
        entry["pax"] += pax
        entry["km"] += km
        self._book(day, "Linien & Ausflüge", revenue)
        self._book(day, "Treibstoff", c_fuel)
        self._book(day, "Wartung & Maut", c_mt)
        self._book(day, "Fahrerlöhne", c_wage)
        self._book(day, "Werkstatt & Pannen", extra)
        report.revenue += revenue
        report.costs += costs
        report.trips += 1
        report.km += km
        report.pax += pax

    # ---- Auswertung -----------------------------------------------------
    def day_stats(self, day: int) -> dict[str, float]:
        return dict(self.ledger.get(day, {"revenue": 0.0, "costs": 0.0, "trips": 0, "pax": 0, "km": 0}))

    def recent_profits(self, days: int = 14) -> list[tuple[int, float]]:
        current = self.now // DAY
        out = []
        for d in range(max(0, current - days + 1), current + 1):
            e = self.ledger.get(d)
            out.append((d, (e["revenue"] - e["costs"]) if e else 0.0))
        return out

    def active_buses(self) -> int:
        return sum(1 for b in self.buses.values() if b.destination)

    # ---- Speichern/Laden ------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": STATE_VERSION,
            "seed": self.seed,
            "name": self.name,
            "now": self.now,
            "cash": self.cash,
            "start_cash": self.start_cash,
            "next_bus_id": self.next_bus_id,
            "reputation": self.reputation,
            "days_charged": self.days_charged,
            "total_paid_out": self.total_paid_out,
            "xp_total": self.xp_total,
            "xp_pending": self.xp_pending,
            "sync_base": self.sync_base,
            "game_earned": self.game_earned,
            "totals": dict(self.totals),
            "trip_mark": self.trip_mark,
            "trip_log": list(self.trip_log),
            "settings": dict(vars(self.settings)),
            "garages": [{"city": g.city, "size": g.size} for g in self.garages.values()],
            "buses": [vars(b).copy() for b in self.buses.values()],
            "drivers": [vars(d).copy() for d in self.drivers.values()],
            "next_driver_id": self.next_driver_id,
            "routes": [vars(r).copy() for r in self.routes.values()],
            "next_route_id": self.next_route_id,
            "contracts": [vars(c).copy() for c in self.contracts.values()],
            "next_contract_id": self.next_contract_id,
            "accepted_offers": list(self.accepted_offers),
            "hired_keys": list(self.hired_keys),
            "ledger": {str(d): e for d, e in self.ledger.items()},
            "fin": {str(d): e for d, e in self.fin.items()},
            "fin_total": self.fin_total,
            "log": [[t, s] for t, s in self.log],
            "catalog": self.catalog.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BusCompany":
        if data.get("version") != STATE_VERSION:
            raise CompanyError("Der gespeicherte Firmenstand hat ein unbekanntes Format.")
        company = cls(BusCatalog.from_dict(data["catalog"]), data["start_cash"], data["seed"],
                      name=data.get("name", "Meine Busfirma"))
        company.now = int(data["now"])
        company.cash = float(data["cash"])
        company.next_bus_id = int(data["next_bus_id"])
        company.reputation = float(data["reputation"])
        company.days_charged = int(data["days_charged"])
        company.total_paid_out = float(data["total_paid_out"])
        company.xp_total = int(data["xp_total"])
        company.xp_pending = int(data["xp_pending"])
        if "sync_base" in data:
            company.sync_base = float(data["sync_base"])
            company.game_earned = float(data.get("game_earned", 0.0))
        else:        # alter Stand mit getrennter Kasse: ungezahlter Gewinn bleibt als Änderung erhalten
            pending = max(0.0, company.cash - company.start_cash - float(data.get("game_debit", 0)))
            company.sync_base = company.cash - pending
        company.totals.update(data.get("totals", {}))
        company.trip_mark = data.get("trip_mark")
        company.trip_log = list(data.get("trip_log", []))
        company.settings = Settings(**data["settings"])
        company.apply_tuning()
        if company.settings.job_share == 0.25:      # alter Standardwert: jetzt geht der ganze Verdienst in die Firma
            company.settings.job_share = 1.0
        company.garages = {g["city"]: Garage(g["city"], g["size"]) for g in data["garages"]}
        company.buses = {int(b["id"]): Bus(**b) for b in data["buses"]}
        company.drivers = {int(d["id"]): Driver(**d) for d in data.get("drivers", [])}
        company.next_driver_id = int(data.get("next_driver_id", 1))
        company.routes = {int(r["id"]): Route(**r) for r in data.get("routes", [])}
        company.next_route_id = int(data.get("next_route_id", 1))
        company.contracts = {int(c["id"]): Contract(**c) for c in data.get("contracts", [])}
        company.next_contract_id = int(data.get("next_contract_id", 1))
        company.accepted_offers = list(data.get("accepted_offers", []))
        company.hired_keys = list(data.get("hired_keys", []))
        if "drivers" not in data:        # alter Stand ohne Fahrer: jedem Bus einen Fahrer geben
            for bus in company.buses.values():
                driver = Driver(company.next_driver_id, f"Fahrer {company.next_driver_id}", bus_id=bus.id,
                                hired_at=company.now)
                company.next_driver_id += 1
                company.drivers[driver.id] = driver
                bus.driver = driver.id
        company.ledger = {int(d): dict(e) for d, e in data["ledger"].items()}
        company.fin = {int(d): dict(e) for d, e in data.get("fin", {}).items()}
        company.fin_total = dict(data.get("fin_total", {}))
        company.log = [(int(t), str(s)) for t, s in data["log"]]
        company.apply_tuning()          # laufende Verträge auf den aktuellen km-Satz setzen
        return company

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False)
        if os.path.exists(path):
            try:
                os.replace(path, path + ".bak")
            except OSError:
                pass
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str) -> "BusCompany":
        try:
            with open(path, encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CompanyError(f"Der Firmenstand konnte nicht gelesen werden: {exc}") from exc


def estimate_trip_profit(model_name: str, km: int, minutes: int, multiplier: float = 1.0,
                         tourist: bool = False) -> float:
    """Grobe Schätzung des Gewinns einer Fahrt (einfache Strecke) auf dieser Route, ohne Versicherung."""
    spec = model_spec(model_name)
    load = min(1.0, (0.70 if tourist else BusCompany._demand_base(km)) * 0.97)
    pax = spec.seats * load
    fare = FARE_BASE * (100 / max(km, 100)) ** 0.12
    if tourist:
        revenue = pax * max(TOURIST_MIN_TICKET, km * fare * TOURIST_FARE_FACTOR) * multiplier * SIM_INCOME_FACTOR
    else:
        revenue = pax * km * fare * multiplier * SIM_INCOME_FACTOR
    costs = (km * spec.fuel_l100 / 100 * FUEL_PRICE + km * (MAINTENANCE_PER_KM + TOLL_PER_KM)
             + (minutes + 20) / 60 * WAGE_PER_HOUR)
    return revenue - costs


def estimate_daily_profit(model_name: str, km: int, minutes: int, multiplier: float = 1.0,
                          tourist: bool = False, respect_hours: bool = True) -> float:
    """Grobe Schätzung des Gewinns pro Bus und Tag auf einer Strecke."""
    trips = (DAY - OPERATING_START) / (minutes + (TOURIST_DWELL if tourist else TURNAROUND) + 10)
    if respect_hours:
        trips = min(trips, MAX_DRIVE_HOURS * 60 / max(1, minutes))
    return trips * estimate_trip_profit(model_name, km, minutes, multiplier, tourist) - INSURANCE_PER_DAY


def default_state_path() -> str:
    override = os.environ.get("ETS2_BUSCO_FILE")
    if override:
        return override
    folder = os.path.join(os.path.expanduser("~"), ".ets2_save_tool")
    path = os.path.join(folder, "company.json")
    legacy = os.path.join(folder, "busfirma.json")          # frühere Dateinamen: einmalig umbenennen
    for suffix in ("", ".bak"):
        if not os.path.exists(path + suffix) and os.path.exists(legacy + suffix):
            try:
                os.replace(legacy + suffix, path + suffix)
            except OSError:
                return legacy
    return path
