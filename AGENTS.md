# AGENTS.md

This repository implements Malaysia SME Pain Radar.

`PROJECT_SPEC.md` is the primary product specification. Read it before changing code.

## Priorities

1. Commercial usefulness
2. Correct data provenance
3. Maintainability
4. Reliability
5. Cost efficiency
6. Performance

## Architecture constraints

Do not introduce new infrastructure without clear justification.

Do not replace Laravel / Nuxt / Python / PostgreSQL / Redis without explicit approval.

Do not prematurely introduce Kafka, Kubernetes, microservices, vector databases, or event sourcing (see `PROJECT_SPEC.md` §54, §59).

## Collectors

All collectors must be:

- idempotent
- retryable
- observable
- configurable

## AI output

All AI output must:

- use a structured schema
- include confidence where appropriate
- remain traceable to evidence
- never overwrite source evidence

Never interpret AI output as verified fact.

## Scoring

Business scoring logic must be deterministic and tested. Weights live in `config/scoring.yaml`, never hard-coded.

Commercial validation evidence always outranks LLM speculation.

## Workflow

Each agent task should:

1. inspect existing code
2. read `PROJECT_SPEC.md`
3. read `AGENTS.md`
4. propose implementation scope internally
5. modify smallest necessary surface
6. write/update tests
7. run tests
8. run lint/static analysis
9. document schema/config changes
10. summarize changes

Never rewrite unrelated modules.

Before completing a task:

- run relevant tests
- run lint/static analysis
- update documentation
- report unresolved risks
