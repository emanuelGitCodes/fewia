from aws_cdk import aws_ec2 as ec2
from constructs import Construct

HOSTING_AVAILABILITY_ZONES: tuple[str, str] = ("us-east-1a", "us-east-1b")


class HostingNetwork(Construct):
    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        self.vpc: ec2.Vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.42.0.0/16"),
            max_azs=2,
            nat_gateways=1,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            restrict_default_security_group=False,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                    map_public_ip_on_launch=False,
                ),
                ec2.SubnetConfiguration(
                    name="Application",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Database",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )
        self.edge_security_group: ec2.SecurityGroup = self._security_group("Edge")
        self.app_security_group: ec2.SecurityGroup = self._security_group("App")
        self.database_security_group: ec2.SecurityGroup = self._security_group(
            "Database"
        )
        self.edge_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443)
        )
        self.edge_security_group.add_egress_rule(
            self.app_security_group, ec2.Port.tcp(8080)
        )
        self.edge_security_group.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        self.app_security_group.add_ingress_rule(
            self.edge_security_group, ec2.Port.tcp(8080)
        )
        self.app_security_group.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        self.app_security_group.add_egress_rule(
            self.database_security_group, ec2.Port.tcp(5432)
        )
        self.database_security_group.add_ingress_rule(
            self.app_security_group, ec2.Port.tcp(5432)
        )

    def _security_group(self, name: str) -> ec2.SecurityGroup:
        return ec2.SecurityGroup(
            self,
            name,
            vpc=self.vpc,
            allow_all_outbound=False,
            allow_all_ipv6_outbound=False,
            disable_inline_rules=True,
        )
