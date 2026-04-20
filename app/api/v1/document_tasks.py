from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.models.enums import KnowledgeBaseScope
from app.schemas.document_task import DocumentTaskRead
from app.services.document_task import get_document_task
from app.services.team import get_team_membership


router = APIRouter(prefix="/document-tasks", tags=["document-tasks"])


@router.get("/{task_id}", response_model=DocumentTaskRead)
async def get_document_task_endpoint(
    task_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    task = get_document_task(db, task_id=task_id)
    if task is None or task.document is None or task.document.knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document task not found.",
        )

    knowledge_base = task.document.knowledge_base
    if knowledge_base.scope == KnowledgeBaseScope.PERSONAL:
        if knowledge_base.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document task not found.",
            )
    else:
        membership = get_team_membership(
            db,
            team_id=knowledge_base.team_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document task not found.",
            )

    return DocumentTaskRead.model_validate(task)
