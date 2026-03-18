"""
alphaXiv semantic search feed — finds papers by conceptual similarity
instead of keyword matching.

Reverse-engineered from the alphaXiv MCP server spec. Calls their API
directly without the MCP transport layer.

Three search modes:
  1. Embedding similarity — vector search, finds conceptually related papers
  2. Full text search — keyword search across all of arXiv
  3. Agentic retrieval — multi-turn autonomous search (beta)

Also supports:
  - Paper content retrieval (full text or AI summary)
  - PDF question answering
  - GitHub repo exploration for paper codebases
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ALPHAXIV_API = "https://api.alphaxiv.org"
ALPHAXIV_KEY = "pk_live_Y2xlcmsuYWxwaGF4aXYub3JnJA"


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ALPHAXIV_KEY}",
        "User-Agent": "SeitharAutoprompt/1.0",
    }


def _mcp_call(tool: str, arguments: dict) -> dict:
    """Call an alphaXiv MCP tool via their HTTP API.

    The MCP server accepts JSON-RPC style requests. We bypass the SSE
    transport and call the tool endpoint directly.
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": arguments,
        },
        "id": int(time.time()),
    }).encode()

    req = urllib.request.Request(
        f"{ALPHAXIV_API}/mcp/v1",
        data=payload,
        headers=_headers(),
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return data.get("result", data)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error("alphaXiv API error %d: %s", e.code, body)
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        logger.error("alphaXiv request failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def semantic_search(query: str) -> list[dict]:
    """Find papers by conceptual similarity using embeddings.

    Args:
        query: 2-3 sentence description of the research area.
               More detailed queries produce better results.

    Returns:
        Up to 25 papers ranked by similarity + popularity.
    """
    result = _mcp_call("embedding_similarity_search", {"query": query})
    if "error" in result:
        logger.warning("Semantic search failed: %s", result["error"])
        return []
    return _extract_papers(result)


def keyword_search(query: str) -> list[dict]:
    """Keyword search across arXiv full text.

    Args:
        query: 3-4 plain keywords separated by spaces. No quotes.

    Returns:
        Up to 25 papers with matching text snippets.
    """
    result = _mcp_call("full_text_papers_search", {"query": query})
    if "error" in result:
        logger.warning("Keyword search failed: %s", result["error"])
        return []
    return _extract_papers(result)


def agentic_search(query: str) -> list[dict]:
    """Multi-turn autonomous paper retrieval (beta).

    Args:
        query: Natural language research question.

    Returns:
        Papers ordered by relevance.
    """
    result = _mcp_call("agentic_paper_retrieval", {"query": query})
    if "error" in result:
        logger.warning("Agentic search failed: %s", result["error"])
        return []
    return _extract_papers(result)


def get_paper_content(url: str, full_text: bool = False) -> str:
    """Retrieve paper content.

    Args:
        url: arXiv or alphaXiv URL.
        full_text: If True, returns raw extracted text. Otherwise AI summary.

    Returns:
        Paper text content.
    """
    args: dict[str, Any] = {"url": url}
    if full_text:
        args["fullText"] = True
    result = _mcp_call("get_paper_content", args)
    if "error" in result:
        return ""
    # Extract text from MCP response
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content
                if isinstance(item, dict)
            )
        return str(content)
    return str(result)


def ask_paper(url: str, question: str) -> str:
    """Ask a question about a specific paper.

    Args:
        url: PDF or abstract URL.
        question: Question about the paper.

    Returns:
        Natural language answer.
    """
    result = _mcp_call("answer_pdf_queries", {"url": url, "query": question})
    if "error" in result:
        return ""
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content
                if isinstance(item, dict)
            )
    return str(result)


def explore_repo(github_url: str, path: str = "/") -> str:
    """Explore a paper's GitHub repository.

    Args:
        github_url: Repository URL.
        path: File/directory path, "/" for root.

    Returns:
        File contents or directory listing.
    """
    result = _mcp_call("read_files_from_github_repository", {
        "githubUrl": github_url,
        "path": path,
    })
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content
                if isinstance(item, dict)
            )
    return str(result)


# ---------------------------------------------------------------------------
# Result normalization
# ---------------------------------------------------------------------------

def _extract_papers(result: Any) -> list[dict]:
    """Extract paper list from MCP response into normalized format."""
    papers = []

    # MCP responses wrap content in a content array
    content = result
    if isinstance(result, dict):
        content = result.get("content", result)

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                # Parse the text content which contains paper data
                text = item.get("text", "")
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        papers.extend(parsed)
                    elif isinstance(parsed, dict):
                        papers.append(parsed)
                except json.JSONDecodeError:
                    # Text content, not JSON — try to extract structured data
                    pass

    return papers


# ---------------------------------------------------------------------------
# Autoprompt integration — search and score for the pipeline
# ---------------------------------------------------------------------------

# Semantic search queries targeting Seithar's domain
SEITHAR_QUERIES = [
    (
        "Adversarial attacks on large language models including prompt injection, "
        "jailbreaking, and red teaming techniques that exploit instruction-following "
        "behavior to bypass safety measures and extract sensitive information."
    ),
    (
        "Cognitive warfare and influence operations using AI systems, including "
        "automated disinformation campaigns, narrative manipulation at scale, "
        "and computational propaganda targeting online communities."
    ),
    (
        "Adversarial machine learning defenses including robustness against "
        "evasion attacks, poisoning attacks on training data, and detection "
        "of adversarial examples in neural networks."
    ),
    (
        "Multi-agent systems for social simulation, opinion dynamics modeling, "
        "and swarm intelligence applied to information operations and "
        "community behavior prediction."
    ),
    (
        "Cognitive security and epistemic resilience including inoculation "
        "against misinformation, critical thinking augmentation, and "
        "detection of manipulative framing in media."
    ),
]


def fetch_semantic_papers(config: dict, seen_ids: set) -> list[dict]:
    """Run semantic searches and return scored results in autoprompt format.

    Args:
        config: Full autoprompt config dict (for keyword scoring).
        seen_ids: Set of already-seen paper IDs.

    Returns:
        List of paper entries in autoprompt pipeline format.
    """
    from src.ingester import score_entry

    all_papers: dict[str, dict] = {}

    for query in SEITHAR_QUERIES:
        try:
            print(f"[autoprompt:alphaxiv] Semantic search: {query[:60]}...")
            papers = semantic_search(query)
            for paper in papers:
                arxiv_id = paper.get("arxiv_id", paper.get("id", ""))
                if arxiv_id and arxiv_id not in all_papers:
                    all_papers[arxiv_id] = paper
            time.sleep(2)  # rate limit courtesy
        except Exception as e:
            print(f"[autoprompt:alphaxiv] Search failed: {e}")
            continue

    print(f"[autoprompt:alphaxiv] Found {len(all_papers)} unique papers")

    results = []
    for arxiv_id, paper in all_papers.items():
        paper_id = f"alphaxiv:{arxiv_id}"
        if paper_id in seen_ids:
            continue

        title = paper.get("title", "")
        abstract = paper.get("abstract", paper.get("abstract_preview", ""))

        entry = {"title": title, "summary": abstract}
        keyword_score, matched = score_entry(entry, config)

        # Boost by popularity signals from alphaXiv
        visits = paper.get("visit_count", 0) or 0
        likes = paper.get("likes", 0) or 0
        popularity_bonus = min((visits + likes * 10) / 100, 3.0)

        total_score = keyword_score + popularity_bonus

        if total_score < config["scoring"]["min_score"]:
            continue

        link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else paper.get("url", "")

        results.append({
            "id": paper_id,
            "title": title,
            "summary": abstract,
            "link": link,
            "feed": "alphaxiv_semantic",
            "score": round(total_score, 1),
            "keyword_score": keyword_score,
            "popularity_bonus": round(popularity_bonus, 1),
            "visits": visits,
            "likes": likes,
            "matched_keywords": matched + [f"visits:{visits}", f"likes:{likes}"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "authors": paper.get("authors", []),
            "organizations": paper.get("organizations", []),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:50]


if __name__ == "__main__":
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    papers = fetch_semantic_papers(config, set())
    print(f"\nFound {len(papers)} relevant papers via semantic search:\n")
    for p in papers[:15]:
        print(f"  [{p['score']:.1f}] {p['title'][:80]}")
        print(f"       {p['link']}")
        print(f"       {p['matched_keywords'][:5]}")
        print()
