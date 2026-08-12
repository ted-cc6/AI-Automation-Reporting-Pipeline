"""Contract for the Client Voices section (curated verbatim bank)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import Verbatim


class ClientVoicesSection(BaseModel):
    green_lights: list[Verbatim] = Field(default_factory=list)  # promoters
    red_flags: list[Verbatim] = Field(default_factory=list)  # detractors, protection signals linked back to Part 5
