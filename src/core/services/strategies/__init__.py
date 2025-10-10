"""Strategy Pattern implementations for multi-mode analysis (V2.3).

This package contains concrete strategy implementations for different game modes:
- SRStrategy: Summoner's Rift (full V2.2 analysis)
- ARAMStrategy: ARAM mode (V1-Lite + ARAM-specific metrics)
- ArenaStrategy: Arena mode (V1-Lite + Arena-specific metrics)
- FallbackStrategy: Graceful degradation for unsupported modes

Author: CLI 2 (Backend)
Date: 2025-10-07
Phase: V2.3
"""

# Note: Individual strategies are imported lazily by AnalysisStrategyFactory
# to avoid circular imports. Do not add imports here unless necessary.
