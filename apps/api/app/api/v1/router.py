"""
Routeur principal de l'API v1 — regroupe tous les endpoints.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    organisations,
    agences,
    utilisateurs,
    qr_codes,
    feedbacks,
    suggestions,
    analyses,
    recommandations,
    dashboard,
    alertes,
    system,
    agent,
    agent_proxy,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentification"])
api_router.include_router(organisations.router, prefix="/organisations", tags=["Organisations"])
api_router.include_router(agences.router, prefix="/agences", tags=["Agences"])
api_router.include_router(utilisateurs.router, prefix="/utilisateurs", tags=["Utilisateurs"])
api_router.include_router(qr_codes.router, prefix="/qr-codes", tags=["QR Codes"])
api_router.include_router(feedbacks.router, prefix="/feedbacks", tags=["Feedbacks"])
api_router.include_router(suggestions.router, prefix="/suggestions", tags=["Suggestions"])
api_router.include_router(analyses.router, prefix="/analyses", tags=["Analyses IA"])
api_router.include_router(recommandations.router, prefix="/recommandations", tags=["Recommandations"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(alertes.router, prefix="/alertes", tags=["Alertes"])
api_router.include_router(system.router, prefix="/system", tags=["Système"])
# ATTENTION — deux implémentations concurrentes de l'agent IA coexistent ici,
# à réconcilier avant merge (voir description de la PR) :
# - agent.router          : agent intégré dans apps/api (déjà sur main)
# - agent_proxy.router     : relais vers le microservice apps/agent (port 8001, cette PR)
api_router.include_router(agent.router, prefix="/agent", tags=["Agent IA"])
api_router.include_router(agent_proxy.router)
