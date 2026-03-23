"""arxiv RSS + GitHub trending ingestion and keyword filtering."""
import feedparser
import yaml
import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path


def load_config(config_path="config.yaml"):
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_state(state_file):
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"seen": [], "last_run": None}
    return {"seen": [], "last_run": None}


def save_state(state_file, state):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def score_entry(entry, config):
    """Score an arxiv entry against keyword filters. Returns (score, matched_keywords).

    Deduplication rule: if a shorter keyword is a substring of an already-matched
    longer keyword, it is skipped to avoid double-counting (e.g. 'adversarial'
    inside 'adversarial attack').
    """
    title = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()
    text = f"{title} {summary}"

    score = 0
    matched = []
    matched_lower = []  # tracks all matched keyword strings for dedup

    def already_covered(kw):
        """Return True if kw is a substring of any keyword already matched."""
        return any(kw in m and kw != m for m in matched_lower)

    tier_map = [
        ("primary",   config["keywords"].get("primary", []),   config["scoring"]["primary_weight"]),
        ("doctrinal", config["keywords"].get("doctrinal", []), config["scoring"].get("doctrinal_weight", 2)),
        ("secondary", config["keywords"].get("secondary", []), config["scoring"]["secondary_weight"]),
    ]

    # Sort each tier longest-first so longer phrases claim the match before substrings
    for tier_name, keywords, base_pts in tier_map:
        for kw in sorted(keywords, key=len, reverse=True):
            kw_l = kw.lower()
            if kw_l not in text:
                continue
            if already_covered(kw_l):
                continue
            pts = base_pts
            if kw_l in title:
                pts *= config["scoring"]["title_multiplier"]
            score += pts
            prefix = "+" if tier_name == "primary" else ("~" if tier_name == "doctrinal" else "")
            matched.append(f"{prefix}{kw}")
            matched_lower.append(kw_l)

    return score, matched


def fetch_papers(config):
    """Fetch and filter papers from all configured feeds."""
    state = load_state(config["state_file"])
    seen_ids = set(state["seen"][-500:])  # rolling window
    results = []
    
    import urllib.request
    
    for feed_cfg in config["feeds"]:
        try:
            print(f"[autoprompt] Fetching {feed_cfg['name']}...")
            req = urllib.request.Request(feed_cfg["url"], headers={"User-Agent": "SeitharAutoprompt/1.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read()
            feed = feedparser.parse(raw)
            print(f"[autoprompt] {feed_cfg['name']}: {len(feed.entries)} entries")
        except Exception as e:
            print(f"[autoprompt] Failed to fetch {feed_cfg['name']}: {e}")
            continue
        for entry in feed.entries:
            eid = entry.get("id", entry.get("link", ""))
            if eid in seen_ids:
                continue
            
            score, matched = score_entry(entry, config)
            if score >= config["scoring"]["min_score"]:
                results.append({
                    "id": eid,
                    "title": entry.get("title", "").strip(),
                    "summary": entry.get("summary", "").strip(),
                    "link": entry.get("link", ""),
                    "feed": feed_cfg["name"],
                    "score": score,
                    "matched_keywords": matched,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                })
            seen_ids.add(eid)
    
    # GitHub trending feed
    if config.get("github", {}).get("enabled", False):
        try:
            from src.github_feed import fetch_trending_repos
            github_results = fetch_trending_repos(config, seen_ids)
            for r in github_results:
                results.append(r)
                seen_ids.add(r["id"])
            print(f"[autoprompt] GitHub: {len(github_results)} trending repos")
        except Exception as e:
            print(f"[autoprompt] GitHub feed failed: {e}")

    # update state
    state["seen"] = list(seen_ids)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(config["state_file"], state)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


if __name__ == "__main__":
    config = load_config()
    papers = fetch_papers(config)
    print(f"Found {len(papers)} relevant papers")
    for p in papers[:10]:
        print(f"  [{p['score']}] {p['title'][:80]}")
        print(f"       {p['matched_keywords']}")
