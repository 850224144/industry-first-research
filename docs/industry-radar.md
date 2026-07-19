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
explicit evidence status. A row is `CROSS_VALIDATED` only when both sources have an exact
normalized industry-name match and report the same daily direction. A conflicting match is
`CONFLICTING`; a missing match is `SINGLE_SOURCE`. Both are marked `INSUFFICIENT` and held
out of confirmation screening.

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
python -m industry_first_research discover --max-selected-industries 3 --company-pool-size 10
```

It runs cross-source industry selection first, resolves source-specific industry IDs, then
loads bounded company pools and LIGHT facts only for selected industries.

With `--with-light-data`, the company pool first reads Tonghuashun LIGHT fields. If
`listing_market` is missing, it performs a bounded Eastmoney company-survey lookup and
accepts the value only when the returned company code matches the candidate. The field
source is retained as `field_sources`; no market is inferred from the stock code.

To screen a saved company-pool snapshot for data completeness:

```text
python -m industry_first_research screen --input data/company_pools/tonghuashun-company-pool-881145-YYYY-MM-DD.json --expected-industry 电力
```

The result is `PASS`, `REVIEW`, or `INSUFFICIENT` for data quality only. It does not estimate
value, rank investment merit, or create a trading decision.

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

For offline development, the adapter accepts an injected byte fetcher; see
`tests/test_eastmoney.py`.
