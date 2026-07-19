from industry_first_research.models import IndustryRadarSnapshot, IndustryState
from industry_first_research.tonghuashun_company_pool import TonghuashunCompanyPool


HTML = """
<table><thead><tr><th>序号</th><th>代码</th><th>名称</th><th>现价</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href="http://stockpage.10jqka.com.cn/300317/">300317</a></td>
<td><a href="http://stockpage.10jqka.com.cn/300317">珈伟新能</a></td><td>4.13</td></tr>
<tr><td>2</td><td><a href="http://stockpage.10jqka.com.cn/600236/">600236</a></td>
<td><a href="http://stockpage.10jqka.com.cn/600236">桂冠电力</a></td><td>10.62</td></tr>
<tr><td>3</td><td><a href="http://stockpage.10jqka.com.cn/000037/">000037</a></td>
<td><a href="http://stockpage.10jqka.com.cn/000037">深南电A</a></td><td>9.20</td></tr>
</tbody></table>
""".encode("gbk")


def industry():
    return IndustryRadarSnapshot(
        industry_id="881145",
        display_name="电力",
        as_of="2026-07-19",
        state=IndustryState.CLEARING,
    )


def test_company_pool_is_bounded_and_traceable():
    provider = TonghuashunCompanyPool(page_size=2, fetcher=lambda url: HTML)

    result = provider.candidates(industry(), limit=30)

    assert [item.company_id for item in result] == ["300317", "600236"]
    assert result[0].display_name == "珈伟新能"
    assert result[0].industry_id == "881145"
    assert result[0].data_tier.value == "LIGHT"
    assert result[0].source.startswith("http://stockpage.10jqka.com.cn/")
    assert provider.metadata()["visible_table_only"] is True
    assert provider.metadata()["full_industry_membership_loaded"] is False


def test_company_pool_uses_source_specific_id_from_cross_source_snapshot():
    cross_industry = industry().__class__(
        industry_id="BK1565",
        display_name="电力",
        as_of="2026-07-19",
        state=IndustryState.CLEARING,
        source_ids={"eastmoney": "BK1565", "tonghuashun": "881145"},
    )
    seen_urls = []
    provider = TonghuashunCompanyPool(
        page_size=1,
        fetcher=lambda url: seen_urls.append(url) or HTML,
    )

    provider.candidates(cross_industry, limit=1)

    assert "/detail/code/881145/" in seen_urls[0]
    assert provider.metadata()["requested_industry_id"] == "BK1565"
    assert provider.metadata()["resolved_tonghuashun_industry_id"] == "881145"
