import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Placeholder silver classify+extract step: logs the input and passes it through unchanged.

    Real Bedrock classification/extraction lands in the silver-classify-extract work item.
    """
    logger.info(json.dumps({"stage": "silver-classify-extract", "event": event}))
    return event
