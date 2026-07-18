"""Human-readable report output for an industry-first scan."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from html import escape

from .models import ScanResult


def render_scan_markdown(
    result: ScanResult,
    config: dict[str, Any],
    source_documents: Iterable[dict[str, Any]] = (),
) -> str:
    selected = result.selected_industries
    industry = selected[0] if selected else None
    assessments = (
        result.industry_opportunity_assessments.get(industry.industry_id, {})
        if industry
        else {}
    )
    lines = [
        f"# 行业优先研究：{config['display_name']}",
        "",
        f"*研究时点：{result.as_of} | 执行模式：LOCAL_ASSET_REUSE | 自动交易：关闭*",
        "",
        "> 本报告是行业雷达与本地研究资产适配的第一版输出，不把研究报告、网页 AI 回答或模型观点直接当作事实。关键数字仍需回到原始公告、正式统计或独立来源核验。",
        "",
        "## 结论先行",
        "",
    ]
    if industry is None:
        lines.extend(
            [
                "本期没有行业通过行业雷达门槛，因此不建立公司深研池。",
                "",
            ]
        )
    else:
        deep_count = sum(len(items) for items in result.company_pools.values())
        lines.extend(
            [
                f"- **行业状态**：`{industry.state.value}`。{industry.reason}",
                f"- **机会类型**：{', '.join(industry.opportunity_types) or '未标记'}。",
                f"- **公司深研结果**：本轮保留 {deep_count} 家，淘汰/阻断 {len(result.rejected_companies)} 家；来源为配置化公司池和本地研究资产，不代表已经完成投资结论。",
                "- **下一步**：对入选公司补充原始公告、财务口径、产品盈利来源、渠道/客户验证和估值，再决定是否建立模拟决策快照。",
                "",
            ]
        )

    lines.extend(["## 行业雷达", ""])
    if industry is None:
        lines.append("本期无入选行业。淘汰行业：" + ", ".join(result.rejected_industries))
    else:
        lines.extend(
            [
                f"- **状态**：`{industry.state.value}`",
                f"- **证据完整度**：`{industry.evidence_completeness}`",
                f"- **数据时点**：{industry.as_of}",
                "",
                "| 信号 | 当前值 | 来源 | 证据状态 |",
                "|---|---|---|---|",
            ]
        )
        for signal in industry.signals:
            lines.append(
                f"| {signal.name} | {signal.value} | {signal.source} | {signal.evidence_status} |"
            )

    lines.extend(["", "## 公司池与资源审计", ""])
    if result.empty_result and industry is not None:
        lines.extend(["本期行业通过雷达，但没有公司进入深研层；这是合法的空结果，不代表行业内没有公司。", ""])
    lines.extend(
        [
            "| 行业 | 公司 | 数据层级 | 初筛分数 | 闸门 | 来源 |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for industry_id, candidates in result.company_pools.items():
        for candidate in candidates:
            lines.append(
                f"| {industry_id} | {candidate.display_name} ({candidate.company_id}) | {candidate.data_tier.value} | "
                f"{candidate.score if candidate.score is not None else '未知'} | {candidate.hard_gate_status} | {candidate.source} |"
            )
    for candidate in result.rejected_companies:
        lines.append(
            f"| {candidate.industry_id} | {candidate.display_name} ({candidate.company_id}) | REJECTED | "
            f"{candidate.score if candidate.score is not None else '未知'} | {candidate.hard_gate_status} | {candidate.source} |"
        )
    if not result.company_pools and not result.rejected_companies:
        lines.append("| - | 本期没有公司池记录 | - | - | - | - |")
    lines.extend(["", "## 机会规则审计", ""])
    lines.extend([
        "| 机会类型 | 状态 | 分数 | 已知理由 | 缺失证据 |",
        "|---|---|---:|---|---|",
    ])
    for opportunity_type, assessment in assessments.items():
        lines.append(
            f"| {opportunity_type} | {assessment.get('status', 'UNKNOWN')} | "
            f"{assessment.get('score', 0)} | {'；'.join(assessment.get('reasons', [])) or '-'} | "
            f"{'；'.join(assessment.get('missing', [])) or '-'} |"
        )
    if not assessments:
        lines.append("| - | 未执行 | 0 | 没有入选行业 | - |")
    lines.extend(["", "## 公司机会筛选审计", ""])
    lines.extend([
        "| 公司 | 机会类型 | 状态 | 分数 | 已知理由 | 缺失证据 |",
        "|---|---|---|---:|---|---|",
    ])
    company_candidates = [
        candidate
        for candidates in result.company_pools.values()
        for candidate in candidates
    ] + result.rejected_companies
    for candidate in company_candidates:
        company_assessments = candidate.metadata.get("opportunity_assessments", {})
        for opportunity_type, assessment in company_assessments.items():
            lines.append(
                f"| {candidate.display_name} | {opportunity_type} | "
                f"{assessment.get('status', 'UNKNOWN')} | {assessment.get('score', 0)} | "
                f"{'；'.join(assessment.get('reasons', [])) or '-'} | "
                f"{'；'.join(assessment.get('missing', [])) or '-'} |"
            )
    if not company_candidates:
        lines.append("| - | - | 未执行 | 0 | 没有公司进入公司池 | - |")
    lines.extend(
        [
            "",
            "```json",
            _json_dump(result.resource_audit),
            "```",
            "",
            "## 本地研究资产",
            "",
        ]
    )
    for source in source_documents:
        path = source.get("path", "")
        label = source.get("title", path)
        level = source.get("level", "UNKNOWN")
        url = source.get("url")
        location = f"[{label}]({url})" if url else f"`{label}`"
        lines.append(f"- {location}：{level}；{source.get('role', '研究参考资料')}。")
    lines.extend(["", "### 公司研究资产状态", ""])
    for industry_id, candidates in result.company_pools.items():
        for candidate in candidates:
            summary = candidate.metadata.get("asset_summary", {})
            lines.append(
                f"- {candidate.display_name}：已配置 {summary.get('configured', 0)} 项，存在 {summary.get('existing', 0)} 项，已解析 {summary.get('parsed', 0)} 项，完整={summary.get('complete', False)}。"
            )
    if not result.company_pools:
        lines.append("- 本轮没有进入深研层的公司，因此没有公司研究资产状态。")
    lines.extend(
        [
            "",
            "## 反证与限制",
            "",
            "- 行业状态来自配置化快照，不能替代实时数据源；公开报告中的数字可能有统计口径、发布日期和更正问题。",
            "- 公司池是代表性研究池，不是全市场主数据；未进入公司池不等于公司被否定。",
            "- 研究资产和网页 AI 线索只能帮助缩小范围；未经核验的内容不能升级为 `CANDIDATE`、`REVIEWABLE` 或模拟决策理由。",
            "- 本输出不构成投资建议，不执行真实交易。",
            "",
        ]
    )
    return "\n".join(lines)


def render_scan_html(
    result: ScanResult,
    config: dict[str, Any],
    source_documents: Iterable[dict[str, Any]] = (),
) -> str:
    """Render the same scan payload as a small dependency-free HTML report."""

    selected = result.selected_industries
    industry = selected[0] if selected else None
    title = escape(f"行业优先研究：{config['display_name']}")
    assessment_summary = (
        result.industry_opportunity_assessments.get(industry.industry_id, {})
        if industry
        else {}
    )
    if industry is None:
        conclusion = "本期没有行业通过行业雷达门槛，因此不建立公司深研池。"
        radar_rows = "<tr><td colspan=\"4\">本期无入选行业</td></tr>"
    else:
        conclusion = (
            f"行业状态为 <strong>{escape(industry.state.value)}</strong>。"
            f"{escape(industry.reason)}"
        )
        radar_rows = "".join(
            "<tr>"
            f"<td>{escape(signal.name)}</td>"
            f"<td>{escape(str(signal.value))}</td>"
            f"<td>{escape(signal.source)}</td>"
            f"<td>{escape(signal.evidence_status)}</td>"
            "</tr>"
            for signal in industry.signals
        ) or "<tr><td colspan=\"4\">没有行业信号</td></tr>"

    company_rows: list[str] = []
    for industry_id, candidates in result.company_pools.items():
        for candidate in candidates:
            company_rows.append(
                "<tr>"
                f"<td>{escape(industry_id)}</td>"
                f"<td>{escape(candidate.display_name)} ({escape(candidate.company_id)})</td>"
                f"<td>{escape(candidate.data_tier.value)}</td>"
                f"<td>{escape(str(candidate.score if candidate.score is not None else '未知'))}</td>"
                f"<td>{escape(candidate.hard_gate_status)}</td>"
                f"<td>{escape(candidate.source)}</td>"
                "</tr>"
            )
    for candidate in result.rejected_companies:
        company_rows.append(
            "<tr class=\"rejected\">"
            f"<td>{escape(candidate.industry_id)}</td>"
            f"<td>{escape(candidate.display_name)} ({escape(candidate.company_id)})</td>"
            "<td>REJECTED</td>"
            f"<td>{escape(str(candidate.score if candidate.score is not None else '未知'))}</td>"
            f"<td>{escape(candidate.hard_gate_status)}</td>"
            f"<td>{escape(candidate.source)}</td>"
            "</tr>"
        )
    if not company_rows:
        message = "行业通过雷达，但没有进入深研层的公司" if industry else "没有进入深研层的公司"
        company_rows.append(f"<tr><td colspan=\"6\">{message}</td></tr>")

    source_items = []
    for source in source_documents:
        label = escape(source.get("title", source.get("path", "研究资料")))
        level = escape(source.get("level", "UNKNOWN"))
        url = source.get("url")
        link = f'<a href="{escape(url, quote=True)}">查看来源</a>' if url else "本地参考"
        source_items.append(f"<li><strong>{label}</strong>：{level}；{link}</li>")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ max-width: 980px; margin: 0 auto; padding: 32px 20px; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; color: #17202a; background: #f6f7f9; line-height: 1.7; }}
main {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 28px; }}
h1 {{ margin-top: 0; border-left: 4px solid #2563eb; padding-left: 12px; }}
h2 {{ margin-top: 32px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }}
.meta, .note {{ color: #5f6b7a; font-size: 14px; }}
.conclusion {{ background: #eff6ff; border-left: 3px solid #2563eb; padding: 12px 16px; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
th, td {{ border: 1px solid #dfe3e8; padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #f1f5f9; }}
tr.rejected {{ background: #fff7ed; color: #7c2d12; }}
code {{ background: #eef2f7; padding: 2px 4px; border-radius: 3px; }}
footer {{ margin-top: 32px; color: #6b7280; font-size: 13px; }}
</style>
</head>
<body><main>
<h1>{title}</h1>
<p class="meta">研究时点：{escape(result.as_of)} | 执行模式：LOCAL_ASSET_REUSE | 自动交易：关闭</p>
<p class="note">本报告是行业雷达与本地研究资产适配的第一版输出。研究资产和网页 AI 线索不自动升级为事实。</p>
<h2>结论先行</h2>
<p class="conclusion">{conclusion}</p>
<ul>
<li>机会类型：{escape(', '.join(industry.opportunity_types) if industry else '未标记')}</li>
<li>进入深研层公司：{sum(len(items) for items in result.company_pools.values())} 家</li>
<li>全市场深度数据：<code>false</code></li>
</ul>
<h2>行业雷达</h2>
<table><thead><tr><th>信号</th><th>当前值</th><th>来源</th><th>证据状态</th></tr></thead><tbody>{radar_rows}</tbody></table>
<h2>公司池与资源审计</h2>
<table><thead><tr><th>行业</th><th>公司</th><th>层级</th><th>分数</th><th>闸门</th><th>来源</th></tr></thead><tbody>{''.join(company_rows)}</tbody></table>
<pre>{escape(_json_dump(result.resource_audit))}</pre>
<h2>机会规则审计</h2>
<table><thead><tr><th>机会类型</th><th>状态</th><th>分数</th><th>理由</th><th>缺失证据</th></tr></thead><tbody>{_assessment_rows_html(assessment_summary)}</tbody></table>
<h2>本地研究资产</h2>
<ul>{''.join(source_items) or '<li>未配置来源</li>'}</ul>
<h2>反证与限制</h2>
<ul>
<li>公司池是代表性研究池，不是全市场主数据。</li>
<li>未经核验的资料不能升级为候选状态或模拟决策理由。</li>
<li>本输出不构成投资建议，不执行真实交易。</li>
</ul>
<footer>Industry First Research</footer>
</main></body></html>
"""


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _assessment_rows_html(assessments: dict[str, Any]) -> str:
    if not assessments:
        return '<tr><td colspan="5">没有入选行业，未执行行业机会规则</td></tr>'
    return "".join(
        "<tr>"
        f"<td>{escape(opportunity_type)}</td>"
        f"<td>{escape(str(assessment.get('status', 'UNKNOWN')))}</td>"
        f"<td>{escape(str(assessment.get('score', 0)))}</td>"
        f"<td>{escape('；'.join(assessment.get('reasons', [])) or '-')}</td>"
        f"<td>{escape('；'.join(assessment.get('missing', [])) or '-')}</td>"
        "</tr>"
        for opportunity_type, assessment in assessments.items()
    )
