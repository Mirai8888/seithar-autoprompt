"""LLM summarization layer using local Ollama model."""
import json
import requests


def summarize_paper(paper, config):
    """Summarize a paper and extract Seithar-relevant findings using local LLM."""
    llm_config = config.get("llm", {})
    if not llm_config.get("summarize", False):
        return None

    base_url = llm_config.get("base_url", "http://localhost:11434")
    model = llm_config.get("model", "qwen2.5:7b")

    prompt = f"""You are a cognitive warfare research analyst. Analyze this paper for relevance to:
1. Adversarial vulnerabilities in human decision-making
2. Adversarial attacks on AI/LLM systems (prompt injection, jailbreaks)
3. Cognitive manipulation techniques (propaganda, persuasion, deception)
4. Defense mechanisms for both human and AI substrates

Paper title: {paper.get('title', 'Unknown')}
Abstract: {paper.get('summary', 'No abstract available')}

Respond in this exact JSON format:
{{
  "relevance": "high|medium|low",
  "summary": "2-3 sentence summary of key findings",
  "attack_surface": "what vulnerability or attack vector this paper addresses",
  "sct_codes": ["SCT-XXX codes that map to this paper's findings"],
  "defense_implications": "how findings can improve cognitive/AI defense",
  "action_items": ["specific updates to make to Seithar tooling based on this paper"]
}}

Be precise. No filler. Clinical."""

    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 512}
            },
            timeout=120
        )
        resp.raise_for_status()
        result = resp.json().get("response", "")

        # Try to parse JSON from response
        try:
            # Find JSON block in response
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass

        return {"raw_summary": result, "parse_error": True}

    except Exception as e:
        return {"error": str(e)}


def batch_summarize(papers, config):
    """Summarize a batch of papers."""
    results = []
    for paper in papers:
        summary = summarize_paper(paper, config)
        if summary:
            paper["llm_analysis"] = summary
        results.append(paper)
    return results
