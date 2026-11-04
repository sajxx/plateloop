import aws_cdk as cdk
from aws_cdk import (aws_iam as iam, aws_lambda as lam, aws_lambda_event_sources as srcs, aws_logs as logs,
                     aws_sqs as sqs)
from constructs import Construct

from stacks.storage import StorageStack


class LabelStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, storage: StorageStack, **kw):
        super().__init__(scope, id, **kw)
        p, lc = cfg["project"], cfg["labeling"]

        dlq = sqs.Queue(self, "Dlq", queue_name=f"{p}-label-dlq", retention_period=cdk.Duration.days(14))
        self.queue = sqs.Queue(
            self, "Queue", queue_name=f"{p}-label-queue", visibility_timeout=cdk.Duration.seconds(180),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq))

        fn = lam.Function(
            self, "Labeller", function_name=f"{p}-labeller", runtime=lam.Runtime.PYTHON_3_12,
            handler="handler.handler", code=lam.Code.from_asset("../labeling/lambdas/labeller"),
            timeout=cdk.Duration.seconds(60), memory_size=256, log_retention=logs.RetentionDays.ONE_MONTH,
            environment={"BUCKET": storage.bucket.bucket_name, "REQUESTS_TABLE": storage.requests.table_name,
                         "STATE_TABLE": storage.state.table_name, "BEDROCK_MODEL": lc["bedrock_model"],
                         "ACCEPT_IOU": str(lc["accept_iou"]),
                         "MAX_NOVA_ONLY_FRACTION": str(lc["max_nova_only_fraction"]),
                         "TRIGGER_FUNCTION": f"{p}-retrain-trigger",
                         "NEW_LABEL_COUNT": str(cfg["retrain_triggers"]["new_label_count"])})
        fn.add_event_source(srcs.SqsEventSource(self.queue, batch_size=1))
        storage.bucket.grant_read(fn, "raw/*")
        storage.bucket.grant_put(fn, "labels/auto/*")
        storage.bucket.grant_put(fn, "quarantine/*")
        storage.requests.grant_read_write_data(fn)
        storage.state.grant_read_write_data(fn)
        model_id = lc["bedrock_model"].split(".", 1)[1]          # amazon.nova-2-lite-v1:0
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{lc['bedrock_model']}",
                       f"arn:aws:bedrock:*::foundation-model/{model_id}"]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:{p}-retrain-trigger"]))
        self.labeller = fn
        cdk.CfnOutput(self, "QueueUrl", value=self.queue.queue_url)
