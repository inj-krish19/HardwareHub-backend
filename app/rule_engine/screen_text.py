"""
Recognise common error screens from their text (for example text read from a photo).

A photo of a blue screen or a boot error contains a lot of words that no guide mentions
("collecting error info", "100% complete"). This module spots the KIND of screen from a
few tell-tale phrases and adds the hand-written search terms of the guides that handle it,
so the usual matcher can find them. It never writes an answer: it only helps choose which
guide to suggest. Pure functions, no database.

It also reads PART LABELS (the sticker on a RAM stick, an SSD, a graphics card, a processor or a power
supply). Printed text such as "DDR4 3200MHz" or "80 PLUS" is reliable to read; judging a part by its
appearance is not, so that is deliberately not attempted.

Every phrase and term below was written by hand. The terms are chosen to equal real keywords
of the guides (see app/data/seed), because the matcher rewards whole keyword phrases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenKind:
    kind: str
    label: str            # shown to the person: "That looks like <label>."
    phrases: tuple[str, ...]   # lower-case; a match on any one is enough
    terms: str            # added to the matcher's query


# Words are compared after lower-casing and squashing every run of non-letters/digits to one space.
SCREEN_KINDS: tuple[ScreenKind, ...] = (
    ScreenKind(
        "bsod", "a Windows blue screen",
        ("ran into a problem", "needs to restart", "stop code", "collecting error info", "collecting some error info",
         "blue screen", "bugcheck", "what failed"),
        "blue screen of death bsod errors",
    ),
    ScreenKind(
        "boot_device", "a message that the PC cannot find its boot drive",
        ("no bootable device", "operating system not found", "reboot and select proper boot device", "boot device not found",
         "missing operating system", "bootmgr is missing", "no boot device", "a disk read error occurred",
         "needs to be repaired", "boot configuration data", "insert system disk", "disk boot failure"),
        "storage drive not detected boot drive not found",
    ),
    ScreenKind(
        "no_signal", "a 'no signal' message from the monitor",
        ("no signal", "no input signal", "no video input", "check signal cable", "cable not connected", "no display signal"),
        "monitor no signal screen says check cable",
    ),
    ScreenKind(
        "fan_error", "a CPU fan error message",
        ("cpu fan error", "cpu fan speed error", "cpu fan failed", "cpu fan not detected", "fan error", "cpu fan has failed"),
        "cooler not detected by motherboard fan speed shows zero",
    ),
    ScreenKind(
        "overheating", "an overheating warning",
        ("cpu over temperature", "cpu temperature too high", "over temperature", "overheat", "thermal shutdown",
         "temperature warning", "system will shut down"),
        "pc shuts down from overheating cpu too hot shutdown",
    ),
    ScreenKind(
        "memory_error", "a memory (RAM) error message",
        ("memory test failed", "memtest", "memory diagnostic", "memory error", "ram error", "dimm error", "memory management",
         "memory_management"),
        "pc crashes randomly game closing with memory error",
    ),
)


@dataclass(frozen=True)
class ScreenHint:
    kind: str
    label: str
    terms: str


def _squash(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


# ---- part labels ----
# (kind, pattern that says "this text is the label of such a part", terms to add)
_I = re.IGNORECASE
PART_RULES: tuple[tuple[str, re.Pattern, str], ...] = (
    ("part_ram", re.compile(r"\bDDR[2-5]\b|\bPC[345]L?-\d{4,5}\b|\bSO-?DIMM\b|\bDIMM\b|\bVengeance\b|\bRipjaws\b", _I),
     "ram type for my motherboard ddr4 or ddr5 ram memory compatible with motherboard"),
    ("part_storage", re.compile(r"\bNVMe\b|\bM\.2\b|\bSATA\s?(?:III|3|6)?\b|\bSSD\b|\bPCIe\s?Gen\s?[345]\b", _I),
     "is this ssd compatible m.2 ssd for my motherboard nvme or sata"),
    ("part_gpu", re.compile(r"\b(?:GeForce|RTX\s?\d{3,4}|GTX\s?\d{3,4}|Radeon|RX\s?\d{3,4}|Arc\s?A\d{3})", _I),
     "graphics card compatibility is my gpu compatible does my psu support this gpu"),
    ("part_cpu", re.compile(r"\bRyzen\s?[3579]\s?\d{3,4}\w*|\bCore\s?i[3579][- ]?\d{4,5}\w*|\bIntel\s?Core\b|\bAthlon\b", _I),
     "cpu compatible with motherboard cpu socket type"),
    ("part_psu", re.compile(r"\b80\s?\+?\s?PLUS\b|\bATX12V\b|\bPSU\b|\bpower\s+supply\b", _I),
     "psu wattage for my pc is my power supply enough"),
)


def _first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, _I)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def _part_label(kind: str, text: str) -> str:
    """Say what the label shows, using only what is printed on it."""
    if kind == "part_ram":
        gen = _first(r"\bDDR[2-5]\b", text)
        speed = re.search(r"\b(\d{3,4})\s?MHz\b", text, _I)
        size = _first(r"\b\d{1,3}\s?GB\b", text)
        bits = " ".join(x for x in (gen.upper() if gen else None, f"{speed.group(1)} MHz" if speed else None) if x)
        return f"a {bits + ' ' if bits else ''}memory module" + (f" ({size.upper()})" if size else "")
    if kind == "part_storage":
        if _first(r"\bNVMe\b|\bM\.2\b", text):
            return "an NVMe / M.2 SSD"
        return "a SATA drive" if _first(r"\bSATA", text) else "an SSD"
    if kind == "part_gpu":
        model = _first(r"\b(?:RTX|GTX|RX)\s?\d{3,4}\w*|\bArc\s?A\d{3}", text)
        return f"a graphics card ({model})" if model else "a graphics card"
    if kind == "part_cpu":
        model = _first(r"\bRyzen\s?[3579]\s?\d{3,4}\w*|\bCore\s?i[3579][- ]?\d{4,5}\w*", text)
        return f"a processor ({model})" if model else "a processor"
    watts = _first(r"\b\d{3,4}\s?W\b", text)
    return f"a power supply ({watts.replace(' ', '').upper()})" if watts else "a power supply"


def detect(text: str) -> list[ScreenHint]:
    """Every kind of screen or part label the text looks like, in the order they appear in the text."""
    squashed = _squash(text)
    found: list[tuple[int, ScreenHint]] = []
    for sk in SCREEN_KINDS:
        positions = [squashed.find(_squash(p)) for p in sk.phrases]
        positions = [p for p in positions if p >= 0]
        if positions:
            found.append((min(positions), ScreenHint(sk.kind, sk.label, sk.terms)))
    for kind, pattern, terms in PART_RULES:
        m = pattern.search(text)
        if m:
            found.append((m.start(), ScreenHint(kind, _part_label(kind, text), terms)))
    return [hint for _, hint in sorted(found, key=lambda item: item[0])]


def augment_query(query: str, hints: list[ScreenHint]) -> str:
    """The text to match on: what the person gave, plus the terms of every recognised screen."""
    return " ".join([query, *[h.terms for h in hints]]) if hints else query


def describe(hints: list[ScreenHint]) -> str:
    """'That looks like a Windows blue screen.' (or two joined with 'and')."""
    if not hints:
        return ""
    labels = [h.label for h in hints[:2]]
    return "That looks like " + " and ".join(labels) + "."