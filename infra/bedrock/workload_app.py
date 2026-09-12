"""Synthesize the unattended Bedrock runtime IAM user stack."""

import re

from aws_cdk import App, DefaultStackSynthesizer, Environment

from workload_stack import BedrockRuntimeStack

_ACCOUNT = re.compile(r"^[0-9]{12}$")
_ORIGIN_REGION = "us-east-1"


def runtime_environment(app: App) -> Environment:
    account = app.node.try_get_context("account")
    region = app.node.try_get_context("region")
    if not isinstance(account, str) or not _ACCOUNT.fullmatch(account.strip()):
        raise ValueError("CDK context account MUST be a 12-digit AWS account id")
    if not isinstance(region, str) or region.strip() != _ORIGIN_REGION:
        raise ValueError("CDK context region MUST be us-east-1")
    return Environment(account=account.strip(), region=region.strip())


def main() -> None:
    app = App()
    env = runtime_environment(app)
    execution_role = f"arn:aws:iam::{env.account}:role/fewia-bedrock-runtime-deployment"
    BedrockRuntimeStack(
        app,
        "FewiaBedrockRuntime",
        env=env,
        synthesizer=DefaultStackSynthesizer(
            # Empty deploy_role_arn selects the CLI caller to submit CloudFormation.
            deploy_role_arn="",
            cloud_formation_execution_role=execution_role,
            generate_bootstrap_version_rule=False,
        ),
    )
    app.synth()


if __name__ == "__main__":
    main()
