# Knowledge Base Management

PureLink supports personal and team knowledge base management with backend-enforced permissions.

## Personal Knowledge Bases

- A personal knowledge base can be deleted by its owner.
- The frontend shows a confirmation dialog before deletion.
- Deletion removes the workspace and its related documents/index data through the existing backend cascade behavior.
- After deletion, the UI refreshes the list or redirects away from the deleted workspace.

## Team Knowledge Bases

- Team knowledge base deletion is restricted to team admins.
- Normal team members do not get the destructive action in the normal UI.
- The backend still enforces admin-only deletion and returns `403` for non-admin members.
- Non-members cannot access the team knowledge base route.

## Product Rule

Deletion is never a frontend-only decision. The frontend can hide or disable actions for clarity, but ownership and team-admin checks remain backend responsibilities.
