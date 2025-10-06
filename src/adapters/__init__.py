"""Adapter implementations for external services."""

from .database import DatabaseAdapter
from .riot_api import RiotAPIAdapter

__all__ = ["RiotAPIAdapter", "DatabaseAdapter"]
