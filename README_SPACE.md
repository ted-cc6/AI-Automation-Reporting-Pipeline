---
title: VFI Report Dashboard
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: other
---

# VFI Report Dashboard

A landing page lets you choose which report family to work on:

- **Insurance Impact Reports** -- Cupboard Week quarterly reports and the Gender Study
  report. Upload a client-survey CSV, pick a country/quarter, provide your own LLM API
  key (Gemini / Anthropic / OpenAI -- bring your own key, nothing is stored server-side),
  and generate the report end-to-end.
- **Core Credit Impact Report** -- the global, multi-country Core Credit portfolio
  report (9 theme sections, benchmarked against the MFI Index). Upload the survey
  export, provide your own Anthropic key, and generate the report end-to-end.

This Space runs the FastAPI backend and the built React/Vite frontend from a
single container.
