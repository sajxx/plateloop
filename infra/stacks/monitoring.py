import aws_cdk as cdk
from aws_cdk import (aws_cloudwatch as cw, aws_cloudwatch_actions as actions, aws_sns as sns,
                     aws_sns_subscriptions as subs)
from constructs import Construct


class MonitoringStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, **kw):
        super().__init__(scope, id, **kw)
        p = cfg["project"]
        mon = cfg["monitoring"]
        period = cdk.Duration.hours(1)

        topic = sns.Topic(self, "Alerts", topic_name=f"{p}-alerts")
        topic.add_subscription(subs.EmailSubscription(cfg["alerts"]["email"]))
        act = actions.SnsAction(topic)

        def metric(name, stat):
            return cw.Metric(namespace="PlateLoop", metric_name=name, statistic=stat, period=period)

        # the drift alarms only judge an hour that had at least min_images requests
        conf_avg, conf_n = metric("TopConfidence", "Average"), metric("TopConfidence", "SampleCount")
        miss_avg = metric("NoPlate", "Average")
        low_conf = cw.Alarm(
            self, "LowConfidence", alarm_name=f"{p}-low-confidence",
            metric=cw.MathExpression(expression=f"IF(n >= {mon['min_images']}, c, 1)",
                                     using_metrics={"c": conf_avg, "n": conf_n}, period=period),
            threshold=mon["min_mean_confidence"], comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            evaluation_periods=1, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description="Mean top confidence fell below the limit: the input images may have drifted")
        many_misses = cw.Alarm(
            self, "NoPlateShare", alarm_name=f"{p}-no-plate-share",
            metric=cw.MathExpression(expression=f"IF(n >= {mon['min_images']}, m, 0)",
                                     using_metrics={"m": miss_avg, "n": conf_n}, period=period),
            threshold=mon["max_no_plate_share"], comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description="Share of images with no plate found is above the limit")

        dims = {"EndpointName": f"{p}-endpoint", "VariantName": "AllTraffic"}
        errors = cw.Alarm(
            self, "Endpoint5xx", alarm_name=f"{p}-endpoint-5xx",
            metric=cw.Metric(namespace="AWS/SageMaker", metric_name="Invocation5XXErrors", dimensions_map=dims,
                             statistic="Sum", period=cdk.Duration.minutes(1)),
            threshold=1, evaluation_periods=1, treat_missing_data=cw.TreatMissingData.NOT_BREACHING)
        slow = cw.Alarm(
            self, "EndpointLatency", alarm_name=f"{p}-endpoint-latency-p95",
            metric=cw.Metric(namespace="AWS/SageMaker", metric_name="ModelLatency", dimensions_map=dims,
                             statistic="p95", period=cdk.Duration.minutes(1)),
            threshold=mon["max_p95_latency_ms"] * 1000, evaluation_periods=3,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)
        for a in (low_conf, many_misses, errors, slow):
            a.add_alarm_action(act)

        dash = cw.Dashboard(self, "Dashboard", dashboard_name=f"{p}-overview")
        dash.add_widgets(
            cw.GraphWidget(title="Top confidence (hourly mean)", left=[conf_avg], left_annotations=[
                cw.HorizontalAnnotation(value=mon["min_mean_confidence"], label="alarm")], width=8),
            cw.GraphWidget(title="No-plate share", left=[miss_avg], left_annotations=[
                cw.HorizontalAnnotation(value=mon["max_no_plate_share"], label="alarm")], width=8),
            cw.GraphWidget(title="Images per hour", left=[conf_n.with_(label="images")], width=8),
            cw.GraphWidget(title="Brightness and blur", left=[metric("Brightness", "Average")],
                           right=[metric("BlurScore", "Average")], width=12),
            cw.GraphWidget(title="Endpoint latency p95 (µs)", left=[slow.metric], width=12))
        self.topic = topic
        cdk.CfnOutput(self, "AlertTopicArn", value=topic.topic_arn)
