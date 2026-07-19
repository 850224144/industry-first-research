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

For offline development, the adapter accepts an injected byte fetcher; see
`tests/test_eastmoney.py`.
