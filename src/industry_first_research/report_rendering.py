"""Dependency-free Markdown and HTML rendering for immutable research reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
import json
from pathlib import Path
import re
from typing import Any


RESEARCH_RENDER_SCHEMA_VERSION = "research-report-render.v1"
_SUPPORTED_SCHEMAS = {
    "company-research-report.v1",
    "futures-fundamentals-report.v1",
    "futures-fundamentals-tracking.v1",
}


class ReportRenderingError(ValueError):
    """Raised when a structured report cannot be rendered safely."""


def render_research_markdown(report: Mapping[str, Any], *, title: str = "") -> str:
    """Render a company, futures, or futures-tracking report as Markdown."""

    _validate_report(report)
    schema = str(report["schema_version"])
    report_title = title.strip() or _default_title(report)
    lines = [
        f"# {report_title}",
        "",
        f"- 报告类型：`{schema}`",
        f"- 报告时点：`{_value(report.get('as_of') or report.get('research_cutoff') or '')}`",
        f"- 状态：`{_value(report.get('status') or report.get('tracking_status') or 'UNKNOWN')}`",
        "- 自动交易：`false`",
        "",
        "> 本文由不可变研究快照渲染，不改变原始报告、研究结论、决策快照或交易状态。",
        "",
    ]
    if schema == "company-research-report.v1":
        lines.extend(_company_markdown(report))
    elif schema == "futures-fundamentals-report.v1":
        lines.extend(_futures_markdown(report))
    else:
        lines.extend(_futures_tracking_markdown(report))
    return "\n".join(lines).rstrip() + "\n"


def render_research_html(report: Mapping[str, Any], *, title: str = "") -> str:
    """Render the same report as a small standalone HTML document."""

    _validate_report(report)
    schema = str(report["schema_version"])
    report_title = title.strip() or _default_title(report)
    sections = _structured_sections(report)
    body = [
        "<!doctype html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(report_title)}</title>",
        "<style>body{max-width:1100px;margin:0 auto;padding:28px 20px;font-family:-apple-system,BlinkMacSystemFont,\"PingFang SC\",\"Microsoft YaHei\",sans-serif;color:#17202a;background:#f6f7f9;line-height:1.6}main{background:#fff;border:1px solid #dfe3e8;border-radius:6px;padding:26px}h1{margin-top:0;border-left:4px solid #2563eb;padding-left:12px}h2{margin-top:28px;border-bottom:1px solid #e5e7eb;padding-bottom:5px}table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}th,td{border:1px solid #dfe3e8;padding:7px 9px;text-align:left;vertical-align:top}th{background:#f1f5f9}.meta{color:#5f6b7a;font-size:14px}.note{background:#eff6ff;border-left:3px solid #2563eb;padding:10px 14px}code{background:#eef2f7;padding:2px 4px;border-radius:3px}footer{margin-top:30px;color:#6b7280;font-size:13px}</style>",
        "</head><body><main>",
        f"<h1>{escape(report_title)}</h1>",
        f"<p class=\"meta\">报告类型：<code>{escape(schema)}</code>；报告时点：<code>{escape(_value(report.get('as_of') or report.get('research_cutoff') or ''))}</code>；自动交易：<code>false</code></p>",
        "<p class=\"note\">本文由不可变研究快照渲染，不改变原始报告、研究结论、决策快照或交易状态。</p>",
    ]
    for heading, headers, rows in sections:
        body.append(f"<h2>{escape(heading)}</h2>")
        body.append(_html_table(headers, rows))
    body.extend(["<footer>Industry First Research · read-only rendering</footer>", "</main></body></html>"])
    return "\n".join(body) + "\n"


def write_rendered_reports(
    report: Mapping[str, Any],
    output_dir: str | Path,
    *,
    formats: Sequence[str] = ("markdown", "html"),
    title: str = "",
    basename: str = "",
) -> dict[str, str]:
    """Write deterministic derived files and return their paths."""

    _validate_report(report)
    selected = [str(value).lower() for value in formats]
    invalid = set(selected) - {"markdown", "html"}
    if not selected or invalid:
        raise ReportRenderingError("formats must contain markdown and/or html")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    name = _safe_name(basename.strip() or _report_id(report))
    result: dict[str, str] = {}
    if "markdown" in selected:
        path = root / f"{name}.md"
        path.write_text(render_research_markdown(report, title=title), encoding="utf-8")
        result["markdown"] = str(path)
    if "html" in selected:
        path = root / f"{name}.html"
        path.write_text(render_research_html(report, title=title), encoding="utf-8")
        result["html"] = str(path)
    return result


def _validate_report(report: Any) -> None:
    if not isinstance(report, Mapping):
        raise ReportRenderingError("report must be an object")
    schema = str(report.get("schema_version") or "")
    if schema not in _SUPPORTED_SCHEMAS:
        raise ReportRenderingError(f"unsupported report schema: {schema or '<empty>'}")


def _default_title(report: Mapping[str, Any]) -> str:
    schema = str(report.get("schema_version") or "")
    if schema == "company-research-report.v1":
        return "公司研究报告"
    if schema == "futures-fundamentals-report.v1":
        return f"期货基本面报告：{report.get('variety_name') or report.get('variety_id') or '未知品种'}"
    return f"期货持续跟踪：{report.get('variety_id') or '未知品种'}"


def _company_markdown(report: Mapping[str, Any]) -> list[str]:
    lines = ["## 公司研究摘要", ""]
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if not items:
        return lines + ["本报告没有公司条目，无法生成公司层结论。", ""]
    for item in items:
        if not isinstance(item, Mapping):
            continue
        company_id = str(item.get("company_id") or "unknown")
        lines.extend([
            f"### {company_id}",
            "",
            f"- 报告状态：`{_value(item.get('report_state') or item.get('status') or 'UNKNOWN')}`",
            f"- 结论状态：`{_value(item.get('conclusion_state') or 'UNKNOWN')}`",
            "",
        ])
        recommendation = item.get("simulation_recommendation")
        if isinstance(recommendation, Mapping):
            lines.extend(
                [
                    "#### 模拟决策建议",
                    "",
                    f"- 状态：`{_value(recommendation.get('state'))}`",
                    f"- 建议动作：`{_value(recommendation.get('recommended_action'))}`",
                    f"- 可选动作：`{_value(recommendation.get('available_actions'))}`",
                    f"- 方向：`{_value(recommendation.get('direction'))}`",
                    f"- 下次复查：`{_value(recommendation.get('next_check_at'))}`",
                    f"- 依据：{_value(recommendation.get('reasons'))}",
                    f"- 数据缺口：{_value(recommendation.get('data_gaps'))}",
                    f"- 失效条件：{_value(recommendation.get('invalidators'))}",
                    "",
                ]
            )
        sections = item.get("sections") if isinstance(item.get("sections"), Mapping) else {}
        for name, section in sections.items():
            if not isinstance(section, Mapping):
                continue
            lines.append(f"#### {name}")
            lines.append("")
            facts = section.get("facts") if isinstance(section.get("facts"), Mapping) else {}
            if facts:
                lines.extend(["| 字段 | 状态 | 值 | 证据 |", "|---|---|---|---|"])
                for field, value in facts.items():
                    value = value if isinstance(value, Mapping) else {"values": value}
                    lines.append(
                        f"| {field} | {_value(value.get('status'))} | {_value(value.get('values'))} | {_value(value.get('evidence_ids'))} |"
                    )
                lines.append("")
            unknowns = section.get("unknowns") or []
            if unknowns:
                lines.append("缺口：" + "、".join(str(value) for value in unknowns))
                lines.append("")
        tracking = item.get("tracking_checklist")
        if isinstance(tracking, Mapping):
            lines.extend(["#### 跟踪清单", "", f"- 状态：`{_value(tracking.get('status'))}`", f"- 下次复查：`{_value(tracking.get('next_check_at'))}`", ""])
    return lines


def _futures_markdown(report: Mapping[str, Any]) -> list[str]:
    lines = ["## 期货研究摘要", "", "| 项目 | 内容 |", "|---|---|"]
    for key in ("exchange", "variety_id", "variety_name", "object_type", "identity_status", "status"):
        lines.append(f"| {key} | {_value(report.get(key))} |")
    lines.extend(["", "## 品种与合约状态", ""])
    for name in ("variety_view", "contract_view", "simulation_view"):
        value = report.get(name)
        if isinstance(value, Mapping):
            lines.append(f"- `{name}`：状态 `{_value(value.get('status'))}`；判断 `{_value(value.get('judgment') or value.get('direction'))}`")
    lines.extend(["", "## 派生指标", "", "| 指标 | 当前值 |", "|---|---|"])
    metrics = report.get("derived_metrics") if isinstance(report.get("derived_metrics"), Mapping) else {}
    for key, value in metrics.items():
        lines.append(f"| {key} | {_value(value)} |")
    scenarios = report.get("price_scenarios") if isinstance(report.get("price_scenarios"), Mapping) else {}
    lines.extend(["", "## 价格情景", "", "| 情景 | 状态 | 区间 |", "|---|---|---|"])
    items = scenarios.get("scenarios") if isinstance(scenarios.get("scenarios"), Mapping) else {}
    for key, value in items.items():
        value = value if isinstance(value, Mapping) else {}
        lines.append(f"| {key} | {_value(value.get('status'))} | {_value(value.get('range'))} |")
    gaps = report.get("evidence_gaps") or []
    lines.extend(["", "## 证据缺口", "", "- " + ("；".join(_value(item) for item in gaps) if gaps else "无显式缺口"), ""])
    return lines


def _futures_tracking_markdown(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "## 期货持续跟踪",
        "",
        f"- 跟踪状态：`{_value(report.get('tracking_status'))}`",
        f"- 当前报告：`{_value(report.get('current_report_id'))}`（{_value(report.get('current_report_as_of'))}）",
        f"- 上一报告：`{_value(report.get('previous_report_id') or '无')}`（{_value(report.get('previous_report_as_of') or '无')}）",
        f"- 待复核：`{_value(report.get('review_required'))}`",
        f"- 受影响模块：`{_value(report.get('affected_modules') or [])}`",
        f"- 决策复核：`{_value((report.get('decision_review') or {}).get('status') if isinstance(report.get('decision_review'), Mapping) else '')}`",
        "",
        "| 区域 | 字段 | 上一值 | 当前值 |",
        "|---|---|---|---|",
    ]
    for change in report.get("changes") or []:
        if isinstance(change, Mapping):
            lines.append(f"| {_value(change.get('area'))} | {_value(change.get('key'))} | {_value(change.get('previous'))} | {_value(change.get('current'))} |")
    if not report.get("changes"):
        lines.append("| - | 无变化 | - | - |")
    lines.extend(["", "## 当前状态", "", "```json", _json(report.get("current_state") or {}), "```", ""])
    return lines


def _structured_sections(report: Mapping[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    schema = str(report["schema_version"])
    sections: list[tuple[str, list[str], list[list[str]]]] = []
    if schema == "company-research-report.v1":
        items = report.get("items") if isinstance(report.get("items"), list) else []
        rows = []
        recommendation_rows = []
        for item in items:
            if isinstance(item, Mapping):
                rows.append([str(item.get("company_id") or ""), str(item.get("report_state") or item.get("status") or ""), str(item.get("conclusion_state") or "")])
                recommendation = item.get("simulation_recommendation")
                if isinstance(recommendation, Mapping):
                    recommendation_rows.append(
                        [
                            str(item.get("company_id") or ""),
                            _value(recommendation.get("state")),
                            _value(recommendation.get("recommended_action")),
                            _value(recommendation.get("available_actions")),
                            _value(recommendation.get("direction")),
                            _value(recommendation.get("next_check_at")),
                        ]
                    )
        sections.append(("公司条目", ["公司", "报告状态", "结论状态"], rows or [["-", "无条目", "-"]]))
        sections.append(
            (
                "模拟决策建议",
                ["公司", "状态", "建议动作", "可选动作", "方向", "下次复查"],
                recommendation_rows or [["-", "无建议", "-", "-", "NEUTRAL", "未知"]],
            )
        )
    elif schema == "futures-fundamentals-report.v1":
        sections.append(("期货对象", ["项目", "内容"], [[key, _value(report.get(key))] for key in ("exchange", "variety_id", "variety_name", "object_type", "status")]))
        metrics = report.get("derived_metrics") if isinstance(report.get("derived_metrics"), Mapping) else {}
        sections.append(("派生指标", ["指标", "当前值"], [[str(key), _value(value)] for key, value in metrics.items()] or [["-", "无指标"]]))
    else:
        changes = report.get("changes") if isinstance(report.get("changes"), list) else []
        sections.append(("期货跟踪变化", ["区域", "字段", "上一值", "当前值"], [[_value(item.get("area")), _value(item.get("key")), _value(item.get("previous")), _value(item.get("current"))] for item in changes if isinstance(item, Mapping)] or [["-", "无变化", "-", "-"]]))
        review = report.get("decision_review") if isinstance(report.get("decision_review"), Mapping) else {}
        sections.append(
            (
                "决策复核入口",
                ["项目", "内容"],
                [
                    ["状态", _value(review.get("status"))],
                    ["受影响模块", _value(review.get("affected_modules") or report.get("affected_modules") or [])],
                    ["复核动作", _value(review.get("actions") or [])],
                    ["需要用户确认", _value(review.get("user_confirmation_required"))],
                ],
            )
        )
    sections.append(("策略边界", ["项目", "状态"], [["directional_conclusion", "false"], ["investment_conclusion", "false"], ["execution_enabled", "false"]]))
    return sections


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{escape(str(value))}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _report_id(report: Mapping[str, Any]) -> str:
    return str(report.get("report_id") or report.get("tracking_id") or "research-report")


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-") or "research-report"


def _value(value: Any) -> str:
    if value is None or value == "":
        return "未知"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
