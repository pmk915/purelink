from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TeamInviteStatus, TeamMemberRole, TeamMemberStatus

if TYPE_CHECKING:
    from app.models.team import Team, TeamMember


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Team name cannot be empty.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class TeamRead(BaseModel):
    id: int
    name: str
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    my_role: TeamMemberRole
    my_status: TeamMemberStatus


class TeamInviteCreateRequest(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=365)


class TeamInviteJoinRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Invitation code cannot be empty.")
        return normalized


class TeamInviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    code: str
    invited_by: int
    expires_at: datetime
    used_by: int | None
    used_at: datetime | None
    status: TeamInviteStatus
    created_at: datetime
    updated_at: datetime


class TeamMemberUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    user_id: int
    role: TeamMemberRole
    status: TeamMemberStatus
    joined_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user: TeamMemberUserRead


def build_team_read(*, team: Team, membership: TeamMember) -> TeamRead:
    return TeamRead(
        id=team.id,
        name=team.name,
        description=team.description,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
        my_role=membership.role,
        my_status=membership.status,
    )
