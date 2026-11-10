"""Prints the AWS resources the platform is running on.

Used for the evidence in Section 6.3 and as a quick check that the bootstrap did
what it claims. In AWS the same information comes from the console.
"""
import json
import sys

from maltashop import aws, config


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "tables"):
        tables = aws.dynamodb().list_tables()["TableNames"]
        print(f"DynamoDB tables ({len(tables)}), one per service:")
        for name in sorted(tables):
            count = aws.dynamodb().describe_table(TableName=name)["Table"]["ItemCount"]
            print(f"  {name:<32} items={count}")
    if what in ("all", "rules"):
        rules = aws.events().list_rules(EventBusName=config.EVENT_BUS)["Rules"]
        print(f"\nEventBridge rules on {config.EVENT_BUS} ({len(rules)}), one per consumer:")
        for rule in rules:
            pattern = json.loads(rule["EventPattern"])
            print(f"  {rule['Name']:<32} {','.join(pattern['detail-type'])[:58]}")
    if what in ("all", "queues"):
        print("\nSQS queues and their depth:")
        for queue in list(config.QUEUES.values()) + ["maltashop-dlq"]:
            attributes = aws.sqs().get_queue_attributes(
                QueueUrl=aws.queue_url(queue),
                AttributeNames=["ApproximateNumberOfMessages",
                                "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
            waiting = int(attributes["ApproximateNumberOfMessages"])
            in_flight = int(attributes["ApproximateNumberOfMessagesNotVisible"])
            print(f"  {queue:<32} waiting={waiting:>3}  in-flight={in_flight:>3}"
                  f"  retained={waiting + in_flight:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
