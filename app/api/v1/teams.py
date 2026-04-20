from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.models.enums import TeamMemberRole
from app.schemas.team import (
    TeamCreateRequest,
    TeamInviteCreateRequest,
    TeamInviteRead,
    TeamMemberRead,
    TeamRead,
    build_team_read,
)
from app.services.team import (
    create_team,
    create_team_invite,
    get_team_membership,
    list_team_invites,
    list_team_members,
    list_teams_for_user,
)


router = APIRouter(prefix="/teams", tags=["teams"])


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


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team_endpoint(
    payload: TeamCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> TeamRead:
    membership = create_team(
        db,
        created_by=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    return build_team_read(team=membership.team, membership=membership)


@router.get("", response_model=list[TeamRead])
async def list_my_teams_endpoint(
    db: DBSession,
    current_user: CurrentUser,
) -> list[TeamRead]:
    memberships = list_teams_for_user(db, user_id=current_user.id)
    return [build_team_read(team=item.team, membership=item) for item in memberships]


@router.get("/{team_id}", response_model=TeamRead)
async def get_team_endpoint(
    team_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> TeamRead:
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    return build_team_read(team=membership.team, membership=membership)


@router.post("/{team_id}/invites", response_model=TeamInviteRead, status_code=status.HTTP_201_CREATED)
async def create_team_invite_endpoint(
    team_id: int,
    payload: TeamInviteCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> TeamInviteRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    invite = create_team_invite(
        db,
        team_id=team_id,
        invited_by=current_user.id,
        expires_in_days=payload.expires_in_days,
    )
    return TeamInviteRead.model_validate(invite)


@router.get("/{team_id}/invites", response_model=list[TeamInviteRead])
async def list_team_invites_endpoint(
    team_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[TeamInviteRead]:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    invites = list_team_invites(db, team_id=team_id)
    return [TeamInviteRead.model_validate(item) for item in invites]


@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
async def list_team_members_endpoint(
    team_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[TeamMemberRead]:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    members = list_team_members(db, team_id=team_id)
    return [TeamMemberRead.model_validate(item) for item in members]
