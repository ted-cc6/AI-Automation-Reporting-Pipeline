"""dashboard/api/main.py -- FastAPI app entrypoint.

Run with:
    uvicorn dashboard.api.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.api.routes import country_routes, csv_routes, llm_routes, run_routes, visuals_routes

app = FastAPI(title="VFI Insurance Report Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(csv_routes.router)
app.include_router(country_routes.router)
app.include_router(llm_routes.router)
app.include_router(run_routes.router)
app.include_router(visuals_routes.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
