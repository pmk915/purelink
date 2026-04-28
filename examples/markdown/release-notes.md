# PureLink Demo Release Notes

## M26 Focus

M26 focuses on making PureLink easier to clone, configure, start, and demonstrate as a local-first self-hosted knowledge system.

## Included Demo Flow

Users can start the Docker Compose stack, register, create a personal knowledge base, upload `examples/text/playbook.txt`, ask a question, and inspect citations.

## Provider Notes

The default configuration uses local fallback retrieval and heuristic answers. Teams can configure OpenAI-compatible LLM and embedding providers in `.env` when they want stronger answer quality.

## Deployment Notes

PureLink is suitable for local machines, small intranet servers, labs, project teams, and user-managed cloud servers.
