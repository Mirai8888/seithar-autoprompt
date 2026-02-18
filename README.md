# seithar-autoprompt

Automated prompt evolution engine. Ingests research from arxiv, extracts prompting technique findings, and generates diff-style suggestions against existing Seithar system prompts.

## Architecture

```
arxiv RSS (cs.CL, cs.AI, cs.CR, cs.MA)
    ↓
[ingester] — keyword filter + scoring
    ↓
[differ] — map findings → prompt sections
    ↓
[output] — diff report (markdown + JSON)
```

## Usage

```bash
pip install -r requirements.txt
python -m src.runner
```

Output lands in `./output/` as timestamped markdown diffs and JSON reports.

## Configuration

Edit `config.yaml` to adjust feeds, keywords, scoring weights, and paths.

## Roadmap

- [ ] v0: RSS ingestion, keyword scoring, section-level diff suggestions ← current
- [ ] v1: LLM-powered paper summarization and specific prompt rewrite suggestions
- [ ] v2: Auto-apply approved diffs, version tracking, regression testing
- [ ] v3: Self-improvement loop — merge approved changes back into active prompts

---

研修生 | Seithar Group Research Division | 認知作戦 | seithar.com
