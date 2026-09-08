"""Synthesize the development Bedrock Converse IAM stack."""

from aws_cdk import App, Environment

from stack import BedrockChatStack


def main() -> None:
    app = App()
    account = app.node.try_get_context("account")
    region = app.node.try_get_context("region")
    if not isinstance(account, str) or not account.strip():
        raise ValueError("CDK context account MUST be set")
    if not isinstance(region, str) or region.strip() != "us-east-1":
        raise ValueError("CDK context region MUST be us-east-1")
    BedrockChatStack(
        app,
        "FewiaBedrockDev",
        env=Environment(account=account.strip(), region=region.strip()),
    )
    app.synth()


if __name__ == "__main__":
    main()
