"""Unit tests for the feature engineering module."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.data.feature_engineering import FeatureEngineer, _haversine
from src.models.enums import MerchantCategory, TransactionChannel, TransactionType
from src.models.schemas import (
    CustomerProfile,
    GeoLocation,
    SpendingStats,
    Transaction,
)


@pytest.fixture
def engineer() -> FeatureEngineer:
    return FeatureEngineer()


def _make_txn(**kwargs) -> Transaction:
    defaults = dict(
        transaction_id="txn_test",
        customer_id="cust_test",
        amount=Decimal("100.00"),
        merchant_id="merch_test",
        merchant_name="Test Merchant",
        merchant_category_code="5411",
        merchant_category=MerchantCategory.GROCERIES,
        transaction_type=TransactionType.PURCHASE,
        channel=TransactionChannel.POS,
        card_present=True,
        timestamp=datetime(2024, 11, 15, 14, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


class TestHaversine:
    def test_same_point(self) -> None:
        assert _haversine(43.0, -79.0, 43.0, -79.0) == pytest.approx(0.0)

    def test_toronto_vancouver(self) -> None:
        # ~3,360 km
        dist = _haversine(43.6532, -79.3832, 49.2827, -123.1207)
        assert 3_300 < dist < 3_500

    def test_symmetry(self) -> None:
        d1 = _haversine(43.0, -79.0, 49.0, -123.0)
        d2 = _haversine(49.0, -123.0, 43.0, -79.0)
        assert d1 == pytest.approx(d2)


class TestFeatureEngineering:
    def test_no_profile_defaults(self, engineer: FeatureEngineer) -> None:
        txn = _make_txn()
        features = engineer.compute_transaction_features(txn, profile=None)
        assert features["amount_z_score"] == 0.0
        assert features["amount_percentile"] == 50.0
        assert features["geo_velocity_kmh"] == 0.0

    def test_amount_z_score_high(
        self, engineer: FeatureEngineer, customer_profile: CustomerProfile
    ) -> None:
        # amount = 3000, mean=65, std=40 → z ≈ 73
        txn = _make_txn(amount=Decimal("3000.00"))
        features = engineer.compute_transaction_features(txn, customer_profile)
        assert features["amount_z_score"] > 10

    def test_amount_z_score_normal(
        self, engineer: FeatureEngineer, customer_profile: CustomerProfile
    ) -> None:
        txn = _make_txn(amount=Decimal("70.00"))
        features = engineer.compute_transaction_features(txn, customer_profile)
        assert abs(features["amount_z_score"]) < 1.0

    def test_time_anomaly_night(self, engineer: FeatureEngineer) -> None:
        txn = _make_txn(
            timestamp=datetime(2024, 11, 15, 3, 0, tzinfo=timezone.utc)  # 03:00 UTC
        )
        features = engineer.compute_transaction_features(txn, profile=None)
        assert features["time_anomaly"] is True

    def test_time_anomaly_day(self, engineer: FeatureEngineer) -> None:
        txn = _make_txn(
            timestamp=datetime(2024, 11, 15, 14, 0, tzinfo=timezone.utc)  # 14:00 UTC
        )
        features = engineer.compute_transaction_features(txn, profile=None)
        assert features["time_anomaly"] is False

    def test_geo_velocity_impossible(
        self, engineer: FeatureEngineer, customer_profile: CustomerProfile
    ) -> None:
        # Toronto → Vancouver in 30 minutes = ~8800 km/h
        txn = _make_txn(
            timestamp=datetime(2024, 11, 15, 14, 30, tzinfo=timezone.utc),
            location=GeoLocation(lat=49.2827, lon=-123.1207, city="Vancouver"),
        )
        features = engineer.compute_transaction_features(txn, customer_profile)
        assert features["geo_velocity_kmh"] > 900

    def test_new_device_flag(
        self, engineer: FeatureEngineer, customer_profile: CustomerProfile
    ) -> None:
        txn = _make_txn(device_fingerprint="dev_completely_new_xyz")
        features = engineer.compute_transaction_features(txn, customer_profile)
        assert features["is_new_device"] is True

    def test_known_device_no_flag(
        self, engineer: FeatureEngineer, customer_profile: CustomerProfile
    ) -> None:
        txn = _make_txn(device_fingerprint="dev_iphone_abc123")  # known device
        features = engineer.compute_transaction_features(txn, customer_profile)
        assert features["is_new_device"] is False

    def test_merchant_category_risk(self, engineer: FeatureEngineer) -> None:
        txn_grocery = _make_txn(merchant_category=MerchantCategory.GROCERIES)
        txn_crypto = _make_txn(merchant_category=MerchantCategory.CRYPTOCURRENCY)
        f_grocery = engineer.compute_transaction_features(txn_grocery, profile=None)
        f_crypto = engineer.compute_transaction_features(txn_crypto, profile=None)
        assert f_crypto["merchant_category_risk"] > f_grocery["merchant_category_risk"]
