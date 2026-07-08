import pathlib

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from constructs import Construct

_HANDLER_SOURCE = (pathlib.Path(__file__).parent / "test_connectivity_handler.py").read_text()


class ClaimsReviewFoundationStack(Stack):
    """Shared foundation: VPC, claim-documents S3 bucket, Aurora Serverless v2 cluster.

    No IAM roles are pre-created here. Each Lambda/Fargate task added in later
    work items gets its own CDK-auto-generated execution role, with
    permissions attached incrementally via grant*() calls at the point that
    resource is defined — see aws-foundation-infra-design.md for rationale.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private-with-egress",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # Claim documents bucket. removal_policy=DESTROY + auto_delete_objects
        # so `cdk destroy` fully tears down between practice sessions — a real
        # production system would use RETAIN instead.
        self.documents_bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=False,
            event_bridge_enabled=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        aurora_security_group = ec2.SecurityGroup(
            self,
            "AuroraSecurityGroup",
            vpc=self.vpc,
            description="Aurora Serverless v2 cluster - no ingress by default;"
            " each compute resource that needs access gets its own explicit SG rule",
            allow_all_outbound=False,
        )
        self.aurora_security_group = aurora_security_group

        self.database = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_13
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[aurora_security_group],
            default_database_name="claims_review",
            credentials=rds.Credentials.from_generated_secret("claims_review_admin"),
            serverless_v2_min_capacity=0,
            serverless_v2_max_capacity=2,
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            storage_encrypted=True,
            removal_policy=RemovalPolicy.DESTROY,
            # Data API lets us run the one-off pgvector CREATE EXTENSION check
            # over the AWS API instead of a direct DB connection — no VPC
            # attachment or Postgres driver needed for that specific check.
            enable_data_api=True,
        )

        # Temporary, one-off Lambda proving the VPC->Aurora network path works
        # (the risk called out in the design doc). stdlib-only handler — no
        # Docker available on this machine to bundle a compiled driver, so
        # this checks TCP reachability rather than running real SQL. Left in
        # place as a documented debug tool; see infra/README.md.
        connectivity_test_sg = ec2.SecurityGroup(
            self,
            "ConnectivityTestFunctionSecurityGroup",
            vpc=self.vpc,
            description="Test-connectivity Lambda - outbound only, no inbound needed",
        )
        aurora_security_group.add_ingress_rule(
            peer=connectivity_test_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow the one-off connectivity-test Lambda to reach Postgres",
        )

        self.connectivity_test_function = lambda_.Function(
            self,
            "ConnectivityTestFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_HANDLER_SOURCE),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[connectivity_test_sg],
            timeout=Duration.seconds(15),
            environment={
                "DB_HOST": self.database.cluster_endpoint.hostname,
                "DB_PORT": str(self.database.cluster_endpoint.port),
            },
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        CfnOutput(self, "DocumentsBucketName", value=self.documents_bucket.bucket_name)
        CfnOutput(
            self,
            "AuroraClusterEndpoint",
            value=self.database.cluster_endpoint.hostname,
        )
        CfnOutput(
            self,
            "AuroraSecretArn",
            value=self.database.secret.secret_arn if self.database.secret else "none",
        )
        CfnOutput(
            self,
            "ConnectivityTestFunctionName",
            value=self.connectivity_test_function.function_name,
        )
