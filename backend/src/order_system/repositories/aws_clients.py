"""Adapters for SNS, SQS and CloudWatch.

Business services depend on these small interfaces, not on boto3 directly,
so they can be unit-tested with in-memory fakes. boto3 is imported lazily.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from ..models.events import OrderEvent
from ..utils.errors import (
    TransientError,
)


class EventPublisher(Protocol):
    def publish(self, event: OrderEvent) -> str: ...


class EmailNotifier(Protocol):
    def publish(self, customer_id: str, subject: str, message: str) -> str: ...

    def subscribe(self, email: str, customer_id: str) -> str: ...


class QueueAdmin(Protocol):
    def attributes(self, queue_url: str) -> dict[str, int]: ...

    def start_redrive(self, source_arn: str, destination_arn: str) -> str: ...

    def send(self, queue_url: str, body: str, attributes: dict[str, str]) -> None: ...


class AlarmReader(Protocol):
    def alarms(self, prefix: str) -> list[dict[str, Any]]: ...


def _client(service: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(service, config=Config(retries={"max_attempts": 4, "mode": "standard"}))


def _wrap_transient(exc: Exception, what: str) -> TransientError:
    return TransientError(f"{what} failed: {type(exc).__name__}")


class SnsEventPublisher:
    def __init__(self, topic_arn: str, client: Any = None) -> None:
        if not topic_arn:
            raise RuntimeError("ORDER_EVENTS_TOPIC_ARN is not configured")
        self.topic_arn = topic_arn
        self.client = client or _client("sns")

    def publish(self, event: OrderEvent) -> str:
        try:
            res = self.client.publish(
                TopicArn=self.topic_arn,
                Message=event.to_json(),
                MessageAttributes={
                    "eventType": {"DataType": "String", "StringValue": event.eventType},
                    "orderId": {"DataType": "String", "StringValue": event.orderId},
                },
            )
        except Exception as exc:  # noqa: BLE001 - every SNS failure is retryable for us
            raise _wrap_transient(exc, "SNS publish") from exc
        return str(res.get("MessageId", ""))


class SnsEmailNotifier:
    """Customer emails through one SNS topic. Each customer's email
    subscription has a filter policy on ``customerId`` so they only receive
    their own messages. SNS acceptance is NOT proof of delivery."""

    def __init__(self, topic_arn: str, client: Any = None) -> None:
        self.topic_arn = topic_arn
        self.client = client or _client("sns")

    def publish(self, customer_id: str, subject: str, message: str) -> str:
        try:
            res = self.client.publish(
                TopicArn=self.topic_arn,
                Subject=subject[:100],
                Message=message,
                MessageAttributes={"customerId": {"DataType": "String", "StringValue": customer_id}},
            )
        except Exception as exc:  # noqa: BLE001
            raise _wrap_transient(exc, "SNS email publish") from exc
        return str(res.get("MessageId", ""))

    def subscribe(self, email: str, customer_id: str) -> str:
        res = self.client.subscribe(
            TopicArn=self.topic_arn,
            Protocol="email",
            Endpoint=email,
            Attributes={"FilterPolicy": json.dumps({"customerId": [customer_id]})},
            ReturnSubscriptionArn=True,
        )
        return str(res.get("SubscriptionArn", ""))


class SqsQueueAdmin:
    def __init__(self, client: Any = None) -> None:
        self.client = client or _client("sqs")

    def attributes(self, queue_url: str) -> dict[str, int]:
        res = self.client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
            ],
        )
        return {k: int(v) for k, v in res.get("Attributes", {}).items()}

    def start_redrive(self, source_arn: str, destination_arn: str) -> str:
        res = self.client.start_message_move_task(
            SourceArn=source_arn, DestinationArn=destination_arn, MaxNumberOfMessagesPerSecond=10
        )
        return str(res.get("TaskHandle", ""))

    def send(self, queue_url: str, body: str, attributes: dict[str, str]) -> None:
        self.client.send_message(
            QueueUrl=queue_url,
            MessageBody=body,
            MessageAttributes={k: {"DataType": "String", "StringValue": v[:256]} for k, v in attributes.items()},
        )


class CloudWatchAlarmReader:
    def __init__(self, client: Any = None) -> None:
        self.client = client or _client("cloudwatch")

    def alarms(self, prefix: str) -> list[dict[str, Any]]:
        res = self.client.describe_alarms(AlarmNamePrefix=prefix, MaxRecords=100)
        return [
            {
                "name": a["AlarmName"],
                "state": a["StateValue"],
                "reason": a.get("StateReason", "")[:300],
                "updatedAt": str(a.get("StateUpdatedTimestamp", "")),
            }
            for a in res.get("MetricAlarms", [])
        ]
