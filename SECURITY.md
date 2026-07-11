# Security Policy

## Supported Versions

PureLink currently supports security fixes for:

- `main`
- the latest tagged release, when a release exists

Older commits, branches, and local forks are not actively maintained.

## Reporting a Vulnerability

Please do not report security vulnerabilities through a public GitHub Issue.

Use GitHub Security Advisories to report security issues privately:

https://github.com/pmk915/purelink/security/advisories/new

PureLink does not currently provide a formal security response SLA. The project maintainer will review reports as availability allows and will prioritize issues based on severity, exploitability, and project scope.

## What to Include

A useful security report should include:

- affected version, release, or commit
- clear steps to reproduce
- impact assessment
- suggested fix or mitigation, if known
- relevant logs or screenshots with secrets removed

## Deployment Notice

PureLink is not a production-security-audited SaaS product. Before exposing an instance beyond a local or controlled environment:

- replace development secrets such as `AUTH_SECRET_KEY`
- replace database and service passwords
- restrict CORS origins
- protect PostgreSQL and Redis from public access
- configure TLS through a trusted reverse proxy
- review upload limits, storage permissions, backups, and provider keys
