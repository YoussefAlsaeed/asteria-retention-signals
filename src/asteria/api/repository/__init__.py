"""Read-only access to the analytical product. All SQL the API runs lives in this package.

Queries are grouped by domain (objectives, signals, trust); `Repository` combines them so
routers depend on a single object.
"""

from asteria.api.repository.base import REQUIRED_TABLES, BaseRepository, DataNotReady
from asteria.api.repository.objectives import ObjectiveQueries
from asteria.api.repository.signals import SignalQueries
from asteria.api.repository.trust import TrustQueries


class Repository(ObjectiveQueries, SignalQueries, TrustQueries):
    """Every read the API performs, over one DuckDB file."""


__all__ = ["REQUIRED_TABLES", "BaseRepository", "DataNotReady", "Repository"]
