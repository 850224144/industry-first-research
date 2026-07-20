import pytest

from industry_first_research.industry_aliases import IndustryAliasError, IndustryAliasRegistry


def test_alias_registry_resolves_source_specific_names():
    registry = IndustryAliasRegistry.from_dict(
        {
            "schema_version": "industry-aliases.v1",
            "mappings": [
                {
                    "canonical_id": "power",
                    "canonical_name": "电力",
                    "aliases": {
                        "eastmoney": ["电能综合服务"],
                        "tonghuashun": ["电力行业"],
                    },
                    "note": "test mapping",
                }
            ],
        }
    )

    assert registry.resolve("eastmoney", "电能综合服务") == "power"
    assert registry.resolve("tonghuashun", "电力行业") == "power"
    assert registry.match_method("tonghuashun", "电力行业") == "ALIAS"
    assert registry.resolve("unknown", "电力") == "电力"


def test_alias_registry_rejects_ambiguous_mapping():
    with pytest.raises(IndustryAliasError):
        IndustryAliasRegistry.from_dict(
            {
                "schema_version": "industry-aliases.v1",
                "mappings": [
                    {
                        "canonical_id": "a",
                        "canonical_name": "甲",
                        "aliases": {"source": ["同名"]},
                        "note": "a",
                    },
                    {
                        "canonical_id": "b",
                        "canonical_name": "乙",
                        "aliases": {"source": ["同名"]},
                        "note": "b",
                    },
                ],
            }
        )
