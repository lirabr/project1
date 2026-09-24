import pandas as pd

from desk import io_utils
from desk.io_utils import write_yaml
from desk.reports import render_report
from desk.sentiment import analyze_news


def test_report_is_read_only_and_escapes_untrusted_text(tmp_path):
    directory = io_utils.ARTIFACT_DIR / "sma_cross"
    directory.mkdir()
    write_yaml(directory / "tearsheet.yaml", {"strategy": "<script>alert(1)</script>", "total_return": .1,
                                              "mean_exposure": .2, "mean_cash_weight": .8})
    pd.DataFrame({"net": [.01], "cash_weight": [.8]}, index=pd.to_datetime(["2026-01-01"])).to_parquet(directory / "returns.parquet")
    output = tmp_path / "report.html"
    render_report(["sma_cross"], output)
    text = output.read_text()
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "mean_cash_weight" in text and "research" in text.lower()
    assert not (io_utils.ARTIFACT_DIR / "desk.sqlite").exists()


def test_sentiment_is_disabled_by_default_and_never_executes_tools():
    from datetime import UTC, datetime

    calls = []
    adapter = lambda article: calls.append(article)
    assert analyze_news([], {}, datetime.now(UTC), adapter) == []
    assert calls == []


def test_shadow_news_has_time_provenance_and_request_budget():
    from datetime import UTC, datetime

    import pytest

    now = datetime(2026, 9, 24, 14, tzinfo=UTC)
    article = {"source_id": "news-1", "published_at": "2026-09-24T12:00:00+00:00",
               "available_at": "2026-09-24T12:01:00+00:00", "text": "Untrusted article"}
    calls = []

    def adapter(item):
        calls.append(item)
        return {"sentiment": .5, "confidence": .8, "model_version": "fixture", "cost_usd": .01}

    cfg = {"enabled": True, "max_articles": 1, "max_cost_usd": .02, "max_call_cost_usd": .02}
    result = analyze_news([article, {**article, "source_id": "news-2"}], cfg, now, adapter)
    assert len(calls) == len(result) == 1
    assert result[0]["shadow_only"] is True
    assert result[0]["source_id"] == "news-1"
    with pytest.raises(ValueError):
        analyze_news([{**article, "available_at": "2026-09-25T00:00:00+00:00"}], cfg, now, adapter)
    assert len(calls) == 1
