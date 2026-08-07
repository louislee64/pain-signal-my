from functools import lru_cache

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
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


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(Settings.from_env().database_url)
