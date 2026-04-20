# Team Domain Model

## Purpose

This document records the team collaboration domain foundation introduced in Milestone M4.5, and the first team-facing APIs introduced in Milestone M4.6.

The goal of this milestone is to prepare the database for:

- team creation
- membership and invitation flow
- team-scoped knowledge bases
- document review workflow

This document still focuses on domain structure first. Team knowledge base APIs and document review APIs are not covered here yet.

## New entities

### Team

- `id`
- `name`
- `description`
- `created_by`
- `created_at`
- `updated_at`

Represents a collaboration space that can own team knowledge bases.

### TeamMember

- `id`
- `team_id`
- `user_id`
- `role`
- `status`
- `joined_at`
- `created_at`
- `updated_at`

Represents the relationship between a user and a team.

Role values:

- `admin`
- `member`

Status values:

- `active`
- `invited`
- `removed`

### TeamInvite

- `id`
- `team_id`
- `code`
- `invited_by`
- `expires_at`
- `used_by`
- `used_at`
- `status`
- `created_at`
- `updated_at`

Represents an invitation code that can be used to join a team.

Status values:

- `active`
- `used`
- `expired`
- `revoked`

## Updated entities

### KnowledgeBase

`KnowledgeBase` now supports two scopes:

- `personal`
- `team`

Rules:

- personal knowledge base:
  - `scope = personal`
  - `owner_id` must be set
  - `team_id` must be null
- team knowledge base:
  - `scope = team`
  - `team_id` must be set
  - `owner_id` must be null

Current personal knowledge base APIs continue to use only `scope = personal`.

### Document

`Document` now separates review lifecycle from processing lifecycle.

Review fields:

- `review_status`
- `reviewed_by`
- `reviewed_at`
- `review_comment`

Processing fields:

- `processing_status`

Upload attribution fields:

- `owner_id`
- `submitted_by`

Review status values:

- `not_required`
- `pending_review`
- `approved`
- `rejected`

Processing status values:

- `uploaded`
- `parsed`
- `indexed`
- `failed`

## Compatibility note

Milestone M4.5 is intentionally layered on top of the current personal knowledge base implementation.

Compatibility is preserved by:

- keeping personal knowledge base creation defaulted to `scope = personal`
- continuing to query personal knowledge bases by `owner_id`
- not mixing current personal knowledge base APIs with team knowledge base APIs
- leaving the authentication flow unchanged

## Current team APIs

Milestone M4.6 currently exposes the minimum team collaboration API surface:

- create team
- list my teams
- read team detail
- create invite code
- list team invite codes
- join team by invite code
- list team members

Business rules already enforced at API/service layer:

- team creator is automatically bootstrapped as `admin`
- only `admin` can create and list invites
- only active members can read team detail and member list
- joining validates invite status and expiration
- duplicate membership is rejected

Still not implemented in this document's scope:

- team knowledge base CRUD
- document submission and review APIs
- search / retrieval / Q&A permissions
