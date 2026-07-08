import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Placeholder bronze-parse step: logs the input and passes it through unchanged.

    Real Textract parsing lands in the bronze-textract-parse work item.
    """
    logger.info(json.dumps({"stage": "bronze-parse", "event": event}))
    return event
