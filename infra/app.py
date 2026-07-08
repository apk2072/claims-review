#!/usr/bin/env python3
import os

import aws_cdk as cdk
from infra.foundation_stack import ClaimsReviewFoundationStack
from infra.pipeline_stack import ClaimsReviewPipelineStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

foundation_stack = ClaimsReviewFoundationStack(app, "ClaimsReviewFoundation", env=env)
ClaimsReviewPipelineStack(
    app,
    "ClaimsReviewPipeline",
    documents_bucket=foundation_stack.documents_bucket,
    env=env,
)

app.synth()
