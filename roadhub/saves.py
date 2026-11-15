"""Finds profiles and save games in the default ETS2 folder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

GAME_FOLDER = "Euro Truck Simulator 2"


@dataclass(frozen=True)
class SaveEntry:
    profile: str      # readable profile name
    folder: str       # name of the save folder (quicksave, autosave, 1, ...)
    path: str         # full path to game.sii
    mtime: float


def candidate_roots() -> list[Path]:
    """Possible folders with 'profiles' / 'steam_profiles' (existing ones only)."""
    home = Path.home()
    bases = [
        home / "Documents",
        home / "Dokumente",
        home / "OneDrive" / "Documents",
        home / "OneDrive" / "Dokumente",
        home / ".local" / "share",                       # Linux
        home / "Library" / "Application Support",        # macOS
    ]
    override = os.environ.get("ETS2_SAVE_ROOT")
    roots: list[Path] = [Path(override)] if override else []
    for base in bases:
        game = base / GAME_FOLDER
        for sub in ("profiles", "steam_profiles"):
            if (game / sub).is_dir():
                roots.append(game / sub)
    return roots


def decode_profile_name(folder: str) -> str:
    """Profile folders are named like the hex-encoded UTF-8 name ('4D79' -> 'My')."""
    try:
        return bytes.fromhex(folder).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return folder


def list_saves(root: Path) -> list[SaveEntry]:
    entries: list[SaveEntry] = []
    try:
        profiles = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return entries
    for profile_dir in profiles:
        save_dir = profile_dir / "save"
        if not save_dir.is_dir():
            continue
        name = decode_profile_name(profile_dir.name)
        for slot in save_dir.iterdir():
            game_sii = slot / "game.sii"
            if game_sii.is_file():
                try:
                    mtime = game_sii.stat().st_mtime
                except OSError:
                    continue
                entries.append(SaveEntry(name, slot.name, str(game_sii), mtime))
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries
