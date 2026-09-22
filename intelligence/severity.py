"""Five-level severity model using observable signals only."""

from __future__ import annotations


class SeverityEngine:
    def assess(self, health_score: float, anomaly_score: float, persistence: float = 0.0, affected_channels: int = 1) -> str:
        composite = (100.0 - health_score) * 0.6 + anomaly_score * 100.0 * 0.4 + persistence * 20.0 + max(0, affected_channels - 1) * 5
        if composite < 15:
            return "NORMAL"
        if composite < 30:
            return "INFORMATION"
        if composite < 50:
            return "WARNING"
        if composite < 75:
            return "CRITICAL"
        return "SEVERE"
