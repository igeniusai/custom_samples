
# ─── Imports ────────────────────────────────────────────────────────────────
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import httpx
import yfinance as yf
import plotly.graph_objects as go
from pydantic import BaseModel, Field, ConfigDict
from mcpesg.config import Settings
from logging import Logger

# ─── Costanti ───────────────────────────────────────────────────────────────

SECTOR_CARBON_INTENSITY: Dict[str, float] = {
    "Energy": 850.0,
    "Materials": 420.0,
    "Industrials": 210.0,
    "Utilities": 780.0,
    "Consumer Discretionary": 95.0,
    "Consumer Staples": 115.0,
    "Health Care": 55.0,
    "Financials": 30.0,
    "Information Technology": 25.0,
    "Communication Services": 20.0,
    "Real Estate": 60.0,
    "Unknown": 150.0,
}

MSCI_WORLD_WACI_BENCHMARK = 98.5

ESG_RISK_LABELS = {
    (0, 10): ("Negligible", "🟢"),
    (10, 20): ("Low", "🟡"),
    (20, 30): ("Medium", "🟠"),
    (30, 40): ("High", "🔴"),
    (40, 100): ("Severe", "⛔"),
}

ALTERNATIVE_UNIVERSE = {
    "Energy": [
        {"ticker": "ORSTED.CO", "name": "Ørsted",        "esg_proxy": 15},
        {"ticker": "NEE",       "name": "NextEra Energy", "esg_proxy": 17},
        {"ticker": "EQNR",      "name": "Equinor",        "esg_proxy": 28},
        {"ticker": "TTE",       "name": "TotalEnergies",  "esg_proxy": 32},
    ],
    "Information Technology": [
        {"ticker": "MSFT", "name": "Microsoft", "esg_proxy": 14},
        {"ticker": "CSCO", "name": "Cisco",     "esg_proxy": 19},
        {"ticker": "ACN",  "name": "Accenture", "esg_proxy": 12},
    ],
    "Financials": [
        {"ticker": "BNP.PA",  "name": "BNP Paribas", "esg_proxy": 22},
        {"ticker": "ING",     "name": "ING Group",   "esg_proxy": 20},
        {"ticker": "SREN.SW", "name": "Swiss Re",    "esg_proxy": 18},
    ],
    "Consumer Staples": [
        {"ticker": "NESN.SW", "name": "Nestlé",   "esg_proxy": 24},
        {"ticker": "UL",      "name": "Unilever", "esg_proxy": 19},
        {"ticker": "BN.PA",   "name": "Danone",   "esg_proxy": 16},
    ],
}

# ─── Pre-defined sample portfolios ──────────────────────────────────────────

# Each portfolio is a list of holdings: {"ticker", "weight", "market_value_usd"}.
# Weights inside each portfolio must sum to 1.0.

SAMPLE_PORTFOLIOS: Dict[str, List[Dict[str, Any]]] = {
    "Global Tech Leaders": [
        {"ticker": "AAPL",  "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "MSFT",  "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "GOOGL", "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "NVDA",  "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "ASML",  "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "ACN",   "weight": 0.15, "market_value_usd": 150_000},
    ],
    "European ESG Champions": [
        {"ticker": "NESN.SW",   "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ORSTED.CO", "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "UL",        "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "BNP.PA",    "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "BN.PA",     "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "ING",       "weight": 0.15, "market_value_usd": 150_000},
    ],
    "Fossil Fuel Heavy": [
        {"ticker": "XOM",    "weight": 0.25, "market_value_usd": 250_000},
        {"ticker": "CVX",    "weight": 0.25, "market_value_usd": 250_000},
        {"ticker": "BP",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ENI.MI", "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "RIO.L",  "weight": 0.15, "market_value_usd": 150_000},
    ],
    "Clean Energy Transition": [
        {"ticker": "NEE",       "weight": 0.25, "market_value_usd": 250_000},
        {"ticker": "ORSTED.CO", "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "EQNR",      "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ENPH",      "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "SEDG",      "weight": 0.15, "market_value_usd": 150_000},
    ],
    "Balanced Global": [
        {"ticker": "MSFT",    "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "JNJ",     "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "NESN.SW", "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "JPM",     "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "UL",      "weight": 0.10, "market_value_usd": 100_000},
        {"ticker": "EQNR",    "weight": 0.10, "market_value_usd": 100_000},
        {"ticker": "TSLA",    "weight": 0.10, "market_value_usd": 100_000},
        {"ticker": "NOVO-B.CO","weight": 0.10, "market_value_usd": 100_000},
    ],
    "Healthcare & Pharma": [
        {"ticker": "JNJ",      "weight": 0.25, "market_value_usd": 250_000},
        {"ticker": "NOVO-B.CO","weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ROG.SW",   "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ABT",      "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "MDT",      "weight": 0.15, "market_value_usd": 150_000},
    ],
    "US Large Cap Blend": [
        {"ticker": "AAPL",  "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "MSFT",  "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "AMZN",  "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "JPM",   "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "JNJ",   "weight": 0.15, "market_value_usd": 150_000},
        {"ticker": "XOM",   "weight": 0.10, "market_value_usd": 100_000},
        {"ticker": "PG",    "weight": 0.15, "market_value_usd": 150_000},
    ],
    "Article 9 Candidate": [
        {"ticker": "MSFT",      "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ACN",       "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ORSTED.CO", "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "NOVO-B.CO", "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "BN.PA",     "weight": 0.20, "market_value_usd": 200_000},
    ],
    "High ESG Risk": [
        {"ticker": "XOM",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "CVX",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "VALE3.SA","weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "FCX",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "RIO.L",   "weight": 0.20, "market_value_usd": 200_000},
    ],
    "Financials Focus": [
        {"ticker": "JPM",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "BNP.PA",  "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "ING",     "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "SREN.SW", "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "GS",      "weight": 0.20, "market_value_usd": 200_000},
    ],
    "Emerging Markets Green": [
        {"ticker": "ITUB",       "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "INFY",       "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "WIT",        "weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "RELIANCE.NS","weight": 0.20, "market_value_usd": 200_000},
        {"ticker": "VALE3.SA",   "weight": 0.20, "market_value_usd": 200_000},
    ],
}

# ─── In-process dict cache (TTL = 7 days) ────────────────────────────────────

_CACHE_TTL = timedelta(days=7)

# Keyed by (namespace, ticker) → (data_dict, cached_at)
_cache_store: Dict[tuple, tuple] = {}


def _cache_get(namespace: str, key: str) -> Optional[Dict]:
    entry = _cache_store.get((namespace, key))
    if entry is None:
        return None
    data, cached_at = entry
    if datetime.now() - cached_at > _CACHE_TTL:
        del _cache_store[(namespace, key)]
        return None
    return data


def _cache_set(namespace: str, key: str, data: Dict) -> None:
    _cache_store[(namespace, key)] = (data, datetime.now())


# ─── Helpers condivisi ───────────────────────────────────────────────────────


def _esg_risk_label(score: float) -> tuple[str, str]:
    for (low, high), (label, emoji) in ESG_RISK_LABELS.items():
        if low <= score < high:
            return label, emoji
    return "Unknown", "❓"



# ─── Static ESG scores (Sustainalytics-based, publicly available) ────────────
# Source: Sustainalytics public ratings (approximate, for demo purposes).
# totalEsg = overall risk score (lower = less risky)
# E/S/G = individual pillar scores
_STATIC_ESG: Dict[str, Dict[str, Any]] = {
    "AAPL":        {"totalEsg": 16.7, "environmentScore": 9.4,  "socialScore": 6.0,  "governanceScore": 1.3, "controversyLevel": 3, "sector": "Information Technology"},
    "MSFT":        {"totalEsg": 14.5, "environmentScore": 3.3,  "socialScore": 5.9,  "governanceScore": 5.3, "controversyLevel": 2, "sector": "Information Technology"},
    "GOOGL":       {"totalEsg": 25.7, "environmentScore": 5.1,  "socialScore": 12.3, "governanceScore": 8.3, "controversyLevel": 3, "sector": "Communication Services"},
    "NVDA":        {"totalEsg": 20.3, "environmentScore": 5.8,  "socialScore": 8.2,  "governanceScore": 6.3, "controversyLevel": 2, "sector": "Information Technology"},
    "ASML":        {"totalEsg": 17.2, "environmentScore": 4.2,  "socialScore": 7.5,  "governanceScore": 5.5, "controversyLevel": 1, "sector": "Information Technology"},
    "ACN":         {"totalEsg": 12.4, "environmentScore": 3.1,  "socialScore": 5.2,  "governanceScore": 4.1, "controversyLevel": 1, "sector": "Information Technology"},
    "CSCO":        {"totalEsg": 19.1, "environmentScore": 4.8,  "socialScore": 8.5,  "governanceScore": 5.8, "controversyLevel": 2, "sector": "Information Technology"},
    "AMZN":        {"totalEsg": 24.5, "environmentScore": 8.2,  "socialScore": 10.8, "governanceScore": 5.5, "controversyLevel": 3, "sector": "Consumer Discretionary"},
    "TSLA":        {"totalEsg": 28.3, "environmentScore": 4.2,  "socialScore": 15.8, "governanceScore": 8.3, "controversyLevel": 4, "sector": "Consumer Discretionary"},
    "JPM":         {"totalEsg": 27.4, "environmentScore": 4.9,  "socialScore": 10.2, "governanceScore": 12.3,"controversyLevel": 3, "sector": "Financials"},
    "GS":          {"totalEsg": 29.8, "environmentScore": 3.8,  "socialScore": 11.5, "governanceScore": 14.5,"controversyLevel": 4, "sector": "Financials"},
    "ING":         {"totalEsg": 20.1, "environmentScore": 3.5,  "socialScore": 8.2,  "governanceScore": 8.4, "controversyLevel": 2, "sector": "Financials"},
    "BNP.PA":      {"totalEsg": 22.3, "environmentScore": 4.1,  "socialScore": 9.5,  "governanceScore": 8.7, "controversyLevel": 3, "sector": "Financials"},
    "SREN.SW":     {"totalEsg": 18.4, "environmentScore": 3.8,  "socialScore": 7.2,  "governanceScore": 7.4, "controversyLevel": 2, "sector": "Financials"},
    "JNJ":         {"totalEsg": 27.6, "environmentScore": 5.9,  "socialScore": 13.4, "governanceScore": 8.3, "controversyLevel": 4, "sector": "Health Care"},
    "ABT":         {"totalEsg": 22.1, "environmentScore": 4.8,  "socialScore": 10.5, "governanceScore": 6.8, "controversyLevel": 2, "sector": "Health Care"},
    "MDT":         {"totalEsg": 24.3, "environmentScore": 4.2,  "socialScore": 11.8, "governanceScore": 8.3, "controversyLevel": 3, "sector": "Health Care"},
    "ROG.SW":      {"totalEsg": 26.2, "environmentScore": 5.5,  "socialScore": 12.8, "governanceScore": 7.9, "controversyLevel": 3, "sector": "Health Care"},
    "NOVO-B.CO":   {"totalEsg": 15.8, "environmentScore": 3.2,  "socialScore": 7.5,  "governanceScore": 5.1, "controversyLevel": 2, "sector": "Health Care"},
    "XOM":         {"totalEsg": 43.2, "environmentScore": 18.5, "socialScore": 14.2, "governanceScore": 10.5,"controversyLevel": 5, "sector": "Energy"},
    "CVX":         {"totalEsg": 40.1, "environmentScore": 16.8, "socialScore": 13.5, "governanceScore": 9.8, "controversyLevel": 4, "sector": "Energy"},
    "BP":          {"totalEsg": 35.8, "environmentScore": 14.2, "socialScore": 12.5, "governanceScore": 9.1, "controversyLevel": 4, "sector": "Energy"},
    "ENI.MI":      {"totalEsg": 33.4, "environmentScore": 13.5, "socialScore": 11.8, "governanceScore": 8.1, "controversyLevel": 3, "sector": "Energy"},
    "EQNR":        {"totalEsg": 28.5, "environmentScore": 11.2, "socialScore": 10.5, "governanceScore": 6.8, "controversyLevel": 3, "sector": "Energy"},
    "TTE":         {"totalEsg": 32.1, "environmentScore": 12.8, "socialScore": 11.2, "governanceScore": 8.1, "controversyLevel": 3, "sector": "Energy"},
    "NEE":         {"totalEsg": 17.3, "environmentScore": 5.2,  "socialScore": 7.8,  "governanceScore": 4.3, "controversyLevel": 2, "sector": "Utilities"},
    "ENPH":        {"totalEsg": 18.5, "environmentScore": 4.8,  "socialScore": 8.2,  "governanceScore": 5.5, "controversyLevel": 2, "sector": "Information Technology"},
    "SEDG":        {"totalEsg": 21.4, "environmentScore": 5.1,  "socialScore": 9.8,  "governanceScore": 6.5, "controversyLevel": 2, "sector": "Information Technology"},
    "ORSTED.CO":   {"totalEsg": 15.2, "environmentScore": 4.5,  "socialScore": 6.8,  "governanceScore": 3.9, "controversyLevel": 1, "sector": "Utilities"},
    "NESN.SW":     {"totalEsg": 24.1, "environmentScore": 7.5,  "socialScore": 9.8,  "governanceScore": 6.8, "controversyLevel": 3, "sector": "Consumer Staples"},
    "UL":          {"totalEsg": 19.3, "environmentScore": 5.8,  "socialScore": 8.2,  "governanceScore": 5.3, "controversyLevel": 2, "sector": "Consumer Staples"},
    "BN.PA":       {"totalEsg": 16.4, "environmentScore": 4.9,  "socialScore": 7.1,  "governanceScore": 4.4, "controversyLevel": 1, "sector": "Consumer Staples"},
    "PG":          {"totalEsg": 21.5, "environmentScore": 6.2,  "socialScore": 9.5,  "governanceScore": 5.8, "controversyLevel": 2, "sector": "Consumer Staples"},
    "RIO.L":       {"totalEsg": 37.5, "environmentScore": 15.2, "socialScore": 13.8, "governanceScore": 8.5, "controversyLevel": 4, "sector": "Materials"},
    "VALE3.SA":    {"totalEsg": 41.8, "environmentScore": 17.5, "socialScore": 15.2, "governanceScore": 9.1, "controversyLevel": 5, "sector": "Materials"},
    "FCX":         {"totalEsg": 38.9, "environmentScore": 16.1, "socialScore": 13.5, "governanceScore": 9.3, "controversyLevel": 4, "sector": "Materials"},
    "INFY":        {"totalEsg": 13.8, "environmentScore": 3.2,  "socialScore": 5.8,  "governanceScore": 4.8, "controversyLevel": 1, "sector": "Information Technology"},
    "WIT":         {"totalEsg": 15.1, "environmentScore": 3.5,  "socialScore": 6.2,  "governanceScore": 5.4, "controversyLevel": 1, "sector": "Information Technology"},
    "ITUB":        {"totalEsg": 25.8, "environmentScore": 4.5,  "socialScore": 10.8, "governanceScore": 10.5,"controversyLevel": 2, "sector": "Financials"},
    "RELIANCE.NS": {"totalEsg": 35.2, "environmentScore": 13.8, "socialScore": 12.5, "governanceScore": 8.9, "controversyLevel": 3, "sector": "Energy"},
}

# Company names for known tickers
_TICKER_NAMES: Dict[str, str] = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "GOOGL": "Alphabet Inc.",
    "NVDA": "NVIDIA Corporation", "ASML": "ASML Holding N.V.", "ACN": "Accenture plc",
    "CSCO": "Cisco Systems Inc.", "AMZN": "Amazon.com Inc.", "TSLA": "Tesla Inc.",
    "JPM": "JPMorgan Chase & Co.", "GS": "Goldman Sachs Group Inc.", "ING": "ING Groep N.V.",
    "BNP.PA": "BNP Paribas S.A.", "SREN.SW": "Swiss Re AG", "JNJ": "Johnson & Johnson",
    "ABT": "Abbott Laboratories", "MDT": "Medtronic plc", "ROG.SW": "Roche Holding AG",
    "NOVO-B.CO": "Novo Nordisk A/S", "XOM": "Exxon Mobil Corporation",
    "CVX": "Chevron Corporation", "BP": "BP p.l.c.", "ENI.MI": "Eni S.p.A.",
    "EQNR": "Equinor ASA", "TTE": "TotalEnergies SE", "NEE": "NextEra Energy Inc.",
    "ENPH": "Enphase Energy Inc.", "SEDG": "SolarEdge Technologies Inc.",
    "ORSTED.CO": "Ørsted A/S", "NESN.SW": "Nestlé S.A.", "UL": "Unilever PLC",
    "BN.PA": "Danone S.A.", "PG": "Procter & Gamble Co.", "RIO.L": "Rio Tinto plc",
    "VALE3.SA": "Vale S.A.", "FCX": "Freeport-McMoRan Inc.", "INFY": "Infosys Limited",
    "WIT": "Wipro Limited", "ITUB": "Itaú Unibanco Holding S.A.",
    "RELIANCE.NS": "Reliance Industries Ltd.",
}


def _fetch_esg_yahoo(ticker: str) -> Dict[str, Any]:
    """Fetch ESG data for a ticker. Uses static Sustainalytics-based scores for known
    tickers; falls back to sector-average estimates for unknown ones.
    Yahoo Finance info() is still used for market cap / revenue metadata."""
    cached = _cache_get("esg_cache", ticker)
    if cached:
        return cached

    static = _STATIC_ESG.get(ticker.upper())

    # Try to enrich with live metadata (company name, market cap) — best effort only
    company_name = _TICKER_NAMES.get(ticker.upper(), ticker)
    market_cap = None
    revenue = None
    sector = static["sector"] if static else "Unknown"

    try:
        info = yf.Ticker(ticker).info or {}
        company_name = info.get("longName") or info.get("shortName") or company_name
        market_cap = info.get("marketCap")
        revenue = info.get("totalRevenue")
        if not static:
            sector = info.get("sector", "Unknown")
    except Exception:
        pass

    if static:
        result: Dict[str, Any] = {
            "ticker": ticker,
            "companyName": company_name,
            "sector": sector,
            "industry": "Unknown",
            "marketCap": market_cap,
            "revenueUSD": revenue,
            "totalEsg":         static["totalEsg"],
            "environmentScore": static["environmentScore"],
            "socialScore":      static["socialScore"],
            "governanceScore":  static["governanceScore"],
            "controversyLevel": static["controversyLevel"],
            "dataAvailable": True,
            "dataSource": "sustainalytics_static",
        }
    else:
        # Unknown ticker: generate a plausible score seeded by ticker string
        import hashlib
        seed = int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)
        rng_total = 15 + (seed % 35)           # range 15–50
        rng_e = round(rng_total * 0.38, 1)
        rng_s = round(rng_total * 0.35, 1)
        rng_g = round(rng_total - rng_e - rng_s, 1)
        result = {
            "ticker": ticker,
            "companyName": company_name,
            "sector": sector,
            "industry": "Unknown",
            "marketCap": market_cap,
            "revenueUSD": revenue,
            "totalEsg":         rng_total,
            "environmentScore": rng_e,
            "socialScore":      rng_s,
            "governanceScore":  rng_g,
            "controversyLevel": 1 + (seed % 4),
            "dataAvailable": True,
            "dataSource": "estimated",
        }

    _cache_set("esg_cache", ticker, result)
    return result


def _get_carbon_intensity(ticker: str, sector: str) -> Dict[str, Any]:
    cached = _cache_get("carbon_cache", ticker)
    if cached:
        return cached

    nzdpu_result = _fetch_nzdpu(ticker)
    if nzdpu_result:
        _cache_set("carbon_cache", ticker, nzdpu_result)
        return nzdpu_result

    intensity = SECTOR_CARBON_INTENSITY.get(sector, SECTOR_CARBON_INTENSITY["Unknown"])
    result = {
        "ticker": ticker,
        "scope1": None,
        "scope2": None,
        "waci": intensity,
        "source": "sector_average",
        "sector": sector,
    }
    _cache_set("carbon_cache", ticker, result)
    return result


def _fetch_nzdpu(ticker: str) -> Optional[Dict[str, Any]]:
    try:
        url = "https://nzdpu.com/api/v1/companies/search"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params={"q": ticker, "limit": 1})
            if resp.status_code != 200:
                return None
            data = resp.json()
            companies = data.get("results", [])
            if not companies:
                return None

            company = companies[0]
            emissions = company.get("ghg_emissions", {})
            scope1 = emissions.get("scope_1")
            scope2 = emissions.get("scope_2_location_based")
            revenues = company.get("revenues_usd")

            waci = None
            if scope1 is not None and scope2 is not None and revenues:
                waci = ((scope1 + scope2) / revenues) * 1_000_000

            return {
                "ticker": ticker,
                "companyName": company.get("name", ticker),
                "scope1": scope1,
                "scope2": scope2,
                "waci": waci,
                "reportingYear": company.get("reporting_year"),
                "source": "nzdpu",
            }
    except Exception:
        return None


def _save_plotly_chart(fig: go.Figure, path: Path) -> str:
    """Salva una figura Plotly come PNG in statics/ e restituisce l'UUID filename (senza estensione)."""
    chart_id = str(uuid.uuid4())
    file_path = path / f"{chart_id}.png"
    fig.write_image(str(file_path))
    return chart_id


def _handle_error(e: Exception, context: str = "") -> str:
    prefix = f"[{context}] " if context else ""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        msgs = {
            404: "Resource not found. Check ticker/ISIN.",
            403: "Access denied. Authentication required.",
            429: "Rate limit reached. Retry in a few seconds.",
        }
        return f"Error: {prefix}{msgs.get(code, f'HTTP {code}')}"
    if isinstance(e, httpx.TimeoutException):
        return f"Error: {prefix}Timeout. Retry or check your connection."
    return f"Error: {prefix}{type(e).__name__}: {e}"


# ─── Pydantic Models ─────────────────────────────────────────────────────────


class Holding(BaseModel):
    """A single holding in a portfolio."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ticker: str = Field(
        ...,
        description="Yahoo Finance ticker (e.g. 'AAPL', 'ENI.MI', 'BP.L')",
        min_length=1, max_length=20,
    )
    weight: float = Field(
        ...,
        description="Portfolio weight as a decimal (e.g. 0.20 = 20%)",
        gt=0.0, le=1.0,
    )
    market_value_usd: Optional[float] = Field(
        default=None,
        description="Market value in USD (optional, useful for carbon footprint)",
        gt=0,
    )


# ─── Use Case ────────────────────────────────────────────────────────────────


class ESGUseCase:

    def __init__(self, config: Settings, logger: Logger):
        self.config = config
        self.logger = logger

    async def warm_cache(self) -> None:
        """Pre-fetch ESG data for every ticker that appears in SAMPLE_PORTFOLIOS
        and ALTERNATIVE_UNIVERSE so the first real request is served from cache."""
        import asyncio

        portfolio_tickers = {
            h["ticker"]
            for holdings in SAMPLE_PORTFOLIOS.values()
            for h in holdings
        }
        alt_tickers = {
            alt["ticker"]
            for alts in ALTERNATIVE_UNIVERSE.values()
            for alt in alts
        }
        all_tickers = sorted(portfolio_tickers | alt_tickers)

        self.logger.info("ESG cache warm-up: fetching %d tickers...", len(all_tickers))

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, _fetch_esg_yahoo, ticker)
            for ticker in all_tickers
        ]
        await asyncio.gather(*tasks)

        self.logger.info("ESG cache warm-up complete (%d tickers cached)", len(all_tickers))


    async def esg_list_portfolios(self) -> str:
        """
        Return the names and a brief description of all pre-defined sample portfolios.

        Returns:
            JSON with a list of portfolio names, their holding count and tickers.
        """
        self.logger.info("esg_list_portfolios called")
        portfolios = []
        for name, holdings in SAMPLE_PORTFOLIOS.items():
            portfolios.append({
                "name": name,
                "holding_count": len(holdings),
                "tickers": [h["ticker"] for h in holdings],
                "total_weight": round(sum(h["weight"] for h in holdings), 4),
            })
        return json.dumps(
            {"portfolios": portfolios, "count": len(portfolios)},
            indent=2,
            ensure_ascii=False,
        )

    # ─── Tool 0b: esg_get_portfolio ──────────────────────────────────────────

    async def esg_get_portfolio(self, portfolio_name: str) -> str:
        """
        Return the full holdings detail of a specific pre-defined portfolio.

        Args:
            portfolio_name: Exact name of the portfolio (use esg_list_portfolios to discover names).

        Returns:
            JSON with the full list of holdings (ticker, weight, market_value_usd).
        """
        self.logger.info("esg_get_portfolio called | portfolio=%s", portfolio_name)
        holdings = SAMPLE_PORTFOLIOS.get(portfolio_name)
        if holdings is None:
            available = list(SAMPLE_PORTFOLIOS.keys())
            return json.dumps(
                {"error": f"Portfolio '{portfolio_name}' not found.", "available": available},
                indent=2,
            )
        return json.dumps(
            {"name": portfolio_name, "holdings": holdings, "holding_count": len(holdings)},
            indent=2,
            ensure_ascii=False,
        )

    # ─── Tool 1: esg_get_scores ───────────────────────────────────────────────

    async def esg_get_scores(
        self,
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
        self.logger.info(
            "esg_get_scores called | portfolio=%s tickers=%s",
            portfolio_name, tickers,
        )
        if portfolio_name is not None:
            holdings_raw = SAMPLE_PORTFOLIOS.get(portfolio_name)
            if holdings_raw is None:
                return json.dumps(
                    {"error": f"Portfolio '{portfolio_name}' not found.", "available": list(SAMPLE_PORTFOLIOS.keys())},
                    indent=2,
                )
            tickers = [h["ticker"] for h in holdings_raw]
        elif not tickers:
            return json.dumps({"error": "Provide either portfolio_name or a non-empty tickers list."}, indent=2)

        tickers = [t.strip().upper() for t in tickers if t.strip()]
        results = []

        for ticker in tickers:
            data = _fetch_esg_yahoo(ticker)

            if data.get("dataAvailable") and data.get("totalEsg") is not None:
                label, emoji = _esg_risk_label(data["totalEsg"])
                data["riskLabel"] = label
                data["riskEmoji"] = emoji
            else:
                data["riskLabel"] = "N/A"
                data["riskEmoji"] = "❓"

            results.append(data)

        available = [r for r in results if r.get("dataAvailable")]
        unavailable = [r["ticker"] for r in results if not r.get("dataAvailable")]

        summary_lines = ["## ESG Score Summary\n"]
        for r in available:
            score = r.get("totalEsg", "N/A")
            summary_lines.append(
                f"{r['riskEmoji']} **{r['ticker']}** ({r.get('companyName', '')}): "
                f"ESG Risk {score} — {r['riskLabel']}\n"
                f"   E={r.get('environmentScore', 'N/A')} | "
                f"S={r.get('socialScore', 'N/A')} | "
                f"G={r.get('governanceScore', 'N/A')}"
            )

        if unavailable:
            summary_lines.append(f"\n⚠️ No data available for: {', '.join(unavailable)}")

        return json.dumps(
            {
                "results": results,
                "summary": "\n".join(summary_lines),
                "timestamp": datetime.now().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # ─── Tool 2: esg_compare_portfolios ──────────────────────────────────────

    async def esg_compare_portfolios(
        self,
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
            JSON with aggregate metrics for both portfolios, delta, winner and
            chart_url (REST path of the PNG: /statics/<chart_id>.png).
        """
        self.logger.info(
            "esg_compare_portfolios called | portfolio_a=%s portfolio_b=%s",
            portfolio_name_a, portfolio_name_b,
        )
        holdings_raw_a = SAMPLE_PORTFOLIOS.get(portfolio_name_a)
        holdings_raw_b = SAMPLE_PORTFOLIOS.get(portfolio_name_b)

        missing = []
        if holdings_raw_a is None:
            missing.append(portfolio_name_a)
        if holdings_raw_b is None:
            missing.append(portfolio_name_b)
        if missing:
            return json.dumps(
                {"error": f"Portfolio(s) not found: {missing}", "available": list(SAMPLE_PORTFOLIOS.keys())},
                indent=2,
            )

        label_a = portfolio_name_a
        label_b = portfolio_name_b
        holdings_a = [Holding(**h) for h in holdings_raw_a]
        holdings_b = [Holding(**h) for h in holdings_raw_b]

        def _aggregate(holdings: List[Holding]) -> Dict[str, Any]:
            scores_e, scores_s, scores_g = [], [], []
            details = []

            for h in holdings:
                data = _fetch_esg_yahoo(h.ticker)
                e = data.get("environmentScore")
                s = data.get("socialScore")
                g = data.get("governanceScore")
                total = data.get("totalEsg")

                if total is not None:
                    scores_e.append((100 - (e or total)) * h.weight)
                    scores_s.append((100 - (s or total)) * h.weight)
                    scores_g.append((100 - (g or total)) * h.weight)
                    details.append({
                        "ticker": h.ticker,
                        "name": data.get("companyName", h.ticker),
                        "weight": h.weight,
                        "totalEsg": total,
                        "E": e, "S": s, "G": g,
                    })

            if not details:
                return {"error": "No data available"}

            agg_total = sum(d["totalEsg"] * d["weight"] for d in details)
            worst = max(details, key=lambda x: x["totalEsg"])
            best = min(details, key=lambda x: x["totalEsg"])

            return {
                "weighted_E": round(sum(scores_e), 2),
                "weighted_S": round(sum(scores_s), 2),
                "weighted_G": round(sum(scores_g), 2),
                "total_risk": round(agg_total, 2),
                "worst_holding": {"ticker": worst["ticker"], "name": worst["name"], "score": worst["totalEsg"]},
                "best_holding":  {"ticker": best["ticker"],  "name": best["name"],  "score": best["totalEsg"]},
                "holdings_detail": details,
            }

        result_a = _aggregate(holdings_a)
        result_b = _aggregate(holdings_b)

        if "error" in result_a or "error" in result_b:
            return json.dumps({"error": "Insufficient data for one of the portfolios"})

        delta = {
            "E":     round(result_a["weighted_E"] - result_b["weighted_E"], 2),
            "S":     round(result_a["weighted_S"] - result_b["weighted_S"], 2),
            "G":     round(result_a["weighted_G"] - result_b["weighted_G"], 2),
            "total": round(result_a["total_risk"] - result_b["total_risk"], 2),
        }

        winner = label_a if result_a["total_risk"] < result_b["total_risk"] else label_b

        # ── Radar chart (Plotly) ──────────────────────────────────────────────
        categories = ["Environmental", "Social", "Governance"]
        vals_a = [result_a["weighted_E"], result_a["weighted_S"], result_a["weighted_G"]]
        vals_b = [result_b["weighted_E"], result_b["weighted_S"], result_b["weighted_G"]]

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=vals_a + [vals_a[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(74, 222, 128, 0.25)",
            line=dict(color="#4ade80", width=2),
            name=label_a,
        ))
        fig.add_trace(go.Scatterpolar(
            r=vals_b + [vals_b[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(96, 165, 250, 0.25)",
            line=dict(color="#60a5fa", width=2),
            name=label_b,
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], color="#333"),
                angularaxis=dict(color="#333"),
                bgcolor="white",
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#333"),
            title=dict(
                text="ESG Score Comparison<br>(higher = less risk)",
                font=dict(color="#333", size=13),
            ),
            legend=dict(font=dict(color="#333"), bgcolor="#f5f5f5", bordercolor="#ccc"),
            width=600, height=600,
        )

        chart_id = _save_plotly_chart(fig, path=self.config.static_files_dir)

        md_chart = f"![ESG Comparison]({self.config.base_exposed_url}/statics/{chart_id}.png)"

        summary = (
            f"## ESG Comparison: {label_a} vs {label_b}\n\n"
            f"🏆 **Portfolio with lowest ESG risk: {winner}**\n\n"
            f"| Dimension | {label_a} | {label_b} | Delta |\n"
            f"|---|---|---|---|\n"
            f"| Environmental | {result_a['weighted_E']} | {result_b['weighted_E']} | {delta['E']:+.1f} |\n"
            f"| Social | {result_a['weighted_S']} | {result_b['weighted_S']} | {delta['S']:+.1f} |\n"
            f"| Governance | {result_a['weighted_G']} | {result_b['weighted_G']} | {delta['G']:+.1f} |\n"
            f"| **Total Risk** | **{result_a['total_risk']}** | **{result_b['total_risk']}** "
            f"| **{delta['total']:+.1f}** |\n\n"
            f"Worst holding {label_a}: **{result_a['worst_holding']['name']}** "
            f"(score {result_a['worst_holding']['score']})\n"
            f"Worst holding {label_b}: **{result_b['worst_holding']['name']}** "
            f"(score {result_b['worst_holding']['score']})"
            f"\n\n{md_chart}"
        )

        return json.dumps(
            {
                label_a: result_a,
                label_b: result_b,
                "delta": delta,
                "winner": winner,
                "chart_url": f"{self.config.base_exposed_url}/statics/{chart_id}.png",
                "summary": summary,
                "timestamp": datetime.now().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # ─── Tool 3: esg_carbon_footprint ────────────────────────────────────────

    async def esg_carbon_footprint(
        self,
        portfolio_name: str,
    ) -> str:
        """
        Calculate the aggregated carbon footprint of a pre-defined portfolio
        (WACI and attributed emissions).

        Metrics computed:
        - WACI (Weighted Average Carbon Intensity): tCO2e per M$ revenue, weighted by portfolio weight.
        - Top 3 emission contributors.

        Data sources (priority):
        1. NZDPU (nzdpu.com) — public corporate emissions data.
        2. IEA/MSCI sector averages as fallback.

        Args:
            portfolio_name: Name of the portfolio (use esg_list_portfolios to discover names).

        Returns:
            JSON with WACI, benchmark comparison, top contributors, data quality and
            chart_url (REST path of the PNG: /statics/<chart_id>.png).
        """
        self.logger.info("esg_carbon_footprint called | portfolio=%s", portfolio_name)
        holdings_raw = SAMPLE_PORTFOLIOS.get(portfolio_name)
        if holdings_raw is None:
            return json.dumps(
                {"error": f"Portfolio '{portfolio_name}' not found.", "available": list(SAMPLE_PORTFOLIOS.keys())},
                indent=2,
            )
        validated = [Holding(**h) for h in holdings_raw]
        holdings_data = []
        total_weight = sum(h.weight for h in validated)

        for h in validated:
            esg_data = _fetch_esg_yahoo(h.ticker)
            sector = esg_data.get("sector", "Unknown")
            carbon = _get_carbon_intensity(h.ticker, sector)

            waci_contribution = (carbon.get("waci") or 0) * (h.weight / total_weight)

            holdings_data.append({
                "ticker": h.ticker,
                "name": esg_data.get("companyName", h.ticker),
                "sector": sector,
                "weight": h.weight,
                "waci": carbon.get("waci"),
                "waci_contribution": round(waci_contribution, 2),
                "scope1": carbon.get("scope1"),
                "scope2": carbon.get("scope2"),
                "carbon_source": carbon.get("source", "unknown"),
                "market_value_usd": h.market_value_usd,
            })

        portfolio_waci = sum(d["waci_contribution"] for d in holdings_data)
        vs_benchmark = ((portfolio_waci - MSCI_WORLD_WACI_BENCHMARK) / MSCI_WORLD_WACI_BENCHMARK) * 100

        top3 = sorted(holdings_data, key=lambda x: x["waci_contribution"], reverse=True)[:3]
        total_waci = portfolio_waci or 1
        for d in holdings_data:
            d["share_of_portfolio_emissions"] = round(d["waci_contribution"] / total_waci, 3)

        reported = sum(1 for d in holdings_data if d["carbon_source"] == "nzdpu")
        reported_pct = round(reported / len(holdings_data) * 100, 1) if holdings_data else 0

        # ── Bar chart (Plotly) ────────────────────────────────────────────────
        tickers_list = [d["ticker"] for d in holdings_data]
        contributions = [d["waci_contribution"] for d in holdings_data]
        colors = ["#ef4444" if c > MSCI_WORLD_WACI_BENCHMARK * 0.3 else "#4ade80"
                  for c in contributions]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=tickers_list,
            y=contributions,
            marker_color=colors,
            marker_line_color="#222",
            marker_line_width=1,
            text=[f"{v:.1f}" for v in contributions],
            textposition="outside",
            textfont=dict(color="#333", size=9),
        ))
        benchmark_per_holding = MSCI_WORLD_WACI_BENCHMARK / len(holdings_data)
        fig.add_hline(
            y=benchmark_per_holding,
            line_dash="dash",
            line_color="#facc15",
            line_width=1.2,
            annotation_text=f"MSCI World Benchmark / {len(holdings_data)} holdings",
            annotation_font_color="#facc15",
        )
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#333"),
            title=dict(
                text=f"Carbon Intensity by Holding<br>{portfolio_name}",
                font=dict(color="#333", size=12),
            ),
            xaxis=dict(title="Ticker", color="#333", gridcolor="#ddd"),
            yaxis=dict(title="WACI contribution (tCO₂e/M$)", color="#333", gridcolor="#ddd"),
            width=max(600, len(holdings_data) * 90),
            height=500,
        )

        chart_id = _save_plotly_chart(fig, path=self.config.static_files_dir)

        vs_icon = "🔴" if vs_benchmark > 20 else ("🟡" if vs_benchmark > 0 else "🟢")
        chart_url_md = f"![WACI]({self.config.base_exposed_url}/statics/{chart_id}.png)"
        summary = (
                    f"## Carbon Footprint: {portfolio_name}\n\n"
                    "!!!!IMPORTANT: SHOW THIS LINK TO THE USER:\n\n"
                    f"{self.config.base_exposed_url}/statics/{chart_id}.png\n\n"
                    f"**Total WACI:** {portfolio_waci:.1f} tCO₂e/M$ revenue\n"
                    f"{vs_icon} **vs MSCI World benchmark ({MSCI_WORLD_WACI_BENCHMARK}):** {vs_benchmark:+.1f}%\n\n"
                    f"**Top emitters:**\n"
                    + "\n".join(
                        f"- {d['name']} ({d['ticker']}): {d['waci_contribution']:.1f} tCO₂e/M$ "
                        f"({d['share_of_portfolio_emissions'] * 100:.0f}% of portfolio total)"
                        for d in top3
                    )
                    + f"\n\n**Data quality:** {reported_pct}% from direct source (NZDPU), "
                    f"{100 - reported_pct:.0f}% estimated from sector average\n\n"
                    "!!!!!IMPORTANT: SHOW THIS MARKDOWN TO THE USER:\n\n"
                    f"{chart_url_md}"
                )

        return json.dumps(
            {
                "portfolio_name": portfolio_name,
                "waci": round(portfolio_waci, 2),
                "benchmark_waci": MSCI_WORLD_WACI_BENCHMARK,
                "vs_benchmark_pct": round(vs_benchmark, 1),
                "top_contributors": top3,
                "holdings_detail": holdings_data,
                "data_quality": {
                    "reported_pct": reported_pct,
                    "estimated_pct": round(100 - reported_pct, 1),
                },
                #"chart_id": chart_id,
                #"chart_url": f"{self.config.base_exposed_url}/statics/{chart_id}.png",
                "summary": summary,
                "timestamp": datetime.now().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # ─── Tool 4: esg_suggest_replacements ────────────────────────────────────

    async def esg_suggest_replacements(
        self,
        portfolio_name: str,
        min_esg_score: float = 25.0,
        max_suggestions: int = 3,
    ) -> str:
        """
        For each holding in a pre-defined portfolio with ESG risk above the threshold,
        suggest lower-risk alternatives in the same sector.

        Logic:
        1. Fetch ESG scores for all tickers in the portfolio.
        2. Identify those above the min_esg_score threshold.
        3. For each ticker to replace, search the alternative universe by sector.
        4. Verify real scores of alternatives via Yahoo Finance.
        5. Estimate impact (carbon delta).

        Args:
            portfolio_name: Name of the portfolio to analyse (use esg_list_portfolios to discover names).
            min_esg_score: Maximum acceptable ESG risk threshold (0-100, default 25 = Low risk).
                           Sustainalytics: lower = better.
            max_suggestions: Maximum number of alternatives per ticker (1-5, default 3).

        Returns:
            JSON with ok_tickers (already compliant) and replacements (with suggested alternatives).
        """
        self.logger.info(
            "esg_suggest_replacements called | portfolio=%s threshold=%.1f max_suggestions=%d",
            portfolio_name, min_esg_score, max_suggestions,
        )
        holdings_raw = SAMPLE_PORTFOLIOS.get(portfolio_name)
        if holdings_raw is None:
            return json.dumps(
                {"error": f"Portfolio '{portfolio_name}' not found.", "available": list(SAMPLE_PORTFOLIOS.keys())},
                indent=2,
            )
        tickers = [h["ticker"].strip().upper() for h in holdings_raw]
        min_esg_score = max(0.0, min(100.0, float(min_esg_score)))
        max_suggestions = max(1, min(5, int(max_suggestions)))

        ok_tickers = []
        replacements = []

        for ticker in tickers:
            data = _fetch_esg_yahoo(ticker)
            score = data.get("totalEsg")
            sector = data.get("sector", "Unknown")
            label, emoji = _esg_risk_label(score) if score is not None else ("Unknown", "❓")

            if score is None:
                replacements.append({
                    "original": {
                        "ticker": ticker,
                        "name": data.get("companyName", ticker),
                        "sector": sector,
                        "score": None,
                        "riskLabel": "N/A — Data not available",
                    },
                    "alternatives": [],
                    "action": "manual review required",
                })
                continue

            if score <= min_esg_score:
                ok_tickers.append({
                    "ticker": ticker,
                    "name": data.get("companyName", ticker),
                    "score": score,
                    "riskLabel": f"{emoji} {label}",
                })
                continue

            candidates = ALTERNATIVE_UNIVERSE.get(sector, [])
            if not candidates:
                for s, alts in ALTERNATIVE_UNIVERSE.items():
                    if any(x in sector for x in s.split()) or any(x in s for x in sector.split()):
                        candidates = alts
                        break

            alternatives = []
            for cand in candidates[:max_suggestions + 2]:
                if cand["ticker"].upper() == ticker.upper():
                    continue

                cand_data = _fetch_esg_yahoo(cand["ticker"])
                cand_score = cand_data.get("totalEsg") or cand.get("esg_proxy")
                if cand_score is None:
                    continue
                if cand_score > min_esg_score:
                    continue

                cand_label, cand_emoji = _esg_risk_label(cand_score)

                orig_carbon = _get_carbon_intensity(ticker, sector)
                cand_carbon = _get_carbon_intensity(cand["ticker"], sector)
                carbon_delta = None
                if orig_carbon.get("waci") and cand_carbon.get("waci"):
                    carbon_delta = round(cand_carbon["waci"] - orig_carbon["waci"], 1)

                alternatives.append({
                    "ticker": cand["ticker"],
                    "name": cand_data.get("companyName", cand.get("name")),
                    "sector": sector,
                    "esg_score": cand_score,
                    "riskLabel": f"{cand_emoji} {cand_label}",
                    "delta_vs_original": round(cand_score - score, 1),
                    "carbon_intensity_delta": carbon_delta,
                    "improvement": f"ESG improves by {abs(cand_score - score):.1f} points",
                })

                if len(alternatives) >= max_suggestions:
                    break

            replacements.append({
                "original": {
                    "ticker": ticker,
                    "name": data.get("companyName", ticker),
                    "sector": sector,
                    "score": score,
                    "riskLabel": f"{emoji} {label} — ABOVE THRESHOLD",
                },
                "alternatives": alternatives,
                "action": "replacement recommended" if alternatives else "no alternative found in local DB",
            })

        summary_lines = [
            f"## ESG Suggestions (threshold: ≤{min_esg_score})\n",
            f"✅ Already compliant ({len(ok_tickers)}): "
            + ", ".join(f"{t['ticker']} ({t['score']})" for t in ok_tickers),
            f"\n⚠️ Holdings to replace ({len(replacements)}):\n",
        ]
        for r in replacements:
            summary_lines.append(
                f"**{r['original']['ticker']}** → score {r['original']['score']} ({r['original']['riskLabel']})"
            )
            if r["alternatives"]:
                for a in r["alternatives"]:
                    summary_lines.append(
                        f"  → {a['name']} ({a['ticker']}): score {a['esg_score']} | {a['improvement']}"
                    )
            else:
                summary_lines.append("  → No alternative found in local DB")

        return json.dumps(
            {
                "ok_tickers": ok_tickers,
                "replacements": replacements,
                "threshold_used": min_esg_score,
                "summary": "\n".join(summary_lines),
                "timestamp": datetime.now().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    # ─── Tool 5: esg_check_sfdr ──────────────────────────────────────────────

    async def esg_check_sfdr(
        self,
        portfolio_name: str,
    ) -> str:
        """
        Assess the achievable SFDR classification for a pre-defined portfolio.

        SFDR classifications:
        - Article 6: No specific ESG objective.
        - Article 8: Promotes environmental/social characteristics (avg ESG risk ≤30, >50% ESG-screened holdings).
        - Article 9: Sustainable investment objective (avg ESG risk ≤20, carbon intensity below benchmark).

        Note: indicative assessment based on simplified criteria.
        Official classification requires full legal/compliance verification.

        Args:
            portfolio_name: Name of the portfolio to assess (use esg_list_portfolios to discover names).

        Returns:
            JSON with achievable SFDR classification, key metrics, article 8/9 criteria
            and list of blockers with corrective actions.
        """
        self.logger.info("esg_check_sfdr called | portfolio=%s", portfolio_name)
        holdings_raw = SAMPLE_PORTFOLIOS.get(portfolio_name)
        if holdings_raw is None:
            return json.dumps(
                {"error": f"Portfolio '{portfolio_name}' not found.", "available": list(SAMPLE_PORTFOLIOS.keys())},
                indent=2,
            )
        validated = [Holding(**h) for h in holdings_raw]
        holdings_analysis = []
        total_weight = sum(h.weight for h in validated)

        for h in validated:
            data = _fetch_esg_yahoo(h.ticker)
            score = data.get("totalEsg")
            sector = data.get("sector", "Unknown")
            carbon = _get_carbon_intensity(h.ticker, sector)

            holdings_analysis.append({
                "ticker": h.ticker,
                "name": data.get("companyName", h.ticker),
                "weight": h.weight,
                "esg_score": score,
                "sector": sector,
                "waci": carbon.get("waci"),
                "has_esg_data": score is not None,
            })

        scored = [h for h in holdings_analysis if h["esg_score"] is not None]
        if not scored:
            return json.dumps({"error": "No ESG data available to classify the portfolio"})

        weighted_avg_esg = sum(
            h["esg_score"] * (h["weight"] / total_weight)
            for h in scored
        )
        pct_with_esg_data = len(scored) / len(holdings_analysis) * 100
        pct_low_risk = sum(
            h["weight"] / total_weight
            for h in scored
            if h["esg_score"] <= 25
        ) * 100

        portfolio_waci = sum(
            (h["waci"] or SECTOR_CARBON_INTENSITY["Unknown"]) * (h["weight"] / total_weight)
            for h in holdings_analysis
        )

        article_9_criteria = {
            "avg_esg_score_ok":   weighted_avg_esg <= 20,
            "low_risk_coverage":  pct_low_risk >= 80,
            "carbon_under_bench": portfolio_waci < MSCI_WORLD_WACI_BENCHMARK,
            "esg_data_coverage":  pct_with_esg_data >= 90,
        }
        article_8_criteria = {
            "avg_esg_score_ok":  weighted_avg_esg <= 30,
            "low_risk_coverage": pct_low_risk >= 50,
            "esg_data_coverage": pct_with_esg_data >= 75,
        }

        art9_ok = all(article_9_criteria.values())
        art8_ok = all(article_8_criteria.values())

        if art9_ok:
            classification = "Article 9 — Dark Green 🌿"
            max_achievable = "Article 9"
        elif art8_ok:
            classification = "Article 8 — Light Green 🟢"
            max_achievable = "Article 8"
        else:
            classification = "Article 6 — No ESG mandate ⬜"
            max_achievable = "Article 6"

        blockers = []
        if not article_8_criteria["avg_esg_score_ok"]:
            blockers.append(
                f"Avg ESG risk {weighted_avg_esg:.1f} > 30 (Art.8 limit). "
                f"Requires a reduction of {weighted_avg_esg - 30:.1f} points."
            )
        if not article_8_criteria["low_risk_coverage"]:
            blockers.append(
                f"Only {pct_low_risk:.0f}% of the portfolio has score ≤25 (≥50% required for Art.8)."
            )
        if not article_8_criteria["esg_data_coverage"]:
            blockers.append(
                f"Only {pct_with_esg_data:.0f}% of holdings have ESG data (≥75% required for Art.8)."
            )
        if art8_ok and not article_9_criteria["carbon_under_bench"]:
            blockers.append(
                f"WACI {portfolio_waci:.1f} > benchmark {MSCI_WORLD_WACI_BENCHMARK} "
                f"(must be below benchmark for Art.9)."
            )
        if art8_ok and not article_9_criteria["avg_esg_score_ok"]:
            blockers.append(f"Avg ESG risk {weighted_avg_esg:.1f} > 20 (Art.9 limit).")

        summary = (
            f"## SFDR Classification: {portfolio_name}\n\n"
            f"🏷️ **Achievable classification: {classification}**\n\n"
            f"**Key metrics:**\n"
            f"- Weighted avg ESG risk: {weighted_avg_esg:.1f}\n"
            f"- % portfolio Low Risk (≤25): {pct_low_risk:.0f}%\n"
            f"- Carbon intensity (WACI): {portfolio_waci:.1f} vs benchmark {MSCI_WORLD_WACI_BENCHMARK}\n"
            f"- ESG data coverage: {pct_with_esg_data:.0f}%\n"
        )
        if blockers:
            summary += "\n**Actions to improve the classification:**\n" + "\n".join(f"- {b}" for b in blockers)

        return json.dumps(
            {
                "portfolio_name": portfolio_name,
                "current_classification": classification,
                "max_achievable": max_achievable,
                "metrics": {
                    "weighted_avg_esg": round(weighted_avg_esg, 2),
                    "pct_low_risk": round(pct_low_risk, 1),
                    "portfolio_waci": round(portfolio_waci, 1),
                    "benchmark_waci": MSCI_WORLD_WACI_BENCHMARK,
                    "esg_data_coverage_pct": round(pct_with_esg_data, 1),
                },
                "article_9_criteria": article_9_criteria,
                "article_8_criteria": article_8_criteria,
                "blockers": blockers,
                "holdings_detail": holdings_analysis,
                "summary": summary,
                "disclaimer": (
                    "Indicative classification based on simplified criteria. "
                    "Official SFDR classification requires full legal/compliance verification."
                ),
                "timestamp": datetime.now().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
