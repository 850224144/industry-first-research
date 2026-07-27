"""Versioned, local-only templates for parsing public disclosures.

Templates describe where a field may be found.  They do not fetch a URL and
they do not decide whether an announcement supports an investment conclusion.
The parser accepts a user-provided JSON, HTML, or text snapshot and produces
the existing ``original-announcement-input.v1`` envelope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any


TEMPLATE_CATALOG_SCHEMA_VERSION = "announcement-template-catalog.v1"
TEMPLATE_SCHEMA_VERSION = "announcement-template.v1"
TEMPLATE_INPUT_SCHEMA_VERSION = "announcement-template-input.v1"
PARSE_ATTEMPT_SCHEMA_VERSION = "announcement-parse-attempt.v1"
ANNOUNCEMENT_INPUT_SCHEMA_VERSION = "original-announcement-input.v1"
RULE_VERSION = "announcement-template-rules.v1"

_FORMATS = {"json", "html", "text"}
_STATUSES = {"READY", "DEGRADED", "BLOCKED"}
_CORRECTION_STATUSES = {"ORIGINAL", "CORRECTED", "SUPPLEMENT", "WITHDRAWN"}
_SUBJECT_TYPES = {"listed_company", "industry", "futures_variety", "futures_contract"}


class AnnouncementTemplateError(ValueError):
    """Raised when a template or local disclosure snapshot is malformed."""


class _HtmlCapture(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.elements: dict[str, str] = {}
        self._element_stack: list[tuple[str, str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "meta":
            name = attributes.get("name") or attributes.get("property") or attributes.get("itemprop")
            content = attributes.get("content", "").strip()
            if name and content:
                self.meta[name.lower()] = content
        if tag.lower() == "title":
            self._in_title = True
            self._title_parts = []
        identifier = attributes.get("id") or attributes.get("data-field")
        if identifier:
            self._element_stack.append((tag.lower(), identifier.lower(), []))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title" and self._in_title:
            self.title = _clean_text(" ".join(self._title_parts))
            self._in_title = False
        if self._element_stack and self._element_stack[-1][0] == lowered:
            _, identifier, parts = self._element_stack.pop()
            self.elements[identifier] = _clean_text(" ".join(parts))

    def handle_data(self, data: str) -> None:
        text = _clean_text(data)
        if not text:
            return
        self.text_parts.append(text)
        if self._in_title:
            self._title_parts.append(text)
        if self._element_stack:
            self._element_stack[-1][2].append(text)

    @property
    def text(self) -> str:
        return _clean_text("\n".join(self.text_parts))


def load_template_catalog(path: str | Path) -> dict[str, Any]:
    """Load and validate a checked-in template catalog."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AnnouncementTemplateError(f"cannot read template catalog: {error}") from error
    return validate_template_catalog(payload)


def validate_template_catalog(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AnnouncementTemplateError("template catalog must be a JSON object")
    if payload.get("schema_version") != TEMPLATE_CATALOG_SCHEMA_VERSION:
        raise AnnouncementTemplateError(
            f"input must be {TEMPLATE_CATALOG_SCHEMA_VERSION}"
        )
    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        raise AnnouncementTemplateError("template catalog must contain templates")
    templates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_templates:
        template = _validate_template(raw)
        if template["template_id"] in seen:
            raise AnnouncementTemplateError(
                f"duplicate template_id: {template['template_id']}"
            )
        seen.add(template["template_id"])
        templates.append(template)
    return {
        "schema_version": TEMPLATE_CATALOG_SCHEMA_VERSION,
        "catalog_version": str(payload.get("catalog_version") or "1.0.0"),
        "as_of": str(payload.get("as_of") or ""),
        "templates": templates,
        "template_count": len(templates),
        "rule_version": RULE_VERSION,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "policy": {
            "local_parser_only": True,
            "template_is_not_a_source_fact": True,
            "unmatched_fields_are_not_inferred": True,
            "failed_attempts_preserved": True,
        },
    }


def get_template(catalog: Mapping[str, Any], template_id: str) -> dict[str, Any]:
    """Return one validated template by stable ID."""

    normalized = validate_template_catalog(catalog)
    identifier = str(template_id or "").strip()
    for template in normalized["templates"]:
        if template["template_id"] == identifier:
            return template
    raise AnnouncementTemplateError(f"unknown announcement template: {identifier}")


def parse_announcement_input(
    payload: Mapping[str, Any] | None,
    raw_content: bytes | str,
    template: Mapping[str, Any],
    *,
    source_url: str = "",
    captured_at: str = "",
    research_as_of: str = "",
    subject_type: str = "",
    subject_id: str = "",
    issuer: str = "",
    document_id: str = "",
    raw_content_uri: str = "",
) -> dict[str, Any]:
    """Parse a local disclosure snapshot into an announcement input envelope.

    The returned object is safe to pass to ``build_announcement_asset`` when
    ``status`` is ``READY`` or ``DEGRADED``.  ``BLOCKED`` records remain useful
    audit artifacts but intentionally fail the immutable asset validation.
    """

    validated_template = _validate_template(template)
    metadata = dict(payload or {})
    if metadata.get("schema_version") not in (None, TEMPLATE_INPUT_SCHEMA_VERSION):
        raise AnnouncementTemplateError(
            f"metadata schema must be {TEMPLATE_INPUT_SCHEMA_VERSION}"
        )
    content_bytes = _content_bytes(raw_content)
    content_hash = sha256(content_bytes).hexdigest()
    content_format = _detect_format(metadata.get("content_format"), content_bytes)
    parsed, html_capture, text = _parse_content(content_bytes, content_format)
    fields: dict[str, str] = {}
    field_locators: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    failures: list[dict[str, str]] = []

    for field, rules in dict(validated_template["field_rules"]).items():
        value, locator = _extract_field(
            field,
            rules,
            parsed=parsed,
            html_capture=html_capture,
            text=text,
        )
        if value:
            fields[field] = value
            field_locators[field] = locator

    explicit = {
        "source_url": source_url or metadata.get("source_url"),
        "captured_at": captured_at or metadata.get("captured_at"),
        "research_as_of": research_as_of or metadata.get("research_as_of"),
        "subject_type": subject_type or metadata.get("subject_type"),
        "subject_id": subject_id or metadata.get("subject_id"),
        "issuer": issuer or metadata.get("issuer"),
        "document_id": document_id or metadata.get("document_id"),
    }
    for field, value in explicit.items():
        if str(value or "").strip():
            fields[field] = str(value).strip()
            field_locators[field] = {"method": "manual_input"}

    source_url_value = str(fields.get("source_url") or "").strip()
    if not source_url_value.startswith(("http://", "https://")):
        failures.append({"field": "source_url", "code": "MISSING_OR_INVALID", "action": "MANUAL_INPUT_REQUIRED"})

    subject_type_value = str(fields.get("subject_type") or validated_template.get("subject_type_default") or "").strip().lower()
    if subject_type_value not in _SUBJECT_TYPES:
        failures.append({"field": "subject_type", "code": "MISSING_OR_INVALID", "action": "MANUAL_INPUT_REQUIRED"})

    subject_id_value = str(fields.get("subject_id") or "").strip()
    if not subject_id_value:
        failures.append({"field": "subject_id", "code": "NOT_EXTRACTED", "action": "MANUAL_INPUT_REQUIRED"})

    title = str(fields.get("title") or "").strip()
    if not title:
        failures.append({"field": "title", "code": "NOT_EXTRACTED", "action": "MANUAL_INPUT_REQUIRED"})

    published_at = _normalise_datetime(fields.get("published_at"))
    if not published_at:
        failures.append({"field": "published_at", "code": "NOT_EXTRACTED_OR_INVALID", "action": "MANUAL_INPUT_REQUIRED"})

    captured = _normalise_datetime(fields.get("captured_at")) or _normalise_datetime(_now())
    if not captured:
        failures.append({"field": "captured_at", "code": "INVALID", "action": "MANUAL_INPUT_REQUIRED"})
    if published_at and captured and _instant(published_at) > _instant(captured):
        failures.append({"field": "captured_at", "code": "BEFORE_PUBLISHED_AT", "action": "MANUAL_INPUT_REQUIRED"})

    document_id_value = str(fields.get("document_id") or "").strip()
    if not document_id_value:
        document_id_value = f"announcement-{validated_template['template_id']}-{content_hash[:16]}"
        field_locators["document_id"] = {"method": "derived_content_hash", "content_hash_prefix": content_hash[:16]}
        warnings.append("document_id was derived from the raw content hash")

    document_type = _document_type(fields, title, text, validated_template)
    if not document_type:
        document_type = "announcement"
        warnings.append("document_type was not mapped; degraded to generic announcement")

    correction_status = _correction_status(fields, title, text)
    supersedes = str(fields.get("supersedes_document_id") or "").strip()
    if correction_status != "ORIGINAL" and not supersedes:
        failures.append({"field": "supersedes_document_id", "code": "CORRECTION_PARENT_NOT_EXTRACTED", "action": "MANUAL_INPUT_REQUIRED"})
    try:
        version = int(metadata.get("version") or fields.get("version") or (1 if correction_status == "ORIGINAL" else 2))
    except (TypeError, ValueError):
        version = 0
    if version < 1 or (correction_status != "ORIGINAL" and version <= 1):
        failures.append({"field": "version", "code": "INVALID_CORRECTION_VERSION", "action": "MANUAL_INPUT_REQUIRED"})

    source_version = str(metadata.get("source_version") or validated_template.get("template_version") or "unknown")
    parser_version = f"{validated_template['template_id']}@{validated_template['template_version']}"
    research_cutoff = _normalise_datetime(
        metadata.get("as_of") or metadata.get("research_as_of") or published_at
    ) or str(metadata.get("as_of") or metadata.get("research_as_of") or published_at or "")
    if published_at and research_cutoff and _instant(published_at) > _instant(research_cutoff):
        failures.append(
            {
                "field": "research_as_of",
                "code": "PUBLISHED_AFTER_RESEARCH_AS_OF",
                "action": "EXCLUDE_FROM_HISTORICAL_RESEARCH",
            }
        )
    status = "BLOCKED" if failures else ("DEGRADED" if warnings else "READY")
    return {
        "schema_version": ANNOUNCEMENT_INPUT_SCHEMA_VERSION,
        "document_id": document_id_value,
        "version": version,
        "subject_type": subject_type_value,
        "subject_id": subject_id_value,
        "issuer": str(fields.get("issuer") or "").strip(),
        "document_type": document_type,
        "title": title,
        "source": str(validated_template["source_name"]),
        "source_url": source_url_value,
        "published_at": published_at or str(fields.get("published_at") or ""),
        "captured_at": captured or str(fields.get("captured_at") or ""),
        "as_of": research_cutoff,
        "research_as_of": research_cutoff,
        "source_version": source_version,
        "parser_version": parser_version,
        "correction_status": correction_status,
        "supersedes_document_id": supersedes or None,
        "correction_reason": str(fields.get("correction_reason") or "").strip(),
        "raw_content_uri": str(raw_content_uri or metadata.get("raw_content_uri") or "").strip(),
        "content_hash": content_hash,
        "content_size_bytes": len(content_bytes),
        "content_encoding": "utf-8",
        "status": status,
        "missing_or_invalid_fields": failures,
        "warnings": warnings,
        "field_locators": field_locators,
        "original_content_locator": _content_locator(content_format, content_bytes, text),
        "template": {
            "template_id": validated_template["template_id"],
            "template_version": validated_template["template_version"],
            "source_name": validated_template["source_name"],
            "market_scope": list(validated_template["market_scope"]),
            "url_contract": dict(validated_template["url_contract"]),
            "document_type_mapping_version": validated_template["document_type_mapping_version"],
        },
        "source_attempts": [
            {
                "schema_version": PARSE_ATTEMPT_SCHEMA_VERSION,
                "source": validated_template["source_name"],
                "template_id": validated_template["template_id"],
                "template_version": validated_template["template_version"],
                "source_url": source_url_value,
                "format": content_format,
                "status": "PARSED" if status != "BLOCKED" else "BLOCKED",
                "reason": "; ".join(item["code"] for item in failures) or "parsed local snapshot",
                "content_hash": content_hash,
            }
        ],
        "metadata": {
            "market_scope": list(validated_template["market_scope"]),
            "source_family": validated_template["source_family"],
            "format": content_format,
            "extraction_mode": "local_only",
            "document_type_mapping_status": "MAPPED" if document_type != "announcement" or fields.get("document_type") else "DEFAULTED",
            "correction_detection": "explicit_field_or_title_rule",
        },
        "immutable": True,
        "read_only": True,
        "review_only": True,
        "investment_conclusion": False,
        "execution_enabled": False,
        "rule_version": RULE_VERSION,
        "policy": {
            "local_input_only": True,
            "no_network_fetch": True,
            "raw_content_hash_required": True,
            "published_at_must_precede_research_as_of": True,
            "failed_attempts_preserved": True,
            "blocked_input_cannot_be_promoted": True,
            "read_only": True,
            "review_only": True,
            "investment_conclusion": False,
            "execution_enabled": False,
        },
    }


def _validate_template(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise AnnouncementTemplateError("template must be a JSON object")
    if raw.get("schema_version") != TEMPLATE_SCHEMA_VERSION:
        raise AnnouncementTemplateError(f"template must be {TEMPLATE_SCHEMA_VERSION}")
    template_id = str(raw.get("template_id") or "").strip()
    source_name = str(raw.get("source_name") or "").strip()
    if not template_id or not source_name:
        raise AnnouncementTemplateError("template_id and source_name are required")
    market_scope = _string_list(raw.get("market_scope"))
    if not market_scope:
        raise AnnouncementTemplateError(f"{template_id}: market_scope is required")
    url_contract = raw.get("url_contract")
    if not isinstance(url_contract, Mapping) or not str(url_contract.get("url_template") or "").strip():
        raise AnnouncementTemplateError(f"{template_id}: url_contract.url_template is required")
    accepted_formats = _string_list(raw.get("accepted_formats"))
    if not accepted_formats or not set(accepted_formats) <= _FORMATS:
        raise AnnouncementTemplateError(f"{template_id}: accepted_formats must be json/html/text")
    rules = raw.get("field_rules")
    if not isinstance(rules, Mapping):
        raise AnnouncementTemplateError(f"{template_id}: field_rules are required")
    required_fields = _string_list(raw.get("required_fields"))
    if not required_fields:
        raise AnnouncementTemplateError(f"{template_id}: required_fields are required")
    document_rules = raw.get("document_type_rules")
    if not isinstance(document_rules, list):
        raise AnnouncementTemplateError(f"{template_id}: document_type_rules are required")
    return {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "template_id": template_id,
        "template_version": str(raw.get("template_version") or "1.0.0"),
        "source_name": source_name,
        "source_family": str(raw.get("source_family") or "public_disclosure"),
        "market_scope": market_scope,
        "subject_type_default": str(raw.get("subject_type_default") or "").strip().lower(),
        "url_contract": {
            "method": str(url_contract.get("method") or "GET").upper(),
            "url_template": str(url_contract["url_template"]),
            "required_params": _string_list(url_contract.get("required_params")),
            "parameter_encoding": str(url_contract.get("parameter_encoding") or "query"),
        },
        "accepted_formats": accepted_formats,
        "document_type_mapping_version": str(raw.get("document_type_mapping_version") or "1.0.0"),
        "document_type_rules": [
            {
                "document_type": str(item.get("document_type") or "").strip().lower(),
                "patterns": _string_list(item.get("patterns")),
            }
            for item in document_rules
            if isinstance(item, Mapping) and str(item.get("document_type") or "").strip()
        ],
        "field_rules": {str(key): dict(value) for key, value in rules.items() if isinstance(value, Mapping)},
        "required_fields": required_fields,
        "failure_policy": dict(raw.get("failure_policy") or {}),
    }


def _parse_content(content: bytes, content_format: str) -> tuple[Any, _HtmlCapture | None, str]:
    text = content.decode("utf-8", errors="replace")
    if content_format == "json":
        try:
            return json.loads(text), None, text
        except json.JSONDecodeError as error:
            raise AnnouncementTemplateError(f"input is not valid JSON: {error}") from error
    if content_format == "html":
        parser = _HtmlCapture()
        try:
            parser.feed(text)
            parser.close()
        except Exception as error:
            raise AnnouncementTemplateError(f"input HTML cannot be parsed: {error}") from error
        return None, parser, parser.text
    return None, None, text


def _extract_field(
    field: str,
    rules: Mapping[str, Any],
    *,
    parsed: Any,
    html_capture: _HtmlCapture | None,
    text: str,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(rules, Mapping):
        return "", {}
    for path in _string_list(rules.get("json_paths")):
        value = _json_path(parsed, path)
        if value not in (None, "", []):
            return _clean_text(value), {"method": "json_path", "path": path}
    if html_capture is not None:
        for name in _string_list(rules.get("meta_names")):
            value = html_capture.meta.get(name.lower())
            if value:
                return _clean_text(value), {"method": "html_meta", "name": name}
        for element_id in _string_list(rules.get("element_ids")):
            value = html_capture.elements.get(element_id.lower())
            if value:
                return _clean_text(value), {"method": "html_element", "id": element_id}
        if field == "title" and html_capture.title:
            return html_capture.title, {"method": "html_title"}
    for label in _string_list(rules.get("labels")):
        value = _value_after_label(text, label)
        if value:
            return value, {"method": "text_label", "label": label}
    for pattern in _string_list(rules.get("regexes")):
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        except re.error as error:
            raise AnnouncementTemplateError(f"invalid regex for {field}: {error}") from error
        if match:
            value = match.groupdict().get("value") if match.groupdict() else None
            value = value or (match.group(1) if match.groups() else match.group(0))
            if value:
                return _clean_text(value), {"method": "regex", "pattern": pattern}
    return "", {}


def _document_type(fields: Mapping[str, str], title: str, text: str, template: Mapping[str, Any]) -> str:
    explicit = str(fields.get("document_type") or "").strip().lower()
    known = {str(item["document_type"]) for item in template["document_type_rules"]}
    if explicit in known:
        return explicit
    searchable = " ".join((explicit, title, text))
    for rule in template["document_type_rules"]:
        if any(pattern and re.search(re.escape(pattern), searchable, re.IGNORECASE) for pattern in rule["patterns"]):
            return rule["document_type"]
    return ""


def _correction_status(fields: Mapping[str, str], title: str, text: str) -> str:
    explicit = str(fields.get("correction_status") or "").strip().upper()
    if explicit in _CORRECTION_STATUSES:
        return explicit
    searchable = " ".join((title, text))
    if re.search(r"撤回|撤销|废止|取消", searchable):
        return "WITHDRAWN"
    if re.search(r"补充|补发", searchable):
        return "SUPPLEMENT"
    if re.search(r"更正|修订|修正", searchable):
        return "CORRECTED"
    return "ORIGINAL"


def _value_after_label(text: str, label: str) -> str:
    escaped = re.escape(label)
    pattern = rf"{escaped}\s*(?:编号|代码|名称|日期|时间)?\s*[:：]?\s*(?P<value>[^\n\r;；|]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return ""
    return _clean_text(match.group("value"))


def _json_path(value: Any, path: str) -> Any:
    current = value
    for part in str(path).split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _content_locator(content_format: str, content: bytes, text: str) -> dict[str, Any]:
    lines = text.splitlines()
    return {
        "format": content_format,
        "encoding": "utf-8",
        "line_start": 1,
        "line_end": max(1, len(lines)),
        "byte_start": 0,
        "byte_end": len(content),
        "content_hash": sha256(content).hexdigest(),
        "locator_kind": "entire_original_snapshot",
    }


def _detect_format(explicit: Any, content: bytes) -> str:
    value = str(explicit or "").strip().lower()
    if value in _FORMATS:
        return value
    text = content.decode("utf-8", errors="replace").lstrip()
    if text.startswith(("{", "[")):
        return "json"
    if re.search(r"<\s*(html|head|meta|title|body|div)\b", text, re.IGNORECASE):
        return "html"
    return "text"


def _normalise_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^(\d{4})[./年](\d{1,2})[./月](\d{1,2})日?", r"\1-\2-\3", text)
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = re.sub(r"^(\d{4})/(\d{1,2})/(\d{1,2})", r"\1-\2-\3", text)
    text = re.sub(r"\s+", " ", text)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _content_bytes(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise AnnouncementTemplateError("raw_content must be bytes or string")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise AnnouncementTemplateError("expected a string list")
    return [str(item) for item in value if str(item).strip()]
