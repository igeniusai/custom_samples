from typing import List, Optional

from fastmcp import FastMCP
from mcpesg.use_cases.esg import ESGUseCase
from logging import Logger
from fastmcp import Context
from fastmcp.dependencies import CurrentContext
import asyncio

def register_tools(mcp: FastMCP, use_case: ESGUseCase, logger: Logger) -> None:
    """Register all ESG-related MCP tools onto the given FastMCP instance."""
    logger.info("Registering ESG MCP tools")

    # ── Tool 0a: esg_list_portfolios ──────────────────────────────────────────

    async def esg_list_portfolios(ctx: Context = CurrentContext()) -> str:
        """
        Return the names and a brief description of all pre-defined sample portfolios.

        Call this first to discover available portfolio names before using other tools.

        Returns:
            JSON with a list of portfolio names, holding count and tickers for each.
        """
        # return a progress
        for i in range(10):
            await ctx.report_progress(progress=i+1, total=10, message=f"Loading portfolio: n {str(i+1)}")
            await asyncio.sleep(0.4)
        return await use_case.esg_list_portfolios()

    # ── Tool 0b: esg_get_portfolio ────────────────────────────────────────────

    async def esg_get_portfolio(portfolio_name: str, ctx: Context) -> str:
        """
        Return the full holdings detail of a specific pre-defined portfolio.

        Args:
            portfolio_name: Exact name of the portfolio (use esg_list_portfolios to discover names).

        Returns:
            JSON with the full list of holdings (ticker, weight, market_value_usd).
        """
        await ctx.report_progress(progress=0, message=f"Fetching requested portfolio: {portfolio_name}")
        return await use_case.esg_get_portfolio(portfolio_name=portfolio_name)

    # ── Tool 1: esg_get_scores ────────────────────────────────────────────────

    async def esg_get_scores(
        portfolio_name: Optional[str] = None,
        tickers: Optional[List[str]] = None,
    ) -> str:
        """
        Fetch Sustainalytics ESG scores for a pre-defined portfolio or an explicit list of tickers.

        Provide either portfolio_name (recommended) or a list of tickers — not both.

        Sustainalytics ESG scores measure RISK: lower = less risky.
        Range 0-100: 0-10=Negligible, 10-20=Low, 20-30=Medium, 30-40=High, 40+=Severe.

        Args:
            portfolio_name: Name of a pre-defined portfolio (use esg_list_portfolios to discover names).
            tickers: Explicit list of Yahoo Finance tickers (e.g. ['AAPL', 'MSFT', 'ENI.MI']).

        Returns:
            JSON with ESG scores for each ticker and a text summary.
        """
        return await use_case.esg_get_scores(
            portfolio_name=portfolio_name,
            tickers=tickers,
        )

    # ── Tool 2: esg_compare_portfolios ───────────────────────────────────────

    async def esg_compare_portfolios(
        portfolio_name_a: str,
        portfolio_name_b: str,
    ) -> str:
        """
        Compare two pre-defined portfolios across E, S, G dimensions with weighted aggregate
        scores and generate a radar chart saved as a PNG.

        Args:
            portfolio_name_a: Name of the first portfolio (use esg_list_portfolios to discover names).
            portfolio_name_b: Name of the second portfolio (use esg_list_portfolios to discover names).

        Returns:
            JSON with aggregate metrics, delta, winner and chart_url.
        """
        return await use_case.esg_compare_portfolios(
            portfolio_name_a=portfolio_name_a,
            portfolio_name_b=portfolio_name_b,
        )

    # ── Tool 3: esg_carbon_footprint ─────────────────────────────────────────

    async def esg_carbon_footprint(portfolio_name: str, ctx: Context = CurrentContext()) -> str:
        """
        Calculate the aggregated carbon footprint of a pre-defined portfolio
        (WACI and attributed emissions).

        Metrics computed:
        - WACI (Weighted Average Carbon Intensity): tCO2e per M$ revenue, weighted by portfolio weight.
        - Top 3 emission contributors.

        Data sources (priority): NZDPU → sector averages (IEA/MSCI).

        This tool also generates a bar chart comparing the portfolio's WACI to a benchmark (e.g. MSCI ACWI), saved as a PNG and return an url. 
        Show the url in the response as a markdown with a link to the image, e.g. "![WACI Chart](<chart url>)".

        Args:
            portfolio_name: Name of the portfolio (use esg_list_portfolios to discover names).

        Returns:
            JSON with WACI, benchmark comparison, top contributors, data quality and chart_url.
        """
        return await use_case.esg_carbon_footprint(portfolio_name=portfolio_name)

    # ── Tool 4: esg_suggest_replacements ─────────────────────────────────────

    async def esg_suggest_replacements(
        portfolio_name: str,
        min_esg_score: float = 25.0,
        max_suggestions: int = 3,
    ) -> str:
        """
        For each holding in a pre-defined portfolio with ESG risk above the threshold,
        suggest lower-risk alternatives in the same sector.

        Args:
            portfolio_name: Name of the portfolio to analyse (use esg_list_portfolios to discover names).
            min_esg_score: Maximum acceptable ESG risk threshold (0-100, default 25).
                           Sustainalytics: lower = better.
            max_suggestions: Maximum number of alternatives per ticker (1-5, default 3).

        Returns:
            JSON with ok_tickers (already compliant) and replacements (with suggested alternatives).
        """
        return await use_case.esg_suggest_replacements(
            portfolio_name=portfolio_name,
            min_esg_score=min_esg_score,
            max_suggestions=max_suggestions,
        )

    # ── Tool 5: esg_check_sfdr ────────────────────────────────────────────────

    async def esg_check_sfdr(portfolio_name: str) -> str:
        """
        Assess the achievable SFDR classification for a pre-defined portfolio.

        SFDR classifications:
        - Article 6: No specific ESG objective.
        - Article 8: Promotes environmental/social characteristics (avg ESG risk ≤30, >50% ESG-screened).
        - Article 9: Sustainable investment objective (avg ESG risk ≤20, carbon below benchmark).

        Note: indicative assessment based on simplified criteria. Official classification
        requires full legal/compliance verification.

        Args:
            portfolio_name: Name of the portfolio to assess (use esg_list_portfolios to discover names).

        Returns:
            JSON with SFDR classification, key metrics, article 8/9 criteria and blockers.
        """
        return await use_case.esg_check_sfdr(portfolio_name=portfolio_name)

    # ------------------------------------------------------------------
    # Register all tools
    # ------------------------------------------------------------------

    mcp.tool(esg_list_portfolios, annotations={
        "title": "List Available Portfolios",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    })

    mcp.tool(esg_get_portfolio, annotations={
        "title": "Get Portfolio Holdings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    })

    mcp.tool(esg_get_scores, annotations={
        "title": "Get ESG Scores",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })

    mcp.tool(esg_compare_portfolios, annotations={
        "title": "Compare ESG Portfolios",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    })

    mcp.tool(esg_carbon_footprint, annotations={
        "title": "Portfolio Carbon Footprint",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    })

    mcp.tool(esg_suggest_replacements, annotations={
        "title": "Suggest ESG Alternatives",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })

    mcp.tool(esg_check_sfdr, annotations={
        "title": "Check SFDR Classification",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })

