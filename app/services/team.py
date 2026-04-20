from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.enums import TeamInviteStatus, TeamMemberRole, TeamMemberStatus
from app.models.team import Team, TeamInvite, TeamMember


class TeamInviteNotFoundError(LookupError):
    pass


class TeamInviteStateError(ValueError):
    pass


class TeamMembershipConflictError(ValueError):
    pass


def create_team(
    db: Session,
    *,
    created_by: int,
    name: str,
    description: str | None,
) -> TeamMember:
    joined_at = datetime.now(UTC)
    team = Team(
        name=name,
        description=description,
        created_by=created_by,
    )
    db.add(team)
    db.flush()

    membership = TeamMember(
        team_id=team.id,
        user_id=created_by,
        role=TeamMemberRole.ADMIN,
        status=TeamMemberStatus.ACTIVE,
        joined_at=joined_at,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return get_team_membership(
        db,
        team_id=team.id,
        user_id=created_by,
    ) or membership


def list_teams_for_user(db: Session, *, user_id: int) -> list[TeamMember]:
    statement = (
        select(TeamMember)
        .options(selectinload(TeamMember.team))
        .join(Team, Team.id == TeamMember.team_id)
        .where(
            TeamMember.user_id == user_id,
            TeamMember.status == TeamMemberStatus.ACTIVE,
        )
        .order_by(Team.created_at.desc(), Team.id.desc())
    )
    return list(db.scalars(statement))


def get_team_membership(
    db: Session,
    *,
    team_id: int,
    user_id: int,
) -> TeamMember | None:
    statement = (
        select(TeamMember)
        .options(selectinload(TeamMember.team))
        .where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.status == TeamMemberStatus.ACTIVE,
        )
    )
    return db.scalar(statement)


def list_team_members(db: Session, *, team_id: int) -> list[TeamMember]:
    statement = (
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(
            TeamMember.team_id == team_id,
            TeamMember.status == TeamMemberStatus.ACTIVE,
        )
        .order_by(TeamMember.created_at.asc(), TeamMember.id.asc())
    )
    return list(db.scalars(statement))


def create_team_invite(
    db: Session,
    *,
    team_id: int,
    invited_by: int,
    expires_in_days: int,
) -> TeamInvite:
    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    for _ in range(5):
        invite = TeamInvite(
            team_id=team_id,
            code=secrets.token_urlsafe(16),
            invited_by=invited_by,
            expires_at=expires_at,
            status=TeamInviteStatus.ACTIVE,
        )
        db.add(invite)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue

        db.refresh(invite)
        return invite

    raise RuntimeError("Failed to generate a unique invitation code.")


def list_team_invites(db: Session, *, team_id: int) -> list[TeamInvite]:
    statement = (
        select(TeamInvite)
        .where(TeamInvite.team_id == team_id)
        .order_by(TeamInvite.created_at.desc(), TeamInvite.id.desc())
    )
    return list(db.scalars(statement))


def join_team_by_invite(
    db: Session,
    *,
    user_id: int,
    code: str,
) -> TeamMember:
    invite = db.scalar(
        _invite_lookup_statement().where(TeamInvite.code == code)
    )
    if invite is None:
        raise TeamInviteNotFoundError("Invitation code not found.")

    now = datetime.now(UTC)
    expires_at = _coerce_utc_datetime(invite.expires_at)

    if invite.status != TeamInviteStatus.ACTIVE:
        raise TeamInviteStateError("Invitation code is no longer active.")

    if expires_at <= now:
        invite.status = TeamInviteStatus.EXPIRED
        db.commit()
        raise TeamInviteStateError("Invitation code has expired.")

    existing_membership = db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == invite.team_id,
            TeamMember.user_id == user_id,
        )
    )
    if existing_membership is not None:
        if existing_membership.status in {TeamMemberStatus.ACTIVE, TeamMemberStatus.INVITED}:
            raise TeamMembershipConflictError("User is already a team member.")

        membership = existing_membership
        membership.role = TeamMemberRole.MEMBER
        membership.status = TeamMemberStatus.ACTIVE
        membership.joined_at = now
    else:
        membership = TeamMember(
            team_id=invite.team_id,
            user_id=user_id,
            role=TeamMemberRole.MEMBER,
            status=TeamMemberStatus.ACTIVE,
            joined_at=now,
        )
        db.add(membership)

    invite.status = TeamInviteStatus.USED
    invite.used_by = user_id
    invite.used_at = now
    db.commit()

    return get_team_membership(
        db,
        team_id=invite.team_id,
        user_id=user_id,
    ) or membership


def _invite_lookup_statement() -> Select[tuple[TeamInvite]]:
    return select(TeamInvite).options(selectinload(TeamInvite.team))


def _coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
