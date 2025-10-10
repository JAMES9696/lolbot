from __future__ import annotations

from pydantic import BaseModel, Field


class TeamfightSegment(BaseModel):
    start_ts: int = Field(description="segment start timestamp (ms)")
    end_ts: int = Field(description="segment end timestamp (ms)")
    start_region: str = Field(description="semantic region label for start")
    end_region: str = Field(description="semantic region label for end")
    blue_centroid_path: list[tuple[float, float]] = Field(
        default_factory=list, description="simplified polyline of blue team centroid"
    )
    red_centroid_path: list[tuple[float, float]] = Field(
        default_factory=list, description="simplified polyline of red team centroid"
    )


class TeamfightPath(BaseModel):
    fight_index: int = Field(description="ranked index by importance (1-based)")
    score: float = Field(description="importance score (0-1)")
    participants_blue: list[int] = Field(default_factory=list)
    participants_red: list[int] = Field(default_factory=list)
    segments: list[TeamfightSegment] = Field(default_factory=list)
    summary: str = Field(default="", description="human-readable summary (CN)")


class TeamfightPathsReport(BaseModel):
    match_id: str = Field(description="Match ID")
    fights: list[TeamfightPath] = Field(default_factory=list)
