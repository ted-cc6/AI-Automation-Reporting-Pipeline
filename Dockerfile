# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React/Vite frontend ----------
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY dashboard/web/package.json dashboard/web/package-lock.json ./
RUN npm ci
COPY dashboard/web/ ./
RUN npm run build
# Output: /frontend/dist (index.html + assets/*)

# ---------- Stage 2: Python runtime serving API + built frontend ----------
FROM python:3.11-slim AS runtime
WORKDIR /app

# Install the package (incl. dashboard extras: fastapi/uvicorn/anthropic/openai)
COPY pyproject.toml ./
COPY run_pipeline.py run_analysis.py utils.py coverage_report.py inspect_spec.py generate_visuals.py llm_providers.py ./
COPY analysis_engine ./analysis_engine
COPY data_loader ./data_loader
COPY generation ./generation
COPY qualitative ./qualitative
COPY report_spec ./report_spec
COPY dashboard_alignment ./dashboard_alignment
COPY dashboard ./dashboard
COPY country_configs ./country_configs
COPY insurance-report-spec.yaml insurance-report-spec.schema.json ./

# GEDSI (Gender Study) pipeline lives in its own sibling project folder, not
# pip-installed -- dashboard/api/config.py adds GENDSI_ROOT to sys.path at
# import time so `from gedsi_pipeline import ...` resolves the same way it
# does in dev. Only the source and the pre-reviewed codebooks ship in the
# image; cache/, docs, RUNBOOK.md, and requirements.txt are dev-only and
# never read at runtime.
COPY GENDSI/gedsi_pipeline ./GENDSI/gedsi_pipeline
COPY GENDSI/work/codebooks ./GENDSI/work/codebooks

RUN pip install --no-cache-dir ".[dashboard]" openpyxl  # openpyxl: gedsi_pipeline's .xlsx workbook output

# Bring in the built frontend from stage 1
COPY --from=frontend-build /frontend/dist ./dashboard/web/dist

# Runtime-writable dirs (uploads/runs/GEDSI's LLM cache) -- created empty, never baked with data
RUN mkdir -p /app/runs /app/dashboard/api/uploads /app/GENDSI/cache

# Hugging Face Spaces (Docker SDK) proxies to the port declared as app_port
# in the Space README (7860 by convention); PORT is read at runtime so
# `docker run -e PORT=...` also works locally.
ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "dashboard.api.main"]
