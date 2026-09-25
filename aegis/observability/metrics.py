"""AEGIS-1303: Prometheus Metrics.

Defines the AEGIS metric model. Metrics are registered lazily
to avoid import-time side effects when prometheus_client isn't installed.
"""

from __future__ import annotations

from typing import Any


class MetricsRegistry:
    """AEGIS metrics registry.

    Wraps prometheus_client counters/histograms. If prometheus_client
    is not installed, metrics are no-ops.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._guard_checks: Any = None
        self._guard_duration: Any = None
        self._guard_forbidden: Any = None
        self._guard_undecidable: Any = None
        self._audit_write_errors: Any = None
        self._kb_facts: Any = None
        self._kb_norms: Any = None
        self._api_requests: Any = None

        try:
            import prometheus_client as prom

            self._guard_checks = prom.Counter(
                "aegis_guard_checks_total",
                "Guard checks by decision and reason type",
                ["decision", "reason_type", "domain"],
            )
            self._guard_duration = prom.Histogram(
                "aegis_guard_duration_seconds",
                "Guard.check() latency",
                ["domain"],
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
            )
            self._guard_forbidden = prom.Counter(
                "aegis_guard_forbidden_total",
                "FORBIDDEN verdicts by reason type",
                ["reason_type", "domain"],
            )
            self._guard_undecidable = prom.Counter(
                "aegis_guard_undecidable_total",
                "UNDECIDABLE verdicts by reason type",
                ["reason_type", "domain"],
            )
            self._audit_write_errors = prom.Counter(
                "aegis_audit_write_errors_total",
                "Failed audit writes",
            )
            self._kb_facts = prom.Gauge(
                "aegis_kb_facts_total",
                "Loaded facts",
                ["domain"],
            )
            self._kb_norms = prom.Gauge(
                "aegis_kb_norms_total",
                "Loaded norms",
                ["domain"],
            )
            self._api_requests = prom.Counter(
                "aegis_api_requests_total",
                "HTTP requests",
                ["endpoint", "status_code"],
            )
            self._enabled = True
        except ImportError:
            pass

    def record_check(
        self,
        decision: str,
        reason_type: str,
        domain: str,
        duration_s: float,
    ) -> None:
        """Record a Guard.check() invocation."""
        if not self._enabled:
            return
        self._guard_checks.labels(
            decision=decision, reason_type=reason_type, domain=domain
        ).inc()
        self._guard_duration.labels(domain=domain).observe(duration_s)
        if decision == "FORBIDDEN":
            self._guard_forbidden.labels(
                reason_type=reason_type, domain=domain
            ).inc()
        elif decision == "UNDECIDABLE":
            self._guard_undecidable.labels(
                reason_type=reason_type, domain=domain
            ).inc()

    def record_audit_error(self) -> None:
        """Record a failed audit write."""
        if self._enabled:
            self._audit_write_errors.inc()

    def set_kb_stats(self, domain: str, facts: int, norms: int) -> None:
        """Set KB gauge values."""
        if not self._enabled:
            return
        self._kb_facts.labels(domain=domain).set(facts)
        self._kb_norms.labels(domain=domain).set(norms)

    def record_api_request(self, endpoint: str, status_code: int) -> None:
        """Record an HTTP API request."""
        if self._enabled:
            self._api_requests.labels(
                endpoint=endpoint, status_code=str(status_code)
            ).inc()


# Global singleton — initialized on first import
metrics = MetricsRegistry()
