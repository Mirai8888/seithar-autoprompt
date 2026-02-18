"""Main runner: ingest papers, generate suggestions, output report."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.ingester import load_config, fetch_papers
from src.differ import find_prompt_files, generate_suggestions
from src.summarizer import batch_summarize


def run(config_path="config.yaml"):
    config = load_config(config_path)

    print("[autoprompt] Fetching papers...")
    papers = fetch_papers(config)
    print(f"[autoprompt] {len(papers)} papers matched filters")

    if not papers:
        print("[autoprompt] No new relevant papers. Done.")
        return

    # LLM summarization (local Ollama)
    if config.get("llm", {}).get("summarize", False):
        print(f"[autoprompt] Running LLM analysis on {len(papers)} papers via {config['llm']['model']}...")
        papers = batch_summarize(papers, config)
        analyzed = sum(1 for p in papers if p.get("llm_analysis") and not p["llm_analysis"].get("error"))
        print(f"[autoprompt] {analyzed}/{len(papers)} papers analyzed successfully")

    prompts_dir = config.get("prompts_dir", "../")
    prompt_files = find_prompt_files(prompts_dir)
    print(f"[autoprompt] Found {len(prompt_files)} prompt files to analyze")

    suggestions = generate_suggestions(papers, prompt_files)
    print(f"[autoprompt] Generated {len(suggestions)} suggestions")

    # Write output
    os.makedirs(config["output_dir"], exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # JSON output
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "papers_found": len(papers),
        "suggestions_generated": len(suggestions),
        "papers": papers[:20],
        "suggestions": suggestions
    }
    json_path = os.path.join(config["output_dir"], f"report-{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    # Human-readable report
    diff_path = os.path.join(config["output_dir"], f"diff-{timestamp}.md")
    with open(diff_path, "w") as f:
        f.write(f"# Autoprompt Report\n")
        f.write(f"**{timestamp}** | Papers: {len(papers)} | Suggestions: {len(suggestions)}\n\n")

        f.write("## Papers\n\n")
        for p in papers[:20]:
            f.write(f"### [{p['score']}] {p['title'][:100]}\n")
            f.write(f"Keywords: {', '.join(p['matched_keywords'])}\n")
            f.write(f"Link: {p['link']}\n\n")

            analysis = p.get("llm_analysis", {})
            if analysis and not analysis.get("error") and not analysis.get("parse_error"):
                f.write(f"**Relevance:** {analysis.get('relevance', 'unknown')}\n")
                f.write(f"**Summary:** {analysis.get('summary', 'N/A')}\n")
                f.write(f"**Attack Surface:** {analysis.get('attack_surface', 'N/A')}\n")
                f.write(f"**SCT Codes:** {', '.join(analysis.get('sct_codes', []))}\n")
                f.write(f"**Defense Implications:** {analysis.get('defense_implications', 'N/A')}\n")
                if analysis.get("action_items"):
                    f.write("**Action Items:**\n")
                    for item in analysis["action_items"]:
                        f.write(f"  - {item}\n")
                f.write("\n")
            elif analysis.get("raw_summary"):
                f.write(f"**Analysis:** {analysis['raw_summary'][:500]}\n\n")

        if suggestions:
            f.write("## Suggested Prompt Updates\n\n")
            for s in suggestions:
                f.write(f"### {s['type']} -> `{s['target_file']}` / {s['target_section']}\n\n")
                f.write(f"> {s['suggestion']}\n\n")
                f.write(f"Source: [{s['paper']}]({s['paper_link']}) (score: {s['paper_score']})\n\n")
                f.write("---\n\n")

    print(f"[autoprompt] Report: {diff_path}")
    print(f"[autoprompt] JSON:   {json_path}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run()
