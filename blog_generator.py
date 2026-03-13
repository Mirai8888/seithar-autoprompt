#!/usr/bin/env python3
"""
blog_generator.py — autoprompt paper → seithar.com blog article pipeline

Reads the latest autoprompt report, generates Seithar-voice articles for
top-scoring papers not yet published, writes HTML to seithar-site, updates
blog/index.html, and pushes to git.

Usage:
    python3 blog_generator.py                  # uses latest report
    python3 blog_generator.py output/foo.json  # uses specific report
    python3 blog_generator.py --dry-run        # generate but don't push
"""

import json
import os
import re
import subprocess
import sys
import glob
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────────
SITE_DIR        = Path.home() / "seithar-site" / "2026ARG"
BLOG_DIR        = SITE_DIR / "blog"
BLOG_INDEX      = BLOG_DIR / "index.html"
OUTPUT_DIR      = Path(__file__).parent / "output"
PAPERS_JSON     = SITE_DIR / "papers.json"
STATE_FILE      = Path(__file__).parent / "state" / "blog_published.json"
MIN_SCORE       = 5          # minimum autoprompt score to generate an article
MAX_PER_RUN     = 3          # max articles generated in one run
LLM_BASE        = "http://localhost:3456/v1"
LLM_MODEL       = "claude-sonnet-4"

MONTH_NAMES = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}

# ── helpers ───────────────────────────────────────────────────────────────────
def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"published": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text[:60].rstrip("-")

def arxiv_id_from_link(link: str) -> str:
    m = re.search(r"(\d{4}\.\d{4,5})", link)
    return m.group(1) if m else link

def latest_report() -> Path | None:
    # Prefer the live site papers.json (always up-to-date after site_bridge runs)
    if PAPERS_JSON.exists():
        return PAPERS_JSON
    # Fall back to latest autoprompt output JSON
    reports = sorted(glob.glob(str(OUTPUT_DIR / "*.json")), reverse=True)
    return Path(reports[0]) if reports else None

def llm_call(system: str, user: str) -> str:
    body = json.dumps({
        "model": LLM_MODEL,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    }).encode()
    req = urllib.request.Request(
        f"{LLM_BASE}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    resp = json.load(urllib.request.urlopen(req, timeout=120))
    return resp["choices"][0]["message"]["content"].strip()

# ── article generator ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the writing engine for Seithar Group, a cognitive security research organization.
You write institutional research articles in a precise, clinical voice.

Voice rules — follow exactly:
- Open with a concrete operational scenario (named, specific, grounded)
- Deliver the thesis in a short standalone sentence after the scenario. No hedging.
- Cite the paper's authors, year, and journal naturally in the argument — never as footnotes
- Use Seithar terminology naturally: cognitive substrate, narrative capture, drift, vulnerability surface, active inference, identity baseline, adversarial pressure
- Technical depth without simplification. The reader is a security professional.
- Subheaders (H2) for pieces over 600 words
- The closing paragraph diagnoses — never sells, never wraps up neatly
- End with the citation in academic format on its own line, then "Seithar Group Intelligence Division  seithar.com" on the next line
- No marketing language. No "In conclusion". No calls to action.
- Short paragraphs for impact. Vary length deliberately.

Output JSON with these fields:
{
  "title": "short punchy title (3-6 words, all caps OK for impact)",
  "slug": "url-slug-lowercase-hyphens",
  "meta_description": "1-2 sentence meta description for SEO, 150 chars max",
  "deck": "1-2 sentence lede for the blog index card",
  "body_html": "full article body as HTML — use <p>, <h2>, <blockquote>, <strong>, <em> only. No divs. No classes."
}"""

def generate_article(paper: dict) -> dict:
    user = f"""Paper to analyze and write about:

Title: {paper['title']}
ArXiv ID: {arxiv_id_from_link(paper.get('link', ''))}
Feed: {paper.get('feed', 'cs.AI')}
Score: {paper['score']}
Matched keywords: {', '.join(paper.get('matched_keywords', []))}

Abstract:
{paper.get('summary', '')}

Write a full Seithar Group blog article about this paper's implications for cognitive security and autonomous agent defense. The article should be 500-800 words. Connect the findings to real operational threat scenarios."""

    raw = llm_call(SYSTEM_PROMPT, user)
    # strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    # extract outermost JSON object in case of preamble text
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    # fix lone backslashes that break JSON parsing (e.g. LaTeX in abstracts)
    raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
    return json.loads(raw)

# ── HTML template ─────────────────────────────────────────────────────────────
def render_html(title: str, slug: str, meta_desc: str, body_html: str, date_str: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Seithar Group</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=UnifrakturMaguntia&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Playfair+Display+SC:wght@400;700&family=DM+Mono:wght@300;400&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300;1,8..60,400&display=swap" rel="stylesheet">
<meta name="description" content="{meta_desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="https://seithar.com/blog/{slug}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:site" content="@SeitharGroup">
<link rel="canonical" href="https://seithar.com/blog/{slug}.html">
<style>
:root {{
  --bg:#ededeb;--card:#f9f9f8;--rule:#c8c8c4;--rule-s:#a0a09a;
  --ink:#111110;--mid:#444440;--dim:#888884;--ghost:#bbbbb6;
}}
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box;}}
html{{font-size:16px;}}
body{{background:var(--bg);color:var(--ink);font-family:"Source Serif 4",serif;font-weight:300;-webkit-font-smoothing:antialiased;}}
a{{text-decoration:none;color:inherit;}}
.hd{{border-bottom:1px solid var(--rule-s);background:var(--bg);position:sticky;top:0;z-index:100;}}
.hd-top{{display:flex;align-items:stretch;height:60px;border-bottom:1px solid var(--rule);}}
.hd-wm{{display:flex;align-items:center;gap:14px;padding:0 20px;border-right:1px solid var(--rule);flex-shrink:0;text-decoration:none;color:inherit;}}
.wm-n{{font-family:"UnifrakturMaguntia",cursive;font-size:1.6rem;font-weight:400;letter-spacing:0.12em;}}
.wm-d{{width:1px;height:14px;background:var(--rule-s);}}
.wm-s{{font-family:"DM Mono",monospace;font-size:0.46rem;letter-spacing:0.18em;text-transform:uppercase;color:var(--dim);}}
.hd-nav{{display:flex;align-items:stretch;flex:1;overflow:hidden;}}
.hd-nav a{{display:flex;align-items:center;justify-content:center;flex:1;padding:0 15px;font-family:"DM Mono",monospace;font-size:0.75rem;letter-spacing:0.2em;text-transform:uppercase;color:var(--dim);border-right:1px solid var(--rule);white-space:nowrap;transition:color .1s,background .1s;}}
.hd-nav a:hover{{color:var(--ink);background:var(--card);}}
.hd-nav a.on{{color:var(--ink);}}
.hd-sub{{display:flex;align-items:stretch;height:24px;overflow:hidden;}}
.hd-cell{{display:flex;align-items:center;padding:0 14px;border-right:1px solid var(--rule);font-family:"DM Mono",monospace;font-size:0.42rem;letter-spacing:0.12em;color:var(--ghost);white-space:nowrap;}}
.page-content{{max-width:820px;margin:0 auto;padding:48px 32px 80px;}}
.ft{{border-top:1px solid var(--rule-s);width:100%;}}
.ft-g{{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--rule);}}
.ft-c{{padding:14px 16px;border-right:1px solid var(--rule);}}
.ft-c:last-child{{border-right:none;}}
.ft-ct{{font-family:"DM Mono",monospace;font-size:0.6rem;letter-spacing:0.28em;text-transform:uppercase;color:var(--ghost);margin-bottom:7px;padding-bottom:5px;border-bottom:1px solid var(--rule);}}
.ft-c a,.ft-c span{{display:block;font-family:"DM Mono",monospace;font-size:0.65rem;color:var(--dim);padding:2px 0;letter-spacing:0.05em;line-height:1.7;}}
.ft-c a:hover{{color:var(--ink);}}
.ft-co{{padding:9px 16px;display:flex;justify-content:space-between;align-items:center;}}
.ft-co span{{font-family:"DM Mono",monospace;font-size:0.6rem;letter-spacing:0.12em;color:var(--ghost);text-transform:uppercase;}}
h1{{font-family:"Playfair Display",serif;font-size:1.8rem;font-weight:700;line-height:1.3;margin-bottom:40px;letter-spacing:-0.01em;}}
h2{{font-family:"DM Mono",monospace;font-size:1rem;font-weight:600;margin:48px 0 16px;letter-spacing:0.02em;}}
p{{margin-bottom:20px;font-size:1.05rem;line-height:1.75;color:var(--mid);}}
.meta-line{{font-family:"DM Mono",monospace;font-size:0.65rem;letter-spacing:0.08em;text-transform:uppercase;color:var(--ghost);margin-bottom:32px;}}
blockquote{{border-left:2px solid var(--rule-s);padding-left:20px;margin:28px 0;color:var(--dim);font-style:italic;}}
.footnote{{font-size:0.85rem;color:var(--dim);border-top:1px solid var(--rule);padding-top:24px;margin-top:64px;}}
.back-link{{display:inline-block;margin-top:48px;font-family:"DM Mono",monospace;font-size:0.75rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--dim);}}
.back-link:hover{{color:var(--ink);}}
strong{{font-weight:600;color:var(--ink);}}
em{{font-style:italic;color:var(--ink);}}
</style>
</head>
<body>

<header class="hd">
  <div class="hd-top">
    <a href="/" class="hd-wm">
      <span class="wm-n">Seithar</span>
      <div class="wm-d"></div>
      <span class="wm-s">Cognitive Warfare</span>
    </a>
    <nav class="hd-nav">
      <a href="/about.html">About</a>
      <a href="/personnel.html">Personnel</a>
      <a href="/research.html">Research</a>
      <a href="/services.html">Services</a>
      <a href="/whitepaper.html">Whitepaper</a>
      <a href="/blog/" class="on">Blog</a>
      <a href="https://discord.gg/8kMvPrStuh">Discord</a>
      <a href="https://seithar.substack.com">Substack</a>
    </nav>
  </div>
  <div class="hd-sub">
    <div class="hd-cell">Seithar Group &middot; Cognitive Warfare Division</div>
    <div class="hd-cell">{date_str}</div>
  </div>
</header>

<div class="page-content">
  <div class="meta-line"><a href="/blog/">Blog</a> &nbsp;&rarr;&nbsp; Research</div>
  <h1>{title}</h1>
  <div class="meta-line">{date_str} &nbsp;&middot;&nbsp; Seithar Group Intelligence Division</div>

{body_html}

  <a href="/blog/" class="back-link">&larr; All Articles</a>
</div>

<footer class="ft">
  <div class="ft-g">
    <div class="ft-c">
      <div class="ft-ct">Seithar Group</div>
      <a href="/">About</a><a href="/personnel.html">Personnel</a>
      <a href="/research.html">Research</a><a href="/services.html">Services</a><a href="/whitepaper.html">Whitepaper</a>
    </div>
    <div class="ft-c">
      <div class="ft-ct">Research</div>
      <a href="/whitepaper.html">Whitepaper</a>
      <a href="/blog/why-your-ai-agent-has-no-immune-system.html">Agent Immune Systems</a>
      <a href="/blog/the-fragmentation-attack.html">Fragmentation Attack</a>
      <a href="/blog/dual-substrate-threat-model.html">Dual-Substrate Threat</a>
    </div>
    <div class="ft-c">
      <div class="ft-ct">Latest Scan</div>
      <span id="ft-scan-date">—</span>
      <span id="ft-scan-count">—</span>
      <span id="ft-scan-agents">—</span>
    </div>
    <div class="ft-c">
      <div class="ft-ct">Contact</div>
      <a href="https://discord.gg/8kMvPrStuh">Discord</a>
      <a href="https://x.com/SeitharGroup">X / Twitter</a>
      <a href="https://seithar.substack.com">Substack</a>
      <a href="/blog/">Blog</a>
    </div>
    <div class="ft-c">
      <div class="ft-ct">Cognitive Warfare</div>
      <span>&copy; 2026 Seithar Group</span>
      <span>seithar.com</span>
    </div>
  </div>
  <div class="ft-co">
    <span>Seithar Group &middot; Cognitive Warfare Division &middot; Est. 2022</span>
    <span>Minds are hackable. We are the security layer.</span>
  </div>
</footer>

</body>
</html>"""

# ── blog index injection ───────────────────────────────────────────────────────
def inject_index_entry(title: str, slug: str, deck: str, month_year: str):
    html = BLOG_INDEX.read_text()
    entry = f"""<article style="margin-bottom:40px;padding-bottom:40px;border-bottom:1px solid var(--rule);">
  <div style="font-family:'DM Mono',monospace;font-size:0.55rem;letter-spacing:0.1em;color:var(--ghost);text-transform:uppercase;margin-bottom:8px;">{month_year}</div>
  <h2 style="font-family:'Playfair Display',serif;font-size:1.3rem;font-weight:700;margin-bottom:10px;line-height:1.3;"><a href="{slug}.html" style="color:var(--ink);border-bottom:1px solid transparent;transition:border-color .1s;">{title}</a></h2>
  <p style="font-size:0.95rem;color:var(--mid);line-height:1.7;margin-bottom:10px;">{deck}</p>
  <a href="{slug}.html" style="font-family:'DM Mono',monospace;font-size:0.65rem;letter-spacing:0.08em;color:var(--dim);">Read &rarr;</a>
</article>

"""
    # inject before the first <article
    html = html.replace("<article ", entry + "<article ", 1)
    BLOG_INDEX.write_text(html)

# ── git push ──────────────────────────────────────────────────────────────────
def git_push(paths: list[str], message: str):
    site_root = Path.home() / "seithar-site"
    subprocess.run(["git", "add"] + paths, cwd=site_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=site_root, check=True)
    subprocess.run(["git", "push"], cwd=site_root, check=True)

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv
    report_path = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and arg.endswith(".json"):
            report_path = Path(arg)

    if report_path is None:
        report_path = latest_report()
    if report_path is None:
        print("[blog_gen] No report found in output/. Run autoprompt first.")
        sys.exit(1)

    print(f"[blog_gen] Reading report: {report_path}")
    report = json.loads(report_path.read_text())
    # papers.json has {"papers": [...]} at top level; directives JSON differs
    if "papers" in report:
        papers = report["papers"]
    elif isinstance(report, list):
        papers = report
    else:
        papers = report.get("papers", [])

    state = load_state()
    published_ids = set(state["published"])

    # normalize link field (papers.json nests it under source.link)
    for p in papers:
        if "link" not in p:
            p["link"] = (p.get("source") or {}).get("link", "")
        if "summary" not in p:
            p["summary"] = p.get("article", {}).get("summary", "")
        if "matched_keywords" not in p:
            p["matched_keywords"] = p.get("tags", [])

    candidates = [
        p for p in papers
        if p.get("score", 0) >= MIN_SCORE
        and arxiv_id_from_link(p.get("link", "")) not in published_ids
    ][:MAX_PER_RUN]

    if not candidates:
        print("[blog_gen] No new papers above threshold. Nothing to publish.")
        return

    now = datetime.now(timezone.utc)
    date_str = f"{MONTH_NAMES[now.month]} {now.day}, {now.year}"
    month_year = f"{MONTH_NAMES[now.month]} {now.year}"
    pushed_paths = []

    for paper in candidates:
        arxiv_id = arxiv_id_from_link(paper.get("link", ""))
        print(f"[blog_gen] Generating article for [{paper['score']}] {paper['title'][:60]}...")

        try:
            article = generate_article(paper)
        except Exception as e:
            print(f"[blog_gen] LLM generation failed: {e}")
            continue

        slug = article.get("slug") or slugify(article.get("title", paper["title"]))
        title = article.get("title", paper["title"])
        meta_desc = article.get("meta_description", "")
        deck = article.get("deck", "")
        body_html = article.get("body_html", "")

        html = render_html(title, slug, meta_desc, body_html, date_str)
        out_path = BLOG_DIR / f"{slug}.html"

        if not dry_run:
            out_path.write_text(html)
            inject_index_entry(title, slug, deck, month_year)
            pushed_paths += [
                str(out_path.relative_to(Path.home() / "seithar-site")),
                str(BLOG_INDEX.relative_to(Path.home() / "seithar-site")),
            ]
            state["published"].append(arxiv_id)
            save_state(state)
            print(f"[blog_gen] Written: {out_path.name}")
        else:
            print(f"[blog_gen] [DRY RUN] Would write: {out_path.name}")
            print(f"  Title: {title}")
            print(f"  Deck:  {deck[:80]}")

    if pushed_paths and not dry_run:
        commit_msg = f"blog: auto-publish {len(candidates)} article(s) from autoprompt scan"
        git_push(list(dict.fromkeys(pushed_paths)), commit_msg)
        print(f"[blog_gen] Pushed {len(candidates)} article(s) to seithar-site.")

if __name__ == "__main__":
    main()
