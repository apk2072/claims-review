"""Composite confidence scoring for the silver layer.

Kept as one named, pure function per coding-standards.md's anti-pattern note
against scattering thresholds/weights across files.
"""

EXTRACT_WEIGHT = 0.6
PARSE_WEIGHT = 0.2
COMPLETENESS_WEIGHT = 0.2


def compute_composite_score(
    extract_confidence: float | None,
    parse_confidence: float,
    completeness_score: float,
) -> float:
    """Blend extract/parse/completeness confidence into one composite score.

    If `extract_confidence` is unavailable (e.g. extraction was skipped
    because the document didn't classify as a claim form), it coalesces to
    `parse_confidence` — the extract-weighted 60% falls back to bronze's
    parse confidence rather than silently zeroing out the score.
    """
    if extract_confidence is None:
        extract_confidence = parse_confidence

    return (
        EXTRACT_WEIGHT * extract_confidence
        + PARSE_WEIGHT * parse_confidence
        + COMPLETENESS_WEIGHT * completeness_score
    )
