from pathlib import Path

import pytest

from research_system.industry_chain_v2 import IndustryChainV2


ROOT = Path(__file__).parents[1]


def test_bundled_v2_data_is_loaded_from_repo_root_independent_of_cwd():
    chain = IndustryChainV2()
    assert chain.get_products_by_company("600438")["products"]
    assert chain.validation["status"] == "VALID"
    assert chain.validation["warning_count"] > 0


def test_directed_supply_edges_expose_both_directions():
    chain = IndustryChainV2(ROOT / "data" / "industry_chains")

    assert [item["product"]["name"] for item in chain.get_upstream_products("硅片")] == ["高纯硅料"]
    assert [item["product"]["name"] for item in chain.get_downstream_products("硅片")] == ["电池片"]

    graph = chain.get_product_chain("硅片", max_depth=3)
    assert graph["data_version"] == "industry-chain.v2"
    assert graph["validation_status"] == "VALID"
    assert graph["upstream"][0]["product"]["name"] == "高纯硅料"
    assert graph["downstream"][0]["product"]["name"] == "电池片"

    assert chain.get_products_by_company("600438.SH")["company"]["stock_code"] == "600438"


def test_invalid_depth_and_relation_writes_are_rejected(tmp_path):
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    (data_dir / "products.json").write_text(
        '[{"name":"A","source":"test"},{"name":"B","source":"test"}]',
        encoding="utf-8",
    )
    (data_dir / "product_relations.json").write_text("[]", encoding="utf-8")
    (data_dir / "company_products.json").write_text("[]", encoding="utf-8")
    chain = IndustryChainV2(data_dir)

    with pytest.raises(ValueError, match="max_depth"):
        chain.get_product_chain("A", max_depth=-1)
    with pytest.raises(ValueError, match="unsupported relation"):
        chain.add_relation("A", "B", "customer", source="test")
    with pytest.raises(ValueError, match="unsupported relation"):
        chain.add_relation("A", "B", "downstream", source="test")
    with pytest.raises(ValueError, match="existing products"):
        chain.add_relation("A", "C", "upstream", source="test")
    with pytest.raises(ValueError, match="source is required"):
        chain.add_relation("A", "B", "upstream")


def test_metadata_count_mismatches_invalidate_dataset(tmp_path):
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    (data_dir / "products.json").write_text(
        '[{"name":"A","source":"test"}]', encoding="utf-8"
    )
    (data_dir / "product_relations.json").write_text("[]", encoding="utf-8")
    (data_dir / "company_products.json").write_text("[]", encoding="utf-8")
    (data_dir / "metadata.json").write_text(
        '{"schema_version":"industry-chain.v2",'
        '"relation_semantics":"directed_supply_edge",'
        '"counts":{"products":2,"relations":0,"companies":0}}',
        encoding="utf-8",
    )

    validation = IndustryChainV2(data_dir).validation
    assert validation["status"] == "INVALID"
    assert "metadata count mismatch for products" in validation["errors"][0]


def test_valid_graph_writes_keep_metadata_counts_in_sync(tmp_path):
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    (data_dir / "products.json").write_text(
        '[{"name":"A","source":"test"},{"name":"B","source":"test"}]',
        encoding="utf-8",
    )
    (data_dir / "product_relations.json").write_text("[]", encoding="utf-8")
    (data_dir / "company_products.json").write_text("[]", encoding="utf-8")
    (data_dir / "metadata.json").write_text(
        '{"schema_version":"industry-chain.v2",'
        '"relation_semantics":"directed_supply_edge",'
        '"counts":{"products":2,"relations":0,"companies":0}}',
        encoding="utf-8",
    )
    chain = IndustryChainV2(data_dir)

    chain.add_relation("A", "B", "upstream", source="test")
    chain.add_company_product("000001", "测试公司", ["A"], source="test")

    assert chain.validation["status"] == "VALID"
    assert chain.metadata["counts"] == {
        "products": 2,
        "relations": 1,
        "companies": 1,
    }


def test_chain_recursion_stops_on_cycles(tmp_path):
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    (data_dir / "products.json").write_text(
        '[{"name":"A"},{"name":"B"}]', encoding="utf-8"
    )
    (data_dir / "product_relations.json").write_text(
        '[{"from":"A","to":"B","relation":"upstream"},'
        '{"from":"B","to":"A","relation":"upstream"}]', encoding="utf-8"
    )
    (data_dir / "company_products.json").write_text("[]", encoding="utf-8")

    chain = IndustryChainV2(data_dir)
    graph = chain.get_product_chain("A", max_depth=10)
    assert graph["downstream"][0]["product"]["name"] == "B"
    assert graph["downstream"][0]["children"] == []
