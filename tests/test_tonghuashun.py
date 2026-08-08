from industry_first_research.models import IndustryState
from industry_first_research.tonghuashun import TonghuashunIndustryRadar


HTML = """
<table><thead><tr><th>序号</th><th>板块</th><th>涨跌幅(%)</th></tr></thead>
<tbody>
<tr>
<td>1</td><td><a href="/thshy/detail/code/881145/">电力</a></td>
<td class="c-rise">1.25</td><td>8886.73</td><td>607.09</td><td>45.11</td>
<td>63</td><td>47</td><td>6.83</td><td>珈伟新能</td><td>4.13</td><td>16.01</td>
</tr>
<tr>
<td>2</td><td><a href="/thshy/detail/code/881148/">港口航运</a></td>
<td class="c-fall">-0.41</td><td>1517.43</td><td>100.46</td><td>2.28</td>
<td>11</td><td>23</td><td>6.62</td><td>招商港口</td><td>22</td><td>5.06</td>
</tr>
</tbody></table>
""".encode("gbk")


def test_tonghuashun_html_becomes_traceable_snapshots():
    radar = TonghuashunIndustryRadar(page_size=2, fetcher=lambda url: HTML)

    items = list(radar.snapshots("2026-07-19"))

    assert [item.industry_id for item in items] == ["881145", "881148"]
    assert items[0].display_name == "电力"
    assert items[0].state == IndustryState.CLEARING
    assert items[1].state == IndustryState.DETERIORATING
    assert items[0].signals[0].value == 1.25
    assert "10jqka.com.cn" in items[0].signals[0].source
    assert radar.metadata("2026-07-19")["returned_rows"] == 2
