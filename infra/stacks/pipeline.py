import aws_cdk as cdk
from aws_cdk import (aws_codebuild as cb, aws_events as events, aws_events_targets as targets, aws_iam as iam,
                     aws_lambda as lam, aws_logs as logs, aws_sns_subscriptions as subs, aws_stepfunctions as sfn,
                     aws_stepfunctions_tasks as tasks)
from constructs import Construct

from stacks.monitoring import MonitoringStack
from stacks.storage import StorageStack

SK_IMAGE = "783357654285.dkr.ecr.{region}.amazonaws.com/sagemaker-scikit-learn:1.4-2-cpu-py3"


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, storage: StorageStack, monitoring: MonitoringStack, **kw):
        super().__init__(scope, id, **kw)
        p = cfg["project"]
        bucket, state = storage.bucket, storage.state
        image = SK_IMAGE.format(region=self.region)
        sm_role_arn = f"arn:aws:iam::{self.account}:role/{p}-sagemaker-role"
        endpoint_arn = f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{p}-endpoint"
        group = cfg["release"]["model_group"]

        def fn(name, folder, timeout=60, fname=None, **env):
            return lam.Function(
                self, name, function_name=fname or f"{p}-{folder.replace('_', '-')}", runtime=lam.Runtime.PYTHON_3_12,
                handler="handler.handler", code=lam.Code.from_asset(f"../pipeline/lambdas/{folder}"),
                timeout=cdk.Duration.seconds(timeout), log_retention=logs.RetentionDays.ONE_MONTH,
                environment={"STATE_TABLE": state.table_name, "BUCKET": bucket.bucket_name, **env})

        # ---- CodeBuild runs the heavy stages (prepare, train, evaluate) on CPU
        project = cb.Project(
            self, "Retrain", project_name=f"{p}-retrain",
            source=cb.Source.s3(bucket=bucket, path="code/pipeline-src.zip"),
            environment=cb.BuildEnvironment(build_image=cb.LinuxBuildImage.STANDARD_7_0,
                                            compute_type=cb.ComputeType.LARGE),
            environment_variables={"BUCKET": cb.BuildEnvironmentVariable(value=bucket.bucket_name)},
            timeout=cdk.Duration.minutes(cfg["training"]["max_runtime_seconds"] // 60 + 30))
        bucket.grant_read_write(project)

        # ---- small steps
        steps = fn("Steps", "steps", timeout=60, MODEL_GROUP=group, IMAGE=image,
                   MIN_AP50_GAIN=str(cfg["release"]["min_map50_gain"]))
        bucket.grant_read(steps, "runs/*")
        state.grant_read_write_data(steps)
        steps.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:CreateModelPackageGroup", "sagemaker:DescribeModelPackageGroup",
                     "sagemaker:CreateModelPackage"], resources=["*"]))

        def build(name, stage):
            return tasks.CodeBuildStartBuild(
                self, name, project=project, integration_pattern=sfn.IntegrationPattern.RUN_JOB,
                environment_variables_override={
                    "STAGE": cb.BuildEnvironmentVariable(value=stage),
                    "RUN_ID": cb.BuildEnvironmentVariable(value=sfn.JsonPath.string_at("$.run_id")),
                    "BASE_VERSION": cb.BuildEnvironmentVariable(value=sfn.JsonPath.string_at("$.base_version"))},
                result_path=sfn.JsonPath.DISCARD)

        def finish(name, outcome):
            return tasks.LambdaInvoke(
                self, name, lambda_function=steps, payload_response_only=True, result_path=sfn.JsonPath.DISCARD,
                payload=sfn.TaskInput.from_object({
                    "action": "finish", "outcome": outcome, "run_id": sfn.JsonPath.string_at("$.run_id"),
                    "detail": sfn.JsonPath.object_at("$")}))

        prepare, train, evaluate = build("Prepare", "prepare"), build("Train", "train"), build("Evaluate", "evaluate")
        rule = tasks.LambdaInvoke(
            self, "ReleaseRule", lambda_function=steps, payload_response_only=True, result_path="$.rule",
            payload=sfn.TaskInput.from_object({"action": "release_rule", "run_id": sfn.JsonPath.string_at("$.run_id")}))
        register = tasks.LambdaInvoke(
            self, "Register", lambda_function=steps, payload_response_only=True, result_path="$.registered",
            payload=sfn.TaskInput.from_object({
                "action": "register", "run_id": sfn.JsonPath.string_at("$.run_id"),
                "reason": sfn.JsonPath.string_at("$.reason"), "base_version": sfn.JsonPath.string_at("$.base_version"),
                "rule": sfn.JsonPath.object_at("$.rule")}))
        failed = finish("FinishFailed", "failed").next(sfn.Fail(self, "RunFailed", cause="pipeline stage failed"))
        for t in (prepare, train, evaluate, rule, register):
            t.add_catch(failed, result_path="$.error")

        done_ok, done_no = finish("FinishRegistered", "registered"), finish("FinishNotBetter", "not_better")
        definition = (prepare.next(train).next(evaluate).next(rule).next(
            sfn.Choice(self, "Better?")
            .when(sfn.Condition.boolean_equals("$.rule.passed", True), register.next(done_ok))
            .otherwise(done_no)))
        machine = sfn.StateMachine(self, "Machine", state_machine_name=f"{p}-retrain",
                                   definition_body=sfn.DefinitionBody.from_chainable(definition),
                                   timeout=cdk.Duration.hours(5))

        # ---- guard + triggers
        trigger = fn("Trigger", "trigger", fname=f"{p}-retrain-trigger", STATE_MACHINE_ARN=machine.state_machine_arn,
                     MIN_HOURS_BETWEEN_RUNS=str(cfg["retrain_triggers"]["min_hours_between_runs"]),
                     DEFAULT_VERSION=cfg["model"]["current_version"])
        state.grant_read_write_data(trigger)
        machine.grant_start_execution(trigger)
        events.Rule(self, "Weekly", rule_name=f"{p}-weekly-retrain", schedule=events.Schedule.rate(cdk.Duration.days(7)),
                    targets=[targets.LambdaFunction(trigger, event=events.RuleTargetInput.from_object({"reason": "weekly"}))])
        monitoring.topic.add_subscription(subs.LambdaSubscription(trigger))

        # ---- release: registry approval -> blue/green update
        deploy = fn("Deploy", "deploy", timeout=120, SAGEMAKER_ROLE_ARN=sm_role_arn, IMAGE=image,
                    ENDPOINT_NAME=f"{p}-endpoint", PROJECT=p, SCORE_THRESHOLD=str(cfg["model"]["score_threshold"]),
                    INSTANCE_TYPE=cfg["serving"]["instance_type"],
                    ROLLBACK_ALARMS=f"{p}-endpoint-5xx,{p}-endpoint-latency-p95")
        bucket.grant_read_write(deploy)
        state.grant_read_write_data(deploy)
        deploy.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:DescribeModelPackage", "sagemaker:CreateModel", "sagemaker:CreateEndpointConfig",
                     "sagemaker:DescribeEndpoint", "sagemaker:UpdateEndpoint", "cloudwatch:DescribeAlarms"],
            resources=["*"]))
        deploy.add_to_role_policy(iam.PolicyStatement(actions=["iam:PassRole"], resources=[sm_role_arn]))
        events.Rule(self, "Approved", rule_name=f"{p}-model-approved",
                    event_pattern=events.EventPattern(
                        source=["aws.sagemaker"], detail_type=["SageMaker Model Package State Change"],
                        detail={"ModelPackageGroupName": [group], "ModelApprovalStatus": ["Approved"]}),
                    targets=[targets.LambdaFunction(deploy)])
        cdk.CfnOutput(self, "StateMachineArn", value=machine.state_machine_arn)
        self.trigger = trigger
