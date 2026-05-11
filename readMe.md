**Real Estate Investment Analyzer — Feature Overview**

What it is: A local Python app for evaluating and comparing Chicago investment properties before you buy. All data stays on your machine.



**Sidebar — Property Editor**

Add as many properties as you want. For each one:



Redfin Lookup — paste an address and it attempts to auto-fill price, beds, sqft, HOA, and estimated rent. Works \~60-70% of the time on active listings; always verify against the actual listing.

Manual entry — the reliable path. Fill in purchase price, loan terms, rent, and expenses directly from your listing sheet.

Utilities toggle — if you're buying a property where the landlord pays utilities, flip this on and hit "Auto-estimate from bedrooms." It fills ComEd + People's Gas + water estimates based on published 2025 rates. If tenant pays, it still shows the estimates in a reference panel so you can price all-inclusive rent correctly.

Property tax — defaults to Cook County's \~1.8% of purchase price. Override with the actual number if you have it.

Projections — set your expected appreciation, rent growth, hold period, and selling costs. These drive the long-term charts and IRR.



**Tab 1 — Comparison**

Side-by-side table across all your properties covering every key metric. Below it, a scorecard with green/yellow/red ratings on:



Cap rate, cash-on-cash return, monthly cash flow, DSCR, GRM, break-even ratio, 1% rule

Break-even rent — the exact monthly rent where you hit $0 cash flow, plus how much cushion your actual rent provides above it



**Tab 2 — Detail View**

Deep dive on one property at a time:



Full capital breakdown (down payment, closing costs, LTV, mortgage)

Monthly cash flow waterfall — every dollar in and out

Returns: cap rate, CoC, GRM, DSCR, IRR, 1% rule with the actual ratio shown

Expense breakdown with 50% rule comparison

Equity table at years 1, 3, 5, 10, 15, 20

Annual depreciation (the non-cash deduction that can offset rental income on your taxes — talk to a CPA for your specific benefit)

Return decomposition — breaks your total profit at exit into four buckets: cash flow earned, appreciation, loan paydown, minus selling costs



**Tab 3 — Charts**

Key metrics bar chart (cap rate, CoC, IRR) with benchmark lines

Monthly cash flow waterfall per property

Stacked return decomposition bar (what's driving the profit)

30-year equity buildup

30-year annual cash flow projection with rent growth



**Tab 4 — Monte Carlo**

The risk analysis tab. Rather than one fixed projection, it runs thousands of simulations where appreciation, rent growth, vacancy, and maintenance all vary randomly around your base assumptions.



Set your uncertainty: dial in how wide the σ (spread) is for each variable — tighter if you're confident in the market, wider if you're not.



Hit Run. For each property you get:



Probability summary — direct answers to the questions that matter: what's the chance you're cash-flow positive in year 1? year 5? what's the chance you clear 8% IRR? what's the chance you make money at all?

Percentile table — bear case (P5), typical downside (P25), median, typical upside (P75), bull case (P95) across IRR, total return, cash flow, and equity

IRR histogram — see the full shape of the return distribution, not just one number

Total return histogram — same for dollar profit at exit

Equity fan chart — 30-year equity range, where the bands show how wide outcomes could be

Cash flow fan chart — same for annual cash flow over time; shows when most scenarios go positive

IRR vs. Return scatter — if you're comparing two properties, this shows whether one dominates or if there's a genuine risk/reward tradeoff between them



**What it doesn't do**

Not financial or tax advice — consult a CPA for depreciation benefits and your actual tax situation

Redfin lookup is best-effort, not guaranteed

Utility estimates are Chicago averages — actual bills vary by building age, insulation, tenant behavior

Appreciation and rent growth assumptions are yours to set; garbage in, garbage out

