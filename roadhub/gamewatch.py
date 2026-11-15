"""Detects whether ETS2 is running and pays out into the newest save game after it exits."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass

from . import busco, editor, saves, sii

PROCESS_NAMES = ("eurotrucks2.exe", "eurotrucks2")


def process_names() -> tuple[str, ...]:
    override = os.environ.get("ETS2_PROCESS_NAME")
    return (override.lower(),) if override else PROCESS_NAMES


def is_game_running() -> bool:
    names = process_names()
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,  # no console window
            ).stdout.lower()
        except (OSError, subprocess.SubprocessError):
            return False
        return any(f'"{n}"' in out for n in names)
    try:
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    with open(f"/proc/{pid}/comm", encoding="utf-8", errors="ignore") as fh:
                        comm = fh.read().strip().lower()
                except OSError:
                    continue
                if any(comm == n[:15] for n in names):
                    return True
    except OSError:
        pass
    return False


def newest_save() -> saves.SaveEntry | None:
    entries: list[saves.SaveEntry] = []
    for root in saves.candidate_roots():
        entries += saves.list_saves(root)
    return max(entries, key=lambda e: e.mtime) if entries else None


def wait_until_stable(path: str, quiet_seconds: float = 3.0, timeout: float = 60.0) -> bool:
    """Waits until the file has not changed for a while (the game still writes when exiting)."""
    deadline = time.time() + timeout
    last = None
    since = time.time()
    while time.time() < deadline:
        try:
            st = os.stat(path)
        except OSError:
            return False
        stamp = (st.st_mtime, st.st_size)
        if stamp != last:
            last, since = stamp, time.time()
        elif time.time() - since >= quiet_seconds:
            return True
        time.sleep(0.5)
    return False


@dataclass
class PayoutResult:
    path: str
    euros: int          # change of the account by the company (can be negative)
    xp: int
    new_money: int
    backup: str | None
    info_note: str


def payout_amounts(company: busco.BusCompany) -> tuple[int, int]:
    """(change of the account by the company, bus XP earned)"""
    return int(round(company.firm_delta())), int(company.xp_pending)


def read_money(path: str) -> int | None:
    doc = sii.load(path)
    value = editor.read_values(doc, editor.ALL_FIELDS).get("money_account")
    return None if value is None else editor.parse_int(value, "Kontostand")


def sync_company(company: busco.BusCompany) -> int | None:
    """Syncs the shared account with the newest save game (only useful when ETS2 is not running)."""
    entry = newest_save()
    if entry is None:
        return None
    try:
        money = read_money(entry.path)
    except (sii.SiiError, OSError):
        return None
    if money is None:
        return None
    company.sync_to_game(money, getattr(entry, "mtime", None))
    return money


def payout_into_save(company: busco.BusCompany, path: str) -> PayoutResult | None:
    """Writes the company change of the account and the bus XP earned into game.sii. None = nothing to write."""
    delta, xp = payout_amounts(company)
    if delta == 0 and xp == 0:
        return None
    doc = sii.load(path)
    if doc.first("economy") is None or doc.first("bank") is None:
        raise sii.SiiError("Das ist kein Spielstand (game.sii).")
    current = editor.read_values(doc, editor.ALL_FIELDS)
    if current.get("money_account") is None:
        raise sii.SiiError("Im Spielstand wurde kein Kontostand gefunden.")
    if current.get("bus_experience_points") is None:
        xp = 0
        if delta == 0:
            raise sii.SiiError("Im Spielstand gibt es keine Bus-Erfahrung, es wäre nichts zu übertragen.")
    money = editor.parse_int(current["money_account"], "Kontostand")
    new_money = max(0, money + delta)
    new_values = {"money_account": new_money}
    if xp:
        new_values["bus_experience_points"] = min(
            99_999_999, editor.parse_int(current["bus_experience_points"] or "0", "Bus-XP") + xp)
    editor.write_profile(doc, new_values)
    backup = sii.save(doc, path, backup=True)
    company.mark_written(new_money - money, new_money, xp)
    note = ""
    try:
        if editor.sync_info_file(path, doc):
            note = "Die Anzeige in der Ladeliste (info.sii) wurde angepasst."
    except sii.SiiError as exc:
        note = f"info.sii konnte nicht angepasst werden ({exc})."
    return PayoutResult(path, new_money - money, xp, new_money, backup, note)
