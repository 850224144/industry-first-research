from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)
from industry_first_research.industry_radar import IndustryRadarCollector
from industry_first_research.config import load_radar_config


class FakeAdapter:
    def __init__(self, name, payload=None, error=None):
        self.name = name
        self.payload = payload
        self.error = error

    def health_check(self):
        return DataSourceHealth(self.name, "test", True)

    def fetch(self, query, as_of):
        if self.error:
            raise self.error
        return {"source": self.name, "data": self.payload, "as_of": as_of}

    def normalize(self, value):
        return value


def test_industry_radar_routes_each_signal_without_loading_companies():
    router = DataSourceRouter(
        [
            FakeAdapter("primary", error=TimeoutError("offline")),
            FakeAdapter("backup", payload={"inventory": "falling"}),
        ],
        FreeDataSourcePolicy(industry_sources=("primary", "backup")),
    )
    config = {
        "industry_id": "generic-materials",
        "display_name": "通用材料行业",
        "as_of": "2026-07-18",
        "state": "INFLECTION_CANDIDATE",
        "radar_queries": [
            {
                "name": "inventory",
                "query": {
                    "required_fields": ["data"],
                    "source_queries": {"primary": {}, "backup": {}},
                },
                "value_path": "data.inventory",
                "source_names": ["primary", "backup"],
            }
        ],
    }

    collection = IndustryRadarCollector(router).collect(config)

    assert collection.collection_status == "READY"
    assert collection.snapshot.signals[-1].value == "falling"
    assert collection.source_results["inventory"]["source"] == "backup"
    assert [
        attempt["status"]
        for attempt in collection.source_results["inventory"]["attempts"]
    ] == ["FAILED", "SUCCESS"]
    assert collection.to_dict()["resource_audit"] == {
        "industry_signal_query_count": 1,
        "company_pool_loaded": False,
        "company_deep_data_loaded": False,
        "full_market_deep_data": False,
    }


def test_industry_radar_preserves_failed_signal_attempts():
    router = DataSourceRouter(
        [FakeAdapter("primary", error=ConnectionError("offline"))],
        FreeDataSourcePolicy(industry_sources=("primary",)),
    )
    config = {
        "industry_id": "generic-materials",
        "display_name": "通用材料行业",
        "as_of": "2026-07-18",
        "state": "INSUFFICIENT",
        "radar_queries": [
            {
                "name": "price",
                "query": {
                    "required_fields": ["data"],
                    "source_queries": {"primary": {}},
                },
                "source_names": ["primary"],
            }
        ],
    }

    collection = IndustryRadarCollector(router).collect(config)

    assert collection.collection_status == "INSUFFICIENT"
    assert collection.missing_signals == ["price"]
    assert collection.source_results["price"]["attempts"][0]["status"] == "FAILED"
    assert collection.source_results["price"]["attempts"][0]["reason"].startswith(
        "ConnectionError"
    )


def test_industry_radar_without_queries_is_static_only():
    router = DataSourceRouter([], FreeDataSourcePolicy(industry_sources=()))
    config = {
        "industry_id": "static-industry",
        "display_name": "静态行业",
        "as_of": "2026-07-18",
        "state": "INSUFFICIENT",
    }

    collection = IndustryRadarCollector(router).collect(config)

    assert collection.collection_status == "STATIC_ONLY"
    assert collection.configured_query_count == 0


def test_radar_loader_does_not_require_company_pool(tmp_path):
    path = tmp_path / "radar.json"
    path.write_text(
        '{"industry_id":"generic","display_name":"通用行业",'
        '"as_of":"2026-07-18","state":"INSUFFICIENT",'
        '"radar_queries":[]}',
        encoding="utf-8",
    )

    config = load_radar_config(path)

    assert "companies" not in config
