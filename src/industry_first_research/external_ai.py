"""Manual ingestion model for answers copied from free web AI products."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4


URL_RE = re.compile(r"https?://[^\s)\]}>，。；：、]+")


@dataclass
class ExternalAIResearchRecord:
    provider: str
    question: str
    answer: str
    model_label: str = "unknown"
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    record_id: str = field(default_factory=lambda: f"ext-ai-{uuid4().hex[:12]}")
    source_urls: list[str] = field(default_factory=list)
    evidence_tier: str = "C"
    verification_status: str = "UNVERIFIED"

    def __post_init__(self) -> None:
        if not self.source_urls:
            self.source_urls = sorted(set(URL_RE.findall(self.answer)))
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.question.strip():
            raise ValueError("question is required")
        if not self.answer.strip():
            raise ValueError("answer is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
