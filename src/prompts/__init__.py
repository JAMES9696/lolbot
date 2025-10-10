"""Prompt templates for LLM-powered features.

This module contains system prompts and template strings for various
LLM-powered features in 蔚-上城人.
"""

from src.prompts.jiangli_prompt import JIANGLI_SYSTEM_PROMPT
from src.prompts.v2_team_relative_prompt import V2_TEAM_RELATIVE_SYSTEM_PROMPT

__all__ = [
    "JIANGLI_SYSTEM_PROMPT",
    "V2_TEAM_RELATIVE_SYSTEM_PROMPT",
]
