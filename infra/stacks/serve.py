import aws_cdk as cdk
from aws_cdk import (aws_apigatewayv2 as apigw, aws_apigatewayv2_integrations as integ, aws_events as events,
                     aws_events_targets as targets, aws_iam as iam, aws_lambda as lam, aws_logs as logs)
from constructs import Construct

from stacks.storage import StorageStack


class ServeStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, storage: StorageStack, label_queue, **kw):
        super().__init__(scope, id, **kw)
        p = cfg["project"]
        endpoint_name = f"{p}-endpoint"

        # Role the SageMaker endpoint runs as
        self.sm_role = iam.Role(
            self, "SageMakerRole", role_name=f"{p}-sagemaker-role",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")])
        storage.bucket.grant_read_write(self.sm_role)

        # ingest Lambda behind an HTTP API
        ingest = lam.Function(
            self, "Ingest", function_name=f"{p}-ingest", runtime=lam.Runtime.PYTHON_3_12,
            handler="handler.handler", code=lam.Code.from_asset("../serving/lambdas/ingest"),
            timeout=cdk.Duration.seconds(30), memory_size=256, log_retention=logs.RetentionDays.ONE_MONTH,
            environment={"BUCKET": storage.bucket.bucket_name, "ENDPOINT_NAME": endpoint_name,
                         "REQUESTS_TABLE": storage.requests.table_name,
                         "TTL_DAYS": str(cfg["aws"]["raw_expiry_days"]),
                         "LABEL_QUEUE_URL": label_queue.queue_url})
        label_queue.grant_send_messages(ingest)
        storage.bucket.grant_put(ingest, "raw/*")
        storage.requests.grant_read_write_data(ingest)
        ingest.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint"],
            resources=[f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{endpoint_name}"]))
        self.ingest = ingest

        api = apigw.HttpApi(self, "Api", api_name=f"{p}-api")
        api.add_routes(path="/predict", methods=[apigw.HttpMethod.POST],
                       integration=integ.HttpLambdaIntegration("IngestIntegration", ingest))

        # idle shutdown
        idle = lam.Function(
            self, "IdleShutdown", function_name=f"{p}-idle-shutdown", runtime=lam.Runtime.PYTHON_3_12,
            handler="handler.handler", code=lam.Code.from_asset("../serving/lambdas/idle_shutdown"),
            timeout=cdk.Duration.seconds(30), log_retention=logs.RetentionDays.ONE_MONTH,
            environment={"ENDPOINT_NAME": endpoint_name, "IDLE_MINUTES": str(cfg["serving"]["idle_shutdown_minutes"]),
                         "STATE_TABLE": storage.state.table_name})
        storage.state.grant_read_data(idle)
        idle.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:DescribeEndpoint", "sagemaker:DeleteEndpoint"],
            resources=[f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{endpoint_name}"]))
        idle.add_to_role_policy(iam.PolicyStatement(actions=["cloudwatch:GetMetricStatistics"], resources=["*"]))
        events.Rule(self, "IdleSchedule", rule_name=f"{p}-idle-check",
                    schedule=events.Schedule.rate(cdk.Duration.minutes(15)),
                    targets=[targets.LambdaFunction(idle)])

        cdk.CfnOutput(self, "ApiUrl", value=api.api_endpoint)
        cdk.CfnOutput(self, "SageMakerRoleArn", value=self.sm_role.role_arn)
