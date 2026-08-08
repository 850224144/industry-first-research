import json
from pathlib import Path

import pytest

from industry_first_research.cli import main
from industry_first_research.third_party_components import (
    ThirdPartyComponentError,
    build_component_health_snapshot,
    build_component_registry,
    build_component_registration_from_candidate,
    build_performance_metrics_report,
    parse_local_document,
    validate_component_health_snapshot,
    validate_component_registry_links,
    validate_component_registry,
    validate_performance_metrics_report,
)
from industry_first_research.third_party_candidate_review import build_candidate_review


def component(component_id="local-parser", **overrides):
    value = {
        "component_id": component_id,
        "project_url": "https://example.com/project",
        "package_name": "example-package",
        "import_name": "example_package",
        "version_or_commit": "v1",
        "license_status": "REVIEWED",
        "adapter_kind": "document_parser",
        "capability_scope": ["text"],
        "candidate_review_id": "review-component",
        "capability_slice": "text",
        "candidate_review_state": "ACCEPTED",
        "adapter_registration_id": "adapter-registration-component",
        "baseline_id": "baseline-component-v1",
        "validation_fixture_ids": ["fixture-component-001"],
        "regression_status": "PASS",
        "fallback_component": "local-parser",
        "decision": "ADAPTER_REUSE",
        "enabled": True,
    }
    value.update(overrides)
    return value


def performance_input():
    return {
        "schema_version": "third-party-performance-input.v1",
        "as_of": "2026-07-31",
        "asset_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-02", "value": 110},
            {"date": "2026-07-03", "value": 105},
        ],
        "benchmark_series": [
            {"date": "2026-07-01", "value": 100},
            {"date": "2026-07-02", "value": 102},
            {"date": "2026-07-03", "value": 103},
        ],
        "periods_per_year": 252,
    }


def test_component_registry_and_local_health_are_immutable_and_non_remote():
    registry = build_component_registry(
        {
            "schema_version": "third-party-component-registry-input.v1",
            "registry_id": "test-registry",
            "version": "1",
            "components": [component("local-parser", enabled=False, decision="REFERENCE_ONLY")],
        }
    )
    assert registry["schema_version"] == "third-party-component-registry.v1"
    assert registry["policy"]["no_remote_health_checks"] is True
    assert validate_component_registry(registry)["content_hash"] == registry["content_hash"]

    health = build_component_health_snapshot(registry, checked_at="2026-07-24T10:00:00+08:00")
    assert health["components"][0]["status"] == "REJECTED"
    assert health["policy"]["remote_endpoint_not_tested"] is True
    assert validate_component_health_snapshot(health)["snapshot_id"] == health["snapshot_id"]


def test_registry_rejects_fork_without_modification_log():
    with pytest.raises(ThirdPartyComponentError, match="modification_log"):
        build_component_registry(
            {
                "schema_version": "third-party-component-registry-input.v1",
                "version": "1",
                "components": [component(decision="FORK_AND_MODIFY")],
            }
        )


def test_enabled_registry_requires_candidate_review_registration():
    with pytest.raises(ThirdPartyComponentError, match="candidate_review_id"):
        build_component_registry(
            {
                "schema_version": "third-party-component-registry-input.v1",
                "version": "1",
                "components": [component(candidate_review_id="")],
            }
        )


def test_registry_links_are_checked_against_candidate_review():
    candidate = build_candidate_review(
        {
            "schema_version": "third-party-candidate-review-input.v1",
            "review_id": "review-component",
            "capability_slice": "text",
            "project_url": "https://example.com/project",
            "package_name": "example-package",
            "source_kind": "github",
            "discovered_at": "2026-07-24T10:00:00+08:00",
            "version_or_commit": "v1",
            "license_snapshot": "MIT",
            "license_status": "REVIEWED",
            "security_status": "PASSED",
            "capability_gap": "text adapter",
            "requested_capability": "text",
            "execution_surface": "local_only",
            "temporal_cutoff_support": "local_input_as_of",
            "future_function_risk": "none",
            "reproducibility_status": "VALIDATED",
            "fixture_ids": ["fixture-component-001"],
            "baseline_id": "baseline-component-v1",
            "adapter_id": "adapter-registration-component",
            "fallback_id": "local-parser",
            "regression_status": "PASS",
            "state": "ACCEPTED",
            "decision": "ACCEPTED",
        }
    )
    registry = build_component_registry(
        {
            "schema_version": "third-party-component-registry-input.v1",
            "version": "1",
            "components": [component()],
        }
    )
    assert validate_component_registry_links(registry, [candidate])["component_count"] == 1

    registration = build_component_registration_from_candidate(
        candidate,
        component_id="generated-component",
        package_name="example-package",
        adapter_kind="document_parser",
    )
    assert registration["candidate_review_id"] == "review-component"
    assert registration["validation_fixture_ids"] == ["fixture-component-001"]
    assert registration["baseline_id"] == "baseline-component-v1"

    mismatched = dict(candidate, capability_slice="other")
    mismatched["content_hash"] = "tampered"
    with pytest.raises(ThirdPartyComponentError, match="content_hash"):
        validate_component_registry_links(registry, [mismatched])


def test_performance_adapter_has_local_fallback_and_no_decision_boundary():
    report = build_performance_metrics_report(performance_input(), result_id="fixture")
    assert report["result_id"] == "third-party-performance-fixture"
    assert report["asset_return"] == pytest.approx(0.05)
    assert report["benchmark_return"] == pytest.approx(0.03)
    assert report["excess_return"] == pytest.approx(0.02)
    assert report["backend"] in {"local", "quantstats"}
    assert report["policy"]["does_not_perform_causal_attribution"] is True
    assert report["execution_enabled"] is False
    assert validate_performance_metrics_report(report)["immutable"] is True


def test_performance_adapter_rejects_future_points_and_date_mismatch():
    payload = performance_input()
    payload["asset_series"].append({"date": "2026-08-01", "value": 106})
    with pytest.raises(ThirdPartyComponentError, match="after as_of"):
        build_performance_metrics_report(payload)

    payload = performance_input()
    payload["benchmark_series"][2]["date"] = "2026-07-04"
    with pytest.raises(ThirdPartyComponentError, match="share dates"):
        build_performance_metrics_report(payload)


def test_missing_document_parser_is_a_clear_optional_dependency_failure():
    with pytest.raises(
        ThirdPartyComponentError,
        match="optional package is not installed|could not open document",
    ):
        parse_local_document(
            "pypdf",
            b"not-a-pdf",
            document_id="doc-1",
            research_as_of="2026-07-24",
        )


def test_component_registry_and_performance_cli(tmp_path, monkeypatch, capsys):
    registry_input = tmp_path / "components.json"
    registry_input.write_text(
        json.dumps(
            {
                "schema_version": "third-party-component-registry-input.v1",
                "registry_id": "cli-registry",
                "version": "1",
                "components": [component("cli-component", enabled=False, decision="REFERENCE_ONLY")],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "components"
    monkeypatch.setattr(
        "sys.argv",
        [
            "industry-first-research",
            "third-party-components",
            "--input",
            str(registry_input),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    registry = json.loads((output_dir / "cli-registry.json").read_text(encoding="utf-8"))
    assert registry["registry_id"] == "cli-registry"

    performance_input_path = tmp_path / "performance.json"
    performance_input_path.write_text(json.dumps(performance_input()), encoding="utf-8")
    performance_dir = tmp_path / "performance"
    monkeypatch.setattr(
        "sys.argv",
        [
            "industry-first-research",
            "performance-metrics",
            "--input",
            str(performance_input_path),
            "--output-dir",
            str(performance_dir),
            "--result-id",
            "cli-result",
        ],
    )
    main()
    capsys.readouterr()
    assert (performance_dir / "third-party-performance-cli-result.json").exists()
