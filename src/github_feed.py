"""GitHub trending repo feed — surfaces repos by star velocity + keyword relevance.

Queries the GitHub Search API for recently created or recently active repos,
calculates star velocity (stars gained per day), and scores against the same
keyword taxonomy used for arXiv papers. Output format matches arXiv entries
so the rest of the autoprompt pipeline works unchanged.

Rate limits: GitHub Search API allows 10 requests/minute unauthenticated,
30/minute with a token. We batch queries to stay within limits.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SeitharAutoprompt/1.0",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _api_get(url: str) -> dict:
    """Make a GitHub API GET request with rate limit handling."""
    req = urllib.request.Request(url, headers=_headers())
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("GitHub API rate limited. Sleeping 60s...")
            time.sleep(60)
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read())
        raise


def _search_repos(query: str, sort: str = "stars", order: str = "desc", per_page: int = 30) -> list[dict]:
    """Search GitHub repos with the given query."""
    params = urllib.parse.urlencode({
        "q": query,
        "sort": sort,
        "order": order,
        "per_page": per_page,
    })
    url = f"{GITHUB_API}/search/repositories?{params}"
    data = _api_get(url)
    return data.get("items", [])


def _get_star_history(owner: str, repo: str) -> int | None:
    """Get approximate star count from 7 days ago using stargazers API.

    Falls back to using created_at date to estimate velocity if history
    is unavailable.
    """
    # Use the stargazers API with timestamps
    url = f"{GITHUB_API}/repos/{owner}/{repo}/stargazers?per_page=1&page=1"
    req = urllib.request.Request(url, headers={
        **_headers(),
        "Accept": "application/vnd.github.star+json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        # Get total count from Link header
        link = resp.headers.get("Link", "")
        if 'rel="last"' in link:
            # Extract last page number = total stargazers
            import re
            match = re.search(r'page=(\d+)>; rel="last"', link)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return None


def calculate_velocity(repo: dict) -> float:
    """Calculate star velocity (stars per day) for a repo.

    Uses created_at date and current star count as baseline.
    More sophisticated approaches would track daily snapshots.
    """
    stars = repo.get("stargazers_count", 0)
    created = repo.get("created_at", "")
    pushed = repo.get("pushed_at", "")

    if not created:
        return 0.0

    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age_days = max((datetime.now(timezone.utc) - created_dt).days, 1)

        # For very new repos (< 30 days), velocity = stars / age
        if age_days <= 30:
            return stars / age_days

        # For older repos, use pushed_at as activity signal
        # Weight recent activity higher
        if pushed:
            pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
            days_since_push = max((datetime.now(timezone.utc) - pushed_dt).days, 1)
            # If pushed recently, assume recent star activity
            if days_since_push <= 7:
                # Estimate: repos pushed recently get ~10% of lifetime velocity
                # as current daily rate, boosted by recency
                lifetime_velocity = stars / age_days
                recency_boost = max(7 - days_since_push, 1)
                return lifetime_velocity * recency_boost
            else:
                return stars / age_days
        return stars / age_days
    except (ValueError, OverflowError):
        return 0.0


def build_search_queries(keywords: dict) -> list[str]:
    """Build GitHub search queries from the keyword taxonomy.

    Groups keywords into search queries to minimize API calls.
    GitHub search supports OR operators within a query.
    """
    queries = []

    # High-value compound queries from primary keywords
    primary = keywords.get("primary", [])
    # GitHub search works best with 2-3 terms per query
    for i in range(0, len(primary), 3):
        chunk = primary[i:i + 3]
        q = " OR ".join(f'"{kw}"' for kw in chunk)
        queries.append(q)

    # Doctrinal keywords
    doctrinal = keywords.get("doctrinal", [])
    for i in range(0, len(doctrinal), 4):
        chunk = doctrinal[i:i + 4]
        q = " OR ".join(f'"{kw}"' for kw in chunk)
        queries.append(q)

    # Topic-specific queries for high-signal combinations
    topic_queries = [
        "LLM red team security",
        "adversarial machine learning attack",
        "cognitive warfare simulation",
        "influence operation detection",
        "prompt injection defense",
        "social engineering AI",
        "disinformation detection",
        "narrative warfare",
        "swarm intelligence agent",
        "OSINT intelligence gathering",
    ]
    queries.extend(topic_queries)

    return queries


def fetch_trending_repos(config: dict, seen_ids: set) -> list[dict]:
    """Fetch and score trending GitHub repos.

    Args:
        config: Full autoprompt config dict.
        seen_ids: Set of already-seen repo IDs to skip.

    Returns:
        List of repo entries in autoprompt paper format.
    """
    keywords = config["keywords"]
    scoring = config["scoring"]
    github_cfg = config.get("github", {})
    min_stars = github_cfg.get("min_stars", 5)
    min_velocity = github_cfg.get("min_velocity", 0.5)
    velocity_weight = github_cfg.get("velocity_weight", 2.0)
    max_results = github_cfg.get("max_results", 50)

    queries = build_search_queries(keywords)
    all_repos: dict[str, dict] = {}  # full_name -> repo data

    # Also search for recently created repos with high stars
    date_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    date_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    queries.append(f"created:>{date_7d} stars:>10")
    queries.append(f"created:>{date_30d} stars:>50")

    for query in queries:
        try:
            print(f"[autoprompt:github] Searching: {query[:60]}...")
            repos = _search_repos(query, per_page=30)
            for repo in repos:
                full_name = repo.get("full_name", "")
                if full_name and full_name not in all_repos:
                    all_repos[full_name] = repo
            # Respect rate limits
            time.sleep(3)
        except Exception as e:
            print(f"[autoprompt:github] Search failed: {e}")
            continue

    print(f"[autoprompt:github] Found {len(all_repos)} unique repos across {len(queries)} queries")

    # Score and filter
    results = []
    for full_name, repo in all_repos.items():
        repo_id = f"github:{full_name}"
        if repo_id in seen_ids:
            continue

        stars = repo.get("stargazers_count", 0)
        if stars < min_stars:
            continue

        # Calculate star velocity
        velocity = calculate_velocity(repo)
        if velocity < min_velocity:
            continue

        # Build text for keyword scoring (name + description + topics)
        description = repo.get("description", "") or ""
        topics = " ".join(repo.get("topics", []))
        language = repo.get("language", "") or ""
        entry = {
            "title": f"{repo.get('name', '')} — {description[:120]}",
            "summary": f"{description} Topics: {topics}. Language: {language}. "
                       f"Stars: {stars}. Forks: {repo.get('forks_count', 0)}. "
                       f"Created: {repo.get('created_at', '')}.",
        }

        # Use existing keyword scorer
        from src.ingester import score_entry
        keyword_score, matched = score_entry(entry, config)

        # Combine keyword score with velocity bonus
        velocity_bonus = min(velocity * velocity_weight, 10)
        total_score = keyword_score + velocity_bonus

        if total_score < scoring["min_score"]:
            continue

        results.append({
            "id": repo_id,
            "title": entry["title"],
            "summary": entry["summary"],
            "link": repo.get("html_url", ""),
            "feed": "github_trending",
            "score": round(total_score, 1),
            "keyword_score": keyword_score,
            "velocity": round(velocity, 2),
            "stars": stars,
            "matched_keywords": matched + [f"velocity:{velocity:.1f}/day"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


if __name__ == "__main__":
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    repos = fetch_trending_repos(config, set())
    print(f"\nFound {len(repos)} trending repos:\n")
    for r in repos[:20]:
        print(f"  [{r['score']:.1f}] {r['title'][:80]}")
        print(f"       stars={r['stars']} velocity={r['velocity']}/day {r['matched_keywords']}")
        print(f"       {r['link']}")
        print()
