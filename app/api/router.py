from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.document_tasks import router as document_tasks_router
from app.api.v1.knowledge_bases import router as knowledge_bases_router
from app.api.v1.processing_jobs import router as processing_jobs_router
from app.api.v1.system import router as system_router
from app.api.v1.team_document_reviews import router as team_document_reviews_router
from app.api.v1.team_invites import router as team_invites_router
from app.api.v1.team_knowledge_bases import router as team_knowledge_bases_router
from app.api.v1.teams import router as teams_router
from app.api.v1.users import router as users_router


router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(conversations_router)
router.include_router(document_tasks_router)
router.include_router(knowledge_bases_router)
router.include_router(processing_jobs_router)
router.include_router(system_router)
router.include_router(team_document_reviews_router)
router.include_router(team_invites_router)
router.include_router(team_knowledge_bases_router)
router.include_router(teams_router)
router.include_router(users_router)
