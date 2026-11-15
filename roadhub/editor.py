"""Editing profile values and cargo jobs in a loaded save."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .sii import SiiDocument, SiiError, Unit

# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    key: str
    unit_type: str
    label: str
    minimum: int
    maximum: int


INT64_MAX = 2**63 - 1

PROFILE_FIELDS: list[FieldSpec] = [
    FieldSpec("money_account", "bank", "Kontostand (interner Euro-Wert)", -INT64_MAX, INT64_MAX),
    FieldSpec("experience_points", "economy", "Erfahrungspunkte (XP)", 0, 2**32 - 1),
    FieldSpec("adr", "economy", "ADR – Gefahrgut (Bitmaske 0–63)", 0, 63),
    FieldSpec("long_dist", "economy", "Langstrecke", 0, 6),
    FieldSpec("heavy", "economy", "Wertvolle Fracht (heavy)", 0, 6),
    FieldSpec("fragile", "economy", "Zerbrechliche Fracht", 0, 6),
    FieldSpec("urgent", "economy", "Just-in-time-Lieferung (urgent)", 0, 6),
    FieldSpec("mechanical", "economy", "Spritsparendes Fahren (mechanical)", 0, 6),
]


# Bus/Coaches values (field names checked against a real save with the Coaches DLC).
# The maximum values of the bus skills are not known; 0-6 is a cautious assumption
# analogous to the truck skills.
BUS_FIELDS: list[FieldSpec] = [
    FieldSpec("bus_experience_points", "economy", "Bus-Erfahrungspunkte (XP)", 0, 99_999_999),
    FieldSpec("long_duty", "economy", "Skill: Lange Schichten (long_duty)", 0, 6),
    FieldSpec("tight_schedule", "economy", "Skill: Enger Fahrplan (tight_schedule)", 0, 6),
    FieldSpec("satisfaction_decrease", "economy", "Skill: Weniger Unzufriedenheit (satisfaction_decrease)", 0, 6),
    FieldSpec("low_acceleration", "economy", "Skill: Sanftes Anfahren (low_acceleration)", 0, 6),
    FieldSpec("satisfaction_increase", "economy", "Skill: Mehr Zufriedenheit (satisfaction_increase)", 0, 6),
    FieldSpec("ecodriving", "economy", "Skill: Spritsparen Bus (ecodriving)", 0, 6),
]

ALL_FIELDS: list[FieldSpec] = PROFILE_FIELDS + BUS_FIELDS


def read_values(doc: SiiDocument, specs: list[FieldSpec]) -> dict[str, str | None]:
    """Current values; None if the field was not found in the save."""
    result: dict[str, str | None] = {}
    for spec in specs:
        unit = doc.first(spec.unit_type)
        result[spec.key] = doc.get(unit, spec.key) if unit else None
    return result


def read_profile(doc: SiiDocument) -> dict[str, str | None]:
    return read_values(doc, PROFILE_FIELDS)


def read_bus_fields(doc: SiiDocument) -> dict[str, str | None]:
    return read_values(doc, BUS_FIELDS)


def parse_int(text: str, label: str) -> int:
    try:
        return int(str(text).strip().replace(".", "").replace(",", "").replace(" ", ""))
    except ValueError:
        raise SiiError(f"„{label}“: '{text}' ist keine ganze Zahl.") from None


def write_profile(doc: SiiDocument, values: dict[str, int]) -> list[str]:
    """Writes the given values. Returns the keys that changed."""
    specs = {s.key: s for s in ALL_FIELDS}
    # check everything first, then write
    for key, value in values.items():
        spec = specs.get(key)
        if spec is None:
            raise SiiError(f"Unbekanntes Feld: {key}")
        if not (spec.minimum <= value <= spec.maximum):
            raise SiiError(
                f"„{spec.label}“: {value} liegt außerhalb des erlaubten Bereichs "
                f"({spec.minimum} bis {spec.maximum})."
            )
        if doc.first(spec.unit_type) is None:
            raise SiiError(f"Im Save fehlt der Abschnitt '{spec.unit_type}'.")

    current = read_values(doc, ALL_FIELDS)
    changed: list[str] = []
    for key, value in values.items():
        if current.get(key) == str(value):
            continue
        doc.set(doc.first(specs[key].unit_type), key, str(value))
        changed.append(key)
    return changed


def read_bus_info(doc: SiiDocument) -> dict[str, str]:
    """Read only: numbers around the bus area in the save."""
    info: dict[str, str] = {}
    eco = doc.first("economy")
    if eco is not None:
        stops = doc.get(eco, "bus_stops")
        if stops is not None:
            info["Bushaltestellen (economy)"] = stops
        for key in ("bus_total_distance", "bus_finished_job_count", "bus_cancelled_job_count",
                    "bus_total_passengers", "bus_total_stops"):
            val = doc.get(eco, key)
            if val is not None:
                info[key] = val
    info["bus_stop-Einheiten im Save"] = str(len(doc.by_type.get("bus_stop", [])))
    info["Bus-Linienangebote (line_offer_data)"] = str(len(doc.by_type.get("line_offer_data", [])))
    log = doc.by_name.get(doc.get(eco, "bus_job_log") or "") if eco is not None else None
    if log is not None:
        info["Einträge im Bus-Auftragslog"] = str(len(_indexed_values(doc, log, "entries")))
    player = doc.first("player")
    if player is not None:
        buses = doc.get(player, "buses")
        if buses is not None:
            info["Eigene Busse (player.buses)"] = buses
    return info


def sync_info_file(game_path: str, doc: SiiDocument) -> str | None:
    """Keeps the display in the load list (info.sii) in line with the save.

    Updates the balance and total XP (truck XP + bus XP, checked against a real save).
    Returns the path if something was changed, otherwise None. Does not insert new fields.
    """
    from . import sii as _sii

    info_path = os.path.join(os.path.dirname(game_path), "info.sii")
    if not os.path.isfile(info_path):
        return None
    info = _sii.load(info_path)
    unit = info.first("save_container")
    if unit is None:
        return None

    profile = read_profile(doc)
    eco = doc.first("economy")
    bus_xp = _safe_int(doc.get(eco, "bus_experience_points")) if eco else 0
    wanted: dict[str, str] = {}
    if profile.get("money_account") is not None:
        wanted["info_money_account"] = str(profile["money_account"])
    if profile.get("experience_points") is not None:
        wanted["info_players_experience"] = str(_safe_int(profile["experience_points"]) + bus_xp)

    changed = False
    for key, value in wanted.items():
        current = info.get(unit, key)
        if current is not None and current != value:
            info.set(info.first("save_container"), key, value)
            changed = True
    if not changed:
        return None
    _sii.save(info, info_path, backup=True)
    return info_path


# --------------------------------------------------------------------------
# Cargo jobs
# --------------------------------------------------------------------------

JOB_SCALAR_KEYS = [
    "target",
    "expiration_time",
    "urgency",
    "shortest_distance_km",
    "ferry_time",
    "ferry_price",
    "cargo",
    "company_truck",
    "trailer_variant",
    "trailer_definition",
    "units_count",
    "fill_ratio",
]

_NAME_PREFIX = "company.volatile."


def strip_quotes(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def company_key(unit_name: str) -> str | None:
    """'company.volatile.aria_food.berlin' -> 'aria_food.berlin'."""
    if unit_name.startswith(_NAME_PREFIX):
        rest = unit_name[len(_NAME_PREFIX):]
        if "." in rest:
            return rest
    return None


def pretty_place(key: str) -> str:
    """'aria_food.berlin' -> 'aria_food @ berlin'."""
    if "." in key:
        comp, city = key.rsplit(".", 1)
        return f"{comp} @ {city}"
    return key


@dataclass(frozen=True)
class CargoTemplate:
    """A consistent combination of cargo and trailer (from existing jobs)."""

    cargo: str
    company_truck: str
    trailer_variant: str
    trailer_definition: str
    units_count: str
    fill_ratio: str

    def label(self) -> str:
        name = self.cargo[6:] if self.cargo.startswith("cargo.") else self.cargo
        trailer = strip_quotes(self.trailer_definition)
        return f"{name}  |  {trailer}  |  {self.units_count} Einheiten"


@dataclass
class JobOffer:
    company_unit: str
    slot: int
    offer_unit: str
    values: dict[str, str]

    @property
    def source_key(self) -> str:
        return company_key(self.company_unit) or self.company_unit

    @property
    def target_key(self) -> str:
        return strip_quotes(self.values.get("target"))

    @property
    def cargo_name(self) -> str:
        cargo = self.values.get("cargo", "")
        return cargo[6:] if cargo.startswith("cargo.") else cargo

    @property
    def is_empty(self) -> bool:
        cargo = self.values.get("cargo", "").strip()
        return cargo in ("", "null", "nil", '""') or not self.target_key or self.target_key in ("null", "nil")

    def template(self) -> CargoTemplate:
        v = self.values
        return CargoTemplate(
            v.get("cargo", ""),
            v.get("company_truck", ""),
            v.get("trailer_variant", ""),
            v.get("trailer_definition", ""),
            v.get("units_count", "0"),
            v.get("fill_ratio", "0"),
        )


def _indexed_values(doc: SiiDocument, unit: Unit, key: str) -> list[tuple[int, str]]:
    pattern = re.compile(rf"^{re.escape(key)}\[(\d+)\]$")
    out = []
    for _, k, v in doc.attrs(unit):
        m = pattern.match(k)
        if m:
            out.append((int(m.group(1)), v))
    return sorted(out)


def list_offers(doc: SiiDocument) -> list[JobOffer]:
    offers: list[JobOffer] = []
    for company in doc.by_type.get("company", []):
        for slot, offer_name in _indexed_values(doc, company, "job_offer"):
            offer_unit = doc.by_name.get(offer_name)
            if offer_unit is None:
                continue
            values = {k: v for _, k, v in doc.attrs(offer_unit) if k in JOB_SCALAR_KEYS}
            offers.append(JobOffer(company.name, slot, offer_name, values))
    return offers


def list_destinations(doc: SiiDocument) -> list[str]:
    """All company+city combinations in the save ('aria_food.berlin')."""
    keys = {company_key(u.name) for u in doc.by_type.get("company", [])}
    keys.discard(None)
    return sorted(keys)  # type: ignore[arg-type]


def list_templates(offers: list[JobOffer]) -> list[CargoTemplate]:
    """Unique cargo/trailer combinations from existing jobs.

    In real saves the tractor (company_truck) depends on the cargo class
    (e.g. "double/…" or "heavy/…"), so it is taken from the first matching
    job and not used to tell combinations apart.
    """
    seen: dict[tuple[str, str, str, str], CargoTemplate] = {}
    for offer in offers:
        if offer.is_empty:
            continue
        tpl = offer.template()
        key = (tpl.cargo, tpl.trailer_variant, tpl.trailer_definition, tpl.units_count)
        seen.setdefault(key, tpl)
    return sorted(
        seen.values(),
        key=lambda t: (t.cargo, strip_quotes(t.trailer_definition), _safe_int(t.units_count)),
    )


def cargo_display_name(cargo: str) -> str:
    return cargo[6:] if cargo.startswith("cargo.") else cargo


def known_routes(offers: list[JobOffer]) -> dict[tuple[str, str], tuple[int, int, int]]:
    """(from, to) -> (distance km, ferry time, ferry price) from existing jobs."""
    routes: dict[tuple[str, str], tuple[int, int, int]] = {}
    for offer in offers:
        if offer.is_empty:
            continue
        try:
            dist = int(offer.values.get("shortest_distance_km", "0"))
        except ValueError:
            continue
        if dist <= 0:
            continue
        ferry_t = _safe_int(offer.values.get("ferry_time"))
        ferry_p = _safe_int(offer.values.get("ferry_price"))
        routes[(offer.source_key, offer.target_key)] = (dist, ferry_t, ferry_p)
    return routes


def _safe_int(value: str | None) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def game_time(doc: SiiDocument) -> int:
    eco = doc.first("economy")
    value = doc.get(eco, "game_time") if eco else None
    if value is None:
        raise SiiError("Im Save wurde die Spielzeit (game_time) nicht gefunden.")
    try:
        return int(value)
    except ValueError:
        raise SiiError(f"Ungültige Spielzeit im Save: {value}") from None


@dataclass
class JobSpec:
    company_unit: str
    slot: int
    target_key: str
    template: CargoTemplate
    distance_km: int
    urgency: int = 0
    hours_valid: int = 72
    ferry_time: int = 0
    ferry_price: int = 0


def _validate_spec(doc: SiiDocument, spec: JobSpec) -> Unit:
    company = doc.by_name.get(spec.company_unit)
    if company is None or company.type != "company":
        raise SiiError(f"Firma '{spec.company_unit}' wurde im Save nicht gefunden.")
    slots = dict(_indexed_values(doc, company, "job_offer"))
    if spec.slot not in slots or slots[spec.slot] not in doc.by_name:
        raise SiiError(f"Die Firma hat keinen Auftrags-Slot {spec.slot}.")
    if spec.target_key not in list_destinations(doc):
        raise SiiError(f"Ziel '{spec.target_key}' gibt es im Save nicht.")
    if spec.target_key == company_key(spec.company_unit):
        raise SiiError("Start und Ziel dürfen nicht dieselbe Firma sein.")
    if not (1 <= spec.distance_km <= 10000):
        raise SiiError("Die Entfernung muss zwischen 1 und 10000 km liegen.")
    if spec.urgency not in (0, 1, 2):
        raise SiiError("Dringlichkeit muss 0 (normal), 1 (eilig) oder 2 (sehr eilig) sein.")
    if not (1 <= spec.hours_valid <= 24 * 30):
        raise SiiError("Die Gültigkeit muss zwischen 1 Stunde und 30 Tagen liegen.")
    if spec.ferry_time < 0 or spec.ferry_price < 0:
        raise SiiError("Fährzeit und Fährpreis dürfen nicht negativ sein.")
    if not spec.template.cargo or not spec.template.trailer_definition:
        raise SiiError("Bitte eine Fracht/Anhänger-Kombination auswählen.")
    return doc.by_name[slots[spec.slot]]


def apply_job(doc: SiiDocument, spec: JobSpec) -> int:
    """Overwrites an existing job slot. Returns the expiry time (game minutes)."""
    offer_unit = _validate_spec(doc, spec)
    expiration = game_time(doc) + spec.hours_valid * 60
    t = spec.template

    writes = {
        "target": f'"{spec.target_key}"',
        "expiration_time": str(expiration),
        "urgency": str(spec.urgency),
        "shortest_distance_km": str(spec.distance_km),
        "ferry_time": str(spec.ferry_time),
        "ferry_price": str(spec.ferry_price),
        "cargo": t.cargo,
        "company_truck": t.company_truck,
        "trailer_variant": t.trailer_variant,
        "trailer_definition": t.trailer_definition,
        "units_count": t.units_count,
        "fill_ratio": t.fill_ratio,
    }
    for key, value in writes.items():
        # offer_unit stays valid: inserting re-indexes, so fetch it fresh every time
        unit = doc.by_name[offer_unit.name]
        doc.set(unit, key, value)

    _update_expiry_event(doc, spec.company_unit, spec.slot, expiration)
    return expiration


def _update_expiry_event(doc: SiiDocument, company_unit: str, slot: int, expiration: int) -> None:
    """The game manages the expiry of jobs through economy_event entries.

    Without an adjustment the job would be re-rolled at the old time.
    """
    for event in doc.by_type.get("economy_event", []):
        link = strip_quotes(doc.get(event, "unit_link"))
        if link == company_unit and _safe_int(doc.get(event, "param")) == slot:
            doc.set(doc.by_name[event.name], "time", str(expiration))
            break
    else:
        return
    _resort_event_queue(doc)


def _resort_event_queue(doc: SiiDocument) -> None:
    queue = doc.first("economy_event_queue")
    if queue is None:
        return
    pattern = re.compile(r"^data\[(\d+)\]$")
    entries = []  # (index in the array, line number, value)
    for line_no, key, value in doc.attrs(queue):
        m = pattern.match(key)
        if m:
            entries.append((int(m.group(1)), line_no, value))
    if not entries:
        return
    entries.sort()

    def event_time(name: str) -> int:
        unit = doc.by_name.get(name)
        return _safe_int(doc.get(unit, "time")) if unit else 0

    ordered = sorted((v for _, _, v in entries), key=event_time)  # stable
    # overwrite lines directly (no inserting/deleting, indices stay valid)
    for (idx, line_no, old), name in zip(entries, ordered):
        if old != name:
            doc.lines[line_no] = f" data[{idx}]: {name}"
