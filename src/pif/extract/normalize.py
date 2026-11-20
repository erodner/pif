"""Text normalisation that keeps a mapping back to the original characters.

Detectors run on normalised text. Every normalised character carries an *owner*
(an index into the caller's list of original units, e.g. spans), so a hit can be
mapped back to page coordinates.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# Zero-width and other invisible formatting characters (Unicode tag block handled separately).
INVISIBLE_CHARS = {
    "­",  # soft hyphen
    "᠎",
    "​", "‌", "‍", "‎", "‏",
    "‪", "‫", "‬", "‭", "‮",
    "⁠", "⁡", "⁢", "⁣", "⁤",
    "⁦", "⁧", "⁨", "⁩",
    "﻿",
}
TAG_START, TAG_END = 0xE0000, 0xE007F

# Common Cyrillic/Greek look-alikes folded to Latin (NFKC does not do this).
HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ԛ": "q", "ԝ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "Х": "X", "У": "Y", "І": "I",
    "α": "a", "ο": "o", "ν": "v", "ι": "i", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
    "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T",
    "Υ": "Y", "Χ": "X",
})


@dataclass
class InvisibleReport:
    invisible_count: int = 0
    tag_payload: str = ""  # ASCII decoded from Unicode tag characters ("ASCII smuggling")
    owners: set[int] = field(default_factory=set)


@dataclass
class NormText:
    text: str
    owners: list[int]  # owner index per character of `text` (-1 = synthetic whitespace)
    invisible: InvisibleReport


def normalize(chars: list[tuple[str, int]]) -> NormText:
    """Normalise (char, owner) pairs: strip invisibles, NFKC, fold homoglyphs, de-hyphenate."""
    out: list[str] = []
    owners: list[int] = []
    inv = InvisibleReport()
    tag_chars: list[str] = []

    for ch, owner in chars:
        cp = ord(ch)
        if TAG_START <= cp <= TAG_END:
            inv.invisible_count += 1
            inv.owners.add(owner)
            if 0xE0020 <= cp <= 0xE007E:
                tag_chars.append(chr(cp - 0xE0000))
            continue
        if ch in INVISIBLE_CHARS or unicodedata.category(ch) == "Cf":
            inv.invisible_count += 1
            inv.owners.add(owner)
            continue
        norm = unicodedata.normalize("NFKC", ch).translate(HOMOGLYPHS)
        for n in norm:
            if n in "\r\t\f\v ":
                n = " "
            out.append(n)
            owners.append(owner)

    inv.tag_payload = "".join(tag_chars)

    # De-hyphenate words broken across lines: "previ-\nous" -> "previous".
    text_chars, text_owners = [], []
    i = 0
    while i < len(out):
        if (
            out[i] == "-"
            and i + 1 < len(out)
            and out[i + 1] == "\n"
            and text_chars
            and text_chars[-1].isalpha()
            and i + 2 < len(out)
            and out[i + 2].islower()
        ):
            i += 2
            continue
        text_chars.append(out[i])
        text_owners.append(owners[i])
        i += 1

    return NormText("".join(text_chars), text_owners, inv)


def normalize_string(s: str) -> NormText:
    return normalize([(c, 0) for c in s])
