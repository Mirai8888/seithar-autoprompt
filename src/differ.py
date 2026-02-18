"""Diff engine: compare paper findings against current Seithar prompts, output suggested changes."""
import os
import re
import glob
from pathlib import Path


def find_prompt_files(prompts_dir):
    """Locate all files likely containing system prompts."""
    patterns = [
        "**/*SOUL*.md", "**/*BRIEFING*.txt", "**/*BRIEFING*.md",
        "**/*prompt*.md", "**/*prompt*.txt", "**/*prompt*.yaml",
        "**/*AGENTS*.md", "**/*SYSTEM*.md"
    ]
    found = []
    for pattern in patterns:
        found.extend(glob.glob(os.path.join(prompts_dir, pattern), recursive=True))
    return list(set(found))


def extract_sections(filepath):
    """Extract headed sections from a prompt file."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []
    
    sections = []
    current_header = "PREAMBLE"
    current_lines = []
    
    for line in content.split("\n"):
        if re.match(r'^#{1,3}\s+', line):
            if current_lines:
                sections.append({
                    "header": current_header,
                    "content": "\n".join(current_lines).strip()
                })
            current_header = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    
    if current_lines:
        sections.append({
            "header": current_header,
            "content": "\n".join(current_lines).strip()
        })
    
    return sections


def generate_suggestions(papers, prompt_files):
    """Generate diff-style suggestions based on paper findings.
    
    This v0 uses keyword matching to identify which prompt sections
    could benefit from insights in the papers. A future version will
    use LLM inference for deeper analysis.
    """
    suggestions = []
    
    # Map paper topics to prompt improvement categories
    topic_map = {
        "jailbreak": {
            "sections": ["BEHAVIOR", "SAFETY", "CONSTRAINT", "NEVER"],
            "suggestion_type": "defense_hardening",
            "template": "Paper '{title}' describes new {kw} techniques. Review defensive constraints in [{section}] for gaps."
        },
        "prompt injection": {
            "sections": ["BEHAVIOR", "SAFETY", "INPUT", "CONSTRAINT"],
            "suggestion_type": "injection_defense",
            "template": "Paper '{title}' covers {kw} vectors. Audit [{section}] for injection surface."
        },
        "chain of thought": {
            "sections": ["BEHAVIOR", "REASONING", "THINKING", "PROCESS"],
            "suggestion_type": "reasoning_upgrade",
            "template": "Paper '{title}' presents improved {kw} methods. Consider updating reasoning directives in [{section}]."
        },
        "alignment": {
            "sections": ["BEHAVIOR", "CORE", "PRINCIPLE", "IDENTITY"],
            "suggestion_type": "alignment_update",
            "template": "Paper '{title}' has findings on {kw}. Review behavioral alignment in [{section}]."
        },
        "persona": {
            "sections": ["IDENTITY", "TONE", "VOICE", "ROLE"],
            "suggestion_type": "persona_refinement",
            "template": "Paper '{title}' studies {kw} dynamics in LLMs. Consider implications for [{section}]."
        },
        "instruction tuning": {
            "sections": ["BEHAVIOR", "CORE", "TASK", "OPERATIONAL"],
            "suggestion_type": "instruction_optimization",
            "template": "Paper '{title}' improves {kw} methods. Evaluate instruction structure in [{section}]."
        },
    }
    
    for paper in papers:
        matched_kws = [kw.lstrip("+") for kw in paper["matched_keywords"]]
        for kw in matched_kws:
            for topic, config in topic_map.items():
                if topic in kw.lower() or kw.lower() in topic:
                    for pf in prompt_files:
                        sections = extract_sections(pf)
                        for section in sections:
                            header_upper = section["header"].upper()
                            if any(s in header_upper for s in config["sections"]):
                                suggestions.append({
                                    "paper": paper["title"][:80],
                                    "paper_link": paper["link"],
                                    "paper_score": paper["score"],
                                    "type": config["suggestion_type"],
                                    "target_file": os.path.basename(pf),
                                    "target_section": section["header"],
                                    "suggestion": config["template"].format(
                                        title=paper["title"][:60],
                                        kw=kw,
                                        section=section["header"]
                                    )
                                })
                                break  # one suggestion per file per paper-topic
    
    # dedupe and sort by paper score
    seen = set()
    unique = []
    for s in suggestions:
        key = (s["paper"], s["target_file"], s["type"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    
    unique.sort(key=lambda x: x["paper_score"], reverse=True)
    return unique


if __name__ == "__main__":
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    files = find_prompt_files(prompts_dir)
    print(f"Found {len(files)} prompt files:")
    for f in files:
        print(f"  {f}")
