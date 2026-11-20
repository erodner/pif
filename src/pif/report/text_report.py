from __future__ import annotations

import textwrap

from ..model import Report, Severity

_ICON = {Severity.HIGH: "HIGH  ", Severity.MEDIUM: "MEDIUM", Severity.LOW: "LOW   ", Severity.INFO: "INFO  "}


def render(reports: list[Report], min_severity: Severity = Severity.LOW) -> str:
    lines: list[str] = []
    for r in reports:
        shown = [f for f in r.findings if f.severity.rank >= min_severity.rank]
        ms = r.max_severity
        if shown:
            status = f"{len(shown)} finding(s), max {ms.value.upper()}"
        else:
            status = "ERROR" if r.errors else "clean"
        lines.append(f"== {r.path}  [{r.pages} pages, {r.seconds:.2f}s]  {status}")
        for e in r.errors:
            lines.append(f"   ERROR {e}")
        for f in shown:
            where = f"p.{f.page}" if f.page else f.carrier
            tech = ", ".join(t.value for t in f.techniques) or "-"
            lines.append(f"   [{_ICON[f.severity]}] {where:<10} {f.carrier}  techniques: {tech}")
            lines.append(f"            {f.detail}")
            if f.rules:
                lines.append(f"            rules: {'; '.join(f.rules)}")
            snippet = f.text if len(f.text) <= 400 else f.text[:400] + "…"
            lines.extend(textwrap.wrap(snippet.replace("\n", " "), 100, initial_indent="            > ", subsequent_indent="              "))
        lines.append("")
    return "\n".join(lines)
