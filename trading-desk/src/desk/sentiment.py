from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from desk.portfolio import digest, finite, timestamp


def analyze_news(articles: list[dict], cfg: dict, now: datetime,
                 adapter: Callable[[dict], dict]) -> list[dict]:
    if not cfg.get("enabled", False):
        return []
    budget = finite(cfg.get("max_cost_usd", 0))
    ceiling = finite(cfg.get("max_call_cost_usd", 0))
    if ceiling <= 0:
        raise ValueError("An adapter per-call cost ceiling is required")
    limit = int(cfg.get("max_articles", 0))
    if not 0 <= limit <= 100:
        raise ValueError("Invalid request limit")
    output, seen, spent = [], set(), 0.
    for article in articles:
        if len(output) >= limit or spent + ceiling > budget:
            break
        source_id = article["source_id"]
        published, available = timestamp(article["published_at"]), timestamp(article["available_at"])
        if not source_id or not published <= available <= now:
            raise ValueError("News provenance contains an invalid availability timestamp")
        if source_id in seen:
            continue
        seen.add(source_id)
        response = adapter({**article, "text": str(article.get("text", ""))[:6000]})
        score = float(response["sentiment"])
        confidence = finite(response["confidence"])
        cost = finite(response["cost_usd"])
        if not -1 <= score <= 1 or confidence > 1 or cost > ceiling or not response["model_version"]:
            raise ValueError("Invalid or over-budget sentiment response")
        spent += cost
        record = {"source_id": source_id, "published_at": published.isoformat(), "available_at": available.isoformat(),
                  "inferred_at": now.isoformat(), "sentiment": score, "confidence": confidence,
                  "model_version": response["model_version"], "cost_usd": cost, "shadow_only": True}
        output.append({"id": digest(record), **record})
    return output
