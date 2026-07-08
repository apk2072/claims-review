"""Auto-verdict threshold routing for the gold layer.

Kept as one named, pure function per coding-standards.md's anti-pattern note
against scattering thresholds across files.
"""

# Strictly greater-than, per system-architecture.md's documented data flow:
# "confidence > 0.92 ? yes -> auto-approved". Exactly 0.92 routes to human
# review, not auto-approval.
DEFAULT_AUTO_VERDICT_THRESHOLD = 0.92


def route_verdict(
    composite_confidence: float, threshold: float = DEFAULT_AUTO_VERDICT_THRESHOLD
) -> bool:
    """Return True (auto-approved) if composite_confidence clears the threshold."""
    return composite_confidence > threshold
