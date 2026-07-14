"""dashboard/api/main.py -- FastAPI app entrypoint.

Local dev:  uvicorn dashboard.api.main:app --reload --port 8000
Container:  python -m dashboard.api.main   (reads PORT env var, default 7860)
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.config import PROJECT_ROOT
from dashboard.api.routes import country_routes, csv_routes, llm_routes, reconcile_routes, run_routes, visuals_routes

app = FastAPI(title="VFI Insurance Report Dashboard API")

_default_origins = "http://localhost:5173"
allowed_origins = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(csv_routes.router)
app.include_router(country_routes.router)
app.include_router(llm_routes.router)
app.include_router(reconcile_routes.router)
app.include_router(run_routes.router)
app.include_router(visuals_routes.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# --- Serve the built frontend (Vite `dist/`), same origin as the API ---
# Registered last so it can never shadow the /api/* routes above --
# Starlette matches routes in registration order.
_frontend_dist = PROJECT_ROOT / "dashboard" / "web" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        return FileResponse(_frontend_dist / "index.html")


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("dashboard.api.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
