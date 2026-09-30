"""One router per resource. `ROUTERS` is the order they are mounted in."""

from asteria.api.routers import associations, findings, health, meta, objectives, signals, trust

ROUTERS = [
    health.router,
    meta.router,
    objectives.router,
    signals.router,
    associations.router,
    findings.router,
    trust.router,
]

__all__ = ["ROUTERS"]
