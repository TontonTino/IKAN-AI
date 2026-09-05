"""
Proxy vers l'agent IA (port 8001) — relaie /api/v1/agent-proxy/* après
authentification par le backend principal, en réémettant un Bearer token
frais pour l'agent (celui-ci ne reçoit jamais le cookie/header d'origine).
"""
from fastapi import APIRouter, Depends, Request, Response
import httpx

from app.api.deps import get_current_active_user
from app.core.security import create_access_token
from app.models.utilisateur import Utilisateur

router = APIRouter(prefix="/agent-proxy", tags=["Agent Proxy"])
AGENT_URL = "http://localhost:8001"


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_agent(
    path: str,
    request: Request,
    current_user: Utilisateur = Depends(get_current_active_user),
):
    agent_token = create_access_token(subject=str(current_user.id))
    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method=request.method,
            url=f"{AGENT_URL}/{path}",
            content=body,
            params=dict(request.query_params),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {agent_token}",
            },
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type="application/json",
    )
