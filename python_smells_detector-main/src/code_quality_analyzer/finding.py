"""Unified finding model shared by all three smell detectors.

The original detectors each return their own near-identical dataclass
(``CodeSmell``, ``StructuralSmell``, ``ArchitecturalSmell``).  For
base/head comparison we need a single shape so that fingerprints and
lifecycle classification do not have to special-case each detector.
"""

from dataclasses import dataclass
from typing import Optional

# Stable category labels used in reports and fingerprints.
CATEGORY_CODE = "code"
CATEGORY_STRUCTURAL = "structural"
CATEGORY_ARCHITECTURAL = "architectural"


@dataclass(frozen=True)
class Finding:
    """A single detected smell normalised to one canonical shape.

    Attributes:
        category: One of ``code`` / ``structural`` / ``architectural``.
        smell_type: The detector's smell name, e.g. ``"Long Method"``.
        file_path: Absolute path to the file in the analysed tree.
        symbol: Qualified owner name (``module.Class`` or ``module.func``).
        line: 1-based line number, or ``None`` when not applicable.
        severity: ``low`` / ``medium`` / ``high`` (empty becomes ``medium``).
        description: Human-readable explanation from the detector.
        metric_value: Optional numeric value behind the smell; populated by
            detectors that expose a metric.  Used by ``WORSENED`` detection
            in a later sprint.
    """

    category: str
    smell_type: str
    file_path: str
    symbol: str
    line: Optional[int] = None
    severity: str = "medium"
    description: str = ""
    metric_value: Optional[float] = None

    @classmethod
    def from_smell(cls, smell, category: str) -> "Finding":
        """Adapt one of the three detector result objects into a Finding."""
        return cls(
            category=category,
            smell_type=smell.name,
            file_path=smell.file_path,
            symbol=getattr(smell, "module_class", "") or "",
            line=getattr(smell, "line_number", None),
            severity=(getattr(smell, "severity", "medium") or "medium").lower(),
            description=getattr(smell, "description", "") or "",
        )
