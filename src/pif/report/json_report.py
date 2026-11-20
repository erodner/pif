from __future__ import annotations

import json

from ..model import Report


def render(reports: list[Report]) -> str:
    return json.dumps([r.to_dict() for r in reports], indent=2, ensure_ascii=False)
