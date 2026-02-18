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


def run(config_path="config.yaml"):
    config = load_config(config_path)
    
    print("[autoprompt] Fetching papers...")
    papers = fetch_papers(config)
    print(f"[autoprompt] {len(papers)} papers matched filters")
    
    if not papers:
        print("[autoprompt] No new relevant papers. Done.")
        return
    
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
    
    # Human-readable diff output
    diff_path = os.path.join(config["output_dir"], f"diff-{timestamp}.md")
    with open(diff_path, "w") as f:
        f.write(f"# Autoprompt Report — {timestamp}\n\n")
        f.write(f"**Papers scanned:** {len(papers)} | **Suggestions:** {len(suggestions)}\n\n")
        
        f.write("## Top Papers\n\n")
        for p in papers[:10]:
            f.write(f"- **[{p['score']}]** [{p['title'][:80]}]({p['link']})\n")
            f.write(f"  Keywords: {', '.join(p['matched_keywords'])}\n\n")
        
        if suggestions:
            f.write("## Suggested Prompt Updates\n\n")
            for s in suggestions:
                f.write(f"### {s['type']} → `{s['target_file']}` / {s['target_section']}\n\n")
                f.write(f"> {s['suggestion']}\n\n")
                f.write(f"Source: [{s['paper']}]({s['paper_link']}) (score: {s['paper_score']})\n\n")
                f.write("---\n\n")
    
    print(f"[autoprompt] Report: {diff_path}")
    print(f"[autoprompt] JSON:   {json_path}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run()
