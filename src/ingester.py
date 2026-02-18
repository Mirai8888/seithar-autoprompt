"""arxiv RSS ingestion and keyword filtering."""
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
    """Score an arxiv entry against keyword filters. Returns (score, matched_keywords)."""
    title = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()
    text = f"{title} {summary}"
    
    score = 0
    matched = []
    
    for kw in config["keywords"]["primary"]:
        if kw.lower() in text:
            pts = config["scoring"]["primary_weight"]
            if kw.lower() in title:
                pts *= config["scoring"]["title_multiplier"]
            score += pts
            matched.append(f"+{kw}")
    
    for kw in config["keywords"]["secondary"]:
        if kw.lower() in text:
            pts = config["scoring"]["secondary_weight"]
            if kw.lower() in title:
                pts *= config["scoring"]["title_multiplier"]
            score += pts
            matched.append(kw)
    
    return score, matched


def fetch_papers(config):
    """Fetch and filter papers from all configured feeds."""
    state = load_state(config["state_file"])
    seen_ids = set(state["seen"][-500:])  # rolling window
    results = []
    
    for feed_cfg in config["feeds"]:
        try:
            feed = feedparser.parse(feed_cfg["url"])
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
                    "summary": entry.get("summary", "").strip()[:500],
                    "link": entry.get("link", ""),
                    "feed": feed_cfg["name"],
                    "score": score,
                    "matched_keywords": matched,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                })
            seen_ids.add(eid)
    
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
