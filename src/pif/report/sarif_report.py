"""SARIF 2.1.0 output for CI integrations (GitHub code scanning etc.)."""

from __future__ import annotations

import json
from pathlib import Path

from .. import __version__
from ..model import Report, Severity

_LEVEL = {Severity.HIGH: "error", Severity.MEDIUM: "warning", Severity.LOW: "note", Severity.INFO: "none"}


def _rule_id(f) -> str:
    if f.rules:
        return f.rules[0].split(":")[0]
    return f.techniques[0].value if f.techniques else "PIF"


def render(reports: list[Report]) -> str:
    rules: dict[str, dict] = {}
    results = []
    for r in reports:
        uri = Path(r.path).as_posix()
        for f in r.findings:
            rid = _rule_id(f)
            rules.setdefault(rid, {"id": rid, "shortDescription": {"text": f.rules[0].split(":", 1)[1] if f.rules else rid}})
            results.append({
                "ruleId": rid,
                "level": _LEVEL[f.severity],
                "message": {"text": f"{f.detail}: {f.text[:300]}"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
                "properties": {
                    "severity": f.severity.value,
                    "page": f.page,
                    "carrier": f.carrier,
                    "techniques": [t.value for t in f.techniques],
                    "bboxes": [list(b) for b in f.bboxes],
                    "semanticScore": f.semantic_score,
                },
            })
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "promptinjectorfinder", "version": __version__, "rules": list(rules.values())}},
            "results": results,
        }],
    }
    return json.dumps(sarif, indent=2, ensure_ascii=False)
