"""View exports

This package exposes the primary renderers used to transform analysis
results into Discord UI components (Embeds, Buttons, etc.).
"""

from src.core.views.analysis_view import render_analysis_embed, render_error_embed

__all__ = ["render_analysis_embed", "render_error_embed"]
