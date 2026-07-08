from pipeline.gold.verdict_routing import DEFAULT_AUTO_VERDICT_THRESHOLD, route_verdict


def test_verdict_routing_above_threshold_auto_approves():
    assert route_verdict(0.93) is True


def test_verdict_routing_below_threshold_queues_for_review():
    assert route_verdict(0.91) is False


def test_verdict_routing_exactly_at_threshold_queues_for_review():
    # Documented boundary behavior: strictly greater-than, so exactly the
    # threshold does NOT auto-approve (system-architecture.md).
    assert route_verdict(DEFAULT_AUTO_VERDICT_THRESHOLD) is False


def test_verdict_routing_custom_threshold_overrides_default():
    assert route_verdict(0.85, threshold=0.8) is True
    assert route_verdict(0.75, threshold=0.8) is False
