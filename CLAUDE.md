# CLAUDE.md

Read `PROJECT_SPEC.md` and `AGENTS.md` before changing code.

When requirements conflict: `PROJECT_SPEC.md` defines product behavior.

Do not implement future phases/milestones unless the current task requires them.

Prefer boring, production-proven solutions.

Do not prematurely introduce:

- Kafka
- Kubernetes
- microservices
- vector databases
- event sourcing

When implementing data collectors: preserve raw source provenance.

When implementing LLM functionality: create a provider abstraction and structured responses.

When implementing scoring: keep weights configurable (`config/scoring.yaml`) and write deterministic tests.

When making architectural changes: document rationale in `docs/architecture.md`.
