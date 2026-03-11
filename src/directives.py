"""Format autoprompt run output for Seithar Discord #directives."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def build_directives_message(report: Dict[str, Any], diff_path: str, json_path: str, site_url: str) -> str:
    papers: List[Dict[str, Any]] = list(report.get("papers", []))
    papers_found = int(report.get("papers_found", len(papers)))
    suggestions_generated = int(report.get("suggestions_generated", 0))
    run_at = str(report.get("run_at", ""))
    date_label = run_at[:10] if run_at else "unknown"

    top = papers[0] if papers else None
    lines = [
        "╔══════════════════════════════════════════════════╗",
        f"║  研修生 AUTOPROMPT CYCLE — {date_label}              ║",
        "╚══════════════════════════════════════════════════╝",
        "",
        "Autoprompt cycle complete.",
        f"Matched filters: {papers_found} papers",
        f"Suggestions generated: {suggestions_generated}",
        "",
    ]

    if top:
        lines.extend([
            "Highest-signal item from this cycle:",
            "",
            f"**[{top.get('score', '?')}] {top.get('title', 'Untitled')}**",
            f"<{top.get('link', '')}>",
        ])
        analysis = top.get("llm_analysis") or {}
        if isinstance(analysis, dict) and analysis.get("defense_implications"):
            lines.append(f"→ {analysis['defense_implications']}")
        elif top.get("matched_keywords"):
            kws = ", ".join(top.get("matched_keywords", [])[:4])
            lines.append(f"→ High-signal scan hit across: {kws}")
        lines.append("")

    lines.extend([
        f"Site dataset: <{site_url}>",
        "",
        "Outputs:",
        f"- diff: `{diff_path}`",
        f"- json: `{json_path}`",
        "",
        "──────────────────────────────────────────────────",
        "研修生 | Seithar Group Research Division",
        "認知作戦 | seithar.com",
        "──────────────────────────────────────────────────",
    ])
    return "\n".join(lines)


def write_directives_payload(output_dir: str, timestamp: str, message: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_path = out_dir / f"directives-{timestamp}.md"
    payload_path.write_text(message, encoding="utf-8")
    latest_path = out_dir / "latest-directives.md"
    latest_path.write_text(message, encoding="utf-8")
    return payload_path


def write_notification_status(output_dir: str, timestamp: str, payload_path: Path, *, sent: bool, verified: bool, detail: str) -> Path:
    out_dir = Path(output_dir)
    status = {
        "timestamp": timestamp,
        "payload_path": str(payload_path),
        "sent": sent,
        "verified": verified,
        "detail": detail,
    }
    status_path = out_dir / f"directives-status-{timestamp}.json"
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    latest_path = out_dir / "latest-directives-status.json"
    latest_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status_path
