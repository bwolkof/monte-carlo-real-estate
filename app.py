"""
Real Estate Investment Analyzer — Streamlit app.
Run:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from calculator import PropertyInputs, analyze, PropertyMetrics, remaining_balance
from monte_carlo import MCParams, MCResults, run_simulation
from fetcher import (
    lookup_property,
    estimate_utilities,
    COOK_COUNTY_TAX_RATE,
    COMED_RATE_PER_KWH,
    PEOPLES_GAS_RATE_PER_THERM,
    CHICAGO_WATER_MONTHLY,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="RE Investment Analyzer",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background: #1e2030;
        border-radius: 10px;
        padding: 14px 18px;
        margin: 5px 0;
    }
    .metric-label { font-size: 0.76rem; color: #8b9cba; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.35rem; font-weight: 700; color: #e8eaf6; }
    .metric-sub   { font-size: 0.72rem; color: #6b7a9b; margin-top: 2px; }
    .positive { color: #4caf73 !important; }
    .negative { color: #e05c6c !important; }
    .neutral  { color: #8b9cba !important; }
    .warn     { color: #f0a500 !important; }
    .section-header {
        font-size: 0.82rem; font-weight: 600; color: #8b9cba;
        text-transform: uppercase; letter-spacing: 0.08em;
        border-bottom: 1px solid #2d3250;
        padding-bottom: 5px; margin: 16px 0 8px 0;
    }
    div[data-testid="stSidebarContent"] { background: #141624; }
    .rule-pass { color: #4caf73; font-weight: 600; }
    .rule-fail { color: #e05c6c; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────

def default_property(n: int) -> PropertyInputs:
    return PropertyInputs(
        name=f"Property {n}",
        bedrooms=2,
        down_payment_pct=0.20,
        closing_costs_pct=0.03,
        loan_rate=0.07,
        loan_term_years=30,
        maintenance_pct=0.01,
        vacancy_rate=0.05,
        annual_appreciation_pct=0.03,
        annual_rent_growth_pct=0.02,
        hold_years=10,
        selling_costs_pct=0.06,
        land_value_pct=0.20,
        tax_bracket=0.0,
    )


if "properties" not in st.session_state:
    p1 = default_property(1)
    p1.address = "123 N Michigan Ave, Chicago, IL"
    p2 = default_property(2)
    p2.address = "456 W Wacker Dr, Chicago, IL"
    st.session_state.properties = [p1, p2]


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_usd(val: float, decimals: int = 0) -> str:
    if val < 0:
        return f"-${abs(val):,.{decimals}f}"
    return f"${val:,.{decimals}f}"


def fmt_pct(val: float, decimals: int = 2) -> str:
    return f"{val:.{decimals}f}%"


def color_class(val: float, reverse: bool = False) -> str:
    if val > 0:
        return "negative" if reverse else "positive"
    if val < 0:
        return "positive" if reverse else "negative"
    return "neutral"


def metric_card(label: str, value: str, css: str = "", sub: str = "") -> str:
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value {css}">{value}</div>'
        f'{sub_html}</div>'
    )


def rating(val: float, lo: float, hi: float, reverse: bool = False) -> str:
    good = val <= lo if reverse else val >= hi
    ok = val <= hi if reverse else val >= lo
    if good:
        return "🟢"
    if ok:
        return "🟡"
    return "🔴"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🏠 Properties")

    if st.button("➕  Add Property", use_container_width=True):
        st.session_state.properties.append(default_property(len(st.session_state.properties) + 1))

    props = st.session_state.properties
    selected_idx = st.radio(
        "Edit",
        options=range(len(props)),
        format_func=lambda i: props[i].name or f"Property {i+1}",
        label_visibility="collapsed",
    )

    if len(props) > 1 and st.button("🗑  Remove selected", use_container_width=True):
        st.session_state.properties.pop(selected_idx)
        st.rerun()

    st.divider()
    p: PropertyInputs = st.session_state.properties[selected_idx]

    # ── Identity ──────────────────────────────────────────────────────────────
    p.name = st.text_input("Label", value=p.name)
    p.address = st.text_input("Address", value=p.address, placeholder="123 Main St, Chicago, IL")

    do_fetch = st.button(
        "🔍  Lookup via Redfin",
        use_container_width=True,
        help="Best-effort scrape from Redfin — ~60-70% success on active listings. "
             "Always verify scraped values against the actual listing.",
    )

    if do_fetch and p.address:
        with st.spinner("Fetching from Redfin…"):
            fetched = lookup_property(p.address)

        fetched_fields = []
        if fetched.get("purchase_price"):
            p.purchase_price = fetched["purchase_price"]
            fetched_fields.append(f"Price: {fmt_usd(p.purchase_price)}")
        if fetched.get("bedrooms"):
            p.bedrooms = int(fetched["bedrooms"])
            fetched_fields.append(f"Beds: {p.bedrooms}")
        if fetched.get("sqft"):
            p.sqft = float(fetched["sqft"])
            fetched_fields.append(f"Sqft: {p.sqft:.0f}")
        if fetched.get("property_tax_annual"):
            p.property_tax_annual = fetched["property_tax_annual"]
        if fetched.get("insurance_annual"):
            p.insurance_annual = fetched["insurance_annual"]
        if fetched.get("hoa_fee"):
            p.hoa_monthly = float(fetched["hoa_fee"])
            fetched_fields.append(f"HOA: {fmt_usd(p.hoa_monthly)}/mo")
        if fetched.get("estimated_rent"):
            p.monthly_rent = float(fetched["estimated_rent"])
            basis = fetched.get("rent_basis", "")
            fetched_fields.append(f"Rent est: {fmt_usd(p.monthly_rent)}/mo")
            if basis:
                st.caption(f"Rent basis: {basis}")

        if fetched_fields:
            st.success("Pulled: " + " · ".join(fetched_fields))
            if fetched.get("property_url"):
                st.caption(f"[View on Redfin]({fetched['property_url']})")
        else:
            st.warning(
                "Redfin lookup returned no data — listing may not be indexed, "
                "or the address format didn't match. Enter details manually."
            )

        st.session_state.properties[selected_idx] = p

    # ── Purchase ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Purchase</div>', unsafe_allow_html=True)

    p.purchase_price = st.number_input(
        "Purchase Price ($)", value=float(p.purchase_price), min_value=0.0, step=5000.0, format="%.0f",
    )
    c1, c2 = st.columns(2)
    p.down_payment_pct = c1.number_input(
        "Down %", value=p.down_payment_pct * 100, min_value=0.0, max_value=100.0, step=1.0,
    ) / 100
    p.closing_costs_pct = c2.number_input(
        "Closing %", value=p.closing_costs_pct * 100, min_value=0.0, max_value=10.0, step=0.1,
    ) / 100

    # ── Property details ──────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Property Details</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    p.bedrooms = int(c1.number_input("Bedrooms", value=int(p.bedrooms), min_value=0, max_value=10, step=1))
    p.sqft = c2.number_input("Sq Ft", value=float(p.sqft), min_value=0.0, step=50.0, format="%.0f")

    # ── Loan ──────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Loan</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    p.loan_rate = c1.number_input(
        "Rate %", value=p.loan_rate * 100, min_value=0.0, max_value=20.0, step=0.05,
    ) / 100
    p.loan_term_years = int(c2.selectbox(
        "Term", [10, 15, 20, 25, 30],
        index=[10, 15, 20, 25, 30].index(p.loan_term_years),
    ))

    # ── Income ────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Income</div>', unsafe_allow_html=True)

    p.monthly_rent = st.number_input(
        "Monthly Rent ($)", value=float(p.monthly_rent), min_value=0.0, step=50.0, format="%.0f",
    )
    p.other_monthly_income = st.number_input(
        "Other Income ($/mo)", value=float(p.other_monthly_income), min_value=0.0, step=25.0, format="%.0f",
        help="Parking, laundry, storage, etc.",
    )

    # ── Fixed Expenses ────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Fixed Expenses</div>', unsafe_allow_html=True)

    if p.property_tax_annual == 0.0 and p.purchase_price > 0:
        p.property_tax_annual = round(p.purchase_price * COOK_COUNTY_TAX_RATE)

    p.property_tax_annual = st.number_input(
        "Property Tax ($/yr)", value=float(p.property_tax_annual), min_value=0.0, step=100.0, format="%.0f",
        help=f"Cook County default: ~{COOK_COUNTY_TAX_RATE*100:.1f}% of purchase price",
    )

    if p.insurance_annual == 0.0 and p.purchase_price > 0:
        p.insurance_annual = round(p.purchase_price * 0.005)

    p.insurance_annual = st.number_input(
        "Insurance ($/yr)", value=float(p.insurance_annual), min_value=0.0, step=50.0, format="%.0f",
    )
    p.hoa_monthly = st.number_input(
        "HOA ($/mo)", value=float(p.hoa_monthly), min_value=0.0, step=25.0, format="%.0f",
    )

    c1, c2 = st.columns(2)
    p.maintenance_pct = c1.number_input(
        "Maintenance %/yr", value=p.maintenance_pct * 100, min_value=0.0, max_value=5.0, step=0.1,
        help="% of purchase price/year for repairs",
    ) / 100
    p.vacancy_rate = c2.number_input(
        "Vacancy %", value=p.vacancy_rate * 100, min_value=0.0, max_value=50.0, step=1.0,
    ) / 100

    p.property_mgmt_pct = st.number_input(
        "Mgmt Fee % of rent", value=p.property_mgmt_pct * 100, min_value=0.0, max_value=20.0, step=1.0,
        help="0 if self-managing",
    ) / 100

    # ── Utilities ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Utilities</div>', unsafe_allow_html=True)

    p.landlord_pays_utilities = st.toggle(
        "Landlord pays utilities",
        value=p.landlord_pays_utilities,
        help="If on, electric + gas + water are added to expenses. "
             "Most Chicago leases are tenant-pays for electric/gas; water is often landlord-paid.",
    )

    if p.landlord_pays_utilities:
        auto_util = st.button("⚡ Auto-estimate from bedrooms", use_container_width=True)
        if auto_util:
            ue = estimate_utilities(p.bedrooms)
            p.electric_monthly = ue["electric_monthly"]
            p.gas_monthly = ue["gas_monthly"]
            p.water_monthly = ue["water_monthly"]
            st.caption(ue["utility_note"])
            st.session_state.properties[selected_idx] = p

        c1, c2, c3 = st.columns(3)
        p.electric_monthly = c1.number_input(
            "Electric $/mo", value=float(p.electric_monthly), min_value=0.0, step=5.0, format="%.0f",
            help=f"ComEd ~${COMED_RATE_PER_KWH}/kWh",
        )
        p.gas_monthly = c2.number_input(
            "Gas $/mo", value=float(p.gas_monthly), min_value=0.0, step=5.0, format="%.0f",
            help=f"People's Gas ~${PEOPLES_GAS_RATE_PER_THERM}/therm",
        )
        p.water_monthly = c3.number_input(
            "Water $/mo", value=float(p.water_monthly), min_value=0.0, step=5.0, format="%.0f",
            help=f"Chicago city estimate ~${CHICAGO_WATER_MONTHLY:.0f}/mo",
        )
    else:
        # Show reference estimates even if tenant-pays (helps with all-in pricing decisions)
        if p.bedrooms > 0:
            ue = estimate_utilities(p.bedrooms)
            with st.expander("📊 Utility reference estimates (tenant-pays)"):
                st.caption(
                    f"**{p.bedrooms}BR unit estimates** (not in your expenses — tenant pays)\n\n"
                    f"- ComEd (electric): **${ue['electric_monthly']:.0f}/mo** "
                    f"({ue['electric_kwh_est']} kWh × ${COMED_RATE_PER_KWH}/kWh)\n"
                    f"- People's Gas: **${ue['gas_monthly']:.0f}/mo** "
                    f"({ue['gas_therms_est']} therms × ${PEOPLES_GAS_RATE_PER_THERM}/therm)\n"
                    f"- Water/sewer: **${CHICAGO_WATER_MONTHLY:.0f}/mo** (city estimate — often landlord-paid)\n\n"
                    f"Showing tenant utility costs helps justify rent pricing for all-inclusive listings."
                )
        p.electric_monthly = 0.0
        p.gas_monthly = 0.0
        p.water_monthly = 0.0

    # ── Projections ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Projections</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    p.annual_appreciation_pct = c1.number_input(
        "Appreciation %/yr", value=p.annual_appreciation_pct * 100,
        min_value=-5.0, max_value=20.0, step=0.1,
    ) / 100
    p.annual_rent_growth_pct = c2.number_input(
        "Rent growth %/yr", value=p.annual_rent_growth_pct * 100,
        min_value=-5.0, max_value=20.0, step=0.1,
    ) / 100

    c1, c2 = st.columns(2)
    p.hold_years = int(c1.number_input(
        "Hold (years)", value=int(p.hold_years), min_value=1, max_value=40, step=1,
    ))
    p.selling_costs_pct = c2.number_input(
        "Selling costs %", value=p.selling_costs_pct * 100,
        min_value=0.0, max_value=15.0, step=0.5,
    ) / 100

    st.session_state.properties[selected_idx] = p


# ── Compute all results ───────────────────────────────────────────────────────

properties = st.session_state.properties
results: list = [(p, analyze(p)) for p in properties]
active = [(p, m) for p, m in results if p.purchase_price > 0]

st.title("Real Estate Investment Analyzer")

tab_compare, tab_detail, tab_charts, tab_mc = st.tabs(["📊 Comparison", "🔍 Detail View", "📈 Charts", "🎲 Monte Carlo"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

with tab_compare:
    if not active:
        st.info("Enter a purchase price for at least one property to see analysis.")
    else:
        rows = []
        for p, m in results:
            if p.purchase_price == 0:
                continue
            irr_str = fmt_pct(m.irr) if m.irr is not None else "N/A"
            rows.append({
                "Property": p.name,
                "Address": p.address or "—",
                "Purchase Price": fmt_usd(p.purchase_price),
                "Total Cash In": fmt_usd(m.total_cash_invested),
                "LTV": fmt_pct(m.ltv, 1),
                "Monthly Mortgage": fmt_usd(m.monthly_mortgage),
                "Break-Even Rent": fmt_usd(m.break_even_rent),
                "Monthly Rent": fmt_usd(p.monthly_rent),
                "1% Rule": "✅ Pass" if m.one_pct_rule else "❌ Fail",
                "Monthly Cash Flow": fmt_usd(m.monthly_cash_flow),
                "Annual Cash Flow": fmt_usd(m.annual_cash_flow),
                "Cap Rate": fmt_pct(m.cap_rate),
                "Cash-on-Cash": fmt_pct(m.cash_on_cash_return),
                "GRM": f"{m.grm:.1f}×" if m.grm else "—",
                "DSCR": f"{m.dscr:.2f}" if m.dscr else "—",
                "Break-Even Ratio": fmt_pct(m.break_even_ratio, 1),
                "Depreciation/yr": fmt_usd(m.depreciation_annual),
                "Depr Tax Shield/yr": fmt_usd(m.depreciation_tax_shield_annual) if p.tax_bracket > 0 else "—",
                "Yr-1 Principal Paydown": fmt_usd(m.yr1_principal_paydown),
                f"IRR ({p.hold_years}yr)": irr_str,
                "Equity Yr 5": fmt_usd(m.equity_year_5),
                "Equity Yr 10": fmt_usd(m.equity_year_10),
                "Ann. Return Yr 5": fmt_pct(m.annualized_return_year_5),
                "Ann. Return Yr 10": fmt_pct(m.annualized_return_year_10),
            })

        df = pd.DataFrame(rows).set_index("Property")
        st.dataframe(df.T, use_container_width=True)

        # ── Scorecard ─────────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Scorecard")
        st.caption("🟢 Good  🟡 Marginal  🔴 Caution — general guidelines, not absolutes")

        score_cols = st.columns(len(active))
        for col, (p, m) in zip(score_cols, active):
            with col:
                st.markdown(f"**{p.name}**")
                checks = [
                    (rating(m.cap_rate, 4, 6), f"Cap Rate {fmt_pct(m.cap_rate)}"),
                    (rating(m.cash_on_cash_return, 5, 8), f"CoC {fmt_pct(m.cash_on_cash_return)}"),
                    (rating(m.monthly_cash_flow, 0, 200), f"Cash Flow {fmt_usd(m.monthly_cash_flow)}/mo"),
                    (rating(m.dscr, 1.1, 1.25), f"DSCR {m.dscr:.2f}"),
                    (rating(m.grm, 15, 10, reverse=True), f"GRM {m.grm:.1f}×"),
                    (rating(m.break_even_ratio, 75, 85, reverse=True), f"Break-Even {fmt_pct(m.break_even_ratio, 1)}"),
                    ("✅" if m.one_pct_rule else "❌", f"1% Rule ({fmt_usd(p.monthly_rent)}/{fmt_usd(p.purchase_price)})"),
                ]
                for dot, label in checks:
                    st.markdown(f"{dot} {label}")

                st.markdown("")
                st.markdown(f"**Break-even rent:** {fmt_usd(m.break_even_rent)}/mo")
                if p.monthly_rent > 0:
                    cushion = p.monthly_rent - m.break_even_rent
                    css = "positive" if cushion > 0 else "negative"
                    sign = "+" if cushion > 0 else ""
                    st.markdown(f"Rent cushion: `{sign}{fmt_usd(cushion)}`")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DETAIL VIEW
# ══════════════════════════════════════════════════════════════════════════════

with tab_detail:
    if not active:
        st.info("Enter a purchase price to see detailed analysis.")
    else:
        detail_idx = st.selectbox(
            "Select property",
            options=[i for i, (p, _) in enumerate(results) if p.purchase_price > 0],
            format_func=lambda i: results[i][0].name,
        )
        p, m = results[detail_idx]

        # Row 1: Capital / Cash Flow / Returns
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown('<div class="section-header">Capital Required</div>', unsafe_allow_html=True)
            st.markdown(metric_card("Purchase Price", fmt_usd(p.purchase_price)), unsafe_allow_html=True)
            st.markdown(metric_card("Down Payment", fmt_usd(m.down_payment),
                                    sub=f"{p.down_payment_pct*100:.0f}% down"), unsafe_allow_html=True)
            st.markdown(metric_card("Closing Costs", fmt_usd(m.closing_costs),
                                    sub=f"{p.closing_costs_pct*100:.1f}%"), unsafe_allow_html=True)
            st.markdown(metric_card("Total Cash In", fmt_usd(m.total_cash_invested)), unsafe_allow_html=True)
            st.markdown(metric_card("Loan Amount", fmt_usd(m.loan_amount),
                                    sub=f"LTV {m.ltv:.1f}%"), unsafe_allow_html=True)
            st.markdown(metric_card("Monthly Mortgage", fmt_usd(m.monthly_mortgage),
                                    sub=f"{p.loan_rate*100:.2f}% / {p.loan_term_years}yr"), unsafe_allow_html=True)
            st.markdown(metric_card("Yr-1 Principal Paydown", fmt_usd(m.yr1_principal_paydown),
                                    "positive", "Equity built via loan paydown in yr 1"), unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="section-header">Monthly Cash Flow</div>', unsafe_allow_html=True)
            st.markdown(metric_card("Gross Rent", fmt_usd(m.gross_monthly_income)), unsafe_allow_html=True)
            st.markdown(metric_card("Eff. Income (after vacancy)", fmt_usd(m.effective_gross_income),
                                    "neutral", f"{p.vacancy_rate*100:.0f}% vacancy assumed"), unsafe_allow_html=True)
            st.markdown(metric_card("Mortgage", f"−{fmt_usd(m.monthly_mortgage)}", "negative"), unsafe_allow_html=True)
            st.markdown(metric_card("Operating Expenses", f"−{fmt_usd(m.monthly_operating_expenses)}", "negative"), unsafe_allow_html=True)

            if p.landlord_pays_utilities and m.utility_monthly_total > 0:
                st.markdown(metric_card("  └ Utilities", f"−{fmt_usd(m.utility_monthly_total)}", "negative",
                                        f"Electric ${p.electric_monthly:.0f} · Gas ${p.gas_monthly:.0f} · Water ${p.water_monthly:.0f}"), unsafe_allow_html=True)

            cf_css = color_class(m.monthly_cash_flow)
            st.markdown(metric_card("Net Cash Flow", fmt_usd(m.monthly_cash_flow), cf_css), unsafe_allow_html=True)
            st.markdown(metric_card("Annual Cash Flow", fmt_usd(m.annual_cash_flow), cf_css), unsafe_allow_html=True)
            st.markdown(metric_card("Break-Even Rent", fmt_usd(m.break_even_rent), "neutral",
                                    "Monthly rent for $0 cash flow"), unsafe_allow_html=True)

        with c3:
            st.markdown('<div class="section-header">Returns & Ratios</div>', unsafe_allow_html=True)
            cap_css = "positive" if m.cap_rate >= 5 else "negative" if m.cap_rate < 4 else "neutral"
            st.markdown(metric_card("Cap Rate", fmt_pct(m.cap_rate), cap_css), unsafe_allow_html=True)
            coc_css = "positive" if m.cash_on_cash_return >= 6 else "negative" if m.cash_on_cash_return < 3 else "neutral"
            st.markdown(metric_card("Cash-on-Cash Return", fmt_pct(m.cash_on_cash_return), coc_css), unsafe_allow_html=True)
            st.markdown(metric_card("GRM", f"{m.grm:.1f}×" if m.grm else "—",
                                    "positive" if m.grm and m.grm < 12 else "negative" if m.grm and m.grm > 18 else "neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("DSCR", f"{m.dscr:.2f}" if m.dscr else "—",
                                    "positive" if m.dscr >= 1.2 else "negative" if m.dscr < 1.0 else "neutral",
                                    "≥1.25 preferred by lenders"), unsafe_allow_html=True)
            irr_str = fmt_pct(m.irr) if m.irr is not None else "N/A"
            st.markdown(metric_card(f"IRR ({p.hold_years}yr hold)", irr_str,
                                    "positive" if (m.irr or 0) >= 8 else "neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("1% Rule", "✅ Pass" if m.one_pct_rule else "❌ Fail",
                                    "positive" if m.one_pct_rule else "negative",
                                    f"{fmt_usd(p.monthly_rent)} ÷ {fmt_usd(p.purchase_price)} = {p.monthly_rent/p.purchase_price*100:.2f}%" if p.purchase_price > 0 else ""), unsafe_allow_html=True)

        st.divider()

        # Row 2: Expenses / Equity / Depreciation + Return Decomp
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown('<div class="section-header">Monthly Expense Breakdown</div>', unsafe_allow_html=True)
            items = {
                "Property Tax": p.property_tax_annual / 12,
                "Insurance": p.insurance_annual / 12,
                "HOA": p.hoa_monthly,
                "Maintenance": (p.purchase_price * p.maintenance_pct) / 12,
                "Vacancy Loss": m.gross_monthly_income * p.vacancy_rate,
                "Mgmt Fee": m.gross_monthly_income * p.property_mgmt_pct,
            }
            if p.landlord_pays_utilities:
                items["Electric"] = p.electric_monthly
                items["Gas"] = p.gas_monthly
                items["Water"] = p.water_monthly

            for label, val in items.items():
                if val > 0:
                    st.markdown(f"`{fmt_usd(val):>10}` &nbsp; {label}", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown(f"**50% Rule opex estimate:** {fmt_usd(m.fifty_pct_rule_opex)}/mo")
            st.caption(
                f"Your actual opex (ex-debt): {fmt_usd(m.monthly_operating_expenses)}/mo — "
                f"{'above' if m.monthly_operating_expenses > m.fifty_pct_rule_opex else 'below'} the 50% rule estimate."
            )

        with c2:
            st.markdown('<div class="section-header">Equity & Appreciation</div>', unsafe_allow_html=True)
            for yr in [1, 3, 5, 10, 15, 20]:
                fv = p.purchase_price * (1 + p.annual_appreciation_pct) ** yr
                eq = fv - remaining_balance(m.loan_amount, p.loan_rate, p.loan_term_years, yr * 12)
                st.markdown(metric_card(f"Year {yr}", fmt_usd(eq), "positive",
                                        f"Value: {fmt_usd(fv)}"), unsafe_allow_html=True)

        with c3:
            st.markdown('<div class="section-header">Depreciation</div>', unsafe_allow_html=True)
            st.markdown(metric_card(
                "Annual Depreciation", fmt_usd(m.depreciation_annual),
                sub=f"Building value {fmt_usd(p.purchase_price*(1-p.land_value_pct))} ÷ 27.5 yrs"
            ), unsafe_allow_html=True)
            st.caption(
                "Depreciation is a non-cash deduction that can offset rental income on your taxes. "
                "Consult a CPA for actual tax benefit based on your situation."
            )

            st.markdown('<div class="section-header" style="margin-top:20px">Return Decomposition</div>', unsafe_allow_html=True)
            st.caption(f"Sources of return over {p.hold_years}-year hold:")
            decomp = {
                "Cash Flow": m.return_from_cash_flow,
                "Appreciation": m.return_from_appreciation,
                "Loan Paydown": m.return_from_paydown,
                "Less: Selling Costs": m.return_from_selling_costs,
            }
            for label, val in decomp.items():
                css = color_class(val)
                sign = "+" if val > 0 else ""
                st.markdown(metric_card(label, f"{sign}{fmt_usd(val)}", css), unsafe_allow_html=True)
            total = sum(decomp.values())
            st.markdown(metric_card("Total Profit", fmt_usd(total), color_class(total)), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CHARTS
# ══════════════════════════════════════════════════════════════════════════════

with tab_charts:
    if not active:
        st.info("Enter purchase prices to see charts.")
    else:
        names = [p.name for p, _ in active]
        colors = px.colors.qualitative.Set2[:len(names)]

        # ── Key return metrics bar chart ──────────────────────────────────────
        fig = make_subplots(
            rows=1, cols=3,
            subplot_titles=["Cap Rate %", "Cash-on-Cash Return %", "IRR %"],
        )
        for i, ((p, m), color) in enumerate(zip(active, colors)):
            fig.add_trace(go.Bar(x=[p.name], y=[m.cap_rate], marker_color=color, showlegend=False), row=1, col=1)
            fig.add_trace(go.Bar(x=[p.name], y=[m.cash_on_cash_return], marker_color=color, showlegend=False), row=1, col=2)
            fig.add_trace(go.Bar(x=[p.name], y=[m.irr if m.irr else 0], marker_color=color, showlegend=i == 0), row=1, col=3)

        for col, thresh in [(1, 5), (2, 8), (3, 10)]:
            fig.add_hline(y=thresh, line_dash="dash", line_color="rgba(255,200,0,0.5)", row=1, col=col)

        fig.update_layout(height=320, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                          font_color="#e8eaf6", bargap=0.35)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Yellow dashed = common benchmark thresholds")

        st.divider()

        # ── Monthly cash flow waterfall ───────────────────────────────────────
        st.subheader("Monthly Cash Flow Breakdown")
        cf_cols = st.columns(len(active))
        for col, (p, m) in zip(cf_cols, active):
            with col:
                labels = ["Gross Rent", "Vacancy", "Mortgage", "Tax", "Insurance", "HOA",
                          "Maintenance", "Mgmt"]
                values = [
                    m.gross_monthly_income,
                    -m.gross_monthly_income * p.vacancy_rate,
                    -m.monthly_mortgage,
                    -p.property_tax_annual / 12,
                    -p.insurance_annual / 12,
                    -p.hoa_monthly,
                    -(p.purchase_price * p.maintenance_pct) / 12,
                    -m.gross_monthly_income * p.property_mgmt_pct,
                ]
                if p.landlord_pays_utilities and m.utility_monthly_total > 0:
                    labels.append("Utilities")
                    values.append(-m.utility_monthly_total)

                labels.append("Net CF")
                values.append(m.monthly_cash_flow)
                measure = ["relative"] * (len(labels) - 1) + ["total"]

                fig2 = go.Figure(go.Waterfall(
                    x=labels, y=values, measure=measure,
                    connector={"line": {"color": "#2d3250"}},
                    increasing={"marker": {"color": "#4caf73"}},
                    decreasing={"marker": {"color": "#e05c6c"}},
                    totals={"marker": {"color": "#4caf73" if m.monthly_cash_flow >= 0 else "#e05c6c"}},
                    texttemplate="%{y:$,.0f}", textposition="outside",
                ))
                fig2.update_layout(
                    title=p.name, height=430,
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font_color="#e8eaf6", font_size=11, showlegend=False,
                    xaxis={"tickangle": -35},
                    margin={"t": 40, "b": 10, "l": 10, "r": 10},
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.divider()

        # ── Return decomposition stacked bar ──────────────────────────────────
        st.subheader(f"Return Decomposition at Hold Period")
        fig3 = go.Figure()
        components = [
            ("Cash Flow", [m.return_from_cash_flow for _, m in active], "#4caf73"),
            ("Appreciation", [m.return_from_appreciation for _, m in active], "#5c88da"),
            ("Loan Paydown", [m.return_from_paydown for _, m in active], "#9c6fe4"),
            ("Selling Costs", [m.return_from_selling_costs for _, m in active], "#e05c6c"),
        ]
        for label, vals, color in components:
            fig3.add_trace(go.Bar(name=label, x=names, y=vals, marker_color=color))

        fig3.update_layout(
            barmode="relative", height=380,
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font_color="#e8eaf6", yaxis_tickformat="$,.0f",
            legend={"bgcolor": "#1e2030"},
        )
        st.plotly_chart(fig3, use_container_width=True)

        st.divider()

        # ── Equity buildup over 30 years ──────────────────────────────────────
        st.subheader("Equity Buildup Over 30 Years")
        fig4 = go.Figure()
        years = list(range(0, 31))
        for (p, m), color in zip(active, colors):
            equities = [
                p.purchase_price * (1 + p.annual_appreciation_pct) ** yr
                - remaining_balance(m.loan_amount, p.loan_rate, p.loan_term_years, yr * 12)
                for yr in years
            ]
            fig4.add_trace(go.Scatter(
                x=years, y=equities, name=p.name, mode="lines",
                line={"color": color, "width": 2.5},
                hovertemplate="%{x}yr: $%{y:,.0f}<extra>" + p.name + "</extra>",
            ))
        fig4.update_layout(
            height=360, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font_color="#e8eaf6", xaxis_title="Year", yaxis_title="Equity ($)",
            yaxis_tickformat="$,.0f", legend={"bgcolor": "#1e2030"}, hovermode="x unified",
        )
        st.plotly_chart(fig4, use_container_width=True)

        st.divider()

        # ── Annual cash flow projection ───────────────────────────────────────
        st.subheader("Annual Cash Flow Projection (with rent growth)")
        fig5 = go.Figure()
        for (p, m), color in zip(active, colors):
            cfs = []
            rent = p.monthly_rent
            other = p.other_monthly_income
            for yr in range(1, 31):
                gross = (rent + other) * (1 - p.vacancy_rate)
                opex = (
                    p.property_tax_annual / 12
                    + p.insurance_annual / 12
                    + p.hoa_monthly
                    + (p.purchase_price * p.maintenance_pct) / 12
                    + (rent + other) * p.property_mgmt_pct
                    + m.utility_monthly_total
                )
                cfs.append((gross - m.monthly_mortgage - opex) * 12)
                rent *= (1 + p.annual_rent_growth_pct)
                other *= (1 + p.annual_rent_growth_pct)
            fig5.add_trace(go.Scatter(
                x=list(range(1, 31)), y=cfs, name=p.name, mode="lines+markers",
                line={"color": color, "width": 2}, marker={"size": 3},
                hovertemplate="Yr %{x}: $%{y:,.0f}/yr<extra>" + p.name + "</extra>",
            ))
        fig5.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.25)")
        fig5.update_layout(
            height=340, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font_color="#e8eaf6", xaxis_title="Year", yaxis_title="Annual Cash Flow ($)",
            yaxis_tickformat="$,.0f", legend={"bgcolor": "#1e2030"}, hovermode="x unified",
        )
        st.plotly_chart(fig5, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MONTE CARLO
# ══════════════════════════════════════════════════════════════════════════════

_DARK = "#0e1117"
_CARD = "#1e2030"

def _fan_traces(years, data_by_year, color_hex, name, showlegend=True):
    """Return Plotly traces for a fan chart (p5/p25/p50/p75/p95 bands)."""
    pcts = {p: np.percentile(data_by_year, p, axis=0) for p in (5, 25, 50, 75, 95)}
    rgb = tuple(int(color_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    traces = []

    def rgba(a): return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{a})"

    # Outer band p5–p95
    traces.append(go.Scatter(
        x=years, y=pcts[95], mode="lines", line={"width": 0},
        showlegend=False, hoverinfo="skip",
    ))
    traces.append(go.Scatter(
        x=years, y=pcts[5], fill="tonexty", mode="lines", line={"width": 0},
        fillcolor=rgba(0.12), showlegend=False, hoverinfo="skip",
    ))
    # Inner band p25–p75
    traces.append(go.Scatter(
        x=years, y=pcts[75], mode="lines", line={"width": 0},
        showlegend=False, hoverinfo="skip",
    ))
    traces.append(go.Scatter(
        x=years, y=pcts[25], fill="tonexty", mode="lines", line={"width": 0},
        fillcolor=rgba(0.28), showlegend=False, hoverinfo="skip",
    ))
    # Median
    traces.append(go.Scatter(
        x=years, y=pcts[50], mode="lines", name=f"{name} (median)",
        line={"color": color_hex, "width": 2.5},
        showlegend=showlegend,
        hovertemplate=f"Yr %{{x}}: $%{{y:,.0f}}<extra>{name} median</extra>",
    ))
    return traces


with tab_mc:
    if not active:
        st.info("Enter a purchase price in the sidebar to run simulations.")
    else:
        # ── Simulation controls ───────────────────────────────────────────────
        st.subheader("Simulation Parameters")
        st.caption(
            "Each simulation samples a different appreciation rate, rent growth, vacancy, "
            "and maintenance cost from normal distributions around your base-case inputs. "
            "Results show the spread of possible outcomes."
        )

        ctrl_cols = st.columns([1, 1, 1, 1, 1])
        n_sims = ctrl_cols[0].selectbox("Simulations", [500, 1000, 2000, 5000], index=2)
        app_std = ctrl_cols[1].number_input(
            "Appreciation σ %", value=2.5, min_value=0.1, max_value=10.0, step=0.5,
            help="Standard deviation of annual appreciation rate. 2.5% means ~68% of trials fall within ±2.5% of your base case.",
        )
        rent_std = ctrl_cols[2].number_input(
            "Rent Growth σ %", value=1.5, min_value=0.1, max_value=8.0, step=0.5,
        )
        vacancy_std = ctrl_cols[3].number_input(
            "Vacancy σ %", value=2.5, min_value=0.1, max_value=15.0, step=0.5,
        )
        maint_std = ctrl_cols[4].number_input(
            "Maintenance σ %", value=0.2, min_value=0.0, max_value=2.0, step=0.1,
            help="Standard deviation of annual maintenance % of purchase price.",
        )

        run_btn = st.button("▶  Run Simulation", type="primary", use_container_width=False)

        if run_btn or "mc_results" in st.session_state:
            if run_btn:  # noqa: SIM102
                params = MCParams(
                    n_simulations=int(n_sims),
                    appreciation_std=app_std / 100,
                    rent_growth_std=rent_std / 100,
                    vacancy_std=vacancy_std / 100,
                    maintenance_std=maint_std / 100,
                    seed=42,
                )
                with st.spinner(f"Running {n_sims:,} simulations…"):
                    st.session_state.mc_results = {
                        p.name: run_simulation(p, params)
                        for p, _ in active
                    }
                    st.session_state.mc_params_display = {
                        "n": n_sims, "app_std": app_std,
                        "rent_std": rent_std, "vacancy_std": vacancy_std,
                    }

            mc_map: dict = st.session_state.mc_results
            # Guard: if properties changed since last run, reuse what we have
            mc_map = {k: v for k, v in mc_map.items() if k in [p.name for p, _ in active]}
            if not mc_map:
                st.warning("No simulation results — click Run Simulation.")
                st.stop()

            colors_mc = px.colors.qualitative.Set2[:len(mc_map)]
            prop_color = dict(zip(mc_map.keys(), colors_mc))

            pd_disp = st.session_state.get("mc_params_display", {})
            st.caption(
                f"Last run: **{pd_disp.get('n', '?'):,} simulations** — "
                f"Appreciation σ {pd_disp.get('app_std', '?')}% · "
                f"Rent Growth σ {pd_disp.get('rent_std', '?')}% · "
                f"Vacancy σ {pd_disp.get('vacancy_std', '?')}%"
            )

            st.divider()

            # ── Probability summary ───────────────────────────────────────────
            st.subheader("Probability Summary")
            prob_cols = st.columns(len(mc_map))
            for col, (prop_name, res) in zip(prob_cols, mc_map.items()):
                with col:
                    st.markdown(f"**{prop_name}**")

                    def prob_card(label, val, good_thresh=0.70):
                        color = "#4caf73" if val >= good_thresh else "#f0a500" if val >= 0.50 else "#e05c6c"
                        return (
                            f'<div class="metric-card">'
                            f'<div class="metric-label">{label}</div>'
                            f'<div class="metric-value" style="color:{color}">{val*100:.0f}%</div>'
                            f'</div>'
                        )

                    st.markdown(prob_card("Positive cash flow Yr 1", res.prob_pos_cf_yr1), unsafe_allow_html=True)
                    st.markdown(prob_card("Positive cash flow Yr 5", res.prob_pos_cf_yr5), unsafe_allow_html=True)
                    st.markdown(prob_card("Profitable at exit", res.prob_profit), unsafe_allow_html=True)
                    st.markdown(prob_card("IRR > 5%", res.prob_irr_gt_5), unsafe_allow_html=True)
                    st.markdown(prob_card("IRR > 8%", res.prob_irr_gt_8, good_thresh=0.60), unsafe_allow_html=True)
                    st.markdown(prob_card("IRR > 10%", res.prob_irr_gt_10, good_thresh=0.50), unsafe_allow_html=True)

            st.divider()

            # ── Percentile table ──────────────────────────────────────────────
            st.subheader("Outcome Distribution (Percentiles)")

            pct_labels = ["P5 (bear)", "P25", "Median", "P75", "P95 (bull)"]

            for prop_name, res in mc_map.items():
                with st.expander(f"📋 {prop_name}", expanded=True):
                    summary = res.summary()
                    rows_pct = []
                    for metric, pct_dict in summary.items():
                        vals = list(pct_dict.values())
                        is_money = "$" in metric
                        is_pct = "%" in metric
                        def fmt(v):
                            if not np.isfinite(v):
                                return "N/A"
                            if is_money:
                                return fmt_usd(v)
                            if is_pct:
                                return fmt_pct(v)
                            return f"{v:.2f}"
                        rows_pct.append({"Metric": metric, **dict(zip(pct_labels, [fmt(v) for v in vals]))})

                    df_pct = pd.DataFrame(rows_pct).set_index("Metric")
                    st.dataframe(df_pct, use_container_width=True)

            st.divider()

            # ── IRR distribution histogram ────────────────────────────────────
            st.subheader("IRR Distribution")
            fig_irr = go.Figure()
            for prop_name, res in mc_map.items():
                valid = res.irr_pct[np.isfinite(res.irr_pct)]
                fig_irr.add_trace(go.Histogram(
                    x=valid, name=prop_name,
                    nbinsx=60,
                    marker_color=prop_color[prop_name],
                    opacity=0.75,
                    hovertemplate="IRR: %{x:.1f}%<br>Count: %{y}<extra>" + prop_name + "</extra>",
                ))
                # Mark median and base-case
                med = float(np.median(valid)) if len(valid) else 0
                fig_irr.add_vline(
                    x=med, line_dash="dash", line_color=prop_color[prop_name],
                    annotation_text=f"{prop_name} median: {med:.1f}%",
                    annotation_position="top right",
                )

            # Benchmark lines
            for thresh, label in [(5, "5%"), (8, "8%"), (10, "10%")]:
                fig_irr.add_vline(
                    x=thresh, line_dash="dot", line_color="rgba(255,200,0,0.4)",
                    annotation_text=label, annotation_position="top left",
                )

            fig_irr.update_layout(
                barmode="overlay", height=360,
                paper_bgcolor=_DARK, plot_bgcolor=_DARK,
                font_color="#e8eaf6",
                xaxis_title="IRR (%)", yaxis_title="Count",
                legend={"bgcolor": _CARD}, bargap=0.02,
            )
            st.plotly_chart(fig_irr, use_container_width=True)

            st.divider()

            # ── Total return distribution ─────────────────────────────────────
            st.subheader("Total Return Distribution at Exit")
            fig_ret = go.Figure()
            for prop_name, res in mc_map.items():
                fig_ret.add_trace(go.Histogram(
                    x=res.total_return / 1000,  # in $K
                    name=prop_name,
                    nbinsx=60,
                    marker_color=prop_color[prop_name],
                    opacity=0.75,
                    hovertemplate="Return: $%{x:.0f}K<br>Count: %{y}<extra>" + prop_name + "</extra>",
                ))
                med_k = float(np.median(res.total_return)) / 1000
                fig_ret.add_vline(
                    x=med_k, line_dash="dash", line_color=prop_color[prop_name],
                    annotation_text=f"${med_k:.0f}K",
                    annotation_position="top right",
                )

            fig_ret.add_vline(x=0, line_dash="solid", line_color="rgba(255,255,255,0.3)")
            fig_ret.update_layout(
                barmode="overlay", height=340,
                paper_bgcolor=_DARK, plot_bgcolor=_DARK,
                font_color="#e8eaf6",
                xaxis_title="Total Return ($K)", yaxis_title="Count",
                legend={"bgcolor": _CARD}, bargap=0.02,
            )
            st.plotly_chart(fig_ret, use_container_width=True)

            st.divider()

            # ── Equity fan chart ──────────────────────────────────────────────
            st.subheader("Equity Fan Chart (30-Year Horizon)")
            st.caption("Bands: outer = P5–P95, inner = P25–P75, line = median")
            years_axis = list(range(1, 31))

            fig_eq = go.Figure()
            for i, (prop_name, res) in enumerate(mc_map.items()):
                color = prop_color[prop_name]
                for trace in _fan_traces(years_axis, res.equity_by_year, color, prop_name, showlegend=True):
                    fig_eq.add_trace(trace)

            fig_eq.update_layout(
                height=420, paper_bgcolor=_DARK, plot_bgcolor=_DARK,
                font_color="#e8eaf6",
                xaxis_title="Year", yaxis_title="Equity ($)",
                yaxis_tickformat="$,.0f",
                legend={"bgcolor": _CARD}, hovermode="x unified",
            )
            st.plotly_chart(fig_eq, use_container_width=True)

            st.divider()

            # ── Annual cash flow fan chart ────────────────────────────────────
            st.subheader("Annual Cash Flow Fan Chart (30-Year Horizon)")
            fig_cf = go.Figure()
            for prop_name, res in mc_map.items():
                color = prop_color[prop_name]
                for trace in _fan_traces(years_axis, res.cf_annual_by_year, color, prop_name):
                    fig_cf.add_trace(trace)

            fig_cf.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.25)")
            fig_cf.update_layout(
                height=400, paper_bgcolor=_DARK, plot_bgcolor=_DARK,
                font_color="#e8eaf6",
                xaxis_title="Year", yaxis_title="Annual Cash Flow ($)",
                yaxis_tickformat="$,.0f",
                legend={"bgcolor": _CARD}, hovermode="x unified",
            )
            st.plotly_chart(fig_cf, use_container_width=True)

            # ── Scatter: IRR vs Total Return ──────────────────────────────────
            if len(mc_map) > 0:
                st.divider()
                st.subheader("IRR vs Total Return — Scatter")
                st.caption("Each dot is one simulated outcome. Helps visualize risk/reward tradeoffs between properties.")
                fig_sc = go.Figure()
                for prop_name, res in mc_map.items():
                    mask = np.isfinite(res.irr_pct)
                    sample_idx = np.random.default_rng(0).choice(np.where(mask)[0], size=min(800, mask.sum()), replace=False)
                    fig_sc.add_trace(go.Scatter(
                        x=res.irr_pct[sample_idx],
                        y=res.total_return[sample_idx] / 1000,
                        mode="markers",
                        name=prop_name,
                        marker={"color": prop_color[prop_name], "size": 4, "opacity": 0.45},
                        hovertemplate="IRR: %{x:.1f}%<br>Return: $%{y:.0f}K<extra>" + prop_name + "</extra>",
                    ))
                fig_sc.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.2)")
                fig_sc.add_vline(x=0, line_dash="dot", line_color="rgba(255,255,255,0.2)")
                fig_sc.update_layout(
                    height=380, paper_bgcolor=_DARK, plot_bgcolor=_DARK,
                    font_color="#e8eaf6",
                    xaxis_title="IRR (%)", yaxis_title="Total Return ($K)",
                    legend={"bgcolor": _CARD},
                )
                st.plotly_chart(fig_sc, use_container_width=True)


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Estimates only — not financial advice. "
    "Cook County tax default: ~1.8% of purchase price. "
    "ComEd rate: $0.1393/kWh. People's Gas: $0.647/therm. "
    "Verify all figures with your lender, CPA, and tax assessor before making investment decisions."
)
