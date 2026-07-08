import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Placeholder gold confidence-route step: logs the input and passes it through unchanged.

    Real confidence blending + auto-verdict routing lands in the gold-verdict-routing work item.
    """
    logger.info(json.dumps({"stage": "gold-confidence-route", "event": event}))
    return event
