"""Structured LLM extraction schemas (PROJECT_SPEC.md §24).

§24 is emphatic about what the LLM is and is not asked. It must NOT be asked
"Is this a good business opportunity?" — that judgement belongs to the
deterministic scoring engine, where it is explainable and testable. The LLM does
bounded extraction only: read one document, report what problem it describes.

Every field is constrained (enums, 0-100 bounds) so a malformed or hallucinated
response fails validation rather than flowing into the scoring engine as if it
were measured fact. §24: "Validate all LLM output with JSON Schema/Pydantic.
Reject malformed results."
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Frequency(StrEnum):
    """Deliberately matches config/signal_rules.yaml's frequency_hint values so
    LLM output and rule-based output land in the same `problem_signals` column
    and remain comparable."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    UNKNOWN = "unknown"


class BuyerType(StrEnum):
    """§5's buyer groups. Constrained to an enum so the model cannot invent a
    buyer category that no downstream scoring rule knows how to weigh."""

    BUSINESS_OWNER = "business_owner"
    OPERATIONS_MANAGER = "operations_manager"
    FINANCE_DEPARTMENT = "finance_department"
    ACCOUNTING_FIRM = "accounting_firm"
    ERP_POS_PROVIDER = "erp_pos_provider"
    BUSINESS_CONSULTANT = "business_consultant"
    INDUSTRY_ASSOCIATION = "industry_association"
    AGENCY = "agency"
    SAAS_PROVIDER = "saas_provider"
    UNKNOWN = "unknown"


class ProblemExtraction(BaseModel):
    """One document's extracted problem signal — §24's example JSON, typed.

    `model_config` forbids extra keys: a provider that returns additional
    invented fields is treated as malformed rather than silently truncated,
    which is how a prompt-injection or a drifting model version gets caught.
    """

    model_config = {"extra": "forbid"}

    problem_present: bool = Field(
        description="Whether this text describes a concrete business problem at all."
    )
    topic: str | None = Field(
        default=None, description="Topic slug from the configured taxonomy."
    )
    subtopic: str | None = Field(default=None, description="Subtopic slug, if identifiable.")
    affected_role: str | None = Field(
        default=None, description="Who experiences the problem (e.g. cashier, finance staff)."
    )
    buyer_type: BuyerType = Field(
        default=BuyerType.UNKNOWN,
        description="Who would pay to solve it — often NOT the affected role (§5).",
    )
    frequency: Frequency = Field(default=Frequency.UNKNOWN)

    severity: int = Field(default=0, ge=0, le=100)
    economic_impact: int = Field(default=0, ge=0, le=100)
    urgency: int = Field(default=0, ge=0, le=100)

    problem_summary: str | None = Field(
        default=None, max_length=500, description="One sentence, in the document's own terms."
    )
    suggested_solution_category: str | None = Field(default=None, max_length=100)

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="The model's own confidence. Kept separate from severity — an extraction "
        "can be confidently low-severity, or a tentative guess at a severe problem.",
    )


class ExtractionResult(BaseModel):
    """An extraction plus the provenance §70 requires stored alongside it."""

    extraction: ProblemExtraction
    provider: str
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
