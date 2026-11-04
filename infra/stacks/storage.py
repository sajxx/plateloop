import aws_cdk as cdk
from aws_cdk import aws_dynamodb as ddb, aws_s3 as s3
from constructs import Construct


class StorageStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, **kw):
        super().__init__(scope, id, **kw)
        aws = cfg["aws"]

        self.bucket = s3.Bucket(
            self, "Bucket",
            bucket_name=f"{cfg['project']}-{self.account}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-raw", prefix="raw/",
                    expiration=cdk.Duration.days(aws["raw_expiry_days"]),
                    noncurrent_version_expiration=cdk.Duration.days(1),
                ),
                s3.LifecycleRule(
                    id="abort-multipart",
                    abort_incomplete_multipart_upload_after=cdk.Duration.days(1),
                ),
            ],
        )

        self.requests = ddb.Table(
            self, "Requests",
            table_name=f"{cfg['project']}-requests",
            partition_key=ddb.Attribute(name="image_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.state = ddb.Table(
            self, "State",
            table_name=f"{cfg['project']}-state",
            partition_key=ddb.Attribute(name="key", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        cdk.CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
