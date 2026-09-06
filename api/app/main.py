from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import notes

# The ingress routes /api here without rewriting, so the app owns the real
# paths. Deliberately not using root_path, which shifts doc URLs but does not
# strip the prefix, and is the usual source of 404s in this setup.
app = FastAPI(title="Notes API", docs_url="/api/docs", openapi_url="/api/openapi.json")

# Only needed when the SPA is served from a different origin, which is the dev
# setup. Behind the ingress everything is one host and this stays empty.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["authorization", "content-type"],
    )

app.include_router(notes.router, prefix="/api")


# Not routed by the ingress. Probes hit the pod directly.
@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
