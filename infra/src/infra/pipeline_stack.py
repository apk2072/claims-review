import pathlib

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

_PIPELINE_SRC = pathlib.Path(__file__).parents[3] / "pipeline" / "src" / "pipeline"
_BRONZE_PARSE_SOURCE = (_PIPELINE_SRC / "bronze" / "parse_handler.py").read_text()
_SILVER_CLASSIFY_EXTRACT_SOURCE = (
    _PIPELINE_SRC / "silver" / "classify_extract_handler.py"
).read_text()
_GOLD_CONFIDENCE_ROUTE_SOURCE = (_PIPELINE_SRC / "gold" / "confidence_route_handler.py").read_text()


class ClaimsReviewPipelineStack(Stack):
    """Step Functions orchestration skeleton wiring bronze/silver/gold placeholder Lambdas.

    Each placeholder Lambda just logs its input and passes it through — real
    Textract/Bedrock/routing logic replaces each handler body in later work
    items without touching this stack's wiring. See
    05-pipeline-orchestration.md for acceptance criteria.
    """

    def __init__(
        self, scope: Construct, construct_id: str, documents_bucket: s3.IBucket, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        parse_function = lambda_.Function(
            self,
            "BronzeParseFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_BRONZE_PARSE_SOURCE),
            timeout=Duration.seconds(15),
        )

        classify_extract_function = lambda_.Function(
            self,
            "SilverClassifyExtractFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(_SILVER_CLASSIFY_EXTRACT_SOURCE),
            timeout=Duration.seconds(15),
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
