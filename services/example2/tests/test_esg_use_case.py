"""
Smoke tests for ESGUseCase — one per method.

Purpose: show a sample output for every tool so it is easy to understand
what each one returns.  Tests pass as long as the response is valid JSON
and contains the expected top-level keys; they do NOT assert specific score
values (those depend on live Yahoo Finance data).

Run with:
    uv run pytest tests/test_esg_use_case.py -v -s
"""

import json

import pytest

from mcpesg.config import Settings
from mcpesg.use_cases.esg import ESGUseCase, SAMPLE_PORTFOLIOS
import logging

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def use_case() -> ESGUseCase:
    return ESGUseCase(config=Settings(), logger=logging.getLogger("test_esg_use_case"))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load(raw: str) -> dict:
    """Parse JSON and pretty-print it so -s shows readable output."""
    data = json.loads(raw)
    print("\n" + json.dumps(data, indent=2, ensure_ascii=False, default=str))
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_esg_list_portfolios(use_case):
    """esg_list_portfolios — should return all 11 pre-defined portfolios."""
    raw = await use_case.esg_list_portfolios()
    data = load(raw)

    assert "portfolios" in data
    assert "count" in data
    assert data["count"] == len(SAMPLE_PORTFOLIOS)
    # Every entry must have name + tickers
    for p in data["portfolios"]:
        assert "name" in p
        assert "tickers" in p
        assert len(p["tickers"]) > 0

    print(f"\n✅ {data['count']} portfolios listed")


@pytest.mark.asyncio
async def test_esg_get_portfolio(use_case):
    """esg_get_portfolio — should return full holdings for a known portfolio."""
    name = "Global Tech Leaders"
    raw = await use_case.esg_get_portfolio(portfolio_name=name)
    data = load(raw)

    assert data["name"] == name
    assert "holdings" in data
    assert data["holding_count"] == len(data["holdings"])
    # Each holding must have the three required keys
    for h in data["holdings"]:
        assert "ticker" in h
        assert "weight" in h

    print(f"\n✅ {data['holding_count']} holdings returned for '{name}'")


@pytest.mark.asyncio
async def test_esg_get_portfolio_not_found(use_case):
    """esg_get_portfolio — unknown name should return an error with available list."""
    raw = await use_case.esg_get_portfolio(portfolio_name="Non Existent Portfolio")
    data = load(raw)

    assert "error" in data
    assert "available" in data
    assert len(data["available"]) == len(SAMPLE_PORTFOLIOS)

    print(f"\n✅ Error returned as expected: {data['error']}")


@pytest.mark.asyncio
async def test_esg_get_scores_by_portfolio(use_case):
    """esg_get_scores — fetch scores via portfolio name."""
    raw = await use_case.esg_get_scores(portfolio_name="Article 9 Candidate")
    data = load(raw)

    assert "results" in data
    assert "summary" in data
    assert "timestamp" in data
    assert len(data["results"]) > 0

    available = [r for r in data["results"] if r.get("dataAvailable")]
    print(f"\n✅ {len(available)}/{len(data['results'])} tickers returned ESG data")


@pytest.mark.asyncio
async def test_esg_get_scores_by_tickers(use_case):
    """esg_get_scores — fetch scores via explicit ticker list."""
    raw = await use_case.esg_get_scores(tickers=["MSFT", "AAPL"])
    data = load(raw)

    assert "results" in data
    assert len(data["results"]) == 2

    print(f"\n✅ Scores fetched for: {[r['ticker'] for r in data['results']]}")


@pytest.mark.asyncio
async def test_esg_compare_portfolios(use_case):
    """esg_compare_portfolios — compare two pre-defined portfolios."""
    raw = await use_case.esg_compare_portfolios(
        portfolio_name_a="European ESG Champions",
        portfolio_name_b="Fossil Fuel Heavy",
    )
    data = load(raw)

    # Yahoo Finance may not return ESG data for all tickers; accept either outcome
    if "error" in data:
        print(f"\n⚠️  No ESG data: {data['error']}")
    else:
        assert "delta" in data
        assert "winner" in data
        assert "chart_id" in data
        assert "chart_url" in data
        assert data["chart_url"].startswith("/statics/")
        assert "summary" in data
        print(f"\n✅ Winner: {data['winner']} | chart: {data['chart_url']}")


@pytest.mark.asyncio
async def test_esg_carbon_footprint(use_case):
    """esg_carbon_footprint — compute WACI and generate bar chart."""
    raw = await use_case.esg_carbon_footprint(portfolio_name="Balanced Global")
    data = load(raw)

    assert "waci" in data
    assert "benchmark_waci" in data
    assert "vs_benchmark_pct" in data
    assert "top_contributors" in data
    assert "chart_id" in data
    assert "chart_url" in data
    assert data["chart_url"].startswith("/statics/")
    assert "data_quality" in data

    print(
        f"\n✅ WACI={data['waci']} vs benchmark {data['benchmark_waci']} "
        f"({data['vs_benchmark_pct']:+.1f}%)"
    )


@pytest.mark.asyncio
async def test_esg_suggest_replacements(use_case):
    """esg_suggest_replacements — find lower-risk alternatives for High ESG Risk portfolio."""
    raw = await use_case.esg_suggest_replacements(
        portfolio_name="High ESG Risk",
        min_esg_score=25.0,
        max_suggestions=2,
    )
    data = load(raw)

    assert "ok_tickers" in data
    assert "replacements" in data
    assert "threshold_used" in data
    assert data["threshold_used"] == 25.0
    assert "summary" in data

    print(
        f"\n✅ {len(data['ok_tickers'])} compliant, "
        f"{len(data['replacements'])} need replacement"
    )


@pytest.mark.asyncio
async def test_esg_check_sfdr(use_case):
    """esg_check_sfdr — classify Article 9 Candidate portfolio."""
    raw = await use_case.esg_check_sfdr(portfolio_name="Article 9 Candidate")
    data = load(raw)

    # Yahoo Finance may not return ESG data for all tickers; accept either outcome
    if "error" in data:
        print(f"\n⚠️  No ESG data: {data['error']}")
    else:
        assert "current_classification" in data
        assert "max_achievable" in data
        assert "metrics" in data
        assert "article_8_criteria" in data
        assert "article_9_criteria" in data
        assert "blockers" in data
        assert "disclaimer" in data

        metrics = data["metrics"]
        assert "weighted_avg_esg" in metrics
        assert "pct_low_risk" in metrics
        assert "portfolio_waci" in metrics

        print(
            f"\n✅ Classification: {data['current_classification']} | "
            f"Avg ESG: {metrics['weighted_avg_esg']} | "
            f"Blockers: {len(data['blockers'])}"
        )
