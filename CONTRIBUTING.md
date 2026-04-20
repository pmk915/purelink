# Contributing to PureLink

Thanks for contributing to PureLink.

## Development Setup

1. Copy environment variables:

   ```bash
   cp .env.example .env
   ```

2. Start the local stack:

   ```bash
   docker compose up --build -d
   ```

3. Run database migrations if needed:

   ```bash
   docker compose exec api alembic upgrade head
   ```

## Quality Checks

Run the core checks before opening a pull request:

```bash
make test
make smoke
```

For a fuller local validation:

```bash
make e2e
```

## Contribution Guidelines

- Keep changes small and focused.
- Preserve current personal and team permission boundaries.
- Add or update tests for behavior changes.
- Update README when setup, API behavior, or developer workflow changes.
- Do not commit local secrets, `.env`, generated `data/` artifacts, or virtualenv files.

## Pull Requests

- Use clear, scoped commit messages.
- Explain the user-visible effect and verification steps.
- If the change affects migrations or workers, call that out explicitly in the PR description.
