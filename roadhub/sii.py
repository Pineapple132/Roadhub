"""Lesen, Entschlüsseln, Parsen und Schreiben von ETS2/ATS-Savegames (game.sii).

Format (verifiziert am Quellcode von SII_Decrypt):
  verschlüsselt:  "ScsC" | HMAC (32) | IV (16) | Datengröße (uint32 LE) | AES-256-CBC(zlib(Text))
  Klartext:       "SiiN" ... (SiiNunit { ... })
  nicht unterstützt: "BSII" (Binärformat) und "3nK\\x01"
"""

from __future__ import annotations

import os
import re
import struct
import time
import zlib
from dataclasses import dataclass, field

SII_KEY = bytes(
    [
        0x2A, 0x5F, 0xCB, 0x17, 0x91, 0xD2, 0x2F, 0xB6,
        0x02, 0x45, 0xB3, 0xD8, 0x36, 0x9E, 0xD0, 0xB2,
        0xC2, 0x73, 0x71, 0x56, 0x3F, 0xBF, 0x1F, 0x3C,
        0x9E, 0xDF, 0x6B, 0x11, 0x82, 0x5A, 0x5D, 0x0A,
    ]
)

SIG_ENCRYPTED = b"ScsC"
SIG_TEXT = b"SiiN"
SIG_BINARY = b"BSII"
SIG_3NK = b"3nK\x01"
HEADER_SIZE = 4 + 32 + 16 + 4


class SiiError(Exception):
    """Basisklasse für alle Fehler dieses Moduls (Meldung ist für Nutzer gedacht)."""


class UnsupportedFormat(SiiError):
    pass


# --------------------------------------------------------------------------
# Ver-/Entschlüsselung
# --------------------------------------------------------------------------

def _aes_cbc(data: bytes, iv: bytes, encrypt: bool) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # pragma: no cover - Fallback
        try:
            from Crypto.Cipher import AES  # type: ignore
        except ImportError as exc:
            raise SiiError(
                "Das Paket 'cryptography' fehlt. Installiere es mit:  pip install cryptography"
            ) from exc
        cipher = AES.new(SII_KEY, AES.MODE_CBC, iv)
        return cipher.encrypt(data) if encrypt else cipher.decrypt(data)

    cipher = Cipher(algorithms.AES(SII_KEY), modes.CBC(iv))
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    return ctx.update(data) + ctx.finalize()


def decrypt_bytes(raw: bytes) -> bytes:
    """Gibt den Klartext-Inhalt einer Save-Datei zurück (egal ob verschlüsselt oder nicht)."""
    sig = raw[:4]
    if sig == SIG_ENCRYPTED:
        if len(raw) < HEADER_SIZE:
            raise SiiError("Die Datei ist zu kurz und vermutlich beschädigt.")
        iv = raw[36:52]
        (size,) = struct.unpack("<I", raw[52:56])
        enc = raw[HEADER_SIZE:]
        enc = enc[: len(enc) - (len(enc) % 16)]
        plain = _aes_cbc(enc, iv, encrypt=False)
        try:
            data = zlib.decompressobj().decompress(plain)
        except zlib.error as exc:
            raise SiiError(
                "Entschlüsselung fehlgeschlagen (zlib-Fehler). Ist die Datei beschädigt?"
            ) from exc
        if len(data) != size:
            raise SiiError(
                f"Entschlüsselung fehlerhaft: erwartet {size} Bytes, erhalten {len(data)}."
            )
        inner = data
    else:
        inner = raw

    if inner[:4] == SIG_TEXT:
        return inner
    if inner[:4] in (SIG_BINARY, SIG_3NK):
        raise UnsupportedFormat(
            "Dieser Save ist im Binärformat gespeichert, das dieses Programm nicht lesen kann.\n"
            "Lösung: In  Dokumente/Euro Truck Simulator 2/config.cfg  die Zeile\n"
            '    uset g_save_format "2"\n'
            "setzen, das Spiel starten und neu speichern. Danach ist der Save im Textformat."
        )
    raise SiiError("Unbekanntes Dateiformat – das ist keine ETS2/ATS-Save-Datei.")


def encrypt_text(plain: bytes) -> bytes:
    """Verschlüsselt Klartext im ScsC-Format (wird nur für Tests und optionalen Export genutzt)."""
    iv = os.urandom(16)
    comp = zlib.compress(plain)
    pad = (-len(comp)) % 16
    enc = _aes_cbc(comp + b"\x00" * pad, iv, encrypt=True)
    return SIG_ENCRYPTED + b"\x00" * 32 + iv + struct.pack("<I", len(plain)) + enc


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

_UNIT_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(\S+)\s*\{\s*$")
_ATTR_RE = re.compile(r"^\s*([A-Za-z_]\w*(?:\[\d*\])?)\s*:\s?(.*)$")


@dataclass
class Unit:
    type: str
    name: str
    start: int  # Index der Kopfzeile "typ : name {"
    end: int    # Index der schließenden "}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"Unit({self.type} : {self.name})"


@dataclass
class SiiDocument:
    lines: list[str]
    eol: str = "\r\n"
    units: list[Unit] = field(default_factory=list)
    by_name: dict[str, Unit] = field(default_factory=dict)
    by_type: dict[str, list[Unit]] = field(default_factory=dict)

    # ---- Aufbau ---------------------------------------------------------
    @classmethod
    def from_bytes(cls, plain: bytes) -> "SiiDocument":
        text = plain.decode("utf-8", errors="surrogateescape")
        eol = "\r\n" if "\r\n" in text[:5000] else "\n"
        lines = [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]
        doc = cls(lines=lines, eol=eol)
        doc.reindex()
        return doc

    def to_bytes(self) -> bytes:
        return self.eol.join(self.lines).encode("utf-8", errors="surrogateescape")

    def reindex(self) -> None:
        self.units = []
        self.by_name = {}
        self.by_type = {}
        current: Unit | None = None
        for i, line in enumerate(self.lines):
            if current is None:
                m = _UNIT_RE.match(line)
                if m and m.group(1) != "SiiNunit":
                    current = Unit(m.group(1), m.group(2), i, -1)
            elif line.rstrip() == "}":
                current.end = i
                self.units.append(current)
                self.by_name[current.name] = current
                self.by_type.setdefault(current.type, []).append(current)
                current = None
        if current is not None:
            raise SiiError(
                f"Die Datei ist unvollständig (Unit '{current.name}' wird nicht geschlossen)."
            )

    # ---- Lesen ----------------------------------------------------------
    def first(self, unit_type: str) -> Unit | None:
        found = self.by_type.get(unit_type)
        return found[0] if found else None

    def attrs(self, unit: Unit):
        for i in range(unit.start + 1, unit.end):
            m = _ATTR_RE.match(self.lines[i])
            if m:
                yield i, m.group(1), m.group(2).rstrip()

    def get(self, unit: Unit, key: str, default: str | None = None) -> str | None:
        for _, k, v in self.attrs(unit):
            if k == key:
                return v
        return default

    def get_array(self, unit: Unit, key: str) -> list[str]:
        """Liest 'key: N' mit den Zeilen 'key[0]: ...'."""
        out: dict[int, str] = {}
        prefix = key + "["
        for _, k, v in self.attrs(unit):
            if k.startswith(prefix) and k.endswith("]"):
                try:
                    out[int(k[len(prefix):-1])] = v
                except ValueError:
                    continue
        return [out[i] for i in sorted(out)]

    # ---- Schreiben ------------------------------------------------------
    def set(self, unit: Unit, key: str, value: str) -> None:
        """Ändert ein vorhandenes Attribut oder fügt es vor der schließenden '}' ein."""
        for i, k, _ in self.attrs(unit):
            if k == key:
                self.lines[i] = f" {key}: {value}"
                return
        self.lines.insert(unit.end, f" {key}: {value}")
        self.reindex()

    def set_array_item(self, unit: Unit, key: str, index: int, value: str) -> None:
        self.set(unit, f"{key}[{index}]", value)

    def replace_array(self, unit: Unit, key: str, values: list[str]) -> None:
        """Ersetzt ein Array komplett: 'key: N' und alle 'key[i]: ...'-Zeilen.

        Steht das Array schon in der Unit, bleiben die neuen Zeilen an derselben Stelle,
        sonst werden sie vor der schließenden '}' eingefügt.
        """
        prefix = key + "["
        positions = [
            i for i, k, _ in self.attrs(unit) if k == key or (k.startswith(prefix) and k.endswith("]"))
        ]
        new_lines = [f" {key}: {len(values)}"] + [f" {key}[{i}]: {v}" for i, v in enumerate(values)]
        if positions:
            at = positions[0]
            for i in reversed(positions):
                del self.lines[i]
        else:
            at = unit.end
        self.lines[at:at] = new_lines
        self.reindex()


# --------------------------------------------------------------------------
# Datei-Ebene
# --------------------------------------------------------------------------

def load(path: str) -> SiiDocument:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise SiiError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    return SiiDocument.from_bytes(decrypt_bytes(raw))


def make_backup(path: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.backup_{stamp}"
    n = 1
    while os.path.exists(backup):
        n += 1
        backup = f"{path}.backup_{stamp}_{n}"
    with open(path, "rb") as src, open(backup, "wb") as dst:
        dst.write(src.read())
    return backup


def save(doc: SiiDocument, path: str, backup: bool = True) -> str | None:
    """Schreibt den Save als Klartext (das Spiel liest Klartext-Saves ohne Probleme).

    Gibt den Pfad des Backups zurück (oder None). Das Original wird erst nach dem
    Backup und über eine temporäre Datei ersetzt.
    """
    backup_path = make_backup(path) if backup and os.path.exists(path) else None
    tmp = path + ".tmp_write"
    try:
        with open(tmp, "wb") as fh:
            fh.write(doc.to_bytes())
        os.replace(tmp, path)
    except OSError as exc:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise SiiError(f"Speichern fehlgeschlagen: {exc}") from exc
    return backup_path
