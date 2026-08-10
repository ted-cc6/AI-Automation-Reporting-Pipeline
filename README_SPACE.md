---
title: VFI Insurance Report Dashboard
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: other
---

# VFI Insurance Report Dashboard

Upload a client-survey CSV, pick a country/quarter, provide your own LLM API
key (Gemini / Anthropic / OpenAI -- bring your own key, nothing is stored
server-side), and generate the VisionFund Insurance Impact Report end-to-end
from this dashboard.

This Space runs the FastAPI backend and the built React/Vite frontend from a
single container. See `README_PACKAGE.md` for the underlying Python
report-generation package this dashboard drives.
