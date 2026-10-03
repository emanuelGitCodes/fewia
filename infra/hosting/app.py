from aws_cdk import App, Environment

from stack import HostingStack


def main() -> None:
    app = App()
    account = app.node.try_get_context("account")
    region = app.node.try_get_context("region")
    if not isinstance(account, str) or not isinstance(region, str):
        raise ValueError("CDK context account and region MUST be strings")
    HostingStack(
        app,
        "FewiaHostingDev",
        env=Environment(account=account, region=region),
    )
    app.synth()


if __name__ == "__main__":
    main()
