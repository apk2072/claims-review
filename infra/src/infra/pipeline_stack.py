import pathlib
import shutil
import subprocess

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

_REPO_ROOT = pathlib.Path(__file__).parents[3]
_PIPELINE_SRC = _REPO_ROOT / "pipeline" / "src" / "pipeline"
_BUILD_ROOT = pathlib.Path(__file__).parent.parent.parent / ".build"

_BRONZE_PARSE_SOURCE = (_PIPELINE_SRC / "bronze" / "parse_handler.py").read_text()
_GOLD_CONFIDENCE_ROUTE_SOURCE = (_PIPELINE_SRC / "gold" / "confidence_route_handler.py").read_text()


def _build_dependency_bundled_lambda_code(
    package_subdir: str, requirements: list[str]
) -> lambda_.Code:
    """Vendor pure-Python-wheel dependencies into a Lambda asset, no Docker required.

    This machine has no Docker for CDK's usual asset-bundling path, but
    `pip install --platform manylinux2014_x86_64 --only-binary=:all:`
    downloads prebuilt Linux wheels directly from PyPI (no compilation, so
    no Docker/Linux host needed) — confirmed working for `pydantic` this
    session. Only suitable for dependencies that ship such wheels; `common`'s
    psycopg[binary] does not have a pure story here, which is why the bronze
    Lambda avoids `common` entirely (see its docstring) rather than using
    this helper.
    """
    build_dir = _BUILD_ROOT / package_subdir
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    shutil.copytree(
        _PIPELINE_SRC,
        build_dir / "pipeline",
        ignore=shutil.ignore_patterns("__pycache__", "bronze", "gold"),
    )

    if requirements:
        subprocess.run(
            [
                "uv",
                "run",
                "pip",
                "install",
                "--platform",
                "manylinux2014_x86_64",
                "--implementation",
                "cp",
                "--python-version",
                "3.12",
                "--abi",
                "cp312",
                "--only-binary=:all:",
                "--target",
                str(build_dir),
                *requirements,
            ],
            cwd=_REPO_ROOT,
            check=True,
        )
        for cache_dir in build_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir)

    return lambda_.Code.from_asset(str(build_dir))


class ClaimsReviewPipelineStack(Stack):
    """Step Functions orchestration skeleton wiring bronze/silver/gold placeholder Lambdas.

    Each placeholder Lambda just logs its input and passes it through — real
    Textract/Bedrock/routing logic replaces each handler body in later work
    items without touching this stack's wiring. See
    05-pipeline-orchestration.md for acceptance criteria.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        documents_bucket: s3.IBucket,
        database: rds.DatabaseCluster,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        parse_function = lambda_.Function(
            self,
            "BronzeParseFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_BRONZE_PARSE_SOURCE),
            timeout=Duration.seconds(60),
            environment={
                "AURORA_CLUSTER_ARN": database.cluster_arn,
                "AURORA_SECRET_ARN": database.secret.secret_arn,
                "AURORA_DATABASE_NAME": "claims_review",
            },
        )
        database.grant_data_api_access(parse_function)
        documents_bucket.grant_read(parse_function)
        # Textract's synchronous AnalyzeDocument doesn't support resource-level
        # permissions, so the action must be granted on "*".
        parse_function.add_to_role_policy(
            iam.PolicyStatement(actions=["textract:AnalyzeDocument"], resources=["*"])
        )

        bedrock_model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

        classify_extract_function = lambda_.Function(
            self,
            "SilverClassifyExtractFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="pipeline.silver.classify_extract_handler.handler",
            code=_build_dependency_bundled_lambda_code(
                "silver-classify-extract", ["pydantic>=2.9"]
            ),
            timeout=Duration.seconds(60),
            environment={
                "AURORA_CLUSTER_ARN": database.cluster_arn,
                "AURORA_SECRET_ARN": database.secret.secret_arn,
                "AURORA_DATABASE_NAME": "claims_review",
                "BEDROCK_MODEL_ID": bedrock_model_id,
            },
        )
        database.grant_data_api_access(classify_extract_function)
        # Cross-region inference profiles (required here — the bare model ID
        # rejects on-demand invocation, see infra/README.md) route to
        # whichever underlying region has capacity, so a tightly-scoped
        # resource ARN would need every region the "us." profile can land
        # in. Wildcarded, same tradeoff as Textract's AnalyzeDocument above.
        classify_extract_function.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )

        confidence_route_function = lambda_.Function(
            self,
            "GoldConfidenceRouteFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_GOLD_CONFIDENCE_ROUTE_SOURCE),
            timeout=Duration.seconds(15),
        )

        failed_state = sfn.Fail(
            self,
            "DocumentProcessingFailed",
            cause="One of the bronze/silver/gold steps failed for this document",
        )

        parse_step = tasks.LambdaInvoke(
            self,
            "Parse",
            lambda_function=parse_function,
            output_path="$.Payload",
        )
        parse_step.add_catch(failed_state, errors=["States.ALL"])

        classify_extract_step = tasks.LambdaInvoke(
            self,
            "ClassifyExtract",
            lambda_function=classify_extract_function,
            output_path="$.Payload",
        )
        classify_extract_step.add_catch(failed_state, errors=["States.ALL"])

        confidence_route_step = tasks.LambdaInvoke(
            self,
            "ConfidenceRoute",
            lambda_function=confidence_route_function,
            output_path="$.Payload",
        )
        confidence_route_step.add_catch(failed_state, errors=["States.ALL"])

        definition = parse_step.next(classify_extract_step).next(confidence_route_step)

        self.state_machine = sfn.StateMachine(
            self,
            "ClaimsProcessingStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            state_machine_type=sfn.StateMachineType.STANDARD,
        )

        ingest_rule = events.Rule(
            self,
            "DocumentIngestRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={"bucket": {"name": [documents_bucket.bucket_name]}},
            ),
        )
        ingest_rule.add_target(targets.SfnStateMachine(self.state_machine))
