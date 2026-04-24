from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.models.enums import KnowledgeBaseScope
from app.schemas.processing_job import ProcessingJobRead
from app.services.processing_job import get_processing_job
from app.services.team import get_team_membership


router = APIRouter(prefix="/processing-jobs", tags=["processing-jobs"])


@router.get("/{job_id}", response_model=ProcessingJobRead)
async def get_processing_job_endpoint(
    job_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobRead:
    job = get_processing_job(db, job_id=job_id)
    if job is None or job.document is None or job.document.knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job not found.",
        )

    knowledge_base = job.document.knowledge_base
    if knowledge_base.scope == KnowledgeBaseScope.PERSONAL:
        if knowledge_base.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Processing job not found.",
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
                detail="Processing job not found.",
            )

    return ProcessingJobRead.model_validate(job)
