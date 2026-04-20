from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.models.enums import DocumentReviewStatus, TeamMemberRole
from app.schemas.document import DocumentRead, DocumentRejectRequest
from app.services.document import (
    approve_document_review,
    get_team_document,
    list_pending_team_documents,
    reject_document_review,
)
from app.services.team import get_team_membership


router = APIRouter(prefix="/teams/{team_id}", tags=["team-document-reviews"])


def _get_active_membership_or_404(
    db: DBSession,
    *,
    team_id: int,
    user_id: int,
):
    membership = get_team_membership(
        db,
        team_id=team_id,
        user_id=user_id,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found.",
        )
    return membership


def _get_admin_membership_or_raise(
    db: DBSession,
    *,
    team_id: int,
    user_id: int,
):
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=user_id,
    )
    if membership.role != TeamMemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return membership


def _get_pending_team_document_or_raise(
    db: DBSession,
    *,
    team_id: int,
    document_id: int,
):
    document = get_team_document(
        db,
        team_id=team_id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not pending review.",
        )
    return document


@router.get("/review-tasks", response_model=list[DocumentRead])
async def list_team_review_tasks_endpoint(
    team_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[DocumentRead]:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    documents = list_pending_team_documents(db, team_id=team_id)
    return [DocumentRead.model_validate(item) for item in documents]


@router.post("/documents/{document_id}/approve", response_model=DocumentRead)
async def approve_team_document_endpoint(
    team_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    document = _get_pending_team_document_or_raise(
        db,
        team_id=team_id,
        document_id=document_id,
    )
    approved = approve_document_review(
        db,
        document=document,
        reviewed_by=current_user.id,
    )
    return DocumentRead.model_validate(approved)


@router.post("/documents/{document_id}/reject", response_model=DocumentRead)
async def reject_team_document_endpoint(
    team_id: int,
    document_id: int,
    payload: DocumentRejectRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    document = _get_pending_team_document_or_raise(
        db,
        team_id=team_id,
        document_id=document_id,
    )
    rejected = reject_document_review(
        db,
        document=document,
        reviewed_by=current_user.id,
        review_comment=payload.review_comment,
    )
    return DocumentRead.model_validate(rejected)
