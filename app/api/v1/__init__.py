from fastapi import APIRouter

from app.api.v1 import (
    auth,
    competitions,
    games,
    homepage,
    media,
    players,
    teams,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(teams.router)
api_router.include_router(players.router)
api_router.include_router(competitions.router)
api_router.include_router(games.router)
api_router.include_router(media.router)
api_router.include_router(homepage.router)

__all__ = ["api_router"]
