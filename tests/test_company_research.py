from industry_first_research.company_research import (
    CompanyResearchAssembler,
    CompanyResearchQuery,
)
from industry_first_research.data_sources import (
    DataSourceHealth,
    DataSourceRouter,
    FreeDataSourcePolicy,
)


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


def test_company_research_assembles_partial_snapshot_with_source_lineage():
    router = DataSourceRouter(
        [
            FakeAdapter("eastmoney", error=TimeoutError("rate limit")),
            FakeAdapter("akshare", payload={"name": "通威股份", "close": 20}),
        ],
        FreeDataSourcePolicy(
            listed_company_sources=("eastmoney", "akshare"),
        ),
    )
    snapshot = CompanyResearchAssembler(router).collect(
        CompanyResearchQuery(
            company_id="600438.SH",
            display_name="通威股份",
            industry_id="photovoltaic",
            business_scope=("高纯晶硅",),
            products=(
                {"product": "高纯晶硅", "system_layer": "上游材料"},
            ),
            as_of="2026-07-18",
            identity_query={"required_fields": ["data"]},
            financial_query={},
            quote_query={"required_fields": ["data"]},
        )
    )
    assert snapshot.research_status == "PARTIAL"
    assert snapshot.industry_id == "photovoltaic"
    assert snapshot.products[0]["product"] == "高纯晶硅"
    assert snapshot.identity is not None
    assert snapshot.quote is not None
    assert snapshot.source_results["identity"]["source"] == "akshare"
    assert snapshot.source_results["identity"]["attempts"][0]["status"] == "FAILED"
    assert "financials.query" in snapshot.missing_fields


def test_company_research_preserves_exhausted_source_attempts():
    router = DataSourceRouter(
        [FakeAdapter("eastmoney", error=TimeoutError("offline"))],
        FreeDataSourcePolicy(listed_company_sources=("eastmoney",)),
    )
    snapshot = CompanyResearchAssembler(router).collect(
        CompanyResearchQuery(
            company_id="600438.SH",
            as_of="2026-07-18",
            identity_query={"required_fields": ["data"]},
        )
    )
    lineage = snapshot.source_results["identity"]
    assert lineage["source"] is None
    assert lineage["requested_sources"] == ["eastmoney"]
    assert lineage["attempts"][0]["status"] == "FAILED"
    assert "TimeoutError" in lineage["attempts"][0]["reason"]


def test_company_research_does_not_invent_missing_sections():
    router = DataSourceRouter(
        [FakeAdapter("akshare", payload={"data": []})],
        FreeDataSourcePolicy(listed_company_sources=("akshare",)),
    )
    snapshot = CompanyResearchAssembler(router).collect(
        CompanyResearchQuery(
            company_id="600438.SH",
            as_of="2026-07-18",
            identity_query={"required_fields": ["data"]},
            financial_query={"required_fields": ["data"]},
            quote_query={"required_fields": ["data"]},
        )
    )
    assert snapshot.research_status == "INSUFFICIENT"
    assert snapshot.identity is None
    assert len(snapshot.errors) == 3
