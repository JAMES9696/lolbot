"""Factory for creating RSO adapters (real or mock)."""

import logging

from src.adapters.mock_rso_adapter import MockRSOAdapter
from src.adapters.rso_adapter import RSOAdapter
from src.config.settings import get_settings
from src.core.rso_port import RSOPort

logger = logging.getLogger(__name__)


def create_rso_adapter(redis_client=None) -> RSOPort:
    """Create RSO adapter based on configuration.

    This factory function creates either a real RSOAdapter (requiring Production
    API Key) or a MockRSOAdapter (for development testing) based on the
    MOCK_RSO_ENABLED configuration flag.

    Args:
        redis_client: Optional Redis client for state storage

    Returns:
        RSOPort implementation (RSOAdapter or MockRSOAdapter)
    """
    settings = get_settings()

    if settings.mock_rso_enabled:
        logger.info("🧪 Using MockRSOAdapter for development testing")
        logger.warning(
            "Mock RSO is enabled - /bind will use test accounts. "
            "Set MOCK_RSO_ENABLED=false for production."
        )
        return MockRSOAdapter(redis_client=redis_client)
    else:
        logger.info("🔐 Using real RSOAdapter with Production API Key")
        if not settings.security_rso_client_id or not settings.security_rso_client_secret:
            logger.warning(
                "RSO credentials not configured. /bind command will fail. "
                "Set MOCK_RSO_ENABLED=true for testing or configure Production API Key."
            )
        return RSOAdapter(redis_client=redis_client)
