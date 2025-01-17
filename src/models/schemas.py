"""Pydantic schemas for the fraud detection system.

All cross-agent data structures are defined here to enforce a single
source of truth for validation and serialisation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.enums import (
    FraudTypology,
    MerchantCategory,
    RecommendedAction,
    RiskLevel,
    SignalSeverity,
    TransactionChannel,
    TransactionType,
)


# ── Geo ──────────────────────────────────────────────────────────────────


class GeoLocation(BaseModel):
    """WGS-84 geographic coordinate with optional metadata."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    city: str | None = Field(default=None)
    country_code: str | None = Field(default=None, max_length=2)  # ISO 3166-1 alpha-2

    model_config = {"frozen": True}


# ── Transaction ───────────────────────────────────────────────────────────


class Transaction(BaseModel):
    """Canonical transaction object passed through the agent graph.

    Represents a single payment event as it would arrive from the
    bank's transaction processing system.
    """

    transaction_id: str = Field(
        default_factory=lambda: f"txn_{uuid4().hex[:12]}",
        description="Unique transaction identifier (UUID-derived)",
    )
    customer_id: str = Field(..., description="Opaque customer identifier")
    amount: Decimal = Field(..., ge=Decimal("0"), description="Transaction amount")
    currency: str = Field(default="CAD", max_length=3, description="ISO 4217 currency code")
    merchant_id: str = Field(..., description="Merchant identifier")
    merchant_name: str = Field(..., description="Human-readable merchant name")
    merchant_category_code: str = Field(
        ..., description="ISO 18245 Merchant Category Code (MCC)"
    )
    merchant_category: MerchantCategory = Field(..., description="Normalised merchant category")
    transaction_type: TransactionType = Field(default=TransactionType.PURCHASE)
    channel: TransactionChannel = Field(..., description="Originating transaction channel")
    card_present: bool = Field(..., description="Whether physical card was present")
    timestamp: datetime = Field(..., description="UTC transaction timestamp")
    location: GeoLocation | None = Field(
        default=None, description="Transaction geographic location"
    )
    device_fingerprint: str | None = Field(
        default=None, description="Hashed device identifier"
    )
    ip_address: str | None = Field(
        default=None, description="Client IP (IPv4 or IPv6)"
    )
    recurring: bool = Field(
        default=False, description="Whether this is a recurring/subscription charge"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extensible key-value metadata"
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _validate_card_present_channel(self) -> "Transaction":
        """Ensure card_present flag is consistent with the channel."""
        expected = self.channel.card_present
        if self.card_present != expected:
            # Soft warning — don't raise, just log inconsistency via metadata
            self.metadata["card_present_mismatch"] = True
        return self


# ── Risk signals ─────────────────────────────────────────────────────────


class RiskSignal(BaseModel):
    """A single atomic risk indicator emitted by an agent."""

    signal_type: str = Field(..., description="Machine-readable signal type key")
    description: str = Field(..., description="Human-readable description")
    severity: SignalSeverity = Field(default=SignalSeverity.MEDIUM)
    score: float = Field(default=0.5, ge=0.0, le=1.0, description="Signal strength 0–1")
    source_agent: str = Field(default="", description="Agent that emitted this signal")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Agent report ─────────────────────────────────────────────────────────


class AgentReport(BaseModel):
    """Structured output from a single specialised agent."""

    agent_name: str = Field(..., description="Identifier of the emitting agent")
    risk_level: RiskLevel = Field(...)
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Analyst-style narrative reasoning")
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    fraud_type: FraudTypology | None = Field(default=None)
    regulatory_flags: list[str] = Field(default_factory=list)
    processing_time_ms: float = Field(default=0.0)
    raw_llm_response: str = Field(default="", description="Raw LLM output for auditing")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Customer profile (runtime) ────────────────────────────────────────────


class SpendingStats(BaseModel):
    """Aggregated spending statistics for a customer over a time window."""

    window_days: int
    mean_amount: float
    std_amount: float
    transaction_count: int
    top_categories: list[str] = Field(default_factory=list)
    typical_hour_range: tuple[int, int] = Field(default=(8, 22))


class CustomerProfile(BaseModel):
    """Customer behavioural baseline used by agents for anomaly scoring.

    Built from the customer's historical transaction data and refreshed
    incrementally.
    """

    customer_id: str
    account_age_days: int = Field(default=0)
    lifetime_transaction_count: int = Field(default=0)
    stats_7d: SpendingStats | None = None
    stats_30d: SpendingStats | None = None
    stats_90d: SpendingStats | None = None
    last_known_location: GeoLocation | None = None
    last_transaction_timestamp: datetime | None = None
    known_device_fingerprints: list[str] = Field(default_factory=list)
    known_ip_prefixes: list[str] = Field(default_factory=list)
    high_risk_flags: list[str] = Field(default_factory=list)


# ── Audit trail ──────────────────────────────────────────────────────────


class AuditRecord(BaseModel):
    """Immutable audit log entry recording a state transition or agent call."""

    record_id: str = Field(default_factory=lambda: uuid4().hex)
    transaction_id: str
    event_type: str = Field(
        ..., description="e.g. AGENT_CALLED, RISK_ROUTED, FINAL_DECISION"
    )
    agent_name: str | None = None
    previous_risk_level: RiskLevel | None = None
    new_risk_level: RiskLevel | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Final assessment ─────────────────────────────────────────────────────


class FraudAssessment(BaseModel):
    """Final fraud determination returned by the API.

    Aggregates the outputs of all agents into a single, compliance-ready
    decision object.
    """

    transaction_id: str
    risk_level: RiskLevel
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    is_fraudulent: bool
    fraud_type: FraudTypology | None = None
    explanation: str = Field(
        ..., description="Plain-English explanation for compliance and operations teams"
    )
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    agent_reports: list[AgentReport] = Field(default_factory=list)
    recommended_action: RecommendedAction
    regulatory_flags: list[str] = Field(default_factory=list)
    processing_time_ms: float
    model_version: str = Field(default="1.0.0")
    audit_trail: list[AuditRecord] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=datetime.utcnow)


# ── API request/response wrappers ─────────────────────────────────────────


class ScoreRequest(BaseModel):
    """Request body for POST /api/v1/transactions/score."""

    transaction: Transaction
    customer_profile: CustomerProfile | None = Field(
        default=None,
        description="Pre-computed customer profile.  If omitted the system will "
        "attempt to look up historical data from the feature store.",
    )


class ScoreResponse(BaseModel):
    """Response body for POST /api/v1/transactions/score."""

    assessment: FraudAssessment
    correlation_id: str


class BatchScoreRequest(BaseModel):
    """Request body for POST /api/v1/transactions/batch."""

    transactions: list[ScoreRequest] = Field(..., max_length=100)


class BatchScoreResponse(BaseModel):
    """Response body for POST /api/v1/transactions/batch."""

    assessments: list[FraudAssessment]
    total: int
    flagged: int
    processing_time_ms: float
    correlation_id: str


class HealthResponse(BaseModel):
    """Response body for GET /api/v1/health."""

    status: str
    version: str
    vector_store: str
    llm_provider: str
    environment: str
    uptime_seconds: float
