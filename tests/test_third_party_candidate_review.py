import json
import sys

import pytest

from industry_first_research.cli import main
from industry_first_research.third_party_candidate_review import (
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    ThirdPartyCandidateReviewError,
    build_candidate_review,
    build_candidate_review_event,
    build_candidate_review_projection,
    validate_candidate_review,
    validate_candidate_review_projection,
)


def review_input(**overrides):
    payload = {
        "schema_version": "third-party-candidate-review-input.v1",
        "review_id": "review-pdf-text",
        "capability_slice": "pdf_text_locator",
        "project_url": "https://example.com/project",
        "package_name": "example-package",
        "source_kind": "github",
        "discovered_at": "2026-07-24T10:00:00+08:00",
        "version_or_commit": "v1",
        "license_snapshot": "MIT",
        "license_status": "REVIEW_REQUIRED",
        "security_status": "REVIEW_REQUIRED",
        "capability_gap": "缺少可追踪的本地文本定位适配",
        "requested_capability": "pdf_text_locator",
        "used_modules": ["parser.text"],
        "excluded_modules": ["remote_fetch", "trade"],
        "dependency_manifest": {"python": ">=3.11"},
        "network_required": False,
        "token_required": False,
        "account_required": False,
        "execution_surface": "local_parser_only",
        "temporal_cutoff_support": "local_input_as_of",
        "future_function_risk": "none_from_parser",
        "reproducibility_status": "NOT_VALIDATED",
        "fixture_ids": [],
        "baseline_id": "",
        "adapter_id": "",
        "fallback_id": "manual-parser",
        "regression_status": "NOT_RUN",
        "enable_conditions": {},
        "capability_matrix_refs": ["platform.third-party-component-registry"],
        "state": "DISCOVERED",
        "owner": "test",
    }
    payload.update(overrides)
    return payload


def test_candidate_review_is_immutable_and_starts_without_installing_anything():
    review = build_candidate_review(review_input())
    assert review["schema_version"] == CANDIDATE_REVIEW_SCHEMA_VERSION
    assert review["state"] == "DISCOVERED"
    assert review["policy"]["no_automatic_install"] is True
    assert review["policy"]["no_remote_fetch"] is True
    assert review["execution_enabled"] is False
    assert validate_candidate_review(review)["content_hash"] == review["content_hash"]


def test_candidate_review_state_chain_requires_the_right_evidence_at_each_gate():
    review = build_candidate_review(review_input())
    events = []

    def advance(to_state, updates=None, day="2026-07-24T11:00:00+08:00"):
        event = build_candidate_review_event(
            review,
            to_state=to_state,
            changed_at=day,
            trigger=f"完成 {to_state}",
            actor="tester",
            field_updates=updates or {},
            previous_events=events,
        )
        events.append(event)

    advance("CAPABILITY_SCOPED")
    advance(
        "LICENSE_AND_SECURITY_REVIEWED",
        {"license_status": "REVIEWED", "security_status": "PASSED"},
    )
    advance(
        "FIXTURE_VALIDATED",
        {
            "fixture_ids": ["fixture-pdf-001"],
            "baseline_id": "baseline-local-parser-v1",
            "regression_status": "PASS",
        },
    )
    advance(
        "ADAPTER_PILOTED",
        {"adapter_id": "pdf-text-adapter-v1", "fallback_id": "manual-parser"},
    )
    advance(
        "CONDITIONAL",
        {"enable_conditions": {"only_local_pdf": True, "human_review": True}},
    )
    projection = build_candidate_review_projection(review, events)
    assert projection["current_state"] == "CONDITIONAL"
    assert projection["review"]["decision"] == "CONDITIONAL"
    assert projection["policy"]["runtime_registry_separate"] is True
    assert projection["base_review_content_hash"] == review["content_hash"]
    assert validate_candidate_review_projection(projection)["event_count"] == 5

    accepted = build_candidate_review_event(
        review,
        to_state="ACCEPTED",
        changed_at="2026-07-25T11:00:00+08:00",
        trigger="条件已满足",
        actor="tester",
        previous_events=events,
    )
    final = build_candidate_review_projection(review, [*events, accepted])
    assert final["current_state"] == "ACCEPTED"


def test_candidate_review_rejects_invalid_gate_and_immutable_field_patch():
    review = build_candidate_review(review_input())
    scoped = build_candidate_review_event(
        review,
        to_state="CAPABILITY_SCOPED",
        changed_at="2026-07-24T10:00:00+08:00",
        trigger="范围已明确",
        actor="tester",
    )
    licensed = build_candidate_review_event(
        review,
        to_state="LICENSE_AND_SECURITY_REVIEWED",
        changed_at="2026-07-24T11:00:00+08:00",
        trigger="完成许可证和安全审查",
        actor="tester",
        field_updates={"license_status": "REVIEWED", "security_status": "PASSED"},
        previous_events=[scoped],
    )
    with pytest.raises(ThirdPartyCandidateReviewError, match="requires fixture_ids"):
        build_candidate_review_event(
            review,
            to_state="FIXTURE_VALIDATED",
            changed_at="2026-07-24T12:00:00+08:00",
            trigger="跳过夹具",
            actor="tester",
            previous_events=[scoped, licensed],
        )
    with pytest.raises(ThirdPartyCandidateReviewError, match="immutable or unsupported"):
        build_candidate_review_event(
            review,
            to_state="CAPABILITY_SCOPED",
            changed_at="2026-07-24",
            trigger="非法修改",
            actor="tester",
            field_updates={"project_url": "https://evil.example"},
        )


def test_candidate_review_tamper_and_non_monotonic_events_are_rejected():
    review = build_candidate_review(review_input())
    event = build_candidate_review_event(
        review,
        to_state="CAPABILITY_SCOPED",
        changed_at="2026-07-24T11:00:00+08:00",
        trigger="范围已明确",
        actor="tester",
    )
    tampered = dict(event, trigger="changed")
    with pytest.raises(ThirdPartyCandidateReviewError, match="content_hash"):
        build_candidate_review_projection(review, [tampered])
    with pytest.raises(ThirdPartyCandidateReviewError, match="content_hash"):
        build_candidate_review_event(
            review,
            to_state="LICENSE_AND_SECURITY_REVIEWED",
            changed_at="2026-07-24T12:00:00+08:00",
            trigger="审查完成",
            actor="tester",
            field_updates={"license_status": "REVIEWED", "security_status": "PASSED"},
            previous_events=[tampered],
        )
    second = build_candidate_review_event(
        review,
        to_state="LICENSE_AND_SECURITY_REVIEWED",
        changed_at="2026-07-24T10:00:00+08:00",
        trigger="审查完成",
        actor="tester",
        field_updates={"license_status": "REVIEWED", "security_status": "PASSED"},
        previous_events=[event],
    )
    with pytest.raises(ThirdPartyCandidateReviewError, match="non-decreasing"):
        build_candidate_review_projection(review, [event, second])


def test_candidate_review_cli_creates_event_and_projection(tmp_path, monkeypatch, capsys):
    review_path = tmp_path / "review-input.json"
    review_path.write_text(json.dumps(review_input(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "reviews"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "third-party-candidate-review",
            "--input",
            str(review_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    created = json.loads(capsys.readouterr().out)
    saved_review = output_dir / "review-pdf-text.json"
    assert saved_review.exists()

    event_input = tmp_path / "event.json"
    event_input.write_text(
        json.dumps(
            {
                "to_state": "CAPABILITY_SCOPED",
                "changed_at": "2026-07-24T12:00:00+08:00",
                "trigger": "范围已明确",
                "actor": "tester",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "industry-first-research",
            "third-party-candidate-review-event",
            "--review",
            str(saved_review),
            "--input",
            str(event_input),
            "--output-dir",
            str(output_dir),
        ],
    )
    main()
    created_event = json.loads(capsys.readouterr().out)
    assert created_event["projection"]["current_state"] == "CAPABILITY_SCOPED"
    assert (output_dir / f"{created_event['event']['event_id']}.json").exists()
    assert (output_dir / f"{created_event['projection']['projection_id']}.json").exists()
