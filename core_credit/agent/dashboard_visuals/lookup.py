"""Core lookup: subsection_id -> screenshot file, or a clear "missing" signal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg")

# Verbatim from the Core Credit Impact Report Template -- reused rather than paraphrased so a
# missing screenshot reads identically to how the template itself marks an unfilled slot.
MISSING_PLACEHOLDER_TEXT = "[ DASHBOARD VISUAL — paste screenshot here ]"


@dataclass(frozen=True)
class DashboardVisual:
    subsection_id: str
    found: bool
    path: Optional[Path]
    placeholder_text: Optional[str]  # set only when found is False


def find_dashboard_visual(subsection_id: str, screenshots_dir: Path = SCREENSHOTS_DIR) -> DashboardVisual:
    """Looks for screenshots_dir/<subsection_id>.{png,jpg,jpeg}, checked in that order.

    If more than one extension exists for the same id, .png wins -- worth knowing if you
    ever save the same screenshot twice under different formats, but not something the
    normal one-screenshot-per-id workflow will hit.
    """
    for ext in SUPPORTED_EXTENSIONS:
        candidate = screenshots_dir / f"{subsection_id}{ext}"
        if candidate.is_file():
            return DashboardVisual(subsection_id=subsection_id, found=True, path=candidate, placeholder_text=None)
    return DashboardVisual(
        subsection_id=subsection_id, found=False, path=None, placeholder_text=MISSING_PLACEHOLDER_TEXT
    )


def find_dashboard_visuals(
    subsection_ids: list[str], screenshots_dir: Path = SCREENSHOTS_DIR
) -> dict[str, DashboardVisual]:
    """Batch convenience: resolves every id at once, for a whole section or report build."""
    return {sid: find_dashboard_visual(sid, screenshots_dir) for sid in subsection_ids}


def missing_dashboard_visuals(results: dict[str, DashboardVisual]) -> list[str]:
    """Which subsection_ids in a batch result still need a screenshot -- for a build-time summary."""
    return [sid for sid, result in results.items() if not result.found]
