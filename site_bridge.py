"""
Bridge: autoprompt report → seithar.com papers.json

Reads the latest autoprompt report, selects top papers by score,
formats them into the site's papers.json schema, writes to the
site directory, and pushes.

Usage:
    python3 site_bridge.py                # uses latest report
    python3 site_bridge.py report.json    # uses specific report
"""

import json
import glob
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SITE_JSON = Path.home() / "seithar-site" / "2026ARG" / "papers.json"
OUTPUT_DIR = Path(__file__).parent / "output"
MAX_PAPERS = 12

ROMAN_MONTHS = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
    7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII"
}

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}


def extract_arxiv_id(link: str) -> str:
    m = re.search(r'(\d{4}\.\d{4,5})', link)
    return m.group(1) if m else ""


def format_date() -> str:
    now = datetime.now()
    return f"{ROMAN_MONTHS[now.month]} {MONTH_NAMES[now.month]}, {now.year}"


def paper_to_site_entry(paper: dict) -> dict:
    arxiv_id = extract_arxiv_id(paper.get("link", ""))
    title = paper.get("title", "Untitled")
    keywords = paper.get("matched_keywords", [])
    score = paper.get("score", 0)

    # Build tags from matched keywords (clean up +/- prefixes)
    tags = []
    for kw in keywords[:4]:
        tag = kw.lstrip("+-").strip().title()
        if tag and tag not in tags:
            tags.append(tag)

    # Generate annotation from title and keywords
    annotation = f"Scored {score} on autoprompt scan. Keywords: {', '.join(kw.lstrip('+-') for kw in keywords[:4])}."

    # Build article body — placeholder that invites the reader
    body = [
        f"This paper enters the scanner at score {score}, flagged on {len(keywords)} keyword matches across the Seithar taxonomy. "
        f"The primary signals — <em>{', '.join(kw.lstrip('+-') for kw in keywords[:3])}</em> — place it at the intersection of offensive and defensive research.",
        f"Full analysis pending integration with the context engine. The matched keywords suggest relevance to "
        f"{'Shield defensive architecture' if any('trust' in k or 'safety' in k or 'alignment' in k for k in keywords) else 'Sword operational methodology'} "
        f"and the broader question of how autonomous systems maintain coherence under adversarial pressure.",
        f"<strong>Scanner note:</strong> this entry was generated automatically by the Seithar autoprompt daemon. "
        f"Papers above score 10 are flagged for manual review and deep-dive analysis."
    ]

    return {
        "id": arxiv_id,
        "score": score,
        "title": title,
        "date": format_date(),
        "tags": tags,
        "annotation": annotation,
        "article": {
            "deck": f"{title} — autoprompt-detected research with {len(keywords)} keyword matches across the Seithar scanning taxonomy",
            "body": body
        }
    }


def main():
    # Find report
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
    else:
        reports = sorted(glob.glob(str(OUTPUT_DIR / "report-*.json")))
        if not reports:
            print("[bridge] No reports found")
            return
        report_path = reports[-1]

    print(f"[bridge] Reading {report_path}")
    with open(report_path) as f:
        report = json.load(f)

    raw_papers = report.get("papers", [])
    suggestions = report.get("suggestions_generated", report.get("suggestions", []))
    if isinstance(suggestions, list):
        n_suggestions = len(suggestions)
    else:
        n_suggestions = suggestions

    # Sort by score descending, take top N
    raw_papers.sort(key=lambda p: p.get("score", 0), reverse=True)
    top = raw_papers[:MAX_PAPERS]

    # Convert to site schema
    site_papers = [paper_to_site_entry(p) for p in top]

    # Build final JSON
    output = {
        "meta": {
            "scan_date": datetime.now().strftime("%Y-%m-%d"),
            "papers_scanned": len(raw_papers),
            "suggestions": n_suggestions,
            "apply_tasks": min(len(top), 5),
            "subagents_dispatched": 1
        },
        "papers": site_papers
    }

    # Write
    SITE_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SITE_JSON, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[bridge] Wrote {len(site_papers)} papers to {SITE_JSON}")

    # Git push
    site_root = SITE_JSON.parent.parent
    try:
        subprocess.run(["git", "add", "-A"], cwd=site_root, capture_output=True, timeout=30)
        subprocess.run(
            ["git", "commit", "-m", f"[autoprompt] scan {datetime.now().strftime('%Y-%m-%d')} — {len(site_papers)} papers"],
            cwd=site_root, capture_output=True, timeout=30
        )
        result = subprocess.run(
            ["git", "push"], cwd=site_root, capture_output=True, timeout=60
        )
        if result.returncode == 0:
            print("[bridge] Pushed to site repo")
        else:
            print(f"[bridge] Push failed: {result.stderr.decode()[:200]}")
    except Exception as e:
        print(f"[bridge] Git error: {e}")


if __name__ == "__main__":
    main()
