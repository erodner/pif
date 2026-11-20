"""promptinjectorfinder: find hidden and visible prompt-injection patterns in PDFs."""

from .model import Finding, Report, Severity, Technique
from .scanner import ScanOptions, scan

__all__ = ["scan", "ScanOptions", "Report", "Finding", "Severity", "Technique"]
__version__ = "0.2.0"
