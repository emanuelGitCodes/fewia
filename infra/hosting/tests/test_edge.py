import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk.assertions import Template
from constructs import IConstruct

from edge import HostingEdge
from identity import HostingIdentity
from network import HostingNetwork
from stack import HostingStack

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_CERTIFICATE = (
    f"arn:aws:acm:{_REGION}:{_ACCOUNT}:certificate/12345678-1234-abcd-1234-123456789abc"
)


@dataclass
class _Inputs:
    stack: Stack
    network: HostingNetwork
    identity: HostingIdentity
    service: ecs.FargateService

    def build(self, certificate_arn: str = _CERTIFICATE) -> HostingEdge:
        return HostingEdge(
            self.stack,
            "Edge",
            network=self.network,
            identity=self.identity,
            service=self.service,
            certificate_arn=certificate_arn,
        )


def _inputs(tmp_path: Path, env: Environment) -> _Inputs:
    app = App(
        outdir=str(tmp_path / "assembly"),
        context={
            "availability-zones:account=111122223333:region=us-east-1": [
                "us-east-1a",
                "us-east-1b",
            ]
        },
    )
    stack = Stack(app, "EdgeTest", env=env)
    network = HostingNetwork(stack, "Network")
    identity = HostingIdentity(
        stack, "Identity", hostname="example.test", domain_prefix="fewia-dev"
    )
    task = ecs.FargateTaskDefinition(stack, "Task")
    for name, port in (("api", 8000), ("web", 8080)):
        task.add_container(
            name,
            container_name=name,
            image=ecs.ContainerImage.from_registry("fixture.invalid/image:offline"),
            port_mappings=[ecs.PortMapping(container_port=port)],
        )
    service = ecs.FargateService(
        stack,
        "Service",
        cluster=ecs.Cluster(stack, "Cluster", vpc=network.vpc),
        task_definition=task,
        security_groups=[network.app_security_group],
        vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        assign_public_ip=False,
        enable_execute_command=False,
    )
    return _Inputs(stack, network, identity, service)


@pytest.fixture
def inputs(tmp_path: Path) -> _Inputs:
    return _inputs(tmp_path, Environment(account=_ACCOUNT, region=_REGION))


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _properties(template: Template, resource: IConstruct) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        template.to_json()["Resources"][_logical_id(resource)]["Properties"],
    )


def test_https_only_listener_has_exact_fixed_default(inputs: _Inputs) -> None:
    edge = inputs.build()
    template = Template.from_stack(inputs.stack)
    assert isinstance(edge.load_balancer, elbv2.ApplicationLoadBalancer)
    assert isinstance(edge.listener, elbv2.ApplicationListener)
    assert isinstance(edge.target_group, elbv2.ApplicationTargetGroup)
    assert isinstance(edge.rule, elbv2.ApplicationListenerRule)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::Listener", 1)
    assert _properties(template, edge.listener) == {
        "LoadBalancerArn": {"Ref": _logical_id(edge.load_balancer)},
        "Port": 443,
        "Protocol": "HTTPS",
        "Certificates": [{"CertificateArn": _CERTIFICATE}],
        "SslPolicy": "ELBSecurityPolicy-TLS13-1-2-Res-2021-06",
        "DefaultActions": [
            {
                "Type": "fixed-response",
                "FixedResponseConfig": {
                    "ContentType": "text/plain",
                    "StatusCode": "404",
                },
            },
        ],
    }


def test_host_rule_authenticates_before_forward_for_all_routes(inputs: _Inputs) -> None:
    edge = inputs.build()
    template = Template.from_stack(inputs.stack)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::ListenerRule", 1)
    rule = _properties(template, edge.rule)
    assert set(rule) == {"Actions", "Conditions", "ListenerArn", "Priority"}
    assert rule["Priority"] == 1
    assert rule["ListenerArn"] == {"Ref": _logical_id(edge.listener)}
    assert rule["Conditions"] == [
        {
            "Field": "host-header",
            "HostHeaderConfig": {"Values": [inputs.identity.hostname]},
        }
    ]
    assert rule["Actions"] == [
        {
            "Type": "authenticate-cognito",
            "Order": 1,
            "AuthenticateCognitoConfig": {
                "UserPoolArn": inputs.stack.resolve(
                    inputs.identity.user_pool.user_pool_arn
                ),
                "UserPoolClientId": inputs.stack.resolve(
                    inputs.identity.client.user_pool_client_id
                ),
                "UserPoolDomain": inputs.stack.resolve(
                    inputs.identity.domain.domain_name
                ),
                "Scope": "openid",
                "OnUnauthenticatedRequest": "authenticate",
                "SessionTimeout": 3600,
            },
        },
        {
            "Type": "forward",
            "Order": 2,
            "TargetGroupArn": {"Ref": _logical_id(edge.target_group)},
        },
    ]
    client = _properties(template, inputs.identity.client)
    assert client["CallbackURLs"] == [
        f"https://{inputs.identity.hostname}/oauth2/idpresponse"
    ]
    assert client["SupportedIdentityProviders"] == ["COGNITO"]
    assert client["AllowedOAuthFlows"] == ["code"]
    assert client["AllowedOAuthScopes"] == ["openid"]
    assert client["GenerateSecret"] is True
    assert client["AccessTokenValidity"] == client["IdTokenValidity"] == 60


def test_public_ipv4_alb_has_exact_group_subnets_and_protection(
    inputs: _Inputs,
) -> None:
    edge = inputs.build()
    template = Template.from_stack(inputs.stack)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 1)
    props = _properties(template, edge.load_balancer)
    assert props["Type"] == "application"
    assert props["Scheme"] == "internet-facing"
    assert props["IpAddressType"] == "ipv4"
    assert props["SecurityGroups"] == [
        inputs.stack.resolve(inputs.network.edge_security_group.security_group_id)
    ]
    assert props["Subnets"] == [
        inputs.stack.resolve(subnet.subnet_id)
        for subnet in inputs.network.vpc.public_subnets
    ]
    attributes = {
        item["Key"]: item["Value"] for item in props["LoadBalancerAttributes"]
    }
    assert attributes["deletion_protection.enabled"] == "true"
    assert attributes["routing.http.drop_invalid_header_fields.enabled"] == "true"
    assert attributes["routing.http.desync_mitigation_mode"] == "strictest"


def test_private_target_health_and_exact_web_registration(inputs: _Inputs) -> None:
    edge = inputs.build()
    template = Template.from_stack(inputs.stack)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::TargetGroup", 1)
    props = _properties(template, edge.target_group)
    assert props["Port"] == 8080
    assert props["Protocol"] == "HTTP"
    assert props["TargetType"] == "ip"
    assert props["VpcId"] == inputs.stack.resolve(inputs.network.vpc.vpc_id)
    assert props["HealthCheckPath"] == "/api/healthz"
    assert props["HealthCheckProtocol"] == "HTTP"
    assert props["HealthCheckPort"] == "8080"
    assert props["Matcher"] == {"HttpCode": "200"}
    assert props["HealthCheckIntervalSeconds"] == 30
    assert props["HealthCheckTimeoutSeconds"] == 5
    assert props["HealthyThresholdCount"] == 2
    assert props["UnhealthyThresholdCount"] == 3
    attributes = {item["Key"]: item["Value"] for item in props["TargetGroupAttributes"]}
    assert attributes["deregistration_delay.timeout_seconds"] == "30"
    assert "Targets" not in props
    template.resource_count_is("AWS::ECS::Service", 1)
    service = _properties(template, inputs.service)
    assert service["LoadBalancers"] == [
        {
            "ContainerName": "web",
            "ContainerPort": 8080,
            "TargetGroupArn": {"Ref": _logical_id(edge.target_group)},
        }
    ]
    assert not service.get("EnableExecuteCommand", False)
    assert service["NetworkConfiguration"]["AwsvpcConfiguration"]["SecurityGroups"] == [
        inputs.stack.resolve(inputs.network.app_security_group.security_group_id)
    ]


def test_edge_adds_no_identity_roles_secrets_or_widened_network(
    inputs: _Inputs,
) -> None:
    existing = {
        node.node.path
        for node in inputs.stack.node.find_all()
        if isinstance(node, CfnResource)
    }
    edge = inputs.build()
    template = Template.from_stack(inputs.stack)
    added = [
        node
        for node in inputs.stack.node.find_all()
        if isinstance(node, CfnResource) and node.node.path not in existing
    ]
    assert {node.cfn_resource_type for node in added} <= {
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::ElasticLoadBalancingV2::Listener",
        "AWS::ElasticLoadBalancingV2::ListenerRule",
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        "AWS::EC2::SecurityGroupIngress",
        "AWS::EC2::SecurityGroupEgress",
    }
    template.resource_count_is("AWS::EC2::SecurityGroup", 3)
    network = inputs.network
    edge_id = inputs.stack.resolve(network.edge_security_group.security_group_id)
    app_id = inputs.stack.resolve(network.app_security_group.security_group_id)
    db_id = inputs.stack.resolve(network.database_security_group.security_group_id)
    for resource in template.find_resources("AWS::EC2::SecurityGroupIngress").values():
        props = resource["Properties"]
        assert props["IpProtocol"] == "tcp"
        assert props["FromPort"] == props["ToPort"]
        if props["GroupId"] == edge_id:
            assert props["FromPort"] == 443
            assert props["CidrIp"] == "0.0.0.0/0"
            assert "SourceSecurityGroupId" not in props
        elif props["GroupId"] == app_id:
            assert props["FromPort"] == 8080
            assert props["SourceSecurityGroupId"] == edge_id
            assert "CidrIp" not in props
        else:
            assert props["GroupId"] == db_id
            assert props["FromPort"] == 5432
            assert props["SourceSecurityGroupId"] == app_id
    for resource in template.find_resources("AWS::EC2::SecurityGroupEgress").values():
        props = resource["Properties"]
        if props["IpProtocol"] == "icmp":
            assert props["GroupId"] in (edge_id, app_id, db_id)
            assert props == {
                "GroupId": props["GroupId"],
                "IpProtocol": "icmp",
                "FromPort": 252,
                "ToPort": 86,
                "CidrIp": "255.255.255.255/32",
                "Description": "Disallow all traffic",
            }
            continue
        assert props["IpProtocol"] == "tcp"
        assert props["FromPort"] == props["ToPort"]
        rule = {key: value for key, value in props.items() if key != "Description"}
        if props["GroupId"] == edge_id and props["FromPort"] == 8080:
            assert rule == {
                "GroupId": edge_id,
                "IpProtocol": "tcp",
                "FromPort": 8080,
                "ToPort": 8080,
                "DestinationSecurityGroupId": app_id,
            }
        elif props["GroupId"] == app_id and props["FromPort"] == 5432:
            assert rule == {
                "GroupId": app_id,
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "DestinationSecurityGroupId": db_id,
            }
        else:
            assert props["GroupId"] in (edge_id, app_id)
            assert rule == {
                "GroupId": props["GroupId"],
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "CidrIp": "0.0.0.0/0",
            }
    assert all(
        node.node.path.startswith(edge.node.path + "/")
        for node in added
        if node.cfn_resource_type.startswith("AWS::ElasticLoadBalancingV2::")
    )
    assert not template.to_json().get("Outputs")


@pytest.mark.parametrize(
    "certificate_arn",
    [
        None,
        123,
        "",
        " " + _CERTIFICATE,
        _CERTIFICATE + " ",
        _CERTIFICATE + "\n",
        _CERTIFICATE + "\r",
        _CERTIFICATE.replace("abcd", "ab\tcd"),
        _CERTIFICATE.replace("arn:aws:", "arn:aws-cn:"),
        _CERTIFICATE.replace("us-east-1", "us-west-2"),
        _CERTIFICATE.replace(_ACCOUNT, "999900001111"),
        _CERTIFICATE.replace(_ACCOUNT, "11112222333"),
        _CERTIFICATE.replace("certificate/", "certificate:"),
        _CERTIFICATE.replace("abcd", "ABCD"),
        _CERTIFICATE.replace("abcd", "abcg"),
        _CERTIFICATE.replace("12345678-", "1234567-", 1),
        _CERTIFICATE.replace("1234-abcd", "123-abcd"),
        _CERTIFICATE.replace("abcd", "abc"),
        _CERTIFICATE.replace("abcd-1234", "abcd-123"),
        _CERTIFICATE[:-1],
        _CERTIFICATE + "/extra",
        _CERTIFICATE.replace("acm:", "iam:"),
    ],
)
def test_invalid_certificate_fails_before_any_edge_resources(
    inputs: _Inputs, certificate_arn: object
) -> None:
    paths = tuple(node.node.path for node in inputs.stack.node.find_all())
    with pytest.raises(ValueError) as error:
        inputs.build(cast(str, certificate_arn))
    assert str(error.value) == "certificate ARN MUST match the concrete edge account"
    assert tuple(node.node.path for node in inputs.stack.node.find_all()) == paths
    Template.from_stack(inputs.stack).resource_count_is(
        "AWS::ElasticLoadBalancingV2::LoadBalancer", 0
    )


def test_token_certificate_fails_before_any_edge_resources(inputs: _Inputs) -> None:
    paths = tuple(node.node.path for node in inputs.stack.node.find_all())
    with pytest.raises(ValueError, match="certificate ARN MUST"):
        inputs.build(inputs.service.service_arn)
    assert tuple(node.node.path for node in inputs.stack.node.find_all()) == paths


@pytest.mark.parametrize(
    "env",
    [
        Environment(),
        Environment(account=_ACCOUNT),
        Environment(region=_REGION),
        Environment(account="123", region=_REGION),
        Environment(account=" " + _ACCOUNT, region=_REGION),
        Environment(account=_ACCOUNT + "\n", region=_REGION),
        Environment(account=_ACCOUNT, region="us-west-2"),
    ],
)
def test_invalid_stack_environment_fails_before_any_edge_resources(
    tmp_path: Path, env: Environment
) -> None:
    inputs = _inputs(tmp_path, env)
    paths = tuple(node.node.path for node in inputs.stack.node.find_all())
    with pytest.raises(ValueError) as error:
        inputs.build()
    assert str(error.value) == "edge stack MUST have a concrete us-east-1 account"
    assert tuple(node.node.path for node in inputs.stack.node.find_all()) == paths
    assert inputs.stack.node.try_find_child("Edge") is None
    assert not any(
        isinstance(node, CfnResource)
        and node.cfn_resource_type.startswith("AWS::ElasticLoadBalancingV2::")
        for node in inputs.stack.node.find_all()
    )


def test_full_synthesis_is_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    inputs = _inputs(tmp_path, Environment(account=_ACCOUNT, region=_REGION))
    inputs.build()
    app = inputs.stack.node.root
    assert isinstance(app, App)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")


def test_minimal_hosting_stack_keeps_edge_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    template = Template.from_stack(stack)
    for resource_type in (
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::ElasticLoadBalancingV2::Listener",
        "AWS::ElasticLoadBalancingV2::ListenerRule",
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        "AWS::ECS::Service",
        "AWS::Cognito::UserPool",
    ):
        template.resource_count_is(resource_type, 0)
