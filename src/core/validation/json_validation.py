"""JSON validation helpers for V2 payloads with metrics and logging.

Applies strict Pydantic V2 validation and reports failures to Prometheus
so CLI 3 can visualize JSON parse failure rates per schema.
"""

from __future__ import annotations

from pydantic import ValidationError

from src.core.metrics import mark_json_validation_error
from src.contracts.v2_team_analysis import V2TeamAnalysisReport
from src.core.observability import llm_debug_wrapper


@llm_debug_wrapper(
    capture_result=False,
    capture_args=False,
    log_level="INFO",
    add_metadata={"operation": "json_validate", "schema": "v2_team_analysis"},
)
def validate_v2_team_json(json_str: str) -> V2TeamAnalysisReport:
    """Validate and parse V2 team analysis JSON string.

    Raises ValidationError on failure and increments Prometheus counter.
    """
    try:
        return V2TeamAnalysisReport.model_validate_json(json_str)
    except ValidationError as e:
        mark_json_validation_error(
            "v2_team_analysis", e.errors()[0].get("type", "validation_error")
        )
        raise
