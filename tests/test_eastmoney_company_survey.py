import json

from industry_first_research.eastmoney_company_survey import (
    EastmoneyCompanySurveyData,
)
from industry_first_research.models import CompanyCandidate, CompanyDataTier


def candidate(profile=None):
    return CompanyCandidate(
        "300317",
        "珈伟新能",
        "881145",
        source="https://basic.10jqka.com.cn/300317/",
        light_profile=profile or {
            "status": "PARTIAL",
            "legal_name": "珈伟新能源股份有限公司",
            "main_business": "新能源发电相关业务",
            "reported_industry": "电力",
            "available_fields": ["legal_name", "main_business", "reported_industry"],
        },
    )


def survey_payload(company_id="300317", market="深圳证券交易所"):
    return json.dumps(
        {"jbzl": {"agdm": company_id, "gsmc": "珈伟新能源股份有限公司", "ssjys": market}},
        ensure_ascii=False,
    ).encode("utf-8")


def test_eastmoney_survey_fills_missing_listing_market_with_field_source():
    seen_urls = []

    def fetcher(url):
        seen_urls.append(url)
        if "SZ300317" in url:
            return survey_payload()
        return survey_payload(company_id="000000", market="")

    provider = EastmoneyCompanySurveyData(fetcher=fetcher)
    result = provider.enrich([candidate()], CompanyDataTier.LIGHT)[0]

    assert result.light_profile["listing_market"] == "深圳证券交易所"
    assert result.light_profile["status"] == "VERIFIED"
    assert result.light_profile["field_sources"]["listing_market"].startswith(
        "https://emweb.securities.eastmoney.com/"
    )
    assert result.light_profile["additional_sources"]
    assert seen_urls[0].endswith("code=SZ300317")


def test_eastmoney_survey_rejects_code_mismatch_without_filling_value():
    provider = EastmoneyCompanySurveyData(
        market_codes=["SZ"], fetcher=lambda url: survey_payload(company_id="000001")
    )

    result = provider.enrich([candidate()], CompanyDataTier.LIGHT)[0]

    assert "listing_market" not in result.light_profile
    assert result.light_profile["status"] == "PARTIAL"


def test_eastmoney_survey_does_not_change_non_light_tiers():
    provider = EastmoneyCompanySurveyData(fetcher=lambda url: survey_payload())

    result = provider.enrich([candidate()], CompanyDataTier.DEEP)[0]

    assert result.light_profile["status"] == "PARTIAL"
    assert "listing_market" not in result.light_profile
