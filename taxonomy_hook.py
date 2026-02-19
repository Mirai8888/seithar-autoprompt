#!/usr/bin/env python3
"""
Seithar Autoprompt Taxonomy Hook

After processing papers, checks extracted techniques against the
SCT taxonomy via evolve.py. Auto-proposes candidates for novel
techniques and accumulates evidence for known ones.

Usage:
    python taxonomy_hook.py --paper-dir ./output
    python taxonomy_hook.py --paper-file ./output/paper.json

Expected paper JSON format:
    {
        "title": "Paper Title",
        "source": "arxiv:XXXX.XXXXX",
        "techniques": [
            {"description": "...", "evidence": "..."}
        ]
    }
"""

import argparse
import json
import sys
from pathlib import Path

# Path to the evolve module
EVOLVE_PATH = Path(__file__).parent.parent / "seithar-cogdef" / "taxonomy"
sys.path.insert(0, str(EVOLVE_PATH))

try:
    import evolve
except ImportError:
    print(
        "ERROR: Cannot import evolve.py. "
        "Ensure ~/seithar-cogdef/taxonomy/evolve.py exists.",
        file=sys.stderr,
    )
    sys.exit(1)


def process_paper(paper: dict) -> list:
    """Process a single paper's techniques against the taxonomy."""
    results = []
    source = paper.get("source", paper.get("title", "unknown"))
    techniques = paper.get("techniques", [])

    for tech in techniques:
        desc = tech.get("description", "")
        evidence = tech.get("evidence", "")
        if not desc:
            continue
        result = evolve.propose_candidate(
            technique_description=desc,
            source=source,
            evidence=evidence,
        )
        results.append(result)

    return results


def process_paper_file(path: Path) -> list:
    """Load and process a single paper JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        paper = json.load(f)
    return process_paper(paper)


def process_paper_dir(dir_path: Path) -> list:
    """Process all paper JSON files in a directory."""
    results = []
    for fpath in sorted(dir_path.glob("*.json")):
        try:
            results.extend(process_paper_file(fpath))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"WARNING: Skipping {fpath}: {e}", file=sys.stderr)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Seithar Autoprompt Taxonomy Hook",
    )
    parser.add_argument("--paper-dir", help="Directory of paper JSON files")
    parser.add_argument("--paper-file", help="Single paper JSON file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    if not args.paper_dir and not args.paper_file:
        parser.print_help()
        sys.exit(1)

    results = []
    if args.paper_file:
        results = process_paper_file(Path(args.paper_file))
    if args.paper_dir:
        results.extend(process_paper_dir(Path(args.paper_dir)))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            action = r.get("action", "unknown")
            code = r.get("code_id", "?")
            if action == "created_candidate":
                print(f"[NEW] {code}: {r.get('name', '')}")
            elif action == "evidence_added":
                print(f"[+EV] {code}: evidence #{r.get('total_evidence', '?')}")
            else:
                print(f"[???] {json.dumps(r)}")

    # Run promotion check after processing
    promoted = evolve.promote_candidates(min_sources=3)
    for p in promoted:
        print(f"[PROMOTED] {p['code_id']} (sources: {p['sources']})")


if __name__ == "__main__":
    main()
