import json
from pathlib import Path

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk.assertions import Template
from constructs import IConstruct

from identity import HostingIdentity
from stack import HostingStack

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_Case = tuple[Stack, HostingIdentity, Template]


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def identity_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
    concrete: bool = request.param
    stack = Stack(
        App(outdir=str(tmp_path / "assembly"), context={}),
        "IdentityTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    identity = HostingIdentity(
        stack, "Identity", hostname="example.test", domain_prefix="fewia-dev"
    )
    return stack, identity, Template.from_stack(stack)


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def test_pool_has_exact_invitation_and_security_settings(identity_case: _Case) -> None:
    _, identity, template = identity_case
    pools = template.find_resources("AWS::Cognito::UserPool")
    assert set(pools) == {_logical_id(identity.user_pool)}
    pool = pools[_logical_id(identity.user_pool)]
    properties = pool["Properties"]
    expected = {
        "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
        "UsernameAttributes": ["email"],
        "UsernameConfiguration": {"CaseSensitive": False},
        "Schema": [{"Name": "email", "Required": True, "Mutable": True}],
        "AutoVerifiedAttributes": ["email"],
        "AccountRecoverySetting": {
            "RecoveryMechanisms": [{"Name": "verified_email", "Priority": 1}],
        },
        "MfaConfiguration": "OPTIONAL",
        "EnabledMfas": ["SOFTWARE_TOKEN_MFA"],
        "Policies": {
            "PasswordPolicy": {
                "MinimumLength": 14,
                "RequireUppercase": True,
                "RequireLowercase": True,
                "RequireNumbers": True,
                "RequireSymbols": True,
                "TemporaryPasswordValidityDays": 3,
            },
        },
        "DeletionProtection": "ACTIVE",
    }
    assert {key: properties[key] for key in expected} == expected
    assert "AliasAttributes" not in properties
    assert "SmsConfiguration" not in properties
    assert "LambdaConfig" not in properties
    assert pool["DeletionPolicy"] == "Retain"
    assert pool["UpdateReplacePolicy"] == "Retain"


def test_client_has_exact_code_grant_and_token_settings(identity_case: _Case) -> None:
    _, identity, template = identity_case
    clients = template.find_resources("AWS::Cognito::UserPoolClient")
    assert set(clients) == {_logical_id(identity.client)}
    assert clients[_logical_id(identity.client)]["Properties"] == {
        "UserPoolId": {"Ref": _logical_id(identity.user_pool)},
        "GenerateSecret": True,
        "SupportedIdentityProviders": ["COGNITO"],
        "AllowedOAuthFlowsUserPoolClient": True,
        "AllowedOAuthFlows": ["code"],
        "AllowedOAuthScopes": ["openid"],
        "CallbackURLs": ["https://example.test/oauth2/idpresponse"],
        "LogoutURLs": ["https://example.test/"],
        "ExplicitAuthFlows": ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        "PreventUserExistenceErrors": "ENABLED",
        "EnableTokenRevocation": True,
        "AccessTokenValidity": 60,
        "IdTokenValidity": 60,
        "RefreshTokenValidity": 1440,
        "TokenValidityUnits": {
            "AccessToken": "minutes",
            "IdToken": "minutes",
            "RefreshToken": "minutes",
        },
    }


def test_exports_and_domain_add_only_identity_resources(identity_case: _Case) -> None:
    _, identity, template = identity_case
    assert isinstance(identity.user_pool, cognito.UserPool)
    assert isinstance(identity.client, cognito.UserPoolClient)
    assert isinstance(identity.domain, cognito.UserPoolDomain)
    ids = {
        _logical_id(identity.user_pool),
        _logical_id(identity.client),
        _logical_id(identity.domain),
    }
    assert len(ids) == 3
    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.resource_count_is("AWS::Cognito::UserPoolClient", 1)
    assert template.find_resources("AWS::Cognito::UserPoolDomain") == {
        _logical_id(identity.domain): {
            "Type": "AWS::Cognito::UserPoolDomain",
            "Properties": {
                "Domain": "fewia-dev",
                "UserPoolId": {"Ref": _logical_id(identity.user_pool)},
            },
        },
    }
    assert {item["Type"] for item in template.to_json()["Resources"].values()} <= {
        "AWS::Cognito::UserPool",
        "AWS::Cognito::UserPoolClient",
        "AWS::Cognito::UserPoolDomain",
        "AWS::CDK::Metadata",
    }
    assert not template.to_json().get("Outputs")


@pytest.mark.parametrize(
    "hostname",
    [
        "",
        "localhost",
        "Example.test",
        "example.test.",
        "*.example.test",
        "https://example.test",
        "example.test/path",
        "example.test?query",
        "example.test#fragment",
        "example.test:443",
        "user@example.test",
        "127.0.0.1",
        "127.1",
        "::1",
        "[::1]",
        " example.test",
        "example.test ",
        "example.\ttest",
        "example.test\n",
        "example.test\r",
        "example.\x00test",
        "example.\x7ftest",
        "example..test",
        ".example.test",
        "-example.test",
        "example-.test",
        "example_test.test",
        "éxample.test",
        "ｅxample.test",
        "a" * 64 + ".test",
        ".".join(["a" * 63] * 4),
    ],
)
def test_invalid_hostname_fails_before_resources(hostname: str, tmp_path: Path) -> None:
    stack = Stack(App(outdir=str(tmp_path / "invalid")), "InvalidHostname")
    children = list(stack.node.children)
    with pytest.raises(ValueError) as error:
        HostingIdentity(stack, "Identity", hostname=hostname, domain_prefix="fewia-dev")
    assert str(error.value) == "hostname MUST be a lowercase DNS hostname"
    assert list(stack.node.children) == children
    assert not Template.from_stack(stack).to_json().get("Resources")


@pytest.mark.parametrize(
    "domain_prefix",
    [
        "",
        "ab",
        "a" * 64,
        "-abc",
        "abc-",
        "Fewia",
        "fewia.dev",
        "fewia_dev",
        "fewia/dev",
        "fewia:443",
        "fewia?query",
        " fewia",
        "fewia ",
        "fewia\n",
        "fewia\r",
        "few\tia",
        "fewia\x00",
        "fewia\x7f",
        "féwia",
        "aws",
        "amazon",
        "cognito",
        "fewia-aws-dev",
        "myamazonapp",
        "mycognitoapp",
    ],
)
def test_invalid_prefix_fails_before_resources(
    domain_prefix: str, tmp_path: Path
) -> None:
    stack = Stack(App(outdir=str(tmp_path / "invalid")), "InvalidPrefix")
    children = list(stack.node.children)
    with pytest.raises(ValueError) as error:
        HostingIdentity(
            stack, "Identity", hostname="example.test", domain_prefix=domain_prefix
        )
    assert str(error.value) == "domain prefix MUST be a valid unreserved Cognito prefix"
    assert list(stack.node.children) == children
    assert not Template.from_stack(stack).to_json().get("Resources")


@pytest.mark.parametrize(
    ("hostname", "domain_prefix"),
    [
        ("example.test", "abc"),
        ("a.b", "a0b"),
        ("0app.my-app.test", "fewia--dev"),
        ("a" * 63 + ".test", "a" * 63),
        (".".join(["a" * 63] * 3 + ["a" * 61]), "fewia-dev"),
    ],
)
def test_valid_offline_names_keep_exact_urls(
    hostname: str, domain_prefix: str, tmp_path: Path
) -> None:
    stack = Stack(App(outdir=str(tmp_path / "valid")), "ValidNames")
    HostingIdentity(stack, "Identity", hostname=hostname, domain_prefix=domain_prefix)
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "CallbackURLs": [f"https://{hostname}/oauth2/idpresponse"],
            "LogoutURLs": [f"https://{hostname}/"],
        },
    )
    template.has_resource_properties(
        "AWS::Cognito::UserPoolDomain", {"Domain": domain_prefix}
    )


def test_synthesis_is_offline_with_synthetic_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    app = App(outdir=str(tmp_path / "offline"), context={})
    stack = Stack(app, "Offline", env=Environment(account=_ACCOUNT, region=_REGION))
    HostingIdentity(
        stack, "Identity", hostname="example.test", domain_prefix="fewia-dev"
    )
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")
    Template.from_stack(stack).resource_count_is("AWS::Cognito::UserPool", 1)


def test_hosting_stack_keeps_identity_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    assert not any(
        isinstance(child, HostingIdentity) for child in stack.node.find_all()
    )
    template = Template.from_stack(stack)
    expected = {
        "AWS::SQS::Queue": 4,
        "AWS::SQS::QueuePolicy": 4,
        "AWS::S3::Bucket": 1,
        "AWS::S3::BucketPolicy": 1,
    }
    for resource_type, count in expected.items():
        template.resource_count_is(resource_type, count)
    assert {item["Type"] for item in template.to_json()["Resources"].values()} <= (
        set(expected) | {"AWS::CDK::Metadata"}
    )
    assert set(template.to_json()["Outputs"]) == {
        "AgentQueueUrl",
        "AgentDlqUrl",
        "SyncQueueUrl",
        "SyncDlqUrl",
        "ArtifactBucketName",
    }
