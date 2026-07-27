"""Map domestic futures varieties to listed-company product exposures.

The mapper is deliberately evidence-bound.  A company industry label is never
enough to create an exposure: the input must identify a product and an explicit
role such as producer, consumer, processor, or trader.  Numeric transmission
is only calculated when the user supplies the relevant volume, sensitivity,
reference price, and hedge assumptions.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from math import isfinite
from typing import Any


class FuturesCompanyExposureError(ValueError):
    """Raised when a futures-company exposure package is unsafe to map."""


EXPOSURE_INPUT_SCHEMA_VERSION = "futures-company-exposure-input.v1"
EXPOSURE_REPORT_SCHEMA_VERSION = "commodity-company-exposure-report.v1"
RULE_VERSION = "commodity-company-exposure-rules.v1"
FUTURES_REPORT_SCHEMA_VERSION = "futures-fundamentals-report.v1"
PRODUCT_PROFILE_SCHEMA_VERSION = "company-product-profile.v1"

_ROLES = {"PRODUCER", "CONSUMER", "PROCESSOR", "TRADER", "BILATERAL"}
_LINKS = {"REVENUE", "COST", "BOTH", "INVENTORY", "MIXED"}
_STATES = {"VERIFIED", "PARTIAL", "UNVERIFIED", "MISSING", "CONFLICTING"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNVERIFIED"}
_PROFILE_STATES = {"READY", "PARTIAL", "INSUFFICIENT", "BLOCKED", "MISSING"}
_SCOPE_STATES = {"VERIFIED", "PARTIAL", "UNVERIFIED", "MISSING", "CONFLICTING"}


def build_futures_company_exposure_report(
    futures_report: Mapping[str, Any],
    exposure_input: Mapping[str, Any],
    *,
    product_profile_report: Mapping[str, Any] | None = None,
    rule_version: str = RULE_VERSION,
    snapshot_id: str = "",
) -> dict[str, Any]:
    """Map explicit company/product exposures to a futures research report.

    ``exposure_input`` may carry a ``companies`` list with lightweight product
    facts, or the existing ``company-product-profile.v1`` report may be passed
    separately.  The two sources are not merged by guessing: a company and
    product must be explicitly present and product matching is exact after
    whitespace/case normalisation.
    """

    _validate_futures_report(futures_report)
    _validate_input(exposure_input)
    if product_profile_report is not None:
        _validate_product_profile(product_profile_report)
    if not rule_version.strip():
        raise FuturesCompanyExposureError("rule_version must not be empty")

    cutoff = _parse_date(exposure_input["as_of"], "as_of")
    futures_as_of = _parse_date(futures_report["as_of"], "futures_report.as_of")
    if cutoff > futures_as_of:
        raise FuturesCompanyExposureError(
            "exposure as_of cannot exceed futures report as_of"
        )
    if product_profile_report is not None and product_profile_report.get("as_of"):
        profile_as_of = _parse_date(product_profile_report["as_of"], "product_profile.as_of")
        if profile_as_of > cutoff:
            raise FuturesCompanyExposureError(
                "product profile as_of cannot exceed exposure as_of"
            )

    companies = _normalise_companies(
        exposure_input.get("companies"), product_profile_report, cutoff
    )
    exposures = _normalise_exposures(exposure_input.get("exposures"), cutoff)
    futures_context = _futures_context(futures_report)
    expected_variety = str(
        exposure_input.get("variety_id") or futures_report.get("variety_id") or ""
    ).strip()
    if not expected_variety:
        raise FuturesCompanyExposureError("variety_id is required")
    if futures_report.get("variety_id") and expected_variety != str(
        futures_report["variety_id"]
    ).strip():
        raise FuturesCompanyExposureError(
            "exposure variety_id does not match futures report variety_id"
        )

    items = [
        _build_exposure_item(
            exposure,
            companies,
            expected_variety=expected_variety,
            futures_context=futures_context,
            futures_status=str(futures_report.get("status") or "INSUFFICIENT").upper(),
            cutoff=cutoff,
            rule_version=rule_version,
        )
        for exposure in exposures
    ]
    company_views = _build_company_views(items, companies)
    counts = Counter(item["mapping_state"] for item in items)
    report_id = snapshot_id.strip() or str(exposure_input.get("report_id") or "")
    if not report_id:
        report_id = f"{expected_variety}-{exposure_input['as_of']}"
    status = _report_status(
        futures_status=str(futures_report.get("status") or "INSUFFICIENT").upper(),
        items=items,
        expected_count=len(exposures),
    )
    return {
        "schema_version": EXPOSURE_REPORT_SCHEMA_VERSION,
        "report_id": f"commodity-company-exposure-{report_id}",
        "input_schema_version": EXPOSURE_INPUT_SCHEMA_VERSION,
        "input_futures_report_id": str(futures_report.get("report_id") or ""),
        "input_product_profile_id": str(
            product_profile_report.get("report_id") if product_profile_report else ""
        ),
        "as_of": str(exposure_input["as_of"]),
        "research_cutoff": str(exposure_input["as_of"]),
        "source": str(exposure_input.get("source") or ""),
        "source_metadata": exposure_input.get("source_metadata") or {},
        "variety_id": expected_variety,
        "variety_name": str(
            exposure_input.get("variety_name")
            or futures_report.get("variety_name")
            or ""
        ),
        "futures_context": futures_context,
        "company_count": len(company_views),
        "exposure_count": len(items),
        "mapping_state_counts": dict(counts),
        "status": status,
        "items": items,
        "company_views": company_views,
        "policy": {
            "explicit_product_required": True,
            "industry_label_is_not_exposure_evidence": True,
            "exact_product_match_only": True,
            "price_correlation_not_used_as_profit_causality": True,
            "numeric_bridge_requires_explicit_assumptions": True,
            "company_profit_forecast_generated": False,
            "investment_conclusion_generated": False,
            "target_price_generated": False,
            "decision_snapshot_created": False,
            "automatic_order_included": False,
            "read_only": True,
            "review_only": True,
            "execution_enabled": False,
        },
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
    }


def _validate_futures_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise FuturesCompanyExposureError("futures report must be a JSON object")
    if report.get("schema_version") != FUTURES_REPORT_SCHEMA_VERSION:
        raise FuturesCompanyExposureError(
            "input must be futures-fundamentals-report.v1"
        )
    if not str(report.get("as_of") or "").strip():
        raise FuturesCompanyExposureError("futures report as_of is required")
    if not str(report.get("variety_id") or "").strip():
        raise FuturesCompanyExposureError("futures report variety_id is required")


def _validate_input(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise FuturesCompanyExposureError("exposure input must be a JSON object")
    if payload.get("schema_version") != EXPOSURE_INPUT_SCHEMA_VERSION:
        raise FuturesCompanyExposureError(
            "input must be futures-company-exposure-input.v1"
        )
    if not str(payload.get("as_of") or "").strip():
        raise FuturesCompanyExposureError("exposure input as_of is required")
    if payload.get("companies") is not None and not isinstance(
        payload.get("companies"), Sequence
    ):
        raise FuturesCompanyExposureError("companies must be a list")
    if not isinstance(payload.get("exposures"), Sequence) or isinstance(
        payload.get("exposures"), (str, bytes, bytearray)
    ):
        raise FuturesCompanyExposureError("exposures must be a list")


def _validate_product_profile(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise FuturesCompanyExposureError("product profile report must be an object")
    if report.get("schema_version") != PRODUCT_PROFILE_SCHEMA_VERSION:
        raise FuturesCompanyExposureError(
            "product profile must be company-product-profile.v1"
        )
    if not isinstance(report.get("items"), list):
        raise FuturesCompanyExposureError("product profile report has no items list")


def _normalise_companies(
    raw_companies: Any,
    product_profile_report: Mapping[str, Any] | None,
    cutoff: date,
) -> dict[str, dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}
    if product_profile_report is not None:
        for item in product_profile_report["items"]:
            company = _company_from_profile(item, cutoff)
            _add_company(companies, company)
    if raw_companies is not None:
        if not isinstance(raw_companies, Sequence) or isinstance(
            raw_companies, (str, bytes, bytearray)
        ):
            raise FuturesCompanyExposureError("companies must be a list")
        for raw in raw_companies:
            company = _company_from_light_input(raw, cutoff)
            if company["company_id"] in companies:
                companies[company["company_id"]] = _merge_company(
                    companies[company["company_id"]], company
                )
            else:
                _add_company(companies, company)
    return companies


def _company_from_profile(item: Any, cutoff: date) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise FuturesCompanyExposureError("product profile item must be an object")
    company_id = str(item.get("company_id") or "").strip()
    if not company_id:
        raise FuturesCompanyExposureError("product profile item company_id is required")
    fields = item.get("fields") or {}
    if not isinstance(fields, Mapping):
        raise FuturesCompanyExposureError("product profile fields must be an object")
    product_field = fields.get("product_list") or {}
    products = _products_from_values(product_field.get("values"), product_field, cutoff)
    return {
        "company_id": company_id,
        "display_name": str(item.get("display_name") or ""),
        "company_scope_status": str(item.get("scope_state") or "MISSING").upper(),
        "profile_status": str(item.get("product_profile_state") or "MISSING").upper(),
        "products": products,
        "source": "company-product-profile",
        "evidence_ids": _string_list(item.get("evidence_ids")),
    }


def _company_from_light_input(raw: Any, cutoff: date) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise FuturesCompanyExposureError("company must be an object")
    company_id = str(raw.get("company_id") or "").strip()
    if not company_id:
        raise FuturesCompanyExposureError("company_id is required")
    products = raw.get("products")
    if not isinstance(products, Sequence) or isinstance(products, (str, bytes, bytearray)):
        raise FuturesCompanyExposureError(f"company products must be a list: {company_id}")
    normalised_products = []
    for product in products:
        if not isinstance(product, Mapping):
            raise FuturesCompanyExposureError("company product must be an object")
        product_id = str(product.get("product_id") or "").strip()
        product_name = str(product.get("product_name") or product.get("product") or "").strip()
        if not product_id and not product_name:
            raise FuturesCompanyExposureError(
                f"company product requires product_id or product_name: {company_id}"
            )
        _validate_record_dates(product, cutoff, f"companies.{company_id}.products")
        normalised_products.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "status": str(product.get("status") or "UNVERIFIED").upper(),
                "evidence_ids": _string_list(product.get("evidence_ids")),
                "sources": _string_list(product.get("sources", product.get("source"))),
                "as_of": _string_list(product.get("as_of")),
                "revenue_share": product.get("revenue_share"),
                "profit_share": product.get("profit_share"),
            }
        )
    profile_status = str(raw.get("profile_status") or "PARTIAL").upper()
    if profile_status not in _PROFILE_STATES:
        raise FuturesCompanyExposureError(
            f"unsupported company profile_status: {profile_status}"
        )
    scope_status = str(raw.get("company_scope_status") or "UNVERIFIED").upper()
    if scope_status not in _SCOPE_STATES:
        raise FuturesCompanyExposureError(
            f"unsupported company_scope_status: {scope_status}"
        )
    return {
        "company_id": company_id,
        "display_name": str(raw.get("display_name") or ""),
        "company_scope_status": scope_status,
        "profile_status": profile_status,
        "products": normalised_products,
        "source": "light-company-input",
        "evidence_ids": _string_list(raw.get("evidence_ids")),
    }


def _products_from_values(
    values: Any, field: Mapping[str, Any], cutoff: date
) -> list[dict[str, Any]]:
    if values is None:
        return []
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        values = [values]
    products = []
    for value in values:
        if isinstance(value, Mapping):
            product_id = str(value.get("product_id") or value.get("id") or "").strip()
            product_name = str(
                value.get("product_name") or value.get("product") or value.get("name") or ""
            ).strip()
            if not product_id and not product_name:
                continue
            _validate_record_dates(value, cutoff, "product_profile.product_list")
            products.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "status": str(value.get("status") or field.get("status") or "UNVERIFIED").upper(),
                    "evidence_ids": _string_list(
                        value.get("evidence_ids", field.get("evidence_ids"))
                    ),
                    "sources": _string_list(value.get("sources", field.get("sources"))),
                    "as_of": _string_list(value.get("as_of", field.get("as_of"))),
                    "revenue_share": value.get("revenue_share"),
                    "profit_share": value.get("profit_share"),
                }
            )
        elif str(value).strip():
            products.append(
                {
                    "product_id": "",
                    "product_name": str(value).strip(),
                    "status": str(field.get("status") or "UNVERIFIED").upper(),
                    "evidence_ids": _string_list(field.get("evidence_ids")),
                    "sources": _string_list(field.get("sources")),
                    "as_of": _string_list(field.get("as_of")),
                    "revenue_share": None,
                    "profit_share": None,
                }
            )
    return products


def _add_company(companies: dict[str, dict[str, Any]], company: dict[str, Any]) -> None:
    if company["company_id"] in companies:
        raise FuturesCompanyExposureError(
            f"duplicate company_id: {company['company_id']}"
        )
    companies[company["company_id"]] = company


def _merge_company(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    products: dict[tuple[str, str], dict[str, Any]] = {}
    for product in [*(left.get("products") or []), *(right.get("products") or [])]:
        key = (_norm(product.get("product_id")), _norm(product.get("product_name")))
        if key == ("", ""):
            continue
        products[key] = dict(product)
    return {
        "company_id": str(left.get("company_id") or right.get("company_id") or ""),
        "display_name": str(right.get("display_name") or left.get("display_name") or ""),
        "company_scope_status": _more_conservative_state(
            str(left.get("company_scope_status") or "MISSING"),
            str(right.get("company_scope_status") or "MISSING"),
        ),
        "profile_status": _more_conservative_profile(
            str(left.get("profile_status") or "MISSING"),
            str(right.get("profile_status") or "MISSING"),
        ),
        "products": list(products.values()),
        "source": f"{left.get('source', '')}+{right.get('source', '')}",
        "evidence_ids": list(dict.fromkeys([*left.get("evidence_ids", []), *right.get("evidence_ids", [])])),
    }


def _normalise_exposures(raw_exposures: Any, cutoff: date) -> list[dict[str, Any]]:
    if not isinstance(raw_exposures, Sequence) or isinstance(
        raw_exposures, (str, bytes, bytearray)
    ):
        raise FuturesCompanyExposureError("exposures must be a list")
    exposures = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_exposures):
        if not isinstance(raw, Mapping):
            raise FuturesCompanyExposureError(f"exposure {index} must be an object")
        exposure_id = str(raw.get("exposure_id") or "").strip()
        company_id = str(raw.get("company_id") or "").strip()
        product_id = str(raw.get("product_id") or "").strip()
        product_name = str(
            raw.get("product_name") or raw.get("product") or ""
        ).strip()
        if not exposure_id or not company_id:
            raise FuturesCompanyExposureError(
                f"exposure {index} requires exposure_id and company_id"
            )
        if exposure_id in seen:
            raise FuturesCompanyExposureError(f"duplicate exposure_id: {exposure_id}")
        if not product_id and not product_name:
            raise FuturesCompanyExposureError(
                f"exposure {exposure_id} requires product_id or product_name"
            )
        seen.add(exposure_id)
        _validate_record_dates(raw, cutoff, f"exposures.{exposure_id}")
        role = str(raw.get("exposure_role") or "").strip().upper()
        if role not in _ROLES:
            raise FuturesCompanyExposureError(
                f"unsupported exposure_role: {role or '<empty>'}"
            )
        link = str(raw.get("revenue_or_cost_link") or "").strip().upper()
        if link not in _LINKS:
            raise FuturesCompanyExposureError(
                f"unsupported revenue_or_cost_link: {link or '<empty>'}"
            )
        status = str(raw.get("status") or "UNVERIFIED").strip().upper()
        if status not in _STATES:
            raise FuturesCompanyExposureError(
                f"unsupported exposure status: {status}"
            )
        confidence = str(raw.get("confidence") or "UNVERIFIED").strip().upper()
        if confidence not in _CONFIDENCE:
            raise FuturesCompanyExposureError(
                f"unsupported exposure confidence: {confidence}"
            )
        pricing_lag = _normalise_text_or_mapping(raw.get("pricing_lag"), "pricing_lag")
        inventory_effect = _normalise_text_or_mapping(
            raw.get("inventory_effect"), "inventory_effect"
        )
        hedging_policy = _normalise_text_or_mapping(
            raw.get("hedging_policy"), "hedging_policy"
        )
        formula = raw.get("transmission_formula", raw.get("transmission_formula_json"))
        if formula is None:
            formula = {}
        if not isinstance(formula, Mapping):
            raise FuturesCompanyExposureError(
                f"transmission_formula must be an object: {exposure_id}"
            )
        formula = dict(formula)
        _validate_formula(formula, exposure_id)
        exposures.append(
            {
                "exposure_id": exposure_id,
                "variety_id": str(raw.get("variety_id") or "").strip(),
                "company_id": company_id,
                "product_id": product_id,
                "product_name": product_name,
                "exposure_role": role,
                "revenue_or_cost_link": link,
                "pricing_lag": pricing_lag,
                "inventory_effect": inventory_effect,
                "hedging_policy": hedging_policy,
                "transmission_formula": formula,
                "source_evidence_ids": _string_list(
                    raw.get("source_evidence_ids", raw.get("source_evidence_id"))
                ),
                "sources": _string_list(raw.get("sources", raw.get("source"))),
                "as_of": _string_list(raw.get("as_of")),
                "status": status,
                "confidence": confidence,
                "notes": _string_list(raw.get("notes")),
            }
        )
    return exposures


def _build_exposure_item(
    exposure: Mapping[str, Any],
    companies: Mapping[str, Mapping[str, Any]],
    *,
    expected_variety: str,
    futures_context: Mapping[str, Any],
    futures_status: str,
    cutoff: date,
    rule_version: str,
) -> dict[str, Any]:
    company_id = str(exposure["company_id"])
    company = companies.get(company_id)
    reasons: list[str] = []
    unknowns: list[str] = []
    blockers: list[str] = []
    if exposure.get("variety_id") and exposure["variety_id"] != expected_variety:
        blockers.append("EXPOSURE_VARIETY_MISMATCH")
    if company is None:
        blockers.append("COMPANY_NOT_IN_PRODUCT_SCOPE")
        company = {
            "company_id": company_id,
            "display_name": "",
            "company_scope_status": "MISSING",
            "profile_status": "MISSING",
            "products": [],
            "source": "missing",
            "evidence_ids": [],
        }
    product, product_match = _match_product(exposure, company.get("products") or [])
    if product is None:
        blockers.append("PRODUCT_NOT_EXPLICITLY_VERIFIED")
    else:
        if product.get("status") != "VERIFIED":
            unknowns.append("product_evidence")
        if not product.get("evidence_ids"):
            unknowns.append("product_evidence_ids")
    if company.get("company_scope_status") in {"MISSING", "CONFLICTING"}:
        blockers.append("COMPANY_SCOPE_NOT_VERIFIED")
    if company.get("profile_status") in {"MISSING", "BLOCKED"}:
        unknowns.append("company_product_profile")
    if exposure["status"] == "CONFLICTING":
        blockers.append("EXPOSURE_EVIDENCE_CONFLICTING")
    if not exposure.get("source_evidence_ids"):
        unknowns.append("exposure_source_evidence")
    for field_name, field_value in (
        ("pricing_lag", exposure.get("pricing_lag")),
        ("inventory_effect", exposure.get("inventory_effect")),
        ("hedging_policy", exposure.get("hedging_policy")),
    ):
        if not field_value:
            unknowns.append(field_name)
    if not exposure["transmission_formula"]:
        unknowns.append("transmission_formula")
    if futures_status == "BLOCKED":
        blockers.append("FUTURES_REPORT_BLOCKED")
    elif futures_status != "READY":
        unknowns.append("futures_fundamentals")

    declared_direction = _directional_reading(
        exposure["exposure_role"], exposure["revenue_or_cost_link"]
    )
    direction = (
        declared_direction
        if product is not None and product.get("status") == "VERIFIED" and product_match == "EXACT"
        else "NOT_ASSESSED"
    )
    bridge = _build_transmission_bridge(
        exposure,
        futures_context,
        direction,
        cutoff,
        numeric_allowed=direction != "NOT_ASSESSED",
    )
    if bridge["status"] != "READY":
        unknowns.extend(bridge["unknowns"])
    mapping_state = _mapping_state(
        blockers=blockers,
        unknowns=unknowns,
        company=company,
        product=product,
        futures_status=futures_status,
        exposure_status=exposure["status"],
    )
    if mapping_state == "READY":
        reasons.append("EXPLICIT_PRODUCT_ROLE_AND_TRANSMISSION_EVIDENCE")
    elif mapping_state == "PARTIAL":
        reasons.append("EXPOSURE_REQUIRES_TRANSMISSION_GAP_REVIEW")
    elif mapping_state == "INSUFFICIENT":
        reasons.append("EXPOSURE_CANNOT_SUPPORT_PROFIT_INFERENCE")
    else:
        reasons.append("EXPOSURE_MAPPING_BLOCKED")
    return {
        "exposure_id": exposure["exposure_id"],
        "variety_id": expected_variety,
        "company_id": company_id,
        "display_name": str(company.get("display_name") or ""),
        "product_id": str((product or {}).get("product_id") or exposure.get("product_id") or ""),
        "product_name": str((product or {}).get("product_name") or exposure.get("product_name") or ""),
        "product_match": product_match,
        "product_status": str((product or {}).get("status") or "MISSING"),
        "exposure_role": exposure["exposure_role"],
        "revenue_or_cost_link": exposure["revenue_or_cost_link"],
        "pricing_lag": exposure["pricing_lag"],
        "inventory_effect": exposure["inventory_effect"],
        "hedging_policy": exposure["hedging_policy"],
        "transmission_formula": exposure["transmission_formula"],
        "directional_reading": direction,
        "declared_directional_reading": declared_direction,
        "transmission_bridge": bridge,
        "source_evidence_ids": list(
            dict.fromkeys(
                [
                    *exposure.get("source_evidence_ids", []),
                    *((product or {}).get("evidence_ids") or []),
                ]
            )
        ),
        "sources": list(dict.fromkeys([*exposure.get("sources", []), *((product or {}).get("sources") or [])])),
        "confidence": exposure["confidence"],
        "mapping_state": mapping_state,
        "reasons": list(dict.fromkeys(reasons)),
        "blockers": list(dict.fromkeys(blockers)),
        "unknowns": list(dict.fromkeys(unknowns)),
        "rule_version": rule_version,
        "review_only": True,
        "investment_conclusion": False,
        "decision_snapshot_created": False,
    }


def _match_product(
    exposure: Mapping[str, Any], products: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    product_id = _norm(exposure.get("product_id"))
    product_name = _norm(exposure.get("product_name"))
    matches = []
    for product in products:
        if product_id and _norm(product.get("product_id")) == product_id:
            matches.append(product)
        elif product_name and _norm(product.get("product_name")) == product_name:
            matches.append(product)
    if not matches:
        return None, "NOT_MATCHED"
    if len(matches) > 1:
        return None, "AMBIGUOUS"
    return dict(matches[0]), "EXACT"


def _build_transmission_bridge(
    exposure: Mapping[str, Any],
    futures_context: Mapping[str, Any],
    direction: str,
    cutoff: date,
    *,
    numeric_allowed: bool,
) -> dict[str, Any]:
    formula = exposure.get("transmission_formula") or {}
    scenarios = futures_context.get("price_scenarios") or {}
    reference_price, reference_source = _reference_price(formula, futures_context)
    numeric_ready, numeric_unknowns = _numeric_formula_readiness(
        formula, reference_price, scenarios
    )
    if not numeric_allowed:
        numeric_ready = False
        numeric_unknowns.insert(0, "verified_product_required")
    scenario_impacts: dict[str, Any] = {}
    if numeric_ready:
        for name, scenario in scenarios.get("scenarios", {}).items():
            price_range = scenario.get("range") or {}
            low = _number(price_range.get("low"), f"scenario.{name}.low")
            high = _number(price_range.get("high"), f"scenario.{name}.high")
            scenario_impacts[name] = _scenario_impact(
                low,
                high,
                reference_price,
                formula,
            )
    elif scenarios.get("status") == "INSUFFICIENT":
        numeric_unknowns.append("futures_price_scenarios")
    cashflow_status = "READY" if numeric_ready and formula.get("cash_conversion_ratio") is not None else "NOT_CALCULATED"
    status = "READY" if numeric_ready else "PARTIAL"
    return {
        "status": status,
        "price_reference": {
            "value": reference_price,
            "source": reference_source,
        },
        "directional_reading": direction,
        "scenario_impacts": scenario_impacts,
        "numeric_bridge": {
            "status": "ILLUSTRATIVE_ONLY" if numeric_ready else "NOT_CALCULATED",
            "formula": "price_delta * volume * (revenue_sensitivity - cost_sensitivity)",
            "assumptions": _formula_projection(formula),
            "after_hedge": bool(formula.get("hedge_ratio") is not None),
        },
        "cash_flow_bridge": {
            "status": cashflow_status,
            "cash_conversion_ratio": formula.get("cash_conversion_ratio"),
            "note": "现金流影响需要营运资金、结算和回款周期证据，不由商品价格单独推出。",
        },
        "inventory_bridge": {
            "status": "ILLUSTRATIVE_ONLY" if formula.get("inventory_quantity") is not None else "NOT_CALCULATED",
            "inventory_quantity": formula.get("inventory_quantity"),
            "note": "库存重估需区分自有库存、代销库存和套保头寸。",
        },
        "hedge_bridge": {
            "status": "VERIFIED" if formula.get("hedge_ratio") is not None else "MISSING",
            "hedge_ratio": formula.get("hedge_ratio"),
            "policy": exposure.get("hedging_policy"),
        },
        "unknowns": list(dict.fromkeys(numeric_unknowns)),
        "as_of": cutoff.isoformat(),
        "profit_forecast": None,
    }


def _scenario_impact(
    low: float | None,
    high: float | None,
    reference: float | None,
    formula: Mapping[str, Any],
) -> dict[str, Any]:
    revenue_sensitivity = _number(formula.get("revenue_sensitivity"), "revenue_sensitivity") or 0.0
    cost_sensitivity = _number(formula.get("cost_sensitivity"), "cost_sensitivity") or 0.0
    volume = _number(formula.get("volume"), "volume") or 0.0
    pass_through = _number(formula.get("pass_through_ratio"), "pass_through_ratio")
    multiplier = pass_through if pass_through is not None else 1.0
    hedge = _number(formula.get("hedge_ratio"), "hedge_ratio")
    net_sensitivity = (revenue_sensitivity - cost_sensitivity) * multiplier
    result = {
        "low_price_delta": low - reference if low is not None and reference is not None else None,
        "high_price_delta": high - reference if high is not None and reference is not None else None,
        "unhedged_low_impact": (low - reference) * volume * net_sensitivity if low is not None and reference is not None else None,
        "unhedged_high_impact": (high - reference) * volume * net_sensitivity if high is not None and reference is not None else None,
        "impact_unit": str(formula.get("impact_unit") or "illustrative_currency_per_period"),
    }
    if hedge is not None:
        result["after_hedge_low_impact"] = result["unhedged_low_impact"] * (1 - hedge) if result["unhedged_low_impact"] is not None else None
        result["after_hedge_high_impact"] = result["unhedged_high_impact"] * (1 - hedge) if result["unhedged_high_impact"] is not None else None
    else:
        result["after_hedge_low_impact"] = None
        result["after_hedge_high_impact"] = None
    if formula.get("cash_conversion_ratio") is not None:
        cash_ratio = _number(formula.get("cash_conversion_ratio"), "cash_conversion_ratio")
        result["illustrative_cashflow_low"] = result["unhedged_low_impact"] * cash_ratio if result["unhedged_low_impact"] is not None else None
        result["illustrative_cashflow_high"] = result["unhedged_high_impact"] * cash_ratio if result["unhedged_high_impact"] is not None else None
    return result


def _numeric_formula_readiness(
    formula: Mapping[str, Any],
    reference_price: float | None,
    scenarios: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    unknowns = []
    if reference_price is None:
        unknowns.append("reference_price")
    if _number(formula.get("volume"), "volume") is None:
        unknowns.append("volume")
    if formula.get("revenue_sensitivity") is None and formula.get("cost_sensitivity") is None:
        unknowns.append("revenue_or_cost_sensitivity")
    if scenarios.get("status") not in {"READY", "PARTIAL"}:
        unknowns.append("price_scenarios")
    ready = not unknowns and bool(scenarios.get("scenarios"))
    return ready, unknowns


def _reference_price(
    formula: Mapping[str, Any], futures_context: Mapping[str, Any]
) -> tuple[float | None, str]:
    if formula.get("reference_price") is not None:
        return _number(formula["reference_price"], "reference_price"), "explicit_formula_reference"
    for key in ("contract_settlement", "spot_price"):
        value = futures_context.get("latest", {}).get(key)
        if isinstance(value, Mapping) and value.get("value") is not None:
            return _number(value["value"], key), f"futures_report.{key}"
    return None, "missing"


def _futures_context(report: Mapping[str, Any]) -> dict[str, Any]:
    derived = report.get("derived_metrics") or {}
    scenarios = report.get("price_scenarios") or {}
    return {
        "status": str(report.get("status") or "INSUFFICIENT").upper(),
        "object_type": str(report.get("object_type") or ""),
        "exchange": str(report.get("exchange") or ""),
        "variety_id": str(report.get("variety_id") or ""),
        "variety_name": str(report.get("variety_name") or ""),
        "latest": {
            "spot_price": derived.get("spot_latest"),
            "contract_settlement": derived.get("contract_settlement_latest"),
            "basis": derived.get("basis_latest"),
            "inventory": derived.get("inventory_latest"),
        },
        "price_scenarios": scenarios,
        "contract_view_status": str(
            (report.get("contract_view") or {}).get("status") or "INSUFFICIENT"
        ),
        "evidence_gaps": list(report.get("evidence_gaps") or []),
    }


def _directional_reading(role: str, link: str) -> str:
    if role == "PRODUCER" and link == "REVENUE":
        return "PRICE_UP_REVENUE_POSITIVE"
    if role == "CONSUMER" and link == "COST":
        return "PRICE_UP_COST_NEGATIVE"
    if role in {"PROCESSOR", "BILATERAL"} or link in {"BOTH", "MIXED"}:
        return "MIXED_SPREAD_DEPENDENT"
    if role == "TRADER" or link == "INVENTORY":
        return "INVENTORY_AND_POSITION_DEPENDENT"
    return "NOT_ASSESSED"


def _mapping_state(
    *,
    blockers: Sequence[str],
    unknowns: Sequence[str],
    company: Mapping[str, Any],
    product: Mapping[str, Any] | None,
    futures_status: str,
    exposure_status: str,
) -> str:
    if blockers:
        if "PRODUCT_NOT_EXPLICITLY_VERIFIED" in blockers and product is None:
            return "INSUFFICIENT"
        return "BLOCKED"
    if product is None or not company.get("products"):
        return "INSUFFICIENT"
    if exposure_status in {"MISSING", "UNVERIFIED"}:
        return "PARTIAL"
    if futures_status != "READY":
        return "PARTIAL"
    if unknowns or company.get("profile_status") != "READY" or product.get("status") != "VERIFIED":
        return "PARTIAL"
    return "READY"


def _build_company_views(
    items: Sequence[Mapping[str, Any]], companies: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_company: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        by_company.setdefault(str(item["company_id"]), []).append(item)
    views = []
    for company_id, company in companies.items():
        company_items = by_company.get(company_id, [])
        directions = list(dict.fromkeys(str(item["directional_reading"]) for item in company_items))
        states = [str(item["mapping_state"]) for item in company_items]
        if not company_items:
            status = "NOT_MAPPED"
        elif any(state == "BLOCKED" for state in states):
            status = "REVIEW_REQUIRED"
        elif any(state == "INSUFFICIENT" for state in states):
            status = "INSUFFICIENT"
        elif any(state == "PARTIAL" for state in states):
            status = "PARTIAL"
        else:
            status = "READY"
        views.append(
            {
                "company_id": company_id,
                "display_name": str(company.get("display_name") or ""),
                "status": status,
                "exposure_ids": [str(item["exposure_id"]) for item in company_items],
                "products": list(
                    dict.fromkeys(
                        str(item["product_name"])
                        for item in company_items
                        if str(item.get("product_name") or "")
                    )
                ),
                "roles": list(dict.fromkeys(str(item["exposure_role"]) for item in company_items)),
                "directional_readings": directions,
                "interpretation": "商品暴露摘要，不等于公司利润预测或投资结论。",
            }
        )
    for company_id, company_items in by_company.items():
        if company_id not in companies:
            views.append(
                {
                    "company_id": company_id,
                    "display_name": str(company_items[0].get("display_name") or ""),
                    "status": "REVIEW_REQUIRED",
                    "exposure_ids": [str(item["exposure_id"]) for item in company_items],
                    "products": [],
                    "roles": [],
                    "directional_readings": [],
                    "interpretation": "公司不在产品范围资料中，无法形成可靠暴露摘要。",
                }
            )
    return views


def _report_status(
    *, futures_status: str, items: Sequence[Mapping[str, Any]], expected_count: int
) -> str:
    if expected_count == 0:
        return "INSUFFICIENT"
    if futures_status == "BLOCKED":
        return "BLOCKED"
    states = [str(item["mapping_state"]) for item in items]
    if all(state == "READY" for state in states) and futures_status == "READY":
        return "READY"
    if any(state == "BLOCKED" for state in states):
        return "REVIEW_REQUIRED"
    if any(state == "INSUFFICIENT" for state in states):
        return "INSUFFICIENT"
    return "PARTIAL"


def _validate_formula(formula: Mapping[str, Any], exposure_id: str) -> None:
    for field in (
        "reference_price",
        "volume",
        "revenue_sensitivity",
        "cost_sensitivity",
        "pass_through_ratio",
        "hedge_ratio",
        "inventory_quantity",
        "cash_conversion_ratio",
    ):
        if field in formula and formula[field] is not None:
            _number(formula[field], f"{exposure_id}.transmission_formula.{field}")
    for field in ("pass_through_ratio", "hedge_ratio", "cash_conversion_ratio"):
        if field in formula and formula[field] is not None:
            value = _number(formula[field], field)
            if value is not None and not 0 <= value <= 1:
                raise FuturesCompanyExposureError(
                    f"{exposure_id}.transmission_formula.{field} must be between 0 and 1"
                )


def _formula_projection(formula: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: formula.get(key)
        for key in (
            "reference_price",
            "volume",
            "volume_unit",
            "revenue_sensitivity",
            "cost_sensitivity",
            "pass_through_ratio",
            "hedge_ratio",
            "inventory_quantity",
            "cash_conversion_ratio",
            "impact_unit",
        )
        if formula.get(key) is not None
    }


def _normalise_text_or_mapping(value: Any, field: str) -> dict[str, Any] | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, Mapping):
        result = dict(value)
        if "status" in result:
            status = str(result["status"]).upper()
            if status not in _STATES:
                raise FuturesCompanyExposureError(
                    f"unsupported {field} status: {status}"
                )
            result["status"] = status
        return result
    return str(value)


def _validate_record_dates(value: Mapping[str, Any], cutoff: date, field: str) -> None:
    for raw_date in _string_list(value.get("as_of")):
        parsed = _parse_date(raw_date, f"{field}.as_of")
        if parsed > cutoff:
            raise FuturesCompanyExposureError(
                f"future data exceeds as_of: {field}.as_of={raw_date}"
            )


def _more_conservative_state(left: str, right: str) -> str:
    order = {"CONFLICTING": 5, "MISSING": 4, "UNVERIFIED": 3, "PARTIAL": 2, "VERIFIED": 1}
    return left if order.get(left, 4) >= order.get(right, 4) else right


def _more_conservative_profile(left: str, right: str) -> str:
    order = {"BLOCKED": 5, "MISSING": 4, "INSUFFICIENT": 3, "PARTIAL": 2, "READY": 1}
    return left if order.get(left, 4) >= order.get(right, 4) else right


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise FuturesCompanyExposureError(f"{field} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FuturesCompanyExposureError(f"{field} must be numeric") from error
    if not isfinite(number):
        raise FuturesCompanyExposureError(f"{field} must be finite")
    return number


def _parse_date(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise FuturesCompanyExposureError(f"{field} is required")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise FuturesCompanyExposureError(f"{field} must be ISO date/datetime") from error


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise FuturesCompanyExposureError("expected a string or string list")
    return [str(item) for item in value if str(item).strip()]
