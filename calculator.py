"""
Core real estate financial calculations.
All monetary inputs in USD. Rates as decimals (e.g. 0.07 = 7%).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PropertyInputs:
    name: str = "Property"
    address: str = ""

    # Purchase
    purchase_price: float = 0.0
    down_payment_pct: float = 0.20
    closing_costs_pct: float = 0.03

    # Loan
    loan_rate: float = 0.07
    loan_term_years: int = 30

    # Property details
    bedrooms: int = 1
    sqft: float = 0.0

    # Income
    monthly_rent: float = 0.0
    other_monthly_income: float = 0.0  # parking, laundry, etc.

    # Expenses (monthly unless noted)
    property_tax_annual: float = 0.0
    insurance_annual: float = 0.0
    hoa_monthly: float = 0.0
    maintenance_pct: float = 0.01      # % of purchase price per year
    property_mgmt_pct: float = 0.0     # % of gross rent
    vacancy_rate: float = 0.05

    # Utilities (only counted as expense if landlord pays)
    landlord_pays_utilities: bool = False
    electric_monthly: float = 0.0
    gas_monthly: float = 0.0
    water_monthly: float = 0.0

    # Depreciation
    land_value_pct: float = 0.20       # land is ~20% of value → not depreciable
    tax_bracket: float = 0.0           # marginal rate for depreciation tax shield (0 = skip)

    # Projections
    annual_appreciation_pct: float = 0.03
    annual_rent_growth_pct: float = 0.02
    hold_years: int = 10
    selling_costs_pct: float = 0.06


@dataclass
class PropertyMetrics:
    # Capital
    down_payment: float = 0.0
    closing_costs: float = 0.0
    total_cash_invested: float = 0.0
    ltv: float = 0.0                   # loan-to-value %

    # Loan
    loan_amount: float = 0.0
    monthly_mortgage: float = 0.0
    annual_debt_service: float = 0.0
    yr1_principal_paydown: float = 0.0

    # Income
    gross_monthly_income: float = 0.0
    effective_gross_income: float = 0.0

    # Expenses
    utility_monthly_total: float = 0.0
    monthly_operating_expenses: float = 0.0
    annual_operating_expenses: float = 0.0

    # Core metrics
    noi: float = 0.0
    monthly_cash_flow: float = 0.0
    annual_cash_flow: float = 0.0

    # Sanity checks
    break_even_rent: float = 0.0
    one_pct_rule: bool = False         # monthly_rent / price >= 1%
    fifty_pct_rule_opex: float = 0.0   # 50%-rule estimated opex for comparison

    # Ratios
    cap_rate: float = 0.0
    cash_on_cash_return: float = 0.0
    grm: float = 0.0
    dscr: float = 0.0
    break_even_ratio: float = 0.0      # (opex + debt) / gross income %
    expense_ratio: float = 0.0

    # Depreciation
    depreciation_annual: float = 0.0
    depreciation_tax_shield_annual: float = 0.0  # 0 if tax_bracket not set

    # Return decomposition (at hold_years)
    return_from_cash_flow: float = 0.0
    return_from_appreciation: float = 0.0
    return_from_paydown: float = 0.0
    return_from_selling_costs: float = 0.0

    # Projections
    irr: Optional[float] = None
    equity_year_5: float = 0.0
    equity_year_10: float = 0.0
    total_return_year_5: float = 0.0
    total_return_year_10: float = 0.0
    annualized_return_year_5: float = 0.0
    annualized_return_year_10: float = 0.0


def monthly_mortgage_payment(principal: float, annual_rate: float, years: int) -> float:
    if annual_rate == 0:
        return principal / (years * 12)
    r = annual_rate / 12
    n = years * 12
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def remaining_balance(principal: float, annual_rate: float, years: int, months_paid: int) -> float:
    if annual_rate == 0:
        return max(0.0, principal - (principal / (years * 12)) * months_paid)
    r = annual_rate / 12
    n = years * 12
    if months_paid >= n:
        return 0.0
    return principal * ((1 + r) ** n - (1 + r) ** months_paid) / ((1 + r) ** n - 1)


def annual_principal_paid(principal: float, annual_rate: float, years: int, year_n: int) -> float:
    start = remaining_balance(principal, annual_rate, years, (year_n - 1) * 12)
    end = remaining_balance(principal, annual_rate, years, year_n * 12)
    return start - end


def calculate_irr(cash_flows: list) -> Optional[float]:
    if not cash_flows or cash_flows[0] >= 0:
        return None
    try:
        guess = 0.1
        for _ in range(1000):
            npv = sum(cf / (1 + guess) ** i for i, cf in enumerate(cash_flows))
            d_npv = sum(-i * cf / (1 + guess) ** (i + 1) for i, cf in enumerate(cash_flows))
            if abs(d_npv) < 1e-10:
                break
            new_guess = guess - npv / d_npv
            if abs(new_guess - guess) < 1e-8:
                return new_guess
            guess = new_guess
        return guess if -1 < guess < 10 else None
    except Exception:
        return None


def analyze(p: PropertyInputs) -> PropertyMetrics:
    m = PropertyMetrics()

    # ── Capital ───────────────────────────────────────────────────────────────
    m.down_payment = p.purchase_price * p.down_payment_pct
    m.closing_costs = p.purchase_price * p.closing_costs_pct
    m.total_cash_invested = m.down_payment + m.closing_costs
    m.loan_amount = p.purchase_price - m.down_payment
    if p.purchase_price > 0:
        m.ltv = (m.loan_amount / p.purchase_price) * 100

    # ── Mortgage ──────────────────────────────────────────────────────────────
    m.monthly_mortgage = monthly_mortgage_payment(m.loan_amount, p.loan_rate, p.loan_term_years)
    m.annual_debt_service = m.monthly_mortgage * 12
    m.yr1_principal_paydown = annual_principal_paid(m.loan_amount, p.loan_rate, p.loan_term_years, 1)

    # ── Income ────────────────────────────────────────────────────────────────
    m.gross_monthly_income = p.monthly_rent + p.other_monthly_income
    m.effective_gross_income = m.gross_monthly_income * (1 - p.vacancy_rate)

    # ── Utilities ─────────────────────────────────────────────────────────────
    if p.landlord_pays_utilities:
        m.utility_monthly_total = p.electric_monthly + p.gas_monthly + p.water_monthly
    else:
        m.utility_monthly_total = 0.0

    # ── Operating expenses ────────────────────────────────────────────────────
    monthly_tax = p.property_tax_annual / 12
    monthly_insurance = p.insurance_annual / 12
    monthly_maintenance = (p.purchase_price * p.maintenance_pct) / 12
    monthly_mgmt = m.gross_monthly_income * p.property_mgmt_pct
    monthly_vacancy_loss = m.gross_monthly_income * p.vacancy_rate

    # OpEx excludes debt service and vacancy (vacancy handled via effective income)
    fixed_monthly_opex = (
        monthly_tax
        + monthly_insurance
        + p.hoa_monthly
        + monthly_maintenance
        + monthly_mgmt
        + m.utility_monthly_total
    )
    m.monthly_operating_expenses = fixed_monthly_opex + monthly_vacancy_loss
    m.annual_operating_expenses = m.monthly_operating_expenses * 12

    # ── Cash flow ─────────────────────────────────────────────────────────────
    m.monthly_cash_flow = m.effective_gross_income - m.monthly_mortgage - fixed_monthly_opex
    m.annual_cash_flow = m.monthly_cash_flow * 12

    # ── NOI (excludes debt service) ───────────────────────────────────────────
    m.noi = (m.effective_gross_income - fixed_monthly_opex) * 12

    # ── Sanity checks ─────────────────────────────────────────────────────────
    if p.purchase_price > 0 and p.monthly_rent > 0:
        m.one_pct_rule = (p.monthly_rent / p.purchase_price) >= 0.01

    # Break-even rent: solve for rent where monthly CF = 0
    # rent*(1-vacancy-mgmt) = mortgage + fixed_non_mgmt_opex + utilities
    denom = 1 - p.vacancy_rate - p.property_mgmt_pct
    fixed_non_mgmt = (
        m.monthly_mortgage
        + monthly_tax
        + monthly_insurance
        + p.hoa_monthly
        + monthly_maintenance
        + m.utility_monthly_total
    )
    m.break_even_rent = fixed_non_mgmt / denom if denom > 0 else 0.0

    # 50% rule: rough estimate that opex ≈ 50% of gross rent (no debt service)
    m.fifty_pct_rule_opex = m.gross_monthly_income * 0.50

    # ── Ratios ────────────────────────────────────────────────────────────────
    if p.purchase_price > 0:
        m.cap_rate = (m.noi / p.purchase_price) * 100
        m.grm = p.purchase_price / (m.gross_monthly_income * 12) if m.gross_monthly_income > 0 else 0.0

    if m.total_cash_invested > 0:
        m.cash_on_cash_return = (m.annual_cash_flow / m.total_cash_invested) * 100

    if m.noi > 0 and m.annual_debt_service > 0:
        m.dscr = m.noi / m.annual_debt_service

    gross_annual = m.gross_monthly_income * 12
    if gross_annual > 0:
        m.break_even_ratio = ((m.annual_operating_expenses + m.annual_debt_service) / gross_annual) * 100
        m.expense_ratio = (m.annual_operating_expenses / gross_annual) * 100

    # ── Depreciation ──────────────────────────────────────────────────────────
    building_value = p.purchase_price * (1 - p.land_value_pct)
    m.depreciation_annual = building_value / 27.5
    if p.tax_bracket > 0:
        m.depreciation_tax_shield_annual = m.depreciation_annual * p.tax_bracket

    # ── Projection helpers ────────────────────────────────────────────────────
    def year_n_fv(n: int) -> float:
        return p.purchase_price * (1 + p.annual_appreciation_pct) ** n

    def year_n_equity(n: int) -> float:
        bal = remaining_balance(m.loan_amount, p.loan_rate, p.loan_term_years, n * 12)
        return year_n_fv(n) - bal

    def year_n_sale_proceeds(n: int) -> float:
        fv = year_n_fv(n)
        bal = remaining_balance(m.loan_amount, p.loan_rate, p.loan_term_years, n * 12)
        return fv - fv * p.selling_costs_pct - bal

    def cumulative_cash_flow(n: int) -> float:
        total = 0.0
        rent = p.monthly_rent
        other = p.other_monthly_income
        for yr in range(n):
            gross = (rent + other) * (1 - p.vacancy_rate)
            opex = (
                monthly_tax
                + monthly_insurance
                + p.hoa_monthly
                + monthly_maintenance
                + (rent + other) * p.property_mgmt_pct
                + m.utility_monthly_total
            )
            total += (gross - m.monthly_mortgage - opex) * 12
            rent *= (1 + p.annual_rent_growth_pct)
            other *= (1 + p.annual_rent_growth_pct)
        return total

    def total_return(n: int) -> float:
        return cumulative_cash_flow(n) + year_n_sale_proceeds(n) - m.total_cash_invested

    m.equity_year_5 = year_n_equity(5)
    m.equity_year_10 = year_n_equity(10)
    m.total_return_year_5 = total_return(5)
    m.total_return_year_10 = total_return(10)

    if m.total_cash_invested > 0:
        r5 = (m.total_return_year_5 + m.total_cash_invested) / m.total_cash_invested
        r10 = (m.total_return_year_10 + m.total_cash_invested) / m.total_cash_invested
        m.annualized_return_year_5 = (r5 ** (1 / 5) - 1) * 100 if r5 > 0 else 0.0
        m.annualized_return_year_10 = (r10 ** (1 / 10) - 1) * 100 if r10 > 0 else 0.0

    # ── Return decomposition at hold_years ────────────────────────────────────
    n = p.hold_years
    fv_at_n = year_n_fv(n)
    total_paydown = m.loan_amount - remaining_balance(m.loan_amount, p.loan_rate, p.loan_term_years, n * 12)
    m.return_from_cash_flow = cumulative_cash_flow(n)
    m.return_from_appreciation = fv_at_n - p.purchase_price
    m.return_from_paydown = total_paydown - m.down_payment  # equity above initial down payment
    m.return_from_selling_costs = -fv_at_n * p.selling_costs_pct

    # ── IRR ───────────────────────────────────────────────────────────────────
    cash_flows = [-m.total_cash_invested]
    rent = p.monthly_rent
    other = p.other_monthly_income
    for yr in range(p.hold_years):
        gross = (rent + other) * (1 - p.vacancy_rate)
        opex = (
            monthly_tax
            + monthly_insurance
            + p.hoa_monthly
            + monthly_maintenance
            + (rent + other) * p.property_mgmt_pct
            + m.utility_monthly_total
        )
        cf = (gross - m.monthly_mortgage - opex) * 12
        rent *= (1 + p.annual_rent_growth_pct)
        other *= (1 + p.annual_rent_growth_pct)
        if yr == p.hold_years - 1:
            cf += year_n_sale_proceeds(p.hold_years)
        cash_flows.append(cf)

    irr_val = calculate_irr(cash_flows)
    m.irr = irr_val * 100 if irr_val is not None else None

    return m
