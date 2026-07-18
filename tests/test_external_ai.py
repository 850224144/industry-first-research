from industry_first_research.external_ai import ExternalAIResearchRecord


def test_external_ai_answer_is_a_c_level_unverified_lead():
    record = ExternalAIResearchRecord(
        provider="DeepSeek Web",
        model_label="web",
        question="研究某行业的库存变化",
        answer="这是线索 https://example.com/source。需要核验。",
    )

    assert record.evidence_tier == "C"
    assert record.verification_status == "UNVERIFIED"
    assert record.source_urls == ["https://example.com/source"]
