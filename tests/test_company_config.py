from pathlib import Path

from industry_first_research.config import load_company_config


ROOT = Path(__file__).parents[1]


def test_tongwei_company_config_has_product_and_source_queries():
    config = load_company_config(ROOT / "config/companies/600438.json")
    assert config["company_id"] == "600438.SH"
    assert len(config["products"]) == 2
    assert config["financial_query"]["source_queries"]["eastmoney"]["url"].startswith(
        "https://"
    )
    assert "baostock" in config["quote_query"]["source_queries"]
