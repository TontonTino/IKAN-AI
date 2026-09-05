"""
Point d'entrée FastAPI de l'agent IA IKAN AI — service indépendant, port 8001.

Lancement local : uvicorn app.main:app --reload --port 8001
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import agent_router, webhook_router
from app.config.settings import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Agent IA conversationnel IKAN AI — Q&A managers, brouillons d'action, alertes automatiques.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(webhook_router)


@app.get("/health", tags=["Santé"])
def health():
    return {"status": "ok", "service": "ikanai-agent"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
