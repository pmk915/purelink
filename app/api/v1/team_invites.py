from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.team import TeamInviteJoinRequest, TeamRead, build_team_read
from app.services.team import (
    TeamInviteNotFoundError,
    TeamInviteStateError,
    TeamMembershipConflictError,
    join_team_by_invite,
)


router = APIRouter(prefix="/team-invites", tags=["team-invites"])


@router.post("/join", response_model=TeamRead)
async def join_team_invite_endpoint(
    payload: TeamInviteJoinRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> TeamRead:
    try:
        membership = join_team_by_invite(
            db,
            user_id=current_user.id,
            code=payload.code,
        )
    except TeamInviteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TeamInviteStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TeamMembershipConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return build_team_read(team=membership.team, membership=membership)
