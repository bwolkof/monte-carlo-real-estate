**Monte Carlo Real Estate Investment Calculator**





**1 time setup**

install python

https://python.org/

follow prompts from install manager

Run `run.bat` in project files



**Project Build Notes**

Stack: Streamlit (Python) — pure Python, runs locally, great for data/financial tools, no separate frontend needed.



**Features:**

Manual property entry + optional address lookup (best-effort scraping)

Full financial model: mortgage, NOI, cap rate, cash-on-cash return, GRM, DSCR, multi-year IRR

Chicago-aware defaults (Cook County tax estimates, typical expense ratios)

Side-by-side comparison table + Plotly charts

Add/remove unlimited properties



**What's built**

4 files, \~650 lines total:



**File	Purpose**

app.py	Streamlit UI — sidebar editor, 3 tabs

calculator.py	All financial math

fetcher.py	Zillow scraping + Chicago defaults

run.bat	Double-click launcher



**Financial metrics calculated:**



Monthly mortgage, cash flow, NOI

Cap rate, cash-on-cash return, GRM, DSCR, break-even ratio

IRR over your hold period

Equity buildup \& annualized total return at 5yr / 10yr

UI tabs:



**Comparison** — side-by-side table + color-coded scorecard (🟢/🟡/🔴) with benchmarks

Detail View — full breakdown per property with expense waterfall

Charts — cap rate/CoC/IRR bars, monthly cash flow waterfall, 30-year equity buildup, 30-year cash flow projection with rent growth

Chicago-specific defaults: Cook County tax \~1.8% of purchase price, neighborhood rent benchmarks for \~25 neighborhoods (Lincoln Park, Wicker Park, Logan Square, etc.), Illinois insurance estimate \~0.5%.





\--Everything below is the full conversation from developing the tool--





**Updates to Address Lookup, utilities, additional calculations 1**



Address lookup (Zillow → Redfin): Zillow is \~30% reliable — they've heavily fingerprinted scrapers. Redfin is better (\~60-70%) because their autocomplete API is more accessible and property pages embed schema.org JSON-LD. I'll switch to Redfin. Both are "convenience only" — you're right that manual entry from the listing you're already looking at will always be more accurate. I'll keep it but relabel it clearly.



Utilities: No per-address API from ComEd or People's Gas exists publicly. Best approach is static rate tables using their published 2024 rates + bedroom-count usage estimates. I'll add a "landlord pays utilities" toggle — if on, electric/gas/water get added to expenses. Always shows estimates for context even if tenant-pays.



New calculations I'll add:



LTV, break-even rent, 1% rule check, annual depreciation (building value ÷ 27.5 yrs), year-1 principal paydown, 50% rule sanity check, total return decomposition (cash flow vs. appreciation vs. paydown vs. selling costs)

Two things I want to check with you first:



After-tax modeling — depreciation creates a paper loss (\~$9K/yr on a $300K property) that shelters income. Worth adding a marginal tax bracket input so it can show the actual after-tax cash flow? Useful if you're a real estate professional or active participant.

Monte Carlo scenarios — the project is literally named for this. Want randomized appreciation/rent growth distributions to show a probability range of outcomes (e.g. "80% confidence cash flow is positive in yr 5")? This would be a separate tab.





**Updates Continued 2**

Address lookup:



Replaced Zillow (unreliable, heavy bot detection) with Redfin — uses their autocomplete API → property page → schema.org JSON-LD parsing. \~60-70% success on active listings, gracefully reports exactly what it did or didn't pull

Realistic expectation: you're always going to be looking at the listing anyway, so manual entry is the accurate path. The lookup is a time-saver for rough estimates, not a replacement

Utilities:



Neither ComEd nor People's Gas have free per-address APIs — best available approach is their published 2025 rates × typical usage by bedroom count

ComEd: $0.1393/kWh (all-in including delivery + taxes)

People's Gas: $0.647/therm (commodity + distribution, annual avg)

Water/sewer: $48/mo (Chicago city quarterly bill ÷ 3)

New "Landlord pays utilities" toggle in the sidebar — when on, electric/gas/water flow into expenses and all charts. When off, shows them in a reference expander so you can still use the numbers for all-inclusive rent pricing decisions

"Auto-estimate from bedrooms" button fills the three fields

New calculations:



Break-even rent — the monthly rent where cash flow hits exactly $0, shown alongside actual rent with a cushion/gap callout

1% Rule pass/fail — shows the actual ratio (Chicago rarely clears this, but good benchmark)

LTV — loan-to-value, relevant for future refi decisions

Annual depreciation — building value (price × 80%) ÷ 27.5 years; add your marginal tax bracket to get the annual tax shield

Year-1 principal paydown — concrete equity built via debt reduction in year 1

50% rule comparison — your actual opex vs. the 50%-of-gross-rent heuristic, flagged if significantly off

Return decomposition — stacked bar chart + detail cards breaking total return into cash flow / appreciation / loan paydown / selling costs

Still want your call on two things:



After-tax modeling — the depreciation tax bracket input is in there now, but a full model (mortgage interest deduction, passive loss rules, active vs. passive participation) gets complex fast. Worth expanding if you plan to use it for tax planning, or keep it at the depreciation shield only?

Monte Carlo tab — run thousands of simulations with randomized appreciation + rent growth to show probability distributions (e.g. "5th percentile return is -2%, median is 8%, 95th is 14%"). Given the project name this seems intentional — want me to build it?



**Here's what the Monte Carlo tab does (prompted to prioritize over after-tax modeling, can consider in later context)**



Controls

* Simulations: 500 / 1000 / 2000 / 5000
* Four σ sliders: appreciation, rent growth, vacancy, maintenance — all default to sensible Chicago ranges
* "Run Simulation" button — results persist in session state so switching tabs doesn't re-run



Output — for each property, side by side:



Probability cards (color-coded green/yellow/red)

* P(positive cash flow yr 1 and yr 5)
* P(profitable at exit)
* P(IRR > 5%), P(IRR > 8%), P(IRR > 10%) 



Percentile table — P5 / P25 / Median / P75 / P95 for:

IRR, total return, cash flow yr 1/5/10, equity yr 5/10



Distributions — overlaid histograms with median lines and benchmark markers:

* IRR distribution
* Total return distribution ($K)



Fan charts — full 30-year horizon with P5–P95 outer band, P25–P75 inner band, median line:



* Equity fan
* Annual cash flow fan



IRR vs Total Return scatter — 800 sampled points per property, good for seeing whether one property dominates or if there's a risk/reward tradeoff between the two



Tax: kept simple — property tax stays as 1.8% Cook County default with custom override, no income tax modeling added.



