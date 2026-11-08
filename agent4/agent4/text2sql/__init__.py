"""Safe Vietnamese financial text-to-SQL application layer.

The public boundary is intentionally plan based: model/user text never reaches
the SQL compiler.  Only :class:`ValidatedPlan` objects can be compiled.
"""

from .api import create_app
from .service import QueryService, build_default_service

__all__ = ["QueryService", "build_default_service", "create_app"]
