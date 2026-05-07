import json
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from mcpesg.use_cases.esg import ESGUseCase
from logging import Logger

def _ok(raw: str) -> JSONResponse:
    """Deserialise the JSON string returned by use-case methods into a proper JSON response."""
    return JSONResponse(content=json.loads(raw))


def add_rest_interfaces(app: FastAPI, use_case: ESGUseCase, logger: Logger) -> None:

    logger.info("Registering ESG REST interfaces")

    # ── Tool 0a: list all portfolios ─────────────────────────────────────────
    async def _list_portfolios() -> JSONResponse:
        return _ok(await use_case.esg_list_portfolios())

    app.add_api_route(
        "/esg/portfolios",
        endpoint=_list_portfolios,
        methods=["GET"],
        summary="List all pre-defined portfolios",
        tags=["ESG"],
    )

    # ── Tool 0b: get a single portfolio's holdings ────────────────────────────
    async def _get_portfolio(
        portfolio_name: str = Query(..., description="Exact portfolio name"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_get_portfolio(portfolio_name=portfolio_name))

    app.add_api_route(
        "/esg/portfolios/detail",
        endpoint=_get_portfolio,
        methods=["GET"],
        summary="Get holdings of a specific portfolio",
        tags=["ESG"],
    )

    # ── Tool 1: ESG scores ────────────────────────────────────────────────────
    async def _get_scores(
        portfolio_name: Optional[str] = Query(None, description="Pre-defined portfolio name"),
        tickers: Optional[List[str]] = Query(None, description="Explicit list of tickers"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_get_scores(portfolio_name=portfolio_name, tickers=tickers))

    app.add_api_route(
        "/esg/scores",
        endpoint=_get_scores,
        methods=["GET"],
        summary="Get ESG scores for a portfolio or explicit tickers",
        tags=["ESG"],
    )

    # ── Tool 2: compare two portfolios ───────────────────────────────────────
    async def _compare_portfolios(
        portfolio_name_a: str = Query(..., description="First portfolio name"),
        portfolio_name_b: str = Query(..., description="Second portfolio name"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_compare_portfolios(
            portfolio_name_a=portfolio_name_a,
            portfolio_name_b=portfolio_name_b,
        ))

    app.add_api_route(
        "/esg/compare",
        endpoint=_compare_portfolios,
        methods=["GET"],
        summary="Compare two portfolios across E, S, G dimensions",
        tags=["ESG"],
    )

    # ── Tool 3: carbon footprint ──────────────────────────────────────────────
    async def _carbon_footprint(
        portfolio_name: str = Query(..., description="Portfolio name"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_carbon_footprint(portfolio_name=portfolio_name))

    app.add_api_route(
        "/esg/carbon",
        endpoint=_carbon_footprint,
        methods=["GET"],
        summary="Calculate the carbon footprint (WACI) of a portfolio",
        tags=["ESG"],
    )

    # ── Tool 4: suggest replacements ──────────────────────────────────────────
    async def _suggest_replacements(
        portfolio_name: str = Query(..., description="Portfolio name"),
        min_esg_score: float = Query(25.0, description="Max acceptable ESG risk score (lower = stricter)"),
        max_suggestions: int = Query(3, description="Max alternatives per holding (1-5)"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_suggest_replacements(
            portfolio_name=portfolio_name,
            min_esg_score=min_esg_score,
            max_suggestions=max_suggestions,
        ))

    app.add_api_route(
        "/esg/suggest",
        endpoint=_suggest_replacements,
        methods=["GET"],
        summary="Suggest lower-risk replacements for holdings above the ESG threshold",
        tags=["ESG"],
    )

    # ── Tool 5: SFDR classification ───────────────────────────────────────────
    async def _check_sfdr(
        portfolio_name: str = Query(..., description="Portfolio name"),
    ) -> JSONResponse:
        return _ok(await use_case.esg_check_sfdr(portfolio_name=portfolio_name))

    app.add_api_route(
        "/esg/sfdr",
        endpoint=_check_sfdr,
        methods=["GET"],
        summary="Assess the achievable SFDR classification for a portfolio",
        tags=["ESG"],
    )
