import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for name in [
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "run_id",
            "counts",
            "error_category",
        ]:
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Avoid logging URL queries, authorization headers or source payloads.
    logging.getLogger("httpx").setLevel(logging.WARNING)
