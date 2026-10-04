import re

from aws_cdk import Duration, Stack, Token
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_elasticloadbalancingv2_actions as actions
from constructs import Construct

from identity import HostingIdentity
from network import HostingNetwork


class HostingEdge(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        network: HostingNetwork,
        identity: HostingIdentity,
        service: ecs.FargateService,
        certificate_arn: str,
    ) -> None:
        stack = Stack.of(scope)
        account = stack.account
        if (
            Token.is_unresolved(account)
            or re.fullmatch(r"[0-9]{12}", account) is None
            or Token.is_unresolved(stack.region)
            or stack.region != "us-east-1"
        ):
            raise ValueError("edge stack MUST have a concrete us-east-1 account")
        if (
            not isinstance(certificate_arn, str)
            or Token.is_unresolved(certificate_arn)
            or re.fullmatch(
                rf"arn:aws:acm:us-east-1:{account}:certificate/"
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                certificate_arn,
            )
            is None
        ):
            raise ValueError("certificate ARN MUST match the concrete edge account")
        super().__init__(scope, construct_id)
        self.load_balancer: elbv2.ApplicationLoadBalancer = (
            elbv2.ApplicationLoadBalancer(
                self,
                "LoadBalancer",
                vpc=network.vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=network.vpc.public_subnets),
                internet_facing=True,
                ip_address_type=elbv2.IpAddressType.IPV4,
                security_group=network.edge_security_group,
                deletion_protection=True,
                drop_invalid_header_fields=True,
                desync_mitigation_mode=elbv2.DesyncMitigationMode.STRICTEST,
            )
        )
        self.target_group: elbv2.ApplicationTargetGroup = elbv2.ApplicationTargetGroup(
            self,
            "TargetGroup",
            vpc=network.vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            targets=[
                service.load_balancer_target(container_name="web", container_port=80)
            ],
            deregistration_delay=Duration.seconds(30),
            health_check=elbv2.HealthCheck(
                protocol=elbv2.Protocol.HTTP,
                path="/api/healthz",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )
        self.listener: elbv2.ApplicationListener = self.load_balancer.add_listener(
            "Https",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificates=[
                acm.Certificate.from_certificate_arn(
                    self, "Certificate", certificate_arn
                )
            ],
            ssl_policy=elbv2.SslPolicy.TLS13_RES,
            open=False,
            default_action=elbv2.ListenerAction.fixed_response(
                404, content_type="text/plain"
            ),
        )
        self.rule: elbv2.ApplicationListenerRule = elbv2.ApplicationListenerRule(
            self,
            "AuthenticatedHost",
            listener=self.listener,
            priority=1,
            conditions=[elbv2.ListenerCondition.host_headers([identity.hostname])],
            action=actions.AuthenticateCognitoAction(
                user_pool=identity.user_pool,
                user_pool_client=identity.client,
                user_pool_domain=identity.domain,
                scope="openid",
                on_unauthenticated_request=elbv2.UnauthenticatedAction.AUTHENTICATE,
                session_timeout=Duration.hours(1),
                allow_https_outbound=False,
                next=elbv2.ListenerAction.forward([self.target_group]),
            ),
        )
