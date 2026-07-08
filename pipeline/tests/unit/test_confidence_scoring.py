from pipeline.silver.confidence_scoring import compute_composite_score


def test_compute_composite_score_blends_weighted_average():
    score = compute_composite_score(
        extract_confidence=0.9, parse_confidence=0.8, completeness_score=1.0
    )

    assert score == 0.6 * 0.9 + 0.2 * 0.8 + 0.2 * 1.0


def test_compute_composite_score_missing_extract_confidence_coalesces_to_parse():
    score = compute_composite_score(
        extract_confidence=None, parse_confidence=0.7, completeness_score=0.5
    )

    # extract weight (0.6) falls back to parse_confidence too: 0.6*0.7 + 0.2*0.7 + 0.2*0.5
    assert score == 0.8 * 0.7 + 0.2 * 0.5


def test_compute_composite_score_all_zero_yields_zero():
    score = compute_composite_score(
        extract_confidence=0.0, parse_confidence=0.0, completeness_score=0.0
    )

    assert score == 0.0


def test_compute_composite_score_all_perfect_yields_one():
    score = compute_composite_score(
        extract_confidence=1.0, parse_confidence=1.0, completeness_score=1.0
    )

    assert score == 1.0
