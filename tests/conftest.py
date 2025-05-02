"""Shared pytest fixtures for unit and integration tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.enums import (
    MerchantCategory,
    RiskLevel,
    SignalSeverity,
    TransactionChannel,
    TransactionType,
)
from src.models.schemas import (
    AgentReport,
    CustomerProfile,
    GeoLocation,
    RiskSignal,
    SpendingStats,
    Transaction,
)


@pytest.fixture
def toronto_location() -> GeoLocation:
    return GeoLocation(lat=43.6532, lon=-79.3832, city="Toronto", country_code="CA")


@pytest.fixture
def vancouver_location() -> GeoLocation:
    return GeoLocation(lat=49.2827, lon=-123.1207, city="Vancouver", country_code="CA")


@pytest.fixture
def sample_transaction(toronto_location: GeoLocation) -> Transaction:
    """A typical legitimate POS transaction at a grocery store."""
    return Transaction(
        transaction_id="txn_test_001",
        customer_id="cust_abc123",
        amount=Decimal("62.50"),
        currency="CAD",
        merchant_id="merch_loblaws_001",
        merchant_name="Loblaws",
        merchant_category_code="5411",
        merchant_category=MerchantCategory.GROCERIES,
        transaction_type=TransactionType.PURCHASE,
        channel=TransactionChannel.POS,
        card_present=True,
        timestamp=datetime(2024, 11, 15, 14, 30, tzinfo=timezone.utc),
        location=toronto_location,
        device_fingerprint="dev_iphone_abc123",
    )


@pytest.fixture
def high_risk_transaction(vancouver_location: GeoLocation) -> Transaction:
    """A high-risk CNP electronics transaction from an unknown IP."""
    return Transaction(
        transaction_id="txn_test_high_001",
        customer_id="cust_abc123",
        amount=Decimal("2500.00"),
        currency="CAD",
        merchant_id="merch_bestbuy_van",
        merchant_name="Best Buy Vancouver",
        merchant_category_code="5065",
        merchant_category=MerchantCategory.ELECTRONICS,
        transaction_type=TransactionType.PURCHASE,
        channel=TransactionChannel.ONLINE,
        card_present=False,
        timestamp=datetime(2024, 11, 15, 14, 30, tzinfo=timezone.utc),
        location=vancouver_location,
        device_fingerprint="dev_unknown_xyz",
        ip_address="185.23.45.67",
    )


@pytest.fixture
def customer_profile(toronto_location: GeoLocation) -> CustomerProfile:
    """A well-established customer profile with normal spending history."""
    stats = SpendingStats(
        window_days=30,
        mean_amount=65.0,
        std_amount=40.0,
        transaction_count=35,
        top_categories=["groceries", "gas_station", "restaurant", "pharmacy"],
        typical_hour_range=(8, 21),
    )
    return CustomerProfile(
        customer_id="cust_abc123",
        account_age_days=1460,  # 4 years
        lifetime_transaction_count=1200,
        stats_7d=SpendingStats(
            window_days=7,
            mean_amount=62.0,
            std_amount=38.0,
            transaction_count=8,
            top_categories=["groceries", "restaurant"],
        ),
        stats_30d=stats,
        stats_90d=SpendingStats(
            window_days=90,
            mean_amount=68.0,
            std_amount=42.0,
            transaction_count=105,
            top_categories=["groceries", "gas_station", "restaurant", "pharmacy"],
        ),
        last_known_location=toronto_location,
        last_transaction_timestamp=datetime(2024, 11, 15, 10, 0, tzinfo=timezone.utc),
        known_device_fingerprints=["dev_iphone_abc123", "dev_macbook_def456"],
        known_ip_prefixes=["192.168.1"],
    )


@pytest.fixture
def mock_llm_response_low_risk() -> str:
    return """{
        "risk_level": "LOW",
        "fraud_probability": 0.08,
        "confidence": 0.88,
        "reasoning": "Transaction amount is within normal range. Merchant category is consistent with the customer's purchase history. Geographic location matches the customer's home city.",
        "risk_signals": []
    }"""


@pytest.fixture
def mock_llm_response_high_risk() -> str:
    return """{
        "risk_level": "HIGH",
        "fraud_probability": 0.82,
        "confidence": 0.79,
        "reasoning": "Transaction amount of $2500 is 38 standard deviations above this customer's 30-day mean. The merchant category (electronics) is not in the customer's purchase history. New device fingerprint detected. Possible geo-velocity violation.",
        "risk_signals": [
            {"signal_type": "amount_anomaly", "description": "Amount 38x above customer mean", "severity": "HIGH"},
            {"signal_type": "new_device", "description": "Device fingerprint not seen before", "severity": "HIGH"}
        ]
    }"""


@pytest.fixture
def sample_agent_report() -> AgentReport:
    return AgentReport(
        agent_name="transaction_agent",
        risk_level=RiskLevel.HIGH,
        fraud_probability=0.82,
        confidence=0.79,
        reasoning="Transaction shows multiple high-risk indicators.",
        risk_signals=[
            RiskSignal(
                signal_type="amount_anomaly",
                description="Amount significantly above customer mean",
                severity=SignalSeverity.HIGH,
                score=0.90,
                source_agent="transaction_agent",
            )
        ],
    )
