from industry_first_research.models import CompanyCandidate, CompanyDataTier
from industry_first_research.tonghuashun_light_data import TonghuashunLightCompanyData


HTML = """
<html><head><title>珈伟新能(300317)最新动态</title></head><body>
<span class="main-bussiness-text"><a>新能源发电相关业务及光伏消费产品的研发、生产与销售。</a></span>
<span id="companyInfoName">深圳珈伟新能源股份有限公司</span>
<span id="companyInfoIndustry">电力</span>
<span id="companyInfoMarket">深圳证券交易所</span>
</body></html>
""".encode("gbk")


def candidate():
    return CompanyCandidate("300317", "珈伟新能", "881145", source="pool")


def test_light_data_extracts_source_bound_profile():
    provider = TonghuashunLightCompanyData(fetcher=lambda url: HTML)

    result = provider.enrich([candidate()], CompanyDataTier.LIGHT)[0]

    assert result.data_tier == CompanyDataTier.LIGHT
    assert result.light_profile["status"] == "VERIFIED"
    assert result.light_profile["legal_name"] == "深圳珈伟新能源股份有限公司"
    assert "新能源发电" in result.light_profile["main_business"]
    assert result.light_profile["reported_industry"] == "电力"
    assert result.light_profile["listing_market"] == "深圳证券交易所"
    assert result.light_profile["read_only"] is True


def test_light_data_downgrades_missing_fields_and_fetch_failure():
    partial_html = "<html><head><title>珈伟新能(300317)</title></head></html>".encode("gbk")
    partial = TonghuashunLightCompanyData(fetcher=lambda url: partial_html)
    failed = TonghuashunLightCompanyData(fetcher=lambda url: (_ for _ in ()).throw(OSError("offline")))

    partial_result = partial.enrich([candidate()], CompanyDataTier.LIGHT)[0]
    failed_result = failed.enrich([candidate()], CompanyDataTier.LIGHT)[0]

    assert partial_result.light_profile["status"] == "PARTIAL"
    assert partial_result.light_profile["legal_name"] == "珈伟新能"
    assert failed_result.light_profile["status"] == "UNAVAILABLE"
    assert failed_result.data_tier == CompanyDataTier.LIGHT


def test_light_data_extracts_labeled_adjacent_shenwan_industry_value():
    page_html = """
    <tr>
      <td><span class="hltip f12 fl">主营业务：</span>
        <span class="tip f14 fl main-bussiness-text">新能源发电</span>
      </td>
      <td><span class="hltip f12 f1">所属申万行业：</span>
        <span class="tip f14">电力</span>
      </td>
    </tr>
    """.encode("gbk")
    provider = TonghuashunLightCompanyData(fetcher=lambda url: page_html)

    result = provider.enrich([candidate()], CompanyDataTier.LIGHT)[0]

    assert result.light_profile["reported_industry"] == "电力"
    assert "reported_industry" in result.light_profile["available_fields"]


def test_light_adapter_does_not_claim_higher_tiers():
    provider = TonghuashunLightCompanyData(fetcher=lambda url: HTML)

    result = provider.enrich([candidate()], CompanyDataTier.DEEP)[0]

    assert result.light_profile == {}
    assert result.data_tier == CompanyDataTier.LIGHT
