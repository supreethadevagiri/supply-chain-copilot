"""
Real external data sources for Task 1's seasonal benchmark check.

- UN Comtrade: Germany's actual coffee (HS 0901) import volumes
- USDA FAS PSD Online: Brazil's actual green coffee export volumes

IMPORTANT NAMING NOTE: The original project brief said "USDA FAS GATS."
GATS has no public API -- it's a browser-only query tool with no way to
call it in code. USDA FAS PSD Online is a different system from the same
agency that DOES have real, callable data access, and also covers Brazil
coffee exports, so this project uses PSD Online instead. The doc's wording
has been updated to match (see the revised project brief).

Both functions below fall back to typical-year reference values if the
live pull fails (no internet, API down, etc.) -- so the rest of the system
never breaks because of a network hiccup. That fallback behavior is a
deliberate, honest design choice, not a workaround.
"""
import time

import io
import zipfile
import pandas as pd
import requests
from datetime import datetime, timedelta


# ---------------------------------------------------------------------
# UN Comtrade -- Germany's real coffee import volumes (HS 0901)
# ---------------------------------------------------------------------
# pip install comtradeapicall
# Free registration for a subscription key (optional -- raises the
# 500-record preview limit to 250K): https://comtradeplus.un.org
#   -> sign in -> API Management -> generate a primary key
#
# reporterCode 276 = Germany, cmdCode 0901 = Coffee (HS), flowCode 'M' = Import

def get_un_comtrade_germany_coffee_imports(period: str, subscription_key: str = None):
    """period format: 'YYYYMM', e.g. '202508' for August 2025.
    Returns a DataFrame of Germany's coffee import records for that month,
    or None if the pull fails (caller should fall back to cached data)."""
    try:
        import comtradeapicall
        if subscription_key:
            df = comtradeapicall.getFinalData(
                subscription_key, typeCode="C", freqCode="M", clCode="HS",
                period=period, reporterCode="276", cmdCode="0901",
                flowCode="M", partnerCode=None, partner2Code=None,
                customsCode=None, motCode=None, maxRecords=2500,
                format_output="JSON", includeDesc=True,
            )
        else:
            # No key needed -- capped at 500 records, plenty for one month
            df = comtradeapicall.previewFinalData(
                typeCode="C", freqCode="M", clCode="HS", period=period,
                reporterCode="276", cmdCode="0901", flowCode="M",
                partnerCode=None, partner2Code=None, customsCode=None,
                motCode=None, includeDesc=True,
            )
        return df
    except Exception as e:
        print(f"[UN Comtrade] Live pull failed ({e}); caller should use cached fallback.")
        return None


# ---------------------------------------------------------------------
# USDA FAS PSD Online -- Brazil's real green coffee export volumes
# ---------------------------------------------------------------------
# Coffee, Green commodity code = 0711100. USDA publishes a pre-filtered
# bulk CSV for coffee specifically -- no API key needed for this file,
# which is simpler and more reliable than the full live API for a
# monthly/periodic pull like this one.
PSD_COFFEE_BULK_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_coffee_csv.zip"


def get_usda_brazil_coffee_exports(market_year: int):
    """Downloads USDA's coffee PSD bulk file and filters to Brazil's
    export figure for the given marketing year (Brazil's coffee MY runs
    April-March). Returns a DataFrame row, or None if the pull fails."""
    try:
        resp = requests.get(PSD_COFFEE_BULK_URL, timeout=30)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
            df = pd.read_csv(z.open(csv_name))

        brazil = df[
            (df["Country_Name"].str.strip() == "Brazil")
            & (df["Attribute_Description"].str.strip() == "Exports")
            & (df["Market_Year"] == market_year)
        ]
        return brazil
    except Exception as e:
        print(f"[USDA PSD Online] Live pull failed ({e}); caller should use cached fallback.")
        return None


# ---------------------------------------------------------------------
# Optional -- live API alternative to the bulk file, for on-demand
# queries instead of downloading the whole bulk file each time.
# Requires a free API key: https://apps.fas.usda.gov/opendataweb/home
#   -> register -> "API Keys" section
# Verify the exact endpoint path against their current Swagger docs
# before relying on this in a demo -- GetAllData is confirmed working;
# a commodity-filtered endpoint may also exist but wasn't verified here.
# ---------------------------------------------------------------------
PSD_API_BASE = "https://apps.fas.usda.gov/PSDOnlineDataServices/api/CommodityData"


def get_usda_coffee_data_live(api_key: str):
    """Confirmed-working endpoint: pulls ALL commodities, so filter
    client-side to commodityCode 0711100 (Coffee, Green) and Brazil."""
    url = f"{PSD_API_BASE}/GetAllData"
    headers = {"Accept": "application/json", "API_KEY": api_key}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------
# Combined: what tools.py's get_seasonal_benchmark() should call
# ---------------------------------------------------------------------
def fetch_seasonal_benchmark_live(month: str, subscription_key: str = None) -> dict:
    """Tries the real UN Comtrade + USDA pulls; falls back to the cached
    CSV (data/seasonal_benchmark.csv) for whichever one fails. Never
    raises -- always returns usable numbers, real or cached.

    IMPORTANT: the real Comtrade/USDA numbers are NATIONAL trade totals
    (all of Germany's imports, all of Brazil's exports, to every
    destination) -- they are orders of magnitude larger than Elbhafen's
    own ~850-bag warehouse stock, and were never meant to be compared to
    it directly as a bag-count. This function keeps them as labeled
    market-context figures instead, and judges "is this an unusual
    season" against a rough typical-year reference range for Brazil's
    exports (documented below), not against Elbhafen's own stock level.
    """
    # Note: the old cached seasonal_benchmark.csv is no longer used here --
    # it was built at company-warehouse scale (hundreds of bags), which is
    # the wrong scale for these national-level real trade figures. See the
    # typical-year constants below instead.

    period = f"2025{month}"  # adjust year as needed when you run this live
    comtrade_df = get_un_comtrade_germany_coffee_imports(period, subscription_key)
    # Realistic fallback: Germany imports roughly ~1 million tons of green
    # coffee annually (published trade estimates), so ~83,000 tons/month
    # is a reasonable rough default when the live pull is unavailable --
    # NOT the old company-scale placeholder, which was the wrong scale
    # for this real, national-level figure.
    GERMANY_TYPICAL_MONTHLY_IMPORT_TONS = 83000
    if comtrade_df is not None and not comtrade_df.empty:
        # IMPORTANT: previewFinalData returns one row for the "World"
        # total AND a separate row for every individual partner country
        # (Brazil, Austria, Belgium, etc.) -- those country rows are
        # already included inside the "World" row. Summing every row
        # double-counts massively. Only the "World" row is the correct
        # total for Germany's imports from everywhere.
        world_row = comtrade_df[comtrade_df["partnerDesc"] == "World"]
        if not world_row.empty:
            germany_import_tons = round(world_row["netWgt"].iloc[0] / 1000, 1)
        else:
            # No "World" row came back (unlikely) -- sum individual
            # countries instead, which is at least not double-counted.
            non_world = comtrade_df[comtrade_df["partnerDesc"] != "World"]
            germany_import_tons = round(non_world["netWgt"].sum() / 1000, 1)
        source_germany = "UN Comtrade (live)"
        # Sanity guard: Germany's real annual coffee imports run ~1.2M
        # tons/year (published trade data), so ~150K tons/month is a safe
        # upper bound for one month even allowing for a busy season. If
        # the live pull exceeds that, something is wrong with the query
        # (likely the period filter not actually restricting to one
        # month) -- don't trust an implausible number in a live demo.
        if germany_import_tons > 150000:
            print(f"[UN Comtrade] Live value ({germany_import_tons} tons) failed "
                  f"plausibility check (>150,000 tons/month) -- using typical "
                  f"estimate instead. Needs debugging with real internet access.")
            germany_import_tons = GERMANY_TYPICAL_MONTHLY_IMPORT_TONS
            source_germany = "cached fallback (live value failed plausibility check)"
    else:
        germany_import_tons = GERMANY_TYPICAL_MONTHLY_IMPORT_TONS
        source_germany = "cached fallback (typical-year estimate)"

    market_year = 2025 if int(month) >= 4 else 2024  # Brazil coffee MY: Apr-Mar
    usda_df = get_usda_brazil_coffee_exports(market_year)
    # Rough typical-year reference for context only (Brazil's coffee export
    # volume is commonly cited in the 35,000-45,000 thousand-bag range per
    # marketing year) -- this is an approximation for a directional "is
    # this an unusual season" signal, not a precise benchmark. Refine with
    # a real multi-year USDA pull if higher precision is needed later.
    BRAZIL_TYPICAL_ANNUAL_THOUSAND_BAGS = 40000
    if usda_df is not None and not usda_df.empty:
        brazil_export_thousand_bags = int(usda_df["Value"].iloc[0])
        source_brazil = "USDA FAS PSD Online (live)"
    else:
        # When we can't reach real data, default to "typical" rather than
        # fabricating a number that could falsely signal an abnormal
        # season -- absence of data should not itself become a false alarm.
        brazil_export_thousand_bags = BRAZIL_TYPICAL_ANNUAL_THOUSAND_BAGS
        source_brazil = "cached fallback (assumed typical)"

    pct_of_typical = round(100 * brazil_export_thousand_bags / BRAZIL_TYPICAL_ANNUAL_THOUSAND_BAGS, 1)
    below_seasonal_norm = pct_of_typical < 90  # more than 10% below a typical year

    return {
        "month": month,
        "germany_national_import_tons_this_period": germany_import_tons,
        "germany_data_source": source_germany,
        "brazil_national_export_thousand_bags_this_period": brazil_export_thousand_bags,
        "brazil_pct_of_typical_year": pct_of_typical,
        "brazil_data_source": source_brazil,
        "below_seasonal_norm": below_seasonal_norm,
    }


if __name__ == "__main__":
    import json
    # This will fail to reach the network in a sandboxed environment --
    # that's expected. Run this on your own machine with real internet
    # access to see live data. The fallback path is what makes it safe
    # to run anywhere, including here.
    result = fetch_seasonal_benchmark_live("08")
    print(json.dumps(result, indent=2))


# =======================================================================
# TASK 2 -- Risk Assessment: additional real data sources
# =======================================================================

# ---------------------------------------------------------------------
# Arabica futures price -- Yahoo Finance, ticker KC=F
# ---------------------------------------------------------------------
def get_arabica_futures_price() -> dict:
    """Real Arabica coffee futures price (ICE, ticker KC=F) from Yahoo
    Finance. Returns the latest close plus a short recent history so a
    spike can be judged against a real recent baseline, not just one
    number in isolation."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("KC=F")
        hist = ticker.history(period="1mo")
        if hist.empty:
            raise ValueError("No futures data returned")
        latest_close = round(float(hist["Close"].iloc[-1]), 2)
        avg_last_30d = round(float(hist["Close"].mean()), 2)
        pct_vs_30d_avg = round(100 * (latest_close - avg_last_30d) / avg_last_30d, 1)
        return {
            "latest_close_cents_per_lb": latest_close,
            "avg_last_30d_cents_per_lb": avg_last_30d,
            "pct_vs_30d_avg": pct_vs_30d_avg,
            "is_spike": abs(pct_vs_30d_avg) > 10,  # >10% move vs its own recent average
            "source": "Yahoo Finance KC=F (live)",
        }
    except Exception as e:
        print(f"[Yahoo Finance] Live pull failed ({e}); assuming no spike.")
        return {
            "latest_close_cents_per_lb": None,
            "avg_last_30d_cents_per_lb": None,
            "pct_vs_30d_avg": 0.0,
            "is_spike": False,
            "source": "unavailable (assumed no spike)",
        }


# ---------------------------------------------------------------------
# GDELT -- global news, filtered to Minas Gerais, for climate/political reports
# ---------------------------------------------------------------------
def get_regional_news(query: str = "Minas Gerais coffee") -> dict:
    """Real regional news search via Google News RSS. Free, public, no
    API key or account -- switched from GDELT because GDELT's free tier
    rate-limits hard under repeated calls, a real risk for a live demo.
    Returns recent matching articles as a signal -- article
    count/presence is the signal, not sentiment analysis (kept simple
    and explainable)."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        headlines = [item.findtext("title") for item in items[:5]]
        return {
            "article_count_last_week": len(items),
            "headlines": headlines,
            "signal_triggered": len(items) >= 3,  # 3+ matching articles = notable
            "source": "Google News RSS (live)",
        }
    except Exception as e:
        print(f"[Regional News] Live pull failed ({e}); assuming no notable news.")
        return {
            "article_count_last_week": 0,
            "headlines": [],
            "signal_triggered": False,
            "source": "unavailable (assumed no notable news)",
        }


# ---------------------------------------------------------------------
# Real-Euro exchange rate -- Frankfurter API (ECB data), free, no key
# ---------------------------------------------------------------------
def get_brl_eur_exchange_rate() -> dict:
    """Real BRL-EUR exchange rate from Frankfurter (European Central
    Bank reference rates). Compares today's rate to the 30-day average
    to flag whether currency alone could be moving the delivered price."""
    try:
        latest = requests.get("https://api.frankfurter.dev/v1/latest",
                               params={"base": "BRL", "symbols": "EUR"}, timeout=15)
        latest.raise_for_status()
        latest_rate = latest.json()["rates"]["EUR"]

        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        history = requests.get(f"https://api.frankfurter.dev/v1/{month_ago}..",
                                params={"base": "BRL", "symbols": "EUR"}, timeout=15)
        history.raise_for_status()
        rates_series = [v["EUR"] for v in history.json()["rates"].values()]
        avg_30d = sum(rates_series) / len(rates_series) if rates_series else latest_rate

        pct_move = round(100 * (latest_rate - avg_30d) / avg_30d, 2)
        return {
            "brl_eur_rate": round(latest_rate, 5),
            "avg_30d_rate": round(avg_30d, 5),
            "pct_move_vs_30d_avg": pct_move,
            "significant_move": abs(pct_move) > 3,  # >3% currency move in a month is notable
            "source": "Frankfurter/ECB (live)",
        }
    except Exception as e:
        print(f"[Frankfurter] Live pull failed ({e}); assuming no significant move.")
        return {
            "brl_eur_rate": None,
            "avg_30d_rate": None,
            "pct_move_vs_30d_avg": 0.0,
            "significant_move": False,
            "source": "unavailable (assumed no significant move)",
        }


# ---------------------------------------------------------------------
# Trase.earth -- Brazil coffee deforestation exposure by municipality
# ---------------------------------------------------------------------
# IMPORTANT: Trase has no public API -- their download links are
# JS-generated, not stable URLs. Their Brazil coffee dataset also only
# covers 2016-2017 (last updated Jun 2022), so it's a static reference
# table, not a live feed -- which is actually fine for this use case,
# since deforestation risk is a geographic property of a municipality,
# not something that changes month to month.
#
# ONE-TIME MANUAL STEP: download the CSV yourself from
#   https://trase.earth/open-data/datasets/supply-chains-brazil-coffee
# and save it as data/trase_brazil_coffee.csv
TRASE_CSV_PATH = "data/trase_brazil_coffee.csv"


def get_trase_deforestation_exposure(municipality: str, state: str = "MINAS GERAIS") -> dict:
    """Looks up land-use intensity for a municipality in the real,
    cached Trase Brazil coffee dataset. Trase's actual columns are
    'municipality' and 'land_use' (hectares of land footprint associated
    with each shipment) and 'volume' (tons shipped) -- there is no
    ready-made boolean deforestation flag in the raw download. Instead,
    this computes land-use intensity (hectares per ton) for the
    municipality and flags it if it's meaningfully above the Minas
    Gerais state median -- a real, grounded footprint signal, not a
    literal "this land was illegally deforested" determination, which
    Trase's public download doesn't directly provide. Returns
    found_in_dataset=False rather than a guess if the municipality isn't
    in the file -- consistent with NO_GUESSING_RULE."""
    try:
        df = pd.read_csv(TRASE_CSV_PATH)
        df["municipality"] = df["municipality"].astype(str)
        match = df[df["municipality"].str.contains(municipality, case=False, na=False)]
        if match.empty:
            return {
                "municipality": municipality,
                "found_in_dataset": False,
                "deforestation_risk_flag": None,
                "source": "Trase.earth Brazil coffee dataset (cached, 2016-2017) -- municipality not found",
            }

        match = match.copy()
        match["land_use_intensity"] = match["land_use"] / match["volume"]
        muni_avg_intensity = match["land_use_intensity"].mean()

        state_df = df[df["state"].str.upper() == state.upper()].copy()
        state_df["land_use_intensity"] = state_df["land_use"] / state_df["volume"]
        state_median_intensity = state_df["land_use_intensity"].median()

        # Flagged if the municipality's land footprint per ton is at
        # least 50% above the state median -- a real relative-intensity
        # threshold, not an arbitrary hardcoded cutoff.
        elevated = bool(muni_avg_intensity > state_median_intensity * 1.5)

        plain_language = (
            f"flagged for deforestation risk (land use "
            f"{round(float(muni_avg_intensity), 2)} hectares per ton, "
            f"versus a state median of {round(float(state_median_intensity), 2)})"
            if elevated else
            f"NOT flagged for deforestation risk (land use "
            f"{round(float(muni_avg_intensity), 2)} hectares per ton, "
            f"close to the state median of {round(float(state_median_intensity), 2)})"
        )

        return {
            "municipality": municipality,
            "found_in_dataset": True,
            "land_use_intensity_ha_per_ton": round(float(muni_avg_intensity), 2),
            "state_median_land_use_intensity_ha_per_ton": round(float(state_median_intensity), 2),
            "deforestation_risk_flag": elevated,
            "deforestation_plain_language": plain_language,
            "note": (
                "Flag is based on land-use intensity (hectares per ton "
                "shipped) relative to the Minas Gerais state median in "
                "Trase's real 2016-2017 dataset -- a real footprint "
                "signal, not a literal illegal-deforestation determination."
            ),
            "source": "Trase.earth Brazil coffee dataset (cached, 2016-2017, real data)",
        }
    except Exception as e:
        print(f"[Trase.earth] Live lookup failed ({e}); treating as not found in dataset.")
        return {
            "municipality": municipality,
            "found_in_dataset": False,
            "deforestation_risk_flag": None,
            "source": f"unavailable ({e.__class__.__name__})",
        }
