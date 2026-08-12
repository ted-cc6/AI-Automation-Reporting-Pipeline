"""World Vision International brand constants, transcribed from wvi-docx.skill's SKILL.md
(read directly, not paraphrased -- see PROJECT_ROOT/wvi-docx.skill). The skill itself is
written for docx-js; these are the same values translated to python-docx's units (EMU/Pt for
sizes, RGBColor for hex) since this pipeline is all-Python. If the skill file is ever updated,
this needs a manual re-sync -- there's no automated extraction of prose/table values, only the
bundled logo images are read programmatically (see skill_assets.py).
"""

from __future__ import annotations

from docx.shared import Pt, RGBColor

# --- Colours (hex from SKILL.md's "Colour Palette" table) -----------------------------------

ORANGE = RGBColor(0xFF, 0x55, 0x15)
MIDNIGHT = RGBColor(0x11, 0x12, 0x22)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FIELD_50 = RGBColor(0xF3, 0xF2, 0xF0)
GREY_700 = RGBColor(0x3F, 0x3D, 0x4C)
GREEN_800 = RGBColor(0x15, 0x59, 0x30)
BLUE_800 = RGBColor(0x0C, 0x79, 0x93)
RED_800 = RGBColor(0xB1, 0x08, 0x31)
TABLE_BORDER_GREY = "CCCCCC"

# --- Typography (SKILL.md's "Font Priority" -- Inter primary, Calibri fallback for documents) -

FONT_HEADING = "Inter"
FONT_BODY = "Inter"
FONT_QUOTE = "Merriweather Light"
FONT_FALLBACK = "Calibri"

# --- Size hierarchy (SKILL.md's "Size Hierarchy (Documents)" table, in points) ---------------

SIZE_MAIN_TITLE = Pt(28)  # 26-30pt range, mid-point
SIZE_SUBTITLE = Pt(19)  # 18-20pt range, mid-point
SIZE_SECTION_HEADING = Pt(17)  # 16-18pt range, mid-point (Heading 1)
SIZE_SUBHEADING = Pt(13)  # 13-14pt range, low end (Heading 2 / subsection numbers)
SIZE_BODY = Pt(11)
SIZE_CAPTION = Pt(9)

LINE_SPACING_BODY = 1.15

# --- Page setup (SKILL.md's "Page Setup" -- US Letter, 1in margins) ---------------------------

PAGE_WIDTH = Pt(12240 / 20)  # 12240 DXA = 612pt = 8.5in
PAGE_HEIGHT = Pt(15840 / 20)  # 15840 DXA = 792pt = 11in
PAGE_MARGIN = Pt(1440 / 20)  # 1440 DXA = 72pt = 1in

# --- Table styling (SKILL.md's "Tables" section) ----------------------------------------------

TABLE_HEADER_BG = "FF5515"  # Orange, hex without '#' for OOXML shading
TABLE_ALT_ROW_BG = "F3F2F0"  # Field 50
TABLE_HEADER_TEXT = WHITE
