import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk.assertions import Template
from constructs import IConstruct

from database import HostingDatabase
from network import HostingNetwork
from stack import HostingStack

_ACCOUNT = "111122223333"


def _network(outdir: Path) -> HostingNetwork:
    application = App(
        outdir=str(outdir),
        context={
            f"availability-zones:account={_ACCOUNT}:region=us-east-1": [
                "us-east-1a",
                "us-east-1b",
            ],
        },
    )
    stack = Stack(
        application,
        "Test",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )
    return HostingNetwork(stack, "Network")


@pytest.fixture
def network(tmp_path: Path) -> HostingNetwork:
    return _network(tmp_path / "assembly")


@pytest.fixture
def database(network: HostingNetwork) -> HostingDatabase:
    return HostingDatabase(Stack.of(network), "Database", network=network)


@pytest.fixture
def template(database: HostingDatabase) -> Template:
    return Template.from_stack(Stack.of(database))


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _resources(
    template: Template, resource_type: str
) -> Mapping[str, Mapping[str, Any]]:
    return template.find_resources(resource_type)


def _instance(template: Template) -> dict[str, Any]:
    resources = _resources(template, "AWS::RDS::DBInstance")
    assert len(resources) == 1
    properties: dict[str, Any] = next(iter(resources.values()))["Properties"]
    return properties


def _secret_reference(secret_id: str, key: str) -> dict[str, Any]:
    return {
        "Fn::Join": [
            "",
            [
                "{{resolve:secretsmanager:",
                {"Ref": secret_id},
                f":SecretString:{key}::}}}}",
            ],
        ]
    }


def test_construct_exports_distinct_credentials(database: HostingDatabase) -> None:
    assert isinstance(database.instance, rds.DatabaseInstance)
    assert isinstance(database.admin_secret, secretsmanager.Secret)
    assert isinstance(database.application_secret, secretsmanager.Secret)
    master_secret = database.instance.secret
    assert master_secret is not None
    assert isinstance(master_secret, secretsmanager.SecretTargetAttachment)
    assert _logical_id(master_secret) != _logical_id(database.admin_secret)
    assert _logical_id(database.admin_secret) != _logical_id(
        database.application_secret
    )


def test_postgres_storage_and_backup_settings(template: Template) -> None:
    props = _instance(template)
    expected = {
        "Engine": "postgres",
        "EngineVersion": "16.15",
        "DBInstanceClass": "db.t4g.micro",
        "MultiAZ": False,
        "DBName": "fewia",
        "Port": "5432",
        "StorageType": "gp3",
        "StorageEncrypted": True,
        "AllocatedStorage": "20",
        "MaxAllocatedStorage": 100,
        "PubliclyAccessible": False,
        "BackupRetentionPeriod": 7,
        "CopyTagsToSnapshot": True,
        "DeletionProtection": True,
        "DeleteAutomatedBackups": False,
        "AutoMinorVersionUpgrade": True,
        "AllowMajorVersionUpgrade": False,
    }
    for key, value in expected.items():
        assert props[key] == value


def test_database_uses_only_isolated_subnets_and_database_group(
    network: HostingNetwork, template: Template
) -> None:
    props = _instance(template)
    subnet_groups = _resources(template, "AWS::RDS::DBSubnetGroup")
    assert len(subnet_groups) == 1
    group_id, group = next(iter(subnet_groups.items()))
    assert props["DBSubnetGroupName"] == {"Ref": group_id}
    assert group["Properties"]["SubnetIds"] == [
        {"Ref": _logical_id(subnet)} for subnet in network.vpc.isolated_subnets
    ]
    assert props["VPCSecurityGroups"] == [
        {"Fn::GetAtt": [_logical_id(network.database_security_group), "GroupId"]}
    ]


def test_database_and_both_secrets_are_retained(
    database: HostingDatabase, template: Template
) -> None:
    resources = template.to_json()["Resources"]
    template.resource_count_is("AWS::SecretsManager::Secret", 2)
    for construct in (
        database.instance,
        database.admin_secret,
        database.application_secret,
    ):
        resource = resources[_logical_id(construct)]
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_generated_secrets_keep_application_credentials_out_of_master(
    database: HostingDatabase, template: Template
) -> None:
    secrets = _resources(template, "AWS::SecretsManager::Secret")
    admin_id = _logical_id(database.admin_secret)
    application_id = _logical_id(database.application_secret)
    admin = secrets[admin_id]["Properties"]
    application = secrets[application_id]["Properties"]
    for secret in (admin, application):
        assert "SecretString" not in secret
        generator = secret["GenerateSecretString"]
        assert generator["GenerateStringKey"] == "password"
        assert "password" not in json.loads(generator["SecretStringTemplate"])
    assert json.loads(admin["GenerateSecretString"]["SecretStringTemplate"]) == {
        "username": "fewia_admin"
    }
    assert application["GenerateSecretString"] == {
        "SecretStringTemplate": json.dumps({"username": "fewia_app"}),
        "GenerateStringKey": "password",
        "PasswordLength": 32,
        "ExcludePunctuation": True,
    }
    props = _instance(template)
    assert props["MasterUsername"] in (
        "fewia_admin",
        _secret_reference(admin_id, "username"),
    )
    assert props["MasterUserPassword"] == _secret_reference(admin_id, "password")
    assert props["MasterUserPassword"] != _secret_reference(application_id, "password")
    attachments = _resources(template, "AWS::SecretsManager::SecretTargetAttachment")
    assert len(attachments) == 1
    assert next(iter(attachments.values()))["Properties"] == {
        "SecretId": {"Ref": admin_id},
        "TargetId": {"Ref": _logical_id(database.instance)},
        "TargetType": "AWS::RDS::DBInstance",
    }
    assert not template.to_json().get("Outputs", {})


def test_parameter_group_requires_postgres_tls(template: Template) -> None:
    groups = _resources(template, "AWS::RDS::DBParameterGroup")
    assert len(groups) == 1
    group_id, group = next(iter(groups.items()))
    assert group["Properties"]["Family"] == "postgres16"
    assert group["Properties"]["Parameters"] == {"rds.force_ssl": "1"}
    assert _instance(template)["DBParameterGroupName"] == {"Ref": group_id}


def test_addition_has_no_new_access_or_role_bootstrap(
    template: Template, tmp_path: Path
) -> None:
    baseline = Template.from_stack(Stack.of(_network(tmp_path / "baseline")))
    before = baseline.to_json()["Resources"]
    after = template.to_json()["Resources"]
    for resource_id, resource in before.items():
        assert after[resource_id] == resource
    added = [resource for key, resource in after.items() if key not in before]
    expected = {
        "AWS::RDS::DBInstance": 1,
        "AWS::RDS::DBSubnetGroup": 1,
        "AWS::RDS::DBParameterGroup": 1,
        "AWS::SecretsManager::Secret": 2,
        "AWS::SecretsManager::SecretTargetAttachment": 1,
    }
    assert len(added) == sum(expected.values())
    for resource_type, count in expected.items():
        assert sum(resource["Type"] == resource_type for resource in added) == count


def test_construct_synthesizes_without_lookups(tmp_path: Path) -> None:
    application = App(outdir=str(tmp_path / "portable"))
    stack = Stack(application, "Portable")
    HostingDatabase(stack, "Database", network=HostingNetwork(stack, "Network"))
    Template.from_stack(stack).resource_count_is("AWS::RDS::DBInstance", 1)
    assembly = application.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing", [])


def test_hosting_stack_keeps_database_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )
    assert stack.node.try_find_child("Database") is None
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::RDS::DBInstance", 0)
    template.resource_count_is("AWS::SecretsManager::Secret", 0)
