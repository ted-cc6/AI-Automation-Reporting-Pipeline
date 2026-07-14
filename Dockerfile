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

RUN pip install --no-cache-dir ".[dashboard]"

# Bring in the built frontend from stage 1
COPY --from=frontend-build /frontend/dist ./dashboard/web/dist

# Runtime-writable dirs (uploads/runs) -- created empty, never baked with data
RUN mkdir -p /app/runs /app/dashboard/api/uploads

# Hugging Face Spaces (Docker SDK) proxies to the port declared as app_port
# in the Space README (7860 by convention); PORT is read at runtime so
# `docker run -e PORT=...` also works locally.
ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "dashboard.api.main"]
