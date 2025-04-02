"""Feature engineering for the Transaction Analysis Agent.

Computes derived numerical features from a Transaction + CustomerProfile
pair.  All features are normalised to comparable scales to assist the LLM's
reasoning and to drive rule-based signal thresholds.

Features produced:
- ``amount_z_score``            – How many std-devs above the 30d mean
- ``amount_percentile``         – Estimated percentile within 30d distribution
- ``time_anomaly``              – Boolean; transaction during unusual hours
- ``geo_velocity_kmh``          – Implied travel speed since last transaction
- ``days_since_last_txn``       – Recency of the most recent prior transaction
- ``merchant_category_risk``    – Merchant-category base risk score [0, 1]
- ``new_merchant``              – Boolean; merchant not seen in 90d history
- ``is_card_not_present``       – CNP flag
- ``is_new_device``             – Device fingerprint not in customer history
- ``is_high_velocity``          – >5 txns in last 7 days (rough hourly rate)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import structlog

from src.models.schemas import CustomerProfile, Transaction

logger = structlog.get_logger(__name__)

# Earth radius in km (WGS-84 mean)
_EARTH_RADIUS_KM = 6_371.0


class FeatureEngineer:
    """Computes fraud-relevant features for a given transaction."""

    def compute_transaction_features(
        self,
        transaction: Transaction,
        profile: CustomerProfile | None,
    ) -> dict[str, Any]:
        """Compute all features for a transaction.

        Args:
            transaction: The transaction to featurise.
            profile: The customer's historical profile.  If ``None``, safe
                default values are used.

        Returns:
            Dict mapping feature name → computed value.
        """
        features: dict[str, Any] = {}

        # ── Amount features ───────────────────────────────────────────
        amount = float(transaction.amount)
        if profile and profile.stats_30d and profile.stats_30d.std_amount > 0:
            mean = profile.stats_30d.mean_amount
            std = profile.stats_30d.std_amount
            z = (amount - mean) / std
            features["amount_z_score"] = round(z, 3)
            features["amount_vs_30d_mean"] = round(amount / max(mean, 1), 3)
            features["amount_percentile"] = round(
                _normal_cdf(z) * 100, 1
            )
        else:
            features["amount_z_score"] = 0.0
            features["amount_vs_30d_mean"] = 1.0
            features["amount_percentile"] = 50.0

        # ── Time features ─────────────────────────────────────────────
        hour = transaction.timestamp.hour  # UTC hour
        # 01:00 – 05:00 UTC is suspicious for most consumers
        time_anomaly_start = 1
        time_anomaly_end = 5
        features["transaction_hour_utc"] = hour
        features["time_anomaly"] = time_anomaly_start <= hour <= time_anomaly_end

        # ── Geo-velocity ──────────────────────────────────────────────
        if (
            transaction.location
            and profile
            and profile.last_known_location
            and profile.last_transaction_timestamp
        ):
            dist_km = _haversine(
                profile.last_known_location.lat,
                profile.last_known_location.lon,
                transaction.location.lat,
                transaction.location.lon,
            )
            now = transaction.timestamp.replace(tzinfo=timezone.utc)
            prev = profile.last_transaction_timestamp
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            elapsed_hours = max((now - prev).total_seconds() / 3600, 1 / 60)
            kmh = dist_km / elapsed_hours
            features["geo_distance_km"] = round(dist_km, 1)
            features["elapsed_since_last_txn_hours"] = round(elapsed_hours, 3)
            features["geo_velocity_kmh"] = round(kmh, 1)
        else:
            features["geo_distance_km"] = 0.0
            features["elapsed_since_last_txn_hours"] = None
            features["geo_velocity_kmh"] = 0.0

        # ── Recency ───────────────────────────────────────────────────
        if profile and profile.last_transaction_timestamp:
            now = transaction.timestamp.replace(tzinfo=timezone.utc)
            prev = profile.last_transaction_timestamp
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            features["days_since_last_txn"] = round(
                (now - prev).total_seconds() / 86_400, 2
            )
        else:
            features["days_since_last_txn"] = None

        # ── Merchant risk ─────────────────────────────────────────────
        features["merchant_category_risk"] = transaction.merchant_category.base_risk_score

        if profile and profile.stats_90d:
            known_cats = {c.lower() for c in profile.stats_90d.top_categories}
            features["new_merchant_category"] = (
                transaction.merchant_category.value not in known_cats
            )
        else:
            features["new_merchant_category"] = None

        # ── Card / channel ────────────────────────────────────────────
        features["is_card_not_present"] = not transaction.card_present

        # ── Device ────────────────────────────────────────────────────
        if transaction.device_fingerprint and profile and profile.known_device_fingerprints:
            features["is_new_device"] = (
                transaction.device_fingerprint not in profile.known_device_fingerprints
            )
        else:
            features["is_new_device"] = None

        # ── Velocity (rough) ──────────────────────────────────────────
        if profile and profile.stats_7d:
            hourly = profile.stats_7d.transaction_count / (7 * 24)
            features["txn_per_hour_7d"] = round(hourly, 4)
            features["is_high_velocity"] = hourly > 5
        else:
            features["txn_per_hour_7d"] = None
            features["is_high_velocity"] = False

        return features


# ── Math utilities ────────────────────────────────────────────────────────


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in km between two WGS-84 coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _normal_cdf(z: float) -> float:
    """Approximate the CDF of the standard normal distribution."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
