"""Config paths that work both inside the container and in CI.

The containers mount `config/` at `/config` and the package at `/app`, so
production code defaults to those absolute paths. CI runs pytest straight from a
checkout where neither exists. Rather than teaching every test about both
layouts, resolve once here: honour the env var the container sets, otherwise
walk up to the repo root.
"""

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# In a checkout this is the repo root (apps/intelligence/tests → ../../..). In
# the container the package is mounted at /app with nothing above it, so there
# is no repo root to find — hence the guard rather than an index that raises.
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[3] if len(_parents) > 3 else None


def config_path(filename: str, env_var: str) -> str:
    configured = os.environ.get(env_var)
    if configured and Path(configured).exists():
        return configured
    if REPO_ROOT is not None:
        return str(REPO_ROOT / "config" / filename)
    # Nothing resolved. Return the container default so the failure names a
    # path someone can act on, rather than an empty string.
    return f"/config/{filename}"


SCORING_CONFIG_PATH = config_path("scoring.yaml", "SCORING_CONFIG_PATH")
TOPICS_REGISTRY_PATH = config_path("topics.yaml", "TOPICS_REGISTRY_PATH")
LLM_CONFIG_PATH = config_path("llm.yaml", "LLM_CONFIG_PATH")

_eval_cases = os.environ.get("EVAL_CASES_PATH")
EVAL_CASES_PATH = (
    _eval_cases
    if _eval_cases and Path(_eval_cases).exists()
    else str(PACKAGE_ROOT / "evaluation" / "cases.yaml")
)
