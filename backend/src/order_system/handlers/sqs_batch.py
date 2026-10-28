"""Shared SQS batch processing with partial batch failure reporting.

* Success / duplicate / stale            -> message deleted.
* ``TransientError`` or unexpected error -> reported in ``batchItemFailures``;
  SQS makes it visible again after the visibility timeout and, after
  ``maxReceiveCount`` (3) receives, moves it to the DLQ.
* ``PermanentError`` (bad JSON, unknown order, impossible state) -> retrying
  cannot help, so the message is copied to this worker's DLQ with the error
  attached (raising a DLQ alarm) and deleted from the source queue.

The event source mapping must enable ``ReportBatchItemFailures``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models.events import OrderEvent
from ..services.container import get_deps
from ..utils.errors import PermanentError, TransientError
from ..utils.logging import get_logger, log_context


def process_batch(service: str, queue: str, event: dict[str, Any], fn: Callable[[OrderEvent], str]) -> dict[str, Any]:
    log = get_logger(service)
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        message_id = record.get("messageId", "")
        receive_count = record.get("attributes", {}).get("ApproximateReceiveCount", "1")
        with log_context(messageId=message_id, receiveCount=receive_count):
            try:
                parsed = OrderEvent.parse(record.get("body", ""))
                with log_context(correlationId=parsed.correlationId, orderId=parsed.orderId):
                    outcome = fn(parsed)
                    log.info("message processed", outcome=outcome)
            except PermanentError as err:
                log.error("permanent failure; parking message in DLQ", error=err.message)
                try:
                    _park(service, queue, record, err.message, log)
                except TransientError:
                    failures.append({"itemIdentifier": message_id})
            except TransientError as err:
                log.warning("transient failure; message will be retried by SQS", error=err.message)
                failures.append({"itemIdentifier": message_id})
            except Exception as exc:  # noqa: BLE001 - unknown errors are retried, then DLQ'd
                log.error(
                    "unexpected failure; message will be retried by SQS",
                    errorType=type(exc).__name__,
                    error=str(exc)[:500],
                )
                failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}


def _park(service: str, queue: str, record: dict[str, Any], reason: str, log: Any) -> None:
    deps = get_deps()
    cfg = deps.settings.queues.get(queue)
    dlq = deps.settings.own_dlq_url or (cfg.dlq_url if cfg else "")
    if not dlq or deps.queues is None:
        log.error("no DLQ configured for permanent failure; message dropped after logging")
        return
    try:
        deps.queues.send(
            dlq,
            record.get("body", ""),
            {"errorReason": reason, "failedService": service, "sourceMessageId": record.get("messageId", "")},
        )
    except Exception as exc:  # noqa: BLE001
        # If even that fails, let SQS retry the original so nothing is lost.
        raise TransientError(f"Could not park message in DLQ: {type(exc).__name__}") from exc
