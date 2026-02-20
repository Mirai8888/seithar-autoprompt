#!/usr/bin/env python3
"""
Auto-task generator: reads latest autoprompt report, produces actionable
task prompts that can be fed directly to subagents via sessions_spawn.

Output: JSON array of task objects with {type, prompt, priority, source_paper}
"""

import json
import os
import glob
import re
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
TASKS_DIR = Path(__file__).parent / "tasks"

# Task templates keyed by paper keyword clusters
TEMPLATES = {
    "adversarial": {
        "type": "research_note",
        "prompt_template": (
            "Write a 400-word Seithar research note analyzing '{title}' "
            "(arxiv: {link}) through the lens of cognitive warfare. "
            "Focus on: how does this map to adversarial manipulation of human "
            "or AI decision-making? What defensive applications exist? "
            "What offensive applications? Be specific and technical. "
            "No em dashes. No marketing language. Clinical voice. "
            "Output as markdown with title and one-paragraph abstract."
        ),
        "priority": 8,
    },
    "jailbreak": {
        "type": "scanner_review",
        "prompt_template": (
            "Review '{title}' ({link}). Extract any new attack patterns "
            "or evasion techniques described. For each, write a 2-sentence "
            "description and suggest whether it maps to an existing SCT code "
            "or warrants a new taxonomy entry. Output as JSON array of "
            "[{{pattern, description, sct_mapping, new_code_needed}}]."
        ),
        "priority": 9,
    },
    "reinforcement learning": {
        "type": "research_note",
        "prompt_template": (
            "Analyze '{title}' ({link}) for applications to behavioral "
            "modeling and substrate manipulation. How could the RL approach "
            "described be adapted to model or influence human decision sequences? "
            "Connect to Dezfouli et al. 2020 if applicable. 300 words, clinical."
        ),
        "priority": 6,
    },
    "manipulation": {
        "type": "content_draft",
        "prompt_template": (
            "Draft a short-form post (under 200 words) for the Seithar voice "
            "about the implications of '{title}' ({link}). "
            "Frame it as something practitioners should know about. "
            "No hashtags. No em dashes. Suitable for Moltbook or similar."
        ),
        "priority": 7,
    },
    "trust": {
        "type": "research_note",
        "prompt_template": (
            "Write a brief analysis of '{title}' ({link}) focusing on trust "
            "dynamics. How does this relate to engineered trust exploitation? "
            "What are the implications for both human and AI substrates? 300 words."
        ),
        "priority": 5,
    },
    "persona": {
        "type": "content_draft",
        "prompt_template": (
            "Review '{title}' ({link}). Extract insights relevant to persona "
            "construction and behavioral modeling. How could these findings "
            "improve synthetic persona fidelity? 200 words, technical."
        ),
        "priority": 7,
    },
}

DEFAULT_TEMPLATE = {
    "type": "research_note",
    "prompt_template": (
        "Write a 200-word research note on '{title}' ({link}) "
        "from a cognitive operations perspective. What's the relevance "
        "to adversarial AI, influence operations, or substrate manipulation? "
        "Clinical voice. No filler."
    ),
    "priority": 3,
}


def get_latest_report():
    """Find the most recent autoprompt report."""
    reports = sorted(glob.glob(str(OUTPUT_DIR / "report-*.json")))
    if not reports:
        # Fall back to markdown
        mds = sorted(glob.glob(str(OUTPUT_DIR / "diff-*.md")))
        if not mds:
            return None
        return parse_markdown_report(mds[-1])
    with open(reports[-1]) as f:
        data = json.load(f)
    # Normalize: report JSON has 'papers' key with 'matched_keywords'
    if "papers" in data:
        for p in data["papers"]:
            if "matched_keywords" in p and "keywords" not in p:
                p["keywords"] = [k.lstrip('+') for k in p["matched_keywords"]]
    return data


def parse_markdown_report(path):
    """Parse the markdown report format into structured data."""
    papers = []
    with open(path) as f:
        content = f.read()

    # Match ### [score] Title\nKeywords: ...\nLink: ...
    pattern = r'### \[(\d+)\] (.+?)\nKeywords: (.+?)\nLink: (.+?)(?:\n|$)'
    for m in re.finditer(pattern, content):
        papers.append({
            "score": int(m.group(1)),
            "title": m.group(2).strip(),
            "keywords": [k.strip().lstrip('+') for k in m.group(3).split(',')],
            "link": m.group(4).strip(),
        })
    return {"papers": papers}


def match_template(keywords):
    """Find best matching template for paper keywords."""
    best = None
    best_prio = -1
    for kw_key, tmpl in TEMPLATES.items():
        for kw in keywords:
            if kw_key in kw.lower():
                if tmpl["priority"] > best_prio:
                    best = tmpl
                    best_prio = tmpl["priority"]
                    break
    return best or DEFAULT_TEMPLATE


def generate_tasks(report, min_score=5, max_tasks=5):
    """Generate task prompts from report papers."""
    papers = report.get("papers", [])
    # Filter by score and sort descending
    papers = [p for p in papers if p.get("score", 0) >= min_score]
    papers.sort(key=lambda p: p.get("score", 0), reverse=True)
    papers = papers[:max_tasks]

    tasks = []
    for paper in papers:
        tmpl = match_template(paper.get("keywords", []))
        prompt = tmpl["prompt_template"].format(
            title=paper["title"],
            link=paper.get("link", "N/A"),
        )
        tasks.append({
            "type": tmpl["type"],
            "prompt": prompt,
            "priority": tmpl["priority"],
            "source_paper": paper["title"],
            "score": paper.get("score", 0),
            "link": paper.get("link", ""),
        })

    return tasks


def main():
    report = get_latest_report()
    if not report:
        print("No autoprompt reports found.")
        return

    tasks = generate_tasks(report)

    TASKS_DIR.mkdir(exist_ok=True)
    # Write latest tasks
    out_path = TASKS_DIR / "latest.json"
    with open(out_path, "w") as f:
        json.dump(tasks, f, indent=2)

    print(f"Generated {len(tasks)} tasks from autoprompt report:")
    for t in tasks:
        print(f"  [{t['priority']}] {t['type']}: {t['source_paper'][:60]}")

    return tasks


if __name__ == "__main__":
    main()
