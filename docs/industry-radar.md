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

For offline development, the adapter accepts an injected byte fetcher; see
`tests/test_eastmoney.py`.
