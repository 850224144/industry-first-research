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

The discovery snapshot also contains a derived `opportunity_discovery` view. It preserves the four
dimensions (`downside_protection`, `inflection_evidence`, `profit_convexity`, `expectation_gap`),
the three clocks, hard-gate results, missing evidence, candidate state, and rejection records.
Missing LIGHT evidence remains `NOT_EVALUABLE` rather than becoming a rejection. This thin layer
reuses the existing radar, company-pool, and screening results; it does not load full-market company
data or create an investment conclusion or simulation record.

For a manually assembled four-dimension evidence package, evaluate one candidate or a bounded scan:

```text
python -m industry_first_research opportunity-candidate \
  --input data/opportunity_candidate_inputs/<candidate>.json \
  --output-dir data/opportunity_candidates

python -m industry_first_research opportunity-scan \
  --input data/opportunity_candidate_inputs/<scan>.json \
  --output-dir data/opportunity_scans
```

`CANDIDATE` requires passed survival/governance gates, at least two independent leading-signal types
across two normal update cycles, and an expectation gap that is not obviously overpriced.
`REVIEWABLE` additionally requires product/profit-source review, survival stress testing, reverse
valuation, and adversarial review. Empty scans, rejected candidates, and re-entry conditions remain
auditable; no state is an investment conclusion.

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

Initialize the bounded local refresh schedule:

```text
python -m industry_first_research schedule-init --output-dir data/scheduler
```

Plan one local tick, optionally with an imported event list:

```text
python -m industry_first_research schedule-plan \
  --schedule data/scheduler/schedule-default.json \
  --state data/scheduler/state-default.json \
  --events data/scheduler/events.json \
  --now 2026-07-21T09:00:00+08:00
```

The scheduler records `industry_radar_refresh`, `daily_delta_scan`, `event_triggered_scan`,
and `company_pool_refresh`, with idempotent event IDs, bounded capacities, retry metadata,
and degraded/final-failure states. It is read-only and does not create a decision snapshot.
The plan can be invoked by a local macOS `launchd` or cron job. Source handlers remain separate
from scheduling so a source failure can degrade the affected task without changing conclusions.

Execute a saved plan with the existing bounded adapters:

```text
python -m industry_first_research schedule-run \
  --state data/scheduler/state-default.json \
  --plan data/scheduler/<scheduler-plan>.json \
  --output-root data
```

The runner writes radar snapshots, daily delta summaries, event review records, or a bounded LIGHT
company pool. It does not invoke deep company research, modify a thesis, create a decision snapshot,
or place an order.

The daily delta artifact also contains `opportunity_tracking`, which compares the latest two bounded
candidate snapshots, their dimension changes, industry trend observations, queue changes, and affected
modules. Trend or queue movement alone creates a review item and cannot upgrade or downgrade a
candidate; without a candidate snapshot the report explicitly uses `NO_SNAPSHOT`.

For continuous tracking, classify evidence freshness:

```text
python -m industry_first_research freshness \
  --input data/company_supplemental/<supplemental>.json \
  --as-of YYYY-MM-DD
```

Compare two immutable research versions:

```text
python -m industry_first_research compare-versions \
  --previous-pipeline data/company_research_pipelines/<old>.json \
  --current-pipeline data/company_research_pipelines/<new>.json \
  --previous-supplemental data/company_supplemental/<old>.json \
  --current-supplemental data/company_supplemental/<new>.json
```

Check a user-confirmed holding thesis locally:

```text
python -m industry_first_research thesis-check \
  --thesis data/holding_theses/<thesis>.json \
  --supplemental data/company_supplemental/<supplemental>.json \
  --as-of YYYY-MM-DD
```

The tracking reports mark `FRESH`, `REFRESH_DUE`, `EXPIRED`, and future-data blocks, explain
version and field changes, and propose `INTACT / WEAKENING / DAMAGED / BROKEN / EXPIRED` thesis
states. They do not rewrite an old report, commit a thesis status, create a decision snapshot, or
treat price movement alone as thesis failure.

Draft or lock a user-confirmed holding thesis:

```text
python -m industry_first_research thesis-lock \
  --input data/holding_theses/<thesis-input>.json \
  --user-confirmed \
  --output-dir data/holding_theses
```

The lock requires the core thesis, 3-7 testable hypotheses, normal-volatility contract, red lines,
three valuation anchors, timebox, and relative-opportunity comparison. Revisions create a new
version and cannot overwrite the prior locked thesis.

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

Compare local structure, `czsc`, and `chan.py` outputs side by side:

```text
python -m industry_first_research market-structure-compare \
  --input data/market_structure/<input>.json \
  --output-dir data/market_structure_comparisons
```

Each implementation keeps its own version, status, normalized structure fields, and raw-output
hash. Missing optional packages or unconfigured runners are recorded as
`PACKAGE_NOT_INSTALLED` or `RUNNER_NOT_CONFIGURED` without blocking the local result. Different
states become `DIVERGENT` and lower confidence; outputs are never merged into a consensus trading
signal.

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

For a prior pipeline, compare and apply new evidence with:

```text
python -m industry_first_research incremental-update \
  --previous-pipeline data/company_research_pipelines/<pipeline>.json \
  --previous-supplemental data/company_supplemental/<supplemental>.json \
  --evidence data/supplemental_evidence/<new-records>.json \
  --as-of YYYY-MM-DD
```

The update report preserves the old version, classifies evidence changes, records the earliest
affected module and creates a new bounded pipeline version. Evidence IDs are immutable. The
current executor uses a full-chain fallback after impact planning, while keeping the plan
ready for future partial recomputation.

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

After a simulation review is closed, generate a dimensioned research-quality scorecard:

```text
python -m industry_first_research quality-scorecard \
  --input data/decision_snapshots/<decision-snapshot>.json \
  --attribution data/attribution_results/<attribution>.json \
  --research-report data/company_research_reports/<research-report>.json \
  --output-dir data/quality_scorecards
```

The scorecard reviews fact accuracy, state judgment, model assumptions, risk identification,
valuation quality, decision process, and outcome performance separately. It has no total score,
does not use return to prove factual accuracy, and marks missing post-validation as
`NOT_EVALUABLE`. Opportunity-discovery metrics retain empty scans, eliminations, and selection
bias. The scorecard is read-only and cannot alter a locked decision, research conclusion, or
execute a trade.

Combine multiple user-confirmed company operations into a full-cash simulation portfolio:

```text
python -m industry_first_research portfolio-create \
  --input data/simulation_portfolio_inputs/<portfolio-input>.json \
  --decision data/decision_snapshots/<open>.json \
  --decision data/decision_snapshots/<adjust-or-hold>.json \
  --decision data/decision_snapshots/<exit>.json \
  --output-dir data/simulation_portfolios
```

The portfolio only references `LOCKED` company decision snapshots. `ADJUST` quantities are target
quantities and `HOLD` keeps the previous target; the original snapshots remain unchanged. Replay
the portfolio with a dated asset and benchmark package:

```text
python -m industry_first_research portfolio-replay \
  --input data/simulation_portfolios/<simulation-portfolio>.json \
  --outcome data/simulation_portfolio_inputs/<dated-outcome>.json \
  --closed-at YYYY-MM-DD \
  --output-dir data/simulation_portfolio_replays
```

The replay reports daily cash, holdings, equity, dividends, fees, drawdown, portfolio return,
locked-benchmark return, and excess return. Missing operation-date data or observations after
`closed_at` produce `NOT_EVALUABLE`; negative cash under full-cash assumptions produces
`REVIEW_REQUIRED`. This first portfolio ledger is for listed-company full-cash accounting only;
domestic futures continue through the specific-contract daily settlement ledger and are not mixed
with stock returns.

Store immutable original-announcement assets and their version chain:

```text
python -m industry_first_research announcement-asset \
  --input data/announcement_inputs/<announcement>.json \
  --raw-content data/announcement_inputs/<original-file> \
  --output-dir data/announcement_assets
```

The raw file is copied under `raw/`; the manifest retains subject, document type, source,
publication/capture times, parser version, content hash, version, and correction/supplement/
withdrawal relationships. Create a review-only affected-module record:

```text
python -m industry_first_research announcement-impact \
  --input data/announcement_assets/<document>-v<version>.json \
  --research-cutoff YYYY-MM-DDTHH:MM:SS+08:00 \
  --output-dir data/announcement_impacts
```

Announcement assets and impact records update the evidence timeline and review queue only; they
do not overwrite historical research, holding theses, or decision snapshots. A correction published
after the cutoff is never backfilled into pre-cutoff research.

For offline development, the adapter accepts an injected byte fetcher; see
`tests/test_eastmoney.py`.
