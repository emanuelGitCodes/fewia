"""Synthesize the unattended Bedrock runtime IAM user stack."""

import re

from aws_cdk import App, Environment

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
    BedrockRuntimeStack(
        app,
        "FewiaBedrockRuntime",
        env=runtime_environment(app),
    )
    app.synth()


if __name__ == "__main__":
    main()
