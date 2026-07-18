"""Industry-first research orchestration primitives."""

from .models import (
    CompanyCandidate,
    CompanyDataTier,
    IndustryRadarSnapshot,
    IndustryState,
    ResourcePolicy,
    ScanResult,
)
from .pipeline import IndustryFirstDiscovery
from .report import render_scan_html, render_scan_markdown
from .data_sources import (
    AkshareDataSourceAdapter,
    BaoStockDataSourceAdapter,
    DataSourceHealth,
    FreeDataSourcePolicy,
    default_free_data_adapters,
)

__all__ = [
    "CompanyCandidate",
    "CompanyDataTier",
    "IndustryFirstDiscovery",
    "IndustryRadarSnapshot",
    "IndustryState",
    "ResourcePolicy",
    "ScanResult",
    "render_scan_markdown",
    "render_scan_html",
    "AkshareDataSourceAdapter",
    "BaoStockDataSourceAdapter",
    "DataSourceHealth",
    "FreeDataSourcePolicy",
    "default_free_data_adapters",
]
