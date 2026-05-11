"""
Best-effort property data fetching.
All functions return dicts with whatever they can find; callers should treat
every field as optional and fall back to manual entry gracefully.
"""

import re
import json
import time
import random
import requests
from urllib.parse import quote
from typing import Optional

# ── Chicago neighborhood rent benchmarks ($/sqft/month, 2025 estimates) ───────
CHICAGO_NEIGHBORHOOD_RENTS: dict = {
    "lincoln park": 2.85,
    "gold coast": 3.30,
    "river north": 3.15,
    "wicker park": 2.65,
    "bucktown": 2.60,
    "logan square": 2.35,
    "pilsen": 1.95,
    "bridgeport": 1.75,
    "hyde park": 2.00,
    "bronzeville": 1.85,
    "andersonville": 2.45,
    "lakeview": 2.75,
    "uptown": 2.25,
    "rogers park": 1.80,
    "edgewater": 2.15,
    "avondale": 2.05,
    "humboldt park": 1.70,
    "austin": 1.45,
    "beverly": 1.65,
    "morgan park": 1.60,
    "south loop": 2.95,
    "west loop": 3.10,
    "streeterville": 3.40,
    "old town": 3.00,
    "noble square": 2.50,
    "ukrainian village": 2.40,
    "east village": 2.30,
    "fulton market": 3.20,
    "tri-taylor": 1.90,
    "little village": 1.60,
    "back of the yards": 1.50,
    "woodlawn": 1.70,
    "south shore": 1.65,
    "chatham": 1.55,
    "englewood": 1.25,
}

# Chicago bedroom-count rent heuristics (2025 market averages)
CHICAGO_BEDROOM_RENTS: dict = {0: 1450, 1: 1900, 2: 2500, 3: 3200, 4: 4000}

# Cook County effective property tax rate estimate
# Assessed at ~10% AV, equalizer ~2.9, levy ~11% → statutory ~3.2%
# Lag between sale price and reassessment means effective rate on purchase ≈ 1.5-2.2%
COOK_COUNTY_TAX_RATE = 0.018

# ── Utility rate constants (2025 published rates) ─────────────────────────────

# ComEd all-in rate (commodity + delivery + taxes, residential average)
COMED_RATE_PER_KWH = 0.1393  # $/kWh

# People's Gas (commodity + distribution, 12-month average)
PEOPLES_GAS_RATE_PER_THERM = 0.647  # $/therm

# Chicago water/sewer (city residential, quarterly bill ÷ 3)
CHICAGO_WATER_MONTHLY = 48.0  # $/month

# Monthly usage estimates by bedroom count (Chicago averages, blended across seasons)
# Electric: includes summer AC, excludes heat (gas-heated buildings)
# Gas: annual average (Chicago winters → ~80-120 therms/mo, summers → ~10-20)
_UTILITY_BY_BR: dict = {
    0: {"electric_kwh": 350, "gas_therms": 22},
    1: {"electric_kwh": 450, "gas_therms": 32},
    2: {"electric_kwh": 620, "gas_therms": 48},
    3: {"electric_kwh": 800, "gas_therms": 65},
    4: {"electric_kwh": 980, "gas_therms": 82},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "DNT": "1",
    "Connection": "keep-alive",
}


def _safe_get(url: str, timeout: int = 12, extra_headers: dict = None) -> Optional[requests.Response]:
    try:
        time.sleep(random.uniform(0.8, 1.8))
        hdrs = {**HEADERS, **(extra_headers or {})}
        resp = requests.get(url, headers=hdrs, timeout=timeout)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None


# ── Redfin ────────────────────────────────────────────────────────────────────

def fetch_redfin(address: str) -> dict:
    """
    Attempt to fetch listing data from Redfin via autocomplete + property page.
    Returns partial dict; any key may be absent. More reliable than Zillow.
    """
    result: dict = {}

    # Step 1: autocomplete to find property URL
    ac_url = (
        "https://www.redfin.com/stingray/do/location-autocomplete"
        f"?location={quote(address)}&v=2&market=chicago&al=1&iss=false"
    )
    resp = _safe_get(ac_url, extra_headers={"Referer": "https://www.redfin.com/"})
    if not resp:
        return result

    text = resp.text
    # Redfin prefixes response with "{}&&" as XSSI protection
    if "&&" in text:
        text = text.split("&&", 1)[1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return result

    property_url = None
    sub_name = ""
    sections = data.get("payload", {}).get("sections", [])

    # type "2" = single property, "4" = condo unit
    for section in sections:
        for row in section.get("rows", []):
            if str(row.get("type", "")) in ("2", "4") or "/home/" in row.get("url", ""):
                property_url = row.get("url", "")
                sub_name = row.get("subName", "")
                break
        if property_url:
            break

    if not property_url:
        return result

    result["source"] = "Redfin"
    result["property_url"] = "https://www.redfin.com" + property_url

    # Try to parse price from autocomplete subName (e.g. "For Sale: $450,000")
    price_m = re.search(r'\$(\d[\d,]+(?:K|M)?)', sub_name)
    if price_m:
        ps = price_m.group(1).replace(",", "")
        if ps.endswith("K"):
            result["purchase_price"] = float(ps[:-1]) * 1_000
        elif ps.endswith("M"):
            result["purchase_price"] = float(ps[:-1]) * 1_000_000
        else:
            try:
                result["purchase_price"] = float(ps)
            except ValueError:
                pass

    # Step 2: fetch property page
    prop_resp = _safe_get(
        result["property_url"],
        extra_headers={"Referer": "https://www.redfin.com/"},
    )
    if not prop_resp:
        return {k: v for k, v in result.items() if v is not None}

    html = prop_resp.text

    # Try schema.org JSON-LD (most structured, most reliable)
    ld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for raw in ld_blocks:
        try:
            ld = json.loads(raw.strip())
            schema_type = ld.get("@type", "")
            if not isinstance(schema_type, str):
                continue
            if not any(t in schema_type for t in ("Residence", "House", "Apartment", "Property", "Home")):
                continue

            offers = ld.get("offers", {})
            if isinstance(offers, dict) and offers.get("price"):
                result["purchase_price"] = float(str(offers["price"]).replace(",", ""))

            beds = ld.get("numberOfBedrooms") or ld.get("numberOfRooms")
            if beds is not None:
                result["bedrooms"] = int(float(str(beds)))

            baths = ld.get("numberOfBathroomsTotal") or ld.get("numberOfBathrooms")
            if baths is not None:
                result["bathrooms"] = float(str(baths))

            floor = ld.get("floorSize", {})
            if isinstance(floor, dict) and floor.get("value"):
                result["sqft"] = float(str(floor["value"]).replace(",", ""))
            break
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # Fallback regex patterns for price, beds, sqft
    if "purchase_price" not in result:
        for pat in [
            r'"listingPrice":\{"amount":(\d+)',
            r'"price":(\d{5,8})\b',
        ]:
            m = re.search(pat, html)
            if m:
                try:
                    result["purchase_price"] = float(m.group(1))
                    break
                except ValueError:
                    continue

    if "bedrooms" not in result:
        m = re.search(r'"beds":(\d+)', html)
        if m:
            result["bedrooms"] = int(m.group(1))

    if "sqft" not in result:
        for pat in [r'"sqFt":\{"value":(\d+)', r'"sqft":(\d+)']:
            m = re.search(pat, html)
            if m:
                result["sqft"] = float(m.group(1))
                break

    if "hoa_fee" not in result:
        m = re.search(r'"hoa(?:Fee|Monthly)?":(\d+)', html, re.IGNORECASE)
        if m:
            result["hoa_fee"] = float(m.group(1))

    return {k: v for k, v in result.items() if v is not None}


# ── Rent estimate ─────────────────────────────────────────────────────────────

def estimate_rent(address: str, sqft: Optional[float] = None, bedrooms: Optional[int] = None) -> dict:
    result: dict = {}
    addr_lower = address.lower()

    matched_rate = None
    for hood, rate in CHICAGO_NEIGHBORHOOD_RENTS.items():
        if hood in addr_lower:
            matched_rate = rate
            result["neighborhood_matched"] = hood.title()
            break

    if matched_rate and sqft and sqft > 0:
        result["estimated_rent"] = round(matched_rate * sqft)
        result["rent_basis"] = f"{result['neighborhood_matched']} · ${matched_rate}/sqft × {sqft:.0f} sqft"
        return result

    if bedrooms is not None and bedrooms in CHICAGO_BEDROOM_RENTS:
        result["estimated_rent"] = CHICAGO_BEDROOM_RENTS[bedrooms]
        hood_label = result.get("neighborhood_matched", "Chicago")
        result["rent_basis"] = f"{hood_label} · {bedrooms}BR market average"

    return result


# ── Utility estimates ─────────────────────────────────────────────────────────

def estimate_utilities(bedrooms: int = 1) -> dict:
    """
    Estimate monthly utility costs for a Chicago rental unit.
    Based on ComEd 2025 rates + People's Gas 2025 rates + city water.

    These are landlord-cost estimates — only applicable if landlord pays utilities.
    Typical Chicago lease: tenant pays electric + gas, landlord pays water.
    """
    br = max(0, min(bedrooms, 4))
    usage = _UTILITY_BY_BR.get(br, _UTILITY_BY_BR[1])

    electric = round(usage["electric_kwh"] * COMED_RATE_PER_KWH, 2)
    gas = round(usage["gas_therms"] * PEOPLES_GAS_RATE_PER_THERM, 2)

    return {
        "electric_monthly": electric,
        "gas_monthly": gas,
        "water_monthly": CHICAGO_WATER_MONTHLY,
        "electric_kwh_est": usage["electric_kwh"],
        "gas_therms_est": usage["gas_therms"],
        "utility_note": (
            f"ComEd: {usage['electric_kwh']} kWh × ${COMED_RATE_PER_KWH}/kWh = ${electric:.0f}/mo  |  "
            f"People's Gas: {usage['gas_therms']} therms × ${PEOPLES_GAS_RATE_PER_THERM}/therm = ${gas:.0f}/mo  |  "
            f"Water/sewer: ${CHICAGO_WATER_MONTHLY:.0f}/mo (city estimate)"
        ),
    }


# ── Combined lookup ───────────────────────────────────────────────────────────

def lookup_property(address: str) -> dict:
    """
    Master lookup: tries Redfin, supplements with local estimates.
    Every field is best-effort — caller must handle missing values.
    """
    result: dict = {"address": address, "fetch_status": "pending"}

    redfin = fetch_redfin(address)
    result.update(redfin)

    # Derived estimates when price is known but fields are missing
    if "purchase_price" in result:
        pp = result["purchase_price"]
        if "property_tax_annual" not in result:
            result["property_tax_annual"] = round(pp * COOK_COUNTY_TAX_RATE)
            result["tax_source"] = f"Cook County estimate ({COOK_COUNTY_TAX_RATE*100:.1f}% of price)"
        if "insurance_annual" not in result:
            result["insurance_annual"] = round(pp * 0.005)
            result["insurance_source"] = "Illinois estimate (0.5% of price)"

    # Rent estimate
    rent_data = estimate_rent(
        address,
        sqft=result.get("sqft"),
        bedrooms=result.get("bedrooms"),
    )
    result.update(rent_data)

    result["fetch_status"] = "ok" if "purchase_price" in result else "partial"
    return result
