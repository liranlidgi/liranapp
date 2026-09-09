"""Confidence scoring.

Confidence is derived from *how* a value was matched to its label, not from
any judgment about the value's content — we never look at the value to
decide how much to trust the match. Two things drive the score:

- Geometric quality of the match (how well the value's column lines up with
  the label's column; how close a checkmark sits to its option).
- Ambiguity: did we have to disambiguate between multiple structurally
  identical candidates to pick this one?

Bands (roughly): 0.95-0.99 near-certain, 0.80-0.94 good, 0.60-0.79 needs
review, <0.60 is never emitted as a result (see engine.py) -- per the "don't
guess" requirement, a low-quality candidate is surfaced as a review flag
rather than a confident field/value pair only down to 0.60; below that we
drop it instead of asserting a field/value pairing we don't trust.
"""
from __future__ import annotations


def clamp(x: float, lo: float = 0.0, hi: float = 0.99) -> float:
    return max(lo, min(hi, x))


def grid_confidence(x_overlap: float, vertical_gap: float, ambiguous_candidates: int) -> float:
    score = 0.99
    score -= (1.0 - x_overlap) * 0.18
    if vertical_gap > 4:
        score -= min((vertical_gap - 4) / 60.0, 0.20)
    if ambiguous_candidates > 1:
        score -= 0.10 * (ambiguous_candidates - 1)
    return clamp(score)


def choice_confidence(gap: float, alternative_selected_count: int) -> float:
    score = 0.99 - (gap / 25.0) * 0.28
    if alternative_selected_count > 0:
        # more than one option looked "selected" near a checkmark -- real
        # ambiguity, not just noise.
        score -= 0.25 * alternative_selected_count
    return clamp(score)


def table_confidence(row_completeness: float) -> float:
    score = 0.95 * row_completeness + 0.02
    return clamp(score)
