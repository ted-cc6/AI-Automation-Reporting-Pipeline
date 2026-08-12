"""Reads the WVI logo images directly out of wvi-docx.skill (a zip archive) -- no extraction
to disk, no duplicated copies of the PNGs living in this repo. If the skill file is ever
replaced with an updated version at the same path, the renderer picks up the new logos
automatically on the next run.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # agent/report_render -> agent -> core_peoject
SKILL_PATH = PROJECT_ROOT / "wvi-docx.skill"

# Path inside the zip, confirmed by inspecting the archive -- "wvi-docx/" is the skill's own
# top-level folder name, not something this file controls.
LOGO_PATHS = {
    "primary": "wvi-docx/assets/WorldVision-Logo-Primary.png",  # dark wordmark, for white/light backgrounds
    "reverse": "wvi-docx/assets/WorldVision-Logo-Reverse.png",  # white wordmark, for dark backgrounds
    "mono": "wvi-docx/assets/WorldVision-Logo-Mono.png",  # all-white, for orange backgrounds
}


def get_logo_bytes(variant: str = "primary") -> io.BytesIO:
    """The logo PNG's bytes, ready to hand to python-docx's add_picture(). `variant` is
    "primary" (default -- for the white document page background), "reverse", or "mono".
    """
    if variant not in LOGO_PATHS:
        raise ValueError(f"Unknown logo variant {variant!r} -- expected one of {sorted(LOGO_PATHS)}")
    if not SKILL_PATH.exists():
        raise FileNotFoundError(f"wvi-docx.skill not found at {SKILL_PATH}")
    with zipfile.ZipFile(SKILL_PATH) as zf:
        return io.BytesIO(zf.read(LOGO_PATHS[variant]))
