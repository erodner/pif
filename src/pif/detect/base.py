"""Detector interface. A detector scores how injection-like (parts of) a text are."""

from __future__ import annotations

from typing import Protocol

from ..model import Match


class Detector(Protocol):
    name: str

    def detect(self, text: str) -> list[Match]:
        """Return hits as character ranges into `text`."""
        ...
