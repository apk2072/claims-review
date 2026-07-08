from pipeline.gold.confidence_route_handler import handler


def test_gold_confidence_route_handler_any_event_passes_through_unchanged():
    event = {"bucket": "claim-documents", "key": "claims/sample.pdf"}

    result = handler(event, None)

    assert result == event


def test_gold_confidence_route_handler_empty_event_does_not_raise():
    result = handler({}, None)

    assert result == {}
