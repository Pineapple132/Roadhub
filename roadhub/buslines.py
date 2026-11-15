"""Bus-Aufträge (Linienangebote, line_offer_data) lesen und bearbeiten.

Aufbau (an einem echten Save mit Coaches-DLC geprüft):
  bus_stop : bus_stop.city.berlin { lines_offer: N  lines_offer[i]: _nameless... }
  line_offer_data : _nameless... {
      type: regular | tourist
      source: bus_stop.city.berlin            (bei leeren Slots: null)
      saved_targets[i]: "city.wien"           Ziele in Reihenfolge (bis 5)
      targets_distances[i], targets_times[i], targets_base_times[i], targets_ferry_times[i]
          -> jeweils pro Etappe (Etappe 0 = Start -> Ziel 0, Etappe i = Ziel i-1 -> Ziel i)
      departure_time_of_day: Minuten ab Mitternacht
      bus_name, expiration_time, ... }
  Der Ablauf wird wie bei Truck-Aufträgen über economy_event gesteuert
  (unit_link = bus_stop-Name, param = Slot) und muss mitgeändert werden.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .editor import (
    _indexed_values,
    _resort_event_queue,
    _safe_int,
    _update_expiry_event,
    game_time,
    strip_quotes,
)
from .sii import SiiDocument, SiiError

LEG_KEYS = ("targets_distances", "targets_times", "targets_base_times", "targets_ferry_times")
MAX_TARGETS = 5
LINE_TYPES = ("regular", "tourist")


@dataclass(frozen=True)
class Leg:
    km: int
    minutes: int
    base_minutes: int
    ferry_minutes: int = 0


@dataclass
class LineOffer:
    stop_unit: str            # z. B. 'bus_stop.city.berlin'
    slot: int
    offer_unit: str
    line_type: str
    source: str               # 'bus_stop.city.berlin' oder 'null'
    targets: list[str]        # ohne Anführungszeichen, z. B. 'city.wien'
    legs: list[Leg]
    bus_name: str
    departure: int
    expiration: str           # roh ('nil' möglich)

    @property
    def is_empty(self) -> bool:
        return not self.targets or self.source in ("null", "", "nil")

    @property
    def total_km(self) -> int:
        return sum(l.km for l in self.legs)

    @property
    def total_minutes(self) -> int:
        return sum(l.minutes for l in self.legs)

    @property
    def start_name(self) -> str:
        return stop_label(self.stop_unit)


def stop_label(unit_name: str) -> str:
    """'bus_stop.city.berlin' -> 'city.berlin'."""
    return unit_name[len("bus_stop."):] if unit_name.startswith("bus_stop.") else unit_name


SIGHT_LABELS: dict[str, str] = {}   # wird von mapdata gefüllt (Anzeigenamen der Sehenswürdigkeiten)


def pretty_stop(name: str) -> str:
    """'city.a_coruna' -> 'A Coruna'; 'viewpoints.isgeyser' -> 'Aussicht: isgeyser'."""
    kind, _, rest = name.partition(".")
    text = rest.replace("_", " ")
    if kind == "viewpoints":
        label = SIGHT_LABELS.get(name)
        return f"Aussicht: {label}" if label else f"Aussicht: {text}"
    return text.title()


def _strings(doc: SiiDocument, unit, key: str) -> list[str]:
    return [v for _, v in _indexed_values(doc, unit, key)]


def _ints(doc: SiiDocument, unit, key: str) -> list[int]:
    return [_safe_int(v) for v in _strings(doc, unit, key)]


def list_line_offers(doc: SiiDocument) -> list[LineOffer]:
    offers: list[LineOffer] = []
    for stop in doc.by_type.get("bus_stop", []):
        for slot, name in _indexed_values(doc, stop, "lines_offer"):
            unit = doc.by_name.get(name)
            if unit is None:
                continue
            targets = [strip_quotes(v) for v in _strings(doc, unit, "saved_targets")]
            cols = [_ints(doc, unit, k) for k in LEG_KEYS]
            legs = []
            for i in range(len(targets)):
                get = lambda c: c[i] if i < len(c) else 0  # noqa: E731
                legs.append(Leg(get(cols[0]), get(cols[1]), get(cols[2]), get(cols[3])))
            offers.append(
                LineOffer(
                    stop_unit=stop.name,
                    slot=slot,
                    offer_unit=name,
                    line_type=doc.get(unit, "type") or "regular",
                    source=doc.get(unit, "source") or "null",
                    targets=targets,
                    legs=legs,
                    bus_name=strip_quotes(doc.get(unit, "bus_name")),
                    departure=_safe_int(doc.get(unit, "departure_time_of_day")),
                    expiration=doc.get(unit, "expiration_time") or "nil",
                )
            )
    return offers


def list_stop_targets(doc: SiiDocument) -> list[str]:
    """Alle möglichen Ziele ('city.berlin', 'viewpoints.isgeyser')."""
    return sorted(stop_label(u.name) for u in doc.by_type.get("bus_stop", []) if u.name.startswith("bus_stop."))


def list_bus_models(offers: list[LineOffer]) -> list[str]:
    return sorted({o.bus_name for o in offers if o.bus_name})


def known_legs(offers: list[LineOffer]) -> dict[tuple[str, str], Leg]:
    """(von, nach) -> Etappe, aus allen vorhandenen Angeboten."""
    legs: dict[tuple[str, str], Leg] = {}
    for offer in offers:
        if offer.is_empty:
            continue
        previous = stop_label(offer.source)
        for target, leg in zip(offer.targets, offer.legs):
            if leg.km > 0:
                legs.setdefault((previous, target), leg)
            previous = target
    return legs


def estimate_leg(km: int, legs: dict[tuple[str, str], Leg]) -> Leg:
    """Fahrzeit einer unbekannten Etappe aus dem Verhältnis bekannter Etappen schätzen."""
    sample = [l for l in legs.values() if l.km >= 50 and l.minutes > 0 and l.base_minutes > 0]
    if sample:
        per_km = statistics.median(l.minutes / l.km for l in sample)
        base_ratio = statistics.median(l.base_minutes / l.minutes for l in sample)
    else:
        per_km, base_ratio = 1.0, 0.8
    minutes = max(1, round(km * per_km))
    return Leg(km, minutes, max(1, round(minutes * base_ratio)), 0)


@dataclass
class LineSpec:
    stop_unit: str
    slot: int
    line_type: str
    targets: list[str]
    legs: list[Leg]
    bus_name: str
    departure: int = 480
    hours_valid: int = 24


def _validate(doc: SiiDocument, spec: LineSpec):
    stop = doc.by_name.get(spec.stop_unit)
    if stop is None or stop.type != "bus_stop":
        raise SiiError(f"Haltestelle '{spec.stop_unit}' wurde im Save nicht gefunden.")
    slots = dict(_indexed_values(doc, stop, "lines_offer"))
    if spec.slot not in slots or slots[spec.slot] not in doc.by_name:
        raise SiiError(f"Die Haltestelle hat keinen Linien-Slot {spec.slot}.")
    if spec.line_type not in LINE_TYPES:
        raise SiiError("Typ muss 'regular' oder 'tourist' sein.")
    if not (1 <= len(spec.targets) <= MAX_TARGETS):
        raise SiiError(f"Eine Linie braucht 1 bis {MAX_TARGETS} Ziele.")
    if len(spec.legs) != len(spec.targets):
        raise SiiError("Zu jedem Ziel gehört genau eine Etappe.")
    valid = set(list_stop_targets(doc))
    previous = stop_label(spec.stop_unit)
    for target, leg in zip(spec.targets, spec.legs):
        if target not in valid:
            raise SiiError(f"Ziel '{target}' gibt es im Save nicht.")
        if target == previous:
            raise SiiError("Zwei aufeinanderfolgende Haltestellen dürfen nicht gleich sein.")
        if not (1 <= leg.km <= 5000):
            raise SiiError(f"Die Etappe nach {pretty_stop(target)} braucht 1 bis 5000 km.")
        if leg.minutes < 1 or leg.base_minutes < 1 or leg.ferry_minutes < 0:
            raise SiiError("Fahrzeiten müssen positiv sein (Fähre darf 0 sein).")
        previous = target
    if not spec.bus_name:
        raise SiiError("Bitte ein Busmodell wählen.")
    if not (0 <= spec.departure <= 1439):
        raise SiiError("Die Abfahrtszeit muss zwischen 00:00 und 23:59 liegen.")
    if not (1 <= spec.hours_valid <= 24 * 30):
        raise SiiError("Die Gültigkeit muss zwischen 1 Stunde und 30 Tagen liegen.")
    return slots[spec.slot]


def apply_line(doc: SiiDocument, spec: LineSpec) -> int:
    """Überschreibt einen Linien-Slot. Gibt die Ablaufzeit (Spielminuten) zurück."""
    offer_name = _validate(doc, spec)
    expiration = game_time(doc) + spec.hours_valid * 60

    def unit():
        return doc.by_name[offer_name]

    doc.set(unit(), "type", spec.line_type)
    doc.set(unit(), "source", spec.stop_unit)
    doc.replace_array(unit(), "saved_targets", [f'"{t}"' for t in spec.targets])
    doc.replace_array(unit(), "targets_distances", [str(l.km) for l in spec.legs])
    doc.replace_array(unit(), "targets_times", [str(l.minutes) for l in spec.legs])
    doc.replace_array(unit(), "targets_ferry_times", [str(l.ferry_minutes) for l in spec.legs])
    doc.replace_array(unit(), "targets_base_times", [str(l.base_minutes) for l in spec.legs])
    doc.set(unit(), "departure_time_of_day", str(spec.departure))
    doc.set(unit(), "bus_name", spec.bus_name)
    doc.set(unit(), "expiration_time", str(expiration))

    _update_expiry_event(doc, spec.stop_unit, spec.slot, expiration)
    return expiration
