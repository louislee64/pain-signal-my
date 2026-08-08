from functools import lru_cache

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from intelligence.config import Settings

metadata = MetaData()

sources_table = Table(
    "sources",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("slug", String, nullable=False, unique=True),
    Column("source_type", String, nullable=False),
    Column("base_url", String, nullable=True),
    Column("collector", String, nullable=False),
    Column("config", JSONB, nullable=True),
    Column("collection_method", String, nullable=True),
    Column("rate_limit", String, nullable=True),
    Column("reliability_score", SmallInteger, nullable=True),
    Column("license", String, nullable=True),
    Column("terms_url", String, nullable=True),
    Column("terms_status", String, nullable=False),
    Column("personal_data_risk", String, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("last_synced_at", DateTime(timezone=True), nullable=True),
    Column("last_dataset_updated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ingestion_runs_table = Table(
    "ingestion_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("status", String, nullable=False),
    Column("records_received", Integer, nullable=False),
    Column("records_inserted", Integer, nullable=False),
    Column("records_updated", Integer, nullable=False),
    Column("records_rejected", Integer, nullable=False),
    Column("error_count", Integer, nullable=False),
    Column("metadata_json", JSONB, nullable=True),
)

raw_documents_table = Table(
    "raw_documents",
    metadata,
    Column("id", String(26), primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("external_id", String, nullable=False),
    Column("url", Text, nullable=True),
    Column("title", Text, nullable=True),
    Column("body", Text, nullable=True),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("language_raw", String, nullable=True),
    Column("region_raw", String, nullable=True),
    Column("metadata_json", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

normalized_documents_table = Table(
    "normalized_documents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("raw_document_id", String(26), ForeignKey("raw_documents.id"), nullable=False, unique=True),
    Column("cleaned_text", Text, nullable=True),
    Column("language", String, nullable=True),
    Column("country", String, nullable=True),
    Column("state", String, nullable=True),
    Column("city", String, nullable=True),
    Column("industry_id", Integer, nullable=True),
    Column("normalized_content_hash", String(64), nullable=True),
    Column(
        "duplicate_of_normalized_document_id",
        Integer,
        ForeignKey("normalized_documents.id"),
        nullable=True,
    ),
    Column("processed_at", DateTime(timezone=True), nullable=False),
)

topics_table = Table(
    "topics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("parent_id", Integer, ForeignKey("topics.id"), nullable=True),
    Column("slug", String, nullable=False, unique=True),
    Column("name", String, nullable=False),
    Column("description", Text, nullable=True),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

document_topics_table = Table(
    "document_topics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("document_id", Integer, ForeignKey("normalized_documents.id"), nullable=False),
    Column("topic_id", Integer, ForeignKey("topics.id"), nullable=False),
    Column("confidence", SmallInteger, nullable=False),
    Column("classification_method", String, nullable=False),
    Column("model_version", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

problem_signals_table = Table(
    "problem_signals",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("document_id", Integer, ForeignKey("normalized_documents.id"), nullable=False),
    Column("topic_id", Integer, ForeignKey("topics.id"), nullable=False),
    Column("signal_date", Date, nullable=False),
    Column("region", String, nullable=True),
    Column("industry_id", Integer, nullable=True),
    Column("severity_score", SmallInteger, nullable=True),
    Column("urgency_score", SmallInteger, nullable=True),
    Column("economic_impact_score", SmallInteger, nullable=True),
    Column("frequency_hint", String, nullable=True),
    Column("payer_type", String, nullable=True),
    Column("evidence_json", JSONB, nullable=True),
    Column("classification_method", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

keywords_table = Table(
    "keywords",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("keyword", String, nullable=False),
    Column("keyword_group", String, nullable=False),
    Column("language", String, nullable=True),
    Column("geo", String, nullable=False),
    Column("source", String, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

trend_metrics_table = Table(
    "trend_metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("date", Date, nullable=False),
    Column("keyword_id", Integer, ForeignKey("keywords.id"), nullable=False),
    Column("country", String, nullable=False),
    Column("region", String, nullable=False),
    Column("interest", SmallInteger, nullable=False),
    Column("rolling_7d", Numeric(6, 2), nullable=True),
    Column("rolling_30d", Numeric(6, 2), nullable=True),
    Column("baseline_90d", Numeric(6, 2), nullable=True),
    Column("growth_7d", Numeric(8, 2), nullable=True),
    Column("growth_30d", Numeric(8, 2), nullable=True),
    Column("growth_score", Numeric(8, 4), nullable=True),
    Column("z_score", Numeric(8, 4), nullable=True),
    Column("collection_method", String, nullable=False),
    Column("collection_batch", String(26), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

topic_daily_metrics_table = Table(
    "topic_daily_metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("date", Date, nullable=False),
    Column("topic_id", Integer, ForeignKey("topics.id"), nullable=False),
    Column("region", String, nullable=False),
    Column("industry_id", Integer, nullable=True),
    Column("mention_count", Integer, nullable=False),
    Column("source_count", Integer, nullable=False),
    Column("avg_severity", Numeric(5, 2), nullable=True),
    Column("avg_urgency", Numeric(5, 2), nullable=True),
    Column("trend_score", Numeric(5, 2), nullable=True),
    Column("official_score", Numeric(5, 2), nullable=True),
    Column("pain_score", Numeric(5, 2), nullable=True),
    Column("commercial_score", Numeric(5, 2), nullable=True),
    Column("opportunity_score", Numeric(5, 2), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


opportunities_table = Table(
    "opportunities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("topic_id", Integer, ForeignKey("topics.id"), nullable=False, unique=True),
    Column("title", String, nullable=False),
    Column("description", Text, nullable=True),
    Column("industry_id", Integer, nullable=True),
    Column("target_buyer", String, nullable=True),
    Column("status", String, nullable=False),
    Column("pain_score", Numeric(5, 2), nullable=True),
    Column("commercial_score", Numeric(5, 2), nullable=True),
    Column("opportunity_score", Numeric(5, 2), nullable=True),
    Column("confidence_score", Numeric(5, 2), nullable=True),
    Column("recommendation", String, nullable=True),
    Column("score_components", JSONB, nullable=True),
    Column("scoring_config_version", String, nullable=True),
    Column("scored_at", DateTime(timezone=True), nullable=True),
    Column("problem_statement", Text, nullable=True),
    Column("existing_workaround", Text, nullable=True),
    Column("possible_solution", Text, nullable=True),
    Column("monetization_model", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ai_usage_table = Table(
    "ai_usage",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("operation", String, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("estimated_cost", Numeric(12, 6), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("document_id", String(26), ForeignKey("raw_documents.id"), nullable=True),
    Column("prompt_version", String, nullable=True),
    Column("processing_version", String, nullable=True),
    Column("succeeded", Boolean, nullable=False),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(Settings.from_env().database_url)
