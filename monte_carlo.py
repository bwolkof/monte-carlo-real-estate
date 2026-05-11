"""
Monte Carlo simulation for real estate investment returns.

Uses vectorized NumPy operations so 5,000 simulations run in < 2 seconds.
Each trial samples: appreciation rate, rent growth, vacancy, and maintenance
from normal distributions centered on the property's base-case assumptions.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from calculator import PropertyInputs, remaining_balance, monthly_mortgage_payment


@dataclass
class MCParams:
    n_simulations: int = 2000
    appreciation_std: float = 0.025   # σ — 1 std dev swing in annual appreciation
    rent_growth_std: float = 0.015    # σ — annual rent growth
    vacancy_std: float = 0.025        # σ — vacancy rate
    maintenance_std: float = 0.002    # σ — maintenance % of price
    seed: Optional[int] = 42          # None = different result each run


@dataclass
class MCResults:
    n: int
    hold_years: int
    total_cash_invested: float

    # Per-simulation arrays (n,)
    irr_pct: np.ndarray         # NaN where Newton-Raphson didn't converge
    total_return: np.ndarray    # dollars profit at hold_years
    cf_yr1: np.ndarray          # annual cash flow in year 1
    cf_yr5: np.ndarray          # annual cash flow in year 5 (or yr hold if shorter)

    # Fan chart data (n, 30) — full 30-year horizon regardless of hold period
    equity_by_year: np.ndarray
    cf_annual_by_year: np.ndarray

    # Probability estimates
    prob_pos_cf_yr1: float
    prob_pos_cf_yr5: float
    prob_irr_gt_5: float
    prob_irr_gt_8: float
    prob_irr_gt_10: float
    prob_profit: float          # P(total_return > 0)

    def pct(self, arr: np.ndarray, levels=(5, 25, 50, 75, 95)) -> dict:
        clean = arr[np.isfinite(arr)]
        if len(clean) == 0:
            return {p: float("nan") for p in levels}
        return {p: float(np.percentile(clean, p)) for p in levels}

    def summary(self) -> dict:
        """Percentile table for all key metrics."""
        lvls = (5, 25, 50, 75, 95)
        yr5 = min(4, self.hold_years - 1)
        yr10 = min(9, self.hold_years - 1)
        return {
            "IRR (%)": self.pct(self.irr_pct, lvls),
            "Total Return ($)": self.pct(self.total_return, lvls),
            "Cash Flow Yr 1 ($/yr)": self.pct(self.cf_annual_by_year[:, 0], lvls),
            "Cash Flow Yr 5 ($/yr)": self.pct(self.cf_annual_by_year[:, yr5], lvls),
            "Cash Flow Yr 10 ($/yr)": self.pct(self.cf_annual_by_year[:, yr10], lvls),
            "Equity Yr 5 ($)": self.pct(self.equity_by_year[:, 4], lvls),
            "Equity Yr 10 ($)": self.pct(self.equity_by_year[:, 9], lvls),
        }


# ── Vectorized Newton-Raphson IRR ─────────────────────────────────────────────

def _vectorized_irr(cf_matrix: np.ndarray, max_iter: int = 300) -> np.ndarray:
    """
    Solve IRR for each row of cf_matrix simultaneously.
    cf_matrix shape: (n_sim, n_periods)  — col 0 is the negative initial outflow.
    Returns decimal IRRs (not percent); NaN where no convergence.
    """
    n, T = cf_matrix.shape
    t = np.arange(T, dtype=np.float64)
    rates = np.full(n, 0.10, dtype=np.float64)

    for _ in range(max_iter):
        r = rates[:, None]                               # (n, 1)
        disc = (1.0 + r) ** t                            # (n, T)
        npv = (cf_matrix / disc).sum(axis=1)             # (n,)
        d_disc = (1.0 + r) ** (t + 1.0)
        d_npv = (-t * cf_matrix / d_disc).sum(axis=1)   # (n,)

        valid = np.abs(d_npv) > 1e-12
        rates[valid] -= npv[valid] / d_npv[valid]
        rates = np.clip(rates, -0.99, 9.0)

    # Verify convergence: final NPV must be near zero
    r = rates[:, None]
    disc = (1.0 + r) ** t
    npv_final = (cf_matrix / disc).sum(axis=1)

    out = rates.copy()
    out[np.abs(npv_final) > 10.0] = np.nan    # didn't converge
    out[(out < -0.99) | (out > 9.0)] = np.nan
    return out


# ── Main simulation ───────────────────────────────────────────────────────────

def run_simulation(p: PropertyInputs, params: MCParams) -> MCResults:
    """Run Monte Carlo simulation. Returns MCResults with all distributions."""
    rng = np.random.default_rng(params.seed)
    n = params.n_simulations

    # ── Deterministic loan values ─────────────────────────────────────────────
    down = p.purchase_price * p.down_payment_pct
    loan = p.purchase_price - down
    closing = p.purchase_price * p.closing_costs_pct
    total_cash = down + closing
    monthly_pmt = monthly_mortgage_payment(loan, p.loan_rate, p.loan_term_years)

    # Fixed monthly opex (does not vary across simulations)
    monthly_tax = p.property_tax_annual / 12
    monthly_ins = p.insurance_annual / 12
    utility = (
        (p.electric_monthly + p.gas_monthly + p.water_monthly)
        if p.landlord_pays_utilities else 0.0
    )
    fixed_opex = monthly_tax + monthly_ins + p.hoa_monthly + utility

    # ── Sample random variables ───────────────────────────────────────────────
    app_rates = rng.normal(p.annual_appreciation_pct, params.appreciation_std, n)
    rent_gr   = rng.normal(p.annual_rent_growth_pct,  params.rent_growth_std,  n)
    vacancy   = np.clip(rng.normal(p.vacancy_rate,    params.vacancy_std,      n), 0.0, 0.60)
    maint_pct = np.clip(rng.normal(p.maintenance_pct, params.maintenance_std,  n), 0.001, 0.06)

    # ── Year axis (1..30) ─────────────────────────────────────────────────────
    years = np.arange(1, 31, dtype=np.float64)   # shape (30,)

    # Remaining loan balances — deterministic for all 30 years
    balances = np.array([
        remaining_balance(loan, p.loan_rate, p.loan_term_years, int(yr) * 12)
        for yr in years
    ])  # shape (30,)

    # Property value: (n, 30)
    values = p.purchase_price * (1.0 + app_rates[:, None]) ** years[None, :]

    # Equity: (n, 30)
    equity = values - balances[None, :]

    # Rent in each year: (n, 30)
    rent_yr  = p.monthly_rent        * (1.0 + rent_gr[:, None]) ** years[None, :]
    other_yr = p.other_monthly_income * (1.0 + rent_gr[:, None]) ** years[None, :]
    gross_yr = rent_yr + other_yr

    # Variable monthly expenses: (n, 30)
    monthly_maint = (p.purchase_price * maint_pct / 12.0)[:, None] * np.ones(30)
    monthly_mgmt  = gross_yr * p.property_mgmt_pct

    # Effective income after vacancy: (n, 30)
    effective = gross_yr * (1.0 - vacancy[:, None])

    # Monthly cash flow → annualized: (n, 30)
    cf_monthly = effective - monthly_pmt - fixed_opex - monthly_maint - monthly_mgmt
    cf_annual  = cf_monthly * 12.0

    # ── IRR over hold_years ───────────────────────────────────────────────────
    hy = min(max(p.hold_years, 1), 30)

    # Terminal sale proceeds at hold year: (n,)
    fv_hold  = p.purchase_price * (1.0 + app_rates) ** hy
    bal_hold = remaining_balance(loan, p.loan_rate, p.loan_term_years, hy * 12)
    sale     = fv_hold - fv_hold * p.selling_costs_pct - bal_hold

    # Build IRR cash flow matrix: (n, hy+1)
    irr_flows = np.zeros((n, hy + 1), dtype=np.float64)
    irr_flows[:, 0]  = -total_cash
    irr_flows[:, 1:] = cf_annual[:, :hy]
    irr_flows[:, hy] += sale

    irr_pct = _vectorized_irr(irr_flows) * 100.0  # convert to percent

    # ── Total return at hold_years ────────────────────────────────────────────
    cum_cf       = cf_annual[:, :hy].sum(axis=1)
    total_return = cum_cf + sale - total_cash

    # ── Probability estimates ─────────────────────────────────────────────────
    valid_irr = irr_pct[np.isfinite(irr_pct)]
    yr5_idx   = min(4, hy - 1)

    return MCResults(
        n=n,
        hold_years=hy,
        total_cash_invested=total_cash,
        irr_pct=irr_pct,
        total_return=total_return,
        cf_yr1=cf_annual[:, 0],
        cf_yr5=cf_annual[:, yr5_idx],
        equity_by_year=equity,
        cf_annual_by_year=cf_annual,
        prob_pos_cf_yr1=float((cf_annual[:, 0] > 0).mean()),
        prob_pos_cf_yr5=float((cf_annual[:, yr5_idx] > 0).mean()),
        prob_irr_gt_5=float((valid_irr > 5).mean()) if len(valid_irr) else 0.0,
        prob_irr_gt_8=float((valid_irr > 8).mean()) if len(valid_irr) else 0.0,
        prob_irr_gt_10=float((valid_irr > 10).mean()) if len(valid_irr) else 0.0,
        prob_profit=float((total_return > 0).mean()),
    )
