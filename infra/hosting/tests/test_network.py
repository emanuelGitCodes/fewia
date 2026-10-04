import json
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk.assertions import Template
from constructs import IConstruct

from network import HostingNetwork
from stack import HostingStack

_ACCOUNT = "111122223333"
_ZONES = ["us-east-1a", "us-east-1b"]


@pytest.fixture
def network(tmp_path: Path) -> HostingNetwork:
    application = App(
        outdir=str(tmp_path / "assembly"),
        context={
            f"availability-zones:account={_ACCOUNT}:region=us-east-1": _ZONES,
        },
    )
    stack = Stack(
        application,
        "Test",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )
    return HostingNetwork(stack, "Network")


@pytest.fixture
def template(network: HostingNetwork) -> Template:
    return Template.from_stack(Stack.of(network))


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _properties(template: Template, resource_type: str) -> dict[str, Any]:
    return {
        name: resource["Properties"]
        for name, resource in template.find_resources(resource_type).items()
    }


def _rules(template: Template, direction: str) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in props.items() if key != "Description"}
        for props in _properties(
            template, f"AWS::EC2::SecurityGroup{direction}"
        ).values()
    ]


def _assert_no_missing_context(application: App) -> None:
    assembly = application.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing", [])


def test_inventory_contains_only_network_resources(template: Template) -> None:
    expected = {
        "AWS::EC2::VPC": 1,
        "AWS::EC2::Subnet": 6,
        "AWS::EC2::RouteTable": 6,
        "AWS::EC2::SubnetRouteTableAssociation": 6,
        "AWS::EC2::InternetGateway": 1,
        "AWS::EC2::VPCGatewayAttachment": 1,
        "AWS::EC2::EIP": 1,
        "AWS::EC2::NatGateway": 1,
        "AWS::EC2::Route": 4,
        "AWS::EC2::SecurityGroup": 3,
        "AWS::EC2::SecurityGroupIngress": 3,
        "AWS::EC2::SecurityGroupEgress": 5,
    }
    types = {resource["Type"] for resource in template.to_json()["Resources"].values()}
    assert set(expected) <= types
    assert types <= set(expected) | {"AWS::CDK::Metadata"}
    for resource_type, count in expected.items():
        template.resource_count_is(resource_type, count)


def test_construct_exports_typed_distinct_resources(network: HostingNetwork) -> None:
    assert isinstance(network.vpc, ec2.Vpc)
    groups = (
        network.edge_security_group,
        network.app_security_group,
        network.database_security_group,
    )
    assert all(isinstance(group, ec2.SecurityGroup) for group in groups)
    assert len({_logical_id(group) for group in groups}) == 3


def test_vpc_and_subnets_use_two_literal_zones(
    network: HostingNetwork, template: Template
) -> None:
    vpcs = _properties(template, "AWS::EC2::VPC")
    props = vpcs[_logical_id(network.vpc)]
    assert props["CidrBlock"] == "10.42.0.0/16"
    assert props["EnableDnsSupport"] is True
    assert props["EnableDnsHostnames"] is True
    subnets = _properties(template, "AWS::EC2::Subnet")
    groups = (
        (network.vpc.public_subnets, {"10.42.0.0/24", "10.42.1.0/24"}),
        (network.vpc.private_subnets, {"10.42.2.0/24", "10.42.3.0/24"}),
        (network.vpc.isolated_subnets, {"10.42.4.0/24", "10.42.5.0/24"}),
    )
    for group, cidrs in groups:
        assert len(group) == 2
        group_props = [subnets[_logical_id(subnet)] for subnet in group]
        assert {item["CidrBlock"] for item in group_props} == cidrs
        assert {item["AvailabilityZone"] for item in group_props} == set(_ZONES)
        for item in group_props:
            assert item["VpcId"] == {"Ref": _logical_id(network.vpc)}
            assert item["MapPublicIpOnLaunch"] is False
    application = network.node.root
    assert isinstance(application, App)
    _assert_no_missing_context(application)


def test_routes_keep_database_isolated(
    network: HostingNetwork, template: Template
) -> None:
    associations = _properties(template, "AWS::EC2::SubnetRouteTableAssociation")
    subnet_tables = {
        item["SubnetId"]["Ref"]: item["RouteTableId"]["Ref"]
        for item in associations.values()
    }
    assert len(subnet_tables) == 6
    tables = _properties(template, "AWS::EC2::RouteTable")
    assert set(subnet_tables.values()) == set(tables)
    for item in tables.values():
        assert item["VpcId"] == {"Ref": _logical_id(network.vpc)}
    routes = _properties(template, "AWS::EC2::Route")
    table_routes: dict[str, list[dict[str, Any]]] = {
        table_id: [] for table_id in tables
    }
    for item in routes.values():
        table_routes[item["RouteTableId"]["Ref"]].append(item)
    gateway_id = next(iter(_properties(template, "AWS::EC2::InternetGateway")))
    nat_id = next(iter(_properties(template, "AWS::EC2::NatGateway")))
    for group, target in (
        (network.vpc.public_subnets, {"GatewayId": {"Ref": gateway_id}}),
        (network.vpc.private_subnets, {"NatGatewayId": {"Ref": nat_id}}),
    ):
        for subnet in group:
            table_id = subnet_tables[_logical_id(subnet)]
            assert table_routes[table_id] == [
                {
                    "RouteTableId": {"Ref": table_id},
                    "DestinationCidrBlock": "0.0.0.0/0",
                    **target,
                }
            ]
    for subnet in network.vpc.isolated_subnets:
        assert table_routes[subnet_tables[_logical_id(subnet)]] == []


def test_single_nat_gateway_uses_a_public_subnet(
    network: HostingNetwork, template: Template
) -> None:
    gateways = _properties(template, "AWS::EC2::NatGateway")
    assert len(gateways) == 1
    props = next(iter(gateways.values()))
    assert props["SubnetId"] in [
        {"Ref": _logical_id(subnet)} for subnet in network.vpc.public_subnets
    ]
    addresses = _properties(template, "AWS::EC2::EIP")
    assert len(addresses) == 1
    address_id = next(iter(addresses))
    assert addresses[address_id]["Domain"] == "vpc"
    assert props["AllocationId"] == {"Fn::GetAtt": [address_id, "AllocationId"]}
    attachments = _properties(template, "AWS::EC2::VPCGatewayAttachment")
    assert list(attachments.values()) == [
        {
            "VpcId": {"Ref": _logical_id(network.vpc)},
            "InternetGatewayId": {
                "Ref": next(iter(_properties(template, "AWS::EC2::InternetGateway")))
            },
        }
    ]


def test_security_group_rules_allow_only_the_named_pairs(
    network: HostingNetwork, template: Template
) -> None:
    stack = Stack.of(network)
    edge = stack.resolve(network.edge_security_group.security_group_id)
    app = stack.resolve(network.app_security_group.security_group_id)
    database = stack.resolve(network.database_security_group.security_group_id)
    ingress = _rules(template, "Ingress")
    egress = _rules(template, "Egress")
    deny_egress = {
        "GroupId": database,
        "CidrIp": "255.255.255.255/32",
        "IpProtocol": "icmp",
        "FromPort": 252,
        "ToPort": 86,
    }
    assert egress.count(deny_egress) == 1
    egress.remove(deny_egress)
    for actual, expected in (
        (
            ingress,
            [
                (edge, "CidrIp", "0.0.0.0/0", 443),
                (app, "SourceSecurityGroupId", edge, 8080),
                (database, "SourceSecurityGroupId", app, 5432),
            ],
        ),
        (
            egress,
            [
                (edge, "DestinationSecurityGroupId", app, 8080),
                (edge, "CidrIp", "0.0.0.0/0", 443),
                (app, "CidrIp", "0.0.0.0/0", 443),
                (app, "DestinationSecurityGroupId", database, 5432),
            ],
        ),
    ):
        assert len(actual) == len(expected)
        for group, peer_key, peer, port in expected:
            assert {
                "GroupId": group,
                "IpProtocol": "tcp",
                "FromPort": port,
                "ToPort": port,
                peer_key: peer,
            } in actual


def test_groups_have_no_inline_access_or_group_dependencies(
    network: HostingNetwork, template: Template
) -> None:
    groups = template.find_resources("AWS::EC2::SecurityGroup")
    for resource in groups.values():
        props = resource["Properties"]
        assert props["VpcId"] == {"Ref": _logical_id(network.vpc)}
        assert not props.get("SecurityGroupIngress", [])
        assert not props.get("SecurityGroupEgress", [])
        assert not set(resource.get("DependsOn", [])) & set(groups)


def test_construct_synthesizes_without_environment_lookups(tmp_path: Path) -> None:
    application = App(outdir=str(tmp_path / "assembly"))
    stack = Stack(application, "Portable")
    HostingNetwork(stack, "Network")
    Template.from_stack(stack).resource_count_is("AWS::EC2::Subnet", 6)
    _assert_no_missing_context(application)


def test_hosting_stack_keeps_network_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "assembly")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )
    assert stack.node.try_find_child("Network") is None
    resources = Template.from_stack(stack).to_json()["Resources"]
    assert all(not item["Type"].startswith("AWS::EC2::") for item in resources.values())
