# Industry Radar

The live industry radar has two read-only adapters: Eastmoney's public industry quote
endpoint and Tonghuashun's public industry table.

Cross-source matching uses the versioned explicit registry in
`docs/industry_aliases.v1.json`. An alias match is recorded as `match_method=ALIAS` in the
snapshot and in source metadata; unknown names are not fuzzy-matched.

Run it from the repository root:

```text
python -m industry_first_research radar --source cross --limit 50
```

The command prints an `industry-radar.v1` JSON snapshot and stores the same payload under
`data/radar/<source>-industry-YYYY-MM-DD.json`.

Each item contains the industry code, display name, date, quote signals, source URL, and an
explicit evidence status. A row is `CROSS_VALIDATED` only when both sources have either an
exact normalized name or an explicit versioned alias match, and report the same daily
direction. A conflicting match is `CONFLICTING`; a missing match is `SINGLE_SOURCE`. Both
are marked `INSUFFICIENT` and held out of confirmation screening. The alias registry records
category-level mappings such as Eastmoney's `白酒Ⅱ/白酒Ⅲ` to Tonghuashun's `白酒`; it does
not use fuzzy matching.

When several primary-source hierarchy rows resolve to the same explicit canonical key,
the cross-source adapter keeps the first source row as the representative and records the
duplicate group and collapsed-row counts in metadata. This prevents one investable category
from loading the same company pool more than once while keeping the normalization auditable.

The daily direction itself maps a non-negative change to `CLEARING` and a negative change to
`DETERIORATING`. Even `CROSS_VALIDATED` remains a strength clue only; it does not confirm a
cycle reversal, company quality, valuation, or an investment decision.

The adapter is intentionally bounded to industry rows. It does not download full-market
company data, place orders, connect to broker accounts, or use web AI output as evidence.

For source diagnostics, `--source eastmoney` and `--source tonghuashun` can be run separately.

To summarize repeated cross-source observations, save snapshots on multiple dates and run:

```text
python -m industry_first_research trend --source cross --window 10 --min-observations 3
```

The trend report is review-only. It requires repeated observations, reports mixed or
insufficient evidence explicitly, and never promotes a trend directly into a company pool.

For a selected industry, the next bounded step is the visible company pool:

```text
python -m industry_first_research company-pool --industry-id 881145 --industry-name 电力 --limit 30
```

This reads only the public industry detail table and records `visible_table_only=true` and
`full_industry_membership_loaded=false`. It is a candidate list, not company-level research.

Use `--with-light-data` to add source-bound company name, main business, reported industry,
and listing market fields. Missing pages or fields are recorded as `UNAVAILABLE` or `PARTIAL`;
the adapter does not infer or fill missing facts.

The end-to-end read-only discovery command is:

```text
python -m industry_first_research discover --radar-limit 50 --max-selected-industries 3 --company-pool-size 10
```

`--radar-limit` controls the bounded number of industry rows scanned by each source;
`--company-pool-size` controls the number of company candidates loaded per selected
industry. They are intentionally independent. The command runs cross-source industry
selection first, resolves source-specific industry IDs, then loads bounded company pools
and LIGHT facts only for selected industries.

With `--with-light-data`, the company pool first reads Tonghuashun LIGHT fields. If
`listing_market` is missing, it performs a bounded Eastmoney company-survey lookup and
accepts the value only when the returned company code matches the candidate. The field
source is retained as `field_sources`; no market is inferred from the stock code.

To screen a saved company-pool snapshot for data completeness:

```text
python -m industry_first_research screen --input data/company_pools/tonghuashun-company-pool-881145-YYYY-MM-DD.json --expected-industry 电力 --alias-file docs/industry_aliases.v1.json
```

The result is `PASS`, `REVIEW`, or `INSUFFICIENT` for data quality only. It does not estimate
value, rank investment merit, or create a trading decision. Industry consistency uses the
same explicit alias registry as the cross-source radar, so hierarchy labels such as `白酒`
and `白酒Ⅱ` can match only when the source-specific mapping is declared.

Turn a saved screen into a traceable review queue with:

```text
python -m industry_first_research queue --input data/company_screens/<screen>.json
```

The output uses `company-candidate-queue.v1`. `PASS` becomes `WATCH`, `REVIEW` remains
`REVIEW`, and missing or contradictory evidence becomes `INSUFFICIENT` or `REJECTED`.
LIGHT data never becomes `CANDIDATE` by itself. Every queue item retains its rule version,
source, date, reasons, blockers, and evidence gaps. The queue is review-only and cannot
place orders or produce an investment conclusion.

Build a supplemental evidence report from a queue and a manually prepared JSON record list:

```text
python -m industry_first_research supplemental \
  --input data/candidate_queues/<queue>.json \
  --evidence data/supplemental_evidence/<records>.json \
  --required-field company_scope \
  --required-field reporting_scope \
  --required-field key_products \
  --required-field key_risks
```

Every evidence record keeps its company, field, value, source, date, evidence tier, and
verification status. Tier `B` requires two source references; tiers `C` and `D` do not count
as verified evidence. The report only describes supplemental coverage as `READY`, `PARTIAL`,
`INSUFFICIENT`, or `BLOCKED`; it preserves the original candidate state and cannot promote
a company or create an investment conclusion.

When a LIGHT profile has a field-level gap such as `LISTING_MARKET_MISSING`, create a
blank, traceable manual evidence template before collecting the source-backed value:

```text
python -m industry_first_research evidence-template \
  --input data/candidate_queues/<queue>.json \
  --company-id 300317 \
  --field listing_market
```

For a full company deep-research template, use `--profile deep-company`; it reuses the
required fields declared by the existing product, application, transmission, industry,
cycle, competition, survival, and valuation gates. Additional `--field` values may be
appended. The records remain blank until manually verified.

The template is intentionally blank. Fill a record only after manual verification and
keep `company_id`, `field`, `source`, `as_of`, `evidence_tier`, and
`verification_status`. Do not infer `listing_market` from a stock code or market
convention. Web AI alone is not sufficient. Pass the completed template JSON to the
`supplemental` command, then rerun `readiness` and `quick-research`.

Derive a researchability gate from the supplemental report:

```text
python -m industry_first_research readiness \
  --input data/company_supplemental/<report>.json
```

`READY` permits standard research, `PARTIAL` permits only degraded research,
`INSUFFICIENT` is screen-only, and `BLOCKED` pauses deep research. The gate preserves
the original candidate state and cannot promote a candidate or create an investment
conclusion.

Create an evidence-only quick research snapshot:

```text
python -m industry_first_research quick-research \
  --readiness data/company_readiness/<readiness>.json \
  --supplemental data/company_supplemental/<supplemental>.json
```

The snapshot separates verified facts, unverified claims, and unknowns. It is `LOCAL_ONLY`,
does not include financial analysis or valuation, and preserves the candidate state.

Build the next design-stage gate, the evidence-only product and profit-source profile:

```text
python -m industry_first_research product-profile \
  --input data/company_supplemental/<supplemental>.json
```

This report covers product list, application, customer purchase reasons, system layer,
criticality, substitution, competitors, market state, profit sources, lifecycle,
validation, and the product-to-revenue/profit/cash-flow bridge. Missing or unverified
fields remain explicit. `READY` is required before application transmission, cycle,
survival, valuation, or decision modules; the command itself does not perform those
analyses or promote a candidate.

Once the product profile is `READY`, build the explicit product-to-application mapping:

```text
python -m industry_first_research application-mapping \
  --input data/company_product_profiles/<product-profile>.json
```

The mapping requires evidence for the product, application, end market, demand driver,
customer validation, order or shipment/revenue evidence, company supply capability,
competition, and transmission state. It preserves missing evidence and blocks without a
`READY` product profile; it does not infer demand, revenue, valuation, or an investment conclusion.

After a `READY` mapping, build the demand-transmission gate:

```text
python -m industry_first_research demand-transmission \
  --input data/company_application_mappings/<application-mapping>.json
```

The gate distinguishes concept linkage, technical feasibility, customer qualification,
orders, revenue, profit/cash-flow validation, and competitive validation. Unverified new
business remains an upside option and cannot enter a base case, valuation, or investment conclusion.

After the transmission gate is `READY`, build the industry situation report:

```text
python -m industry_first_research industry-situation \
  --input data/company_demand_transmission/<demand-transmission>.json
```

This report records long-term demand, value-chain profit distribution, supply/demand,
inventory, price, utilization, competition, policy/technology/overseas factors, cycle
stage, three key industry variables, and reversal validation conditions. It does not
confirm an industrial reversal or perform survival, valuation, or investment analysis.

For applicable cyclical or supply/demand-driven industries, build the cycle-reversal report:

```text
python -m industry_first_research cycle-reversal \
  --input data/company_industry_situations/<industry-situation>.json
```

The report distinguishes `PRICE_REBOUND`, `TURNING_POINT_CANDIDATE`, and
`INDUSTRIAL_REVERSAL_CONFIRMED`, and requires matching demand, effective supply,
inventory, price, capacity-exit, and industry-cash-flow evidence. Non-cyclical industries
are explicitly marked `NOT_APPLICABLE`; the command does not perform survival, valuation,
or investment analysis.

After the cycle evidence gate, build the company business-model and competitive-position report:

```text
python -m industry_first_research competitive-position \
  --input data/company_cycle_reversals/<cycle-reversal>.json
```

The report covers business model, revenue structure, cost, technology, customers, channels,
capital, market share, and a competition matrix for cost, performance, yield, certification,
delivery, customers, scale, and substitution route. Missing evidence remains explicit; the
command does not infer a moat or perform survival, valuation, or investment analysis.

After the competitive-position evidence gate, run survival and stress testing:

```text
python -m industry_first_research survival-analysis \
  --input data/company_competitive_positions/<competitive-position>.json
```

The gate requires six scenarios: prolonged weakness, refinancing failure, operating shock,
asset impairment, technology replacement, and governance shock. Each scenario retains cash
runway, debt gap, minimum cash, capex reduction, asset-sale actions, financing dependency,
and survival outcome. `self_funded`, `refinancing_dependent`, and
`external_support_dependent` remain separate; missing evidence does not produce a survivor
or reversal-beneficiary conclusion.

After the survival gate, build the three-scenario valuation and reverse-valuation framework:

```text
python -m industry_first_research valuation-scenarios \
  --input data/company_survival_analysis/<survival-analysis>.json
```

The framework requires bear, base, and bull scenarios, current-price timing, historical
financials, cycle-center profit, net debt and dilution, implied assumptions,
evidence-backed assumptions, model assumptions, base-case exclusions, and sensitivity.
It is an auditable framework only: no target price or investment conclusion is generated,
and unverified themes or peak-cycle profit cannot enter the base case.

Market structure is an optional timing aid. Lock the subject, cutoff, timeframe,
adjustment, and OHLCV snapshot before running:

```text
python -m industry_first_research market-structure \
  --input data/market_structure/<input>.json
```

The snapshot reports multi-timeframe trend, volatility, range position, confirmation, and
repaint risk only. It emits no buy/sell signal or automatic order; continuous futures series
must also retain their main-contract, roll, stitching, and adjustment rules.

After valuation and optional market-structure inputs are prepared, run adversarial review:

```text
python -m industry_first_research adversarial-review \
  --input data/company_valuation_scenarios/<valuation-scenarios>.json \
  --market-structure data/market_structure/<snapshot>.json
```

The review checks future information, evidence conflicts, counterevidence and invalidators,
cash-flow conversion, base-case exclusions, external-AI independence, market-size-to-profit
leaks, valuation boundaries, market-structure signal leakage, and candidate-state changes.
It returns `PASS`, `REVIEW`, or `BLOCKED` without rewriting facts or producing an investment conclusion.

After adversarial review, assemble the structured company research report and tracking checklist:

```text
python -m industry_first_research research-report \
  --input data/company_adversarial_reviews/<adversarial-review>.json
```

The report keeps industry situation, company quality, product/transmission, survival,
valuation framework, counterevidence, and follow-up checks separate. Only a passing audit
with an eligible candidate is marked `REVIEWABLE`; no directional conclusion, target price,
or decision snapshot is created, and simulation requires user confirmation.

To run the complete bounded deep-research chain from one supplemental evidence package:

```text
python -m industry_first_research research-pipeline \
  --input data/company_supplemental/<supplemental>.json
```

It runs product profile, application mapping, demand transmission, industry situation,
cycle, competitive position, survival, valuation, adversarial review, and structured report
in order. The output keeps every stage snapshot under `stages` and provides `stage_summary`.
Missing evidence remains `PARTIAL`, `INSUFFICIENT`, or `BLOCKED`; the pipeline never promotes
a `WATCH` item or creates an investment conclusion.

After explicit user confirmation, create the immutable simulation decision snapshot:

```text
python -m industry_first_research decision-snapshot \
  --input data/company_research_reports/<research-report>.json \
  --decision data/decision_inputs/<decision>.json \
  --user-confirmed
```

The snapshot locks the subject, cutoff, action, direction, price/quantity/capital assumptions,
reasons, risks, triggers, invalidators, review date, and benchmark as `LOCKED`. Futures
snapshots must bind a specific contract rather than a continuous series; revisions create a
new version, and no broker order or execution is performed.

For offline development, the adapter accepts an injected byte fetcher; see
`tests/test_eastmoney.py`.
