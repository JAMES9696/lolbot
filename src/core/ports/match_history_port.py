"""Port interface for match history retrieval.

Abstracts the Riot API match history operations for dependency inversion.
"""

from abc import ABC, abstractmethod


class IMatchHistoryService(ABC):
    """Port interface for retrieving player match history.

    This abstraction decouples CLI 1 from CLI 2's Riot API implementation
    (whether using Cassiopeia or direct HTTP calls).
    """

    @abstractmethod
    async def get_match_id_list(self, puuid: str, region: str, count: int = 20) -> list[str]:
        """Retrieve list of recent match IDs for a player.

        Args:
            puuid: Player's persistent unique ID
            region: Regional routing (e.g., 'americas', 'asia', 'europe')
            count: Maximum number of match IDs to return (default 20)

        Returns:
            List of match IDs in Match-V5 format (newest first)

        Raises:
            RiotAPIError: If API call fails
            PlayerNotFoundError: If PUUID is invalid
        """
        pass

    @abstractmethod
    async def get_analysis_status(self, match_id: str) -> dict[str, str] | None:
        """Check if match analysis already exists in database.

        Args:
            match_id: Match ID to check

        Returns:
            Dictionary with status info if exists:
            {
                'status': 'pending' | 'processing' | 'completed' | 'failed',
                'created_at': ISO timestamp,
                'result_data': JSONB (if completed)
            }
            None if no analysis record exists

        Raises:
            DatabaseError: If query fails
        """
        pass
