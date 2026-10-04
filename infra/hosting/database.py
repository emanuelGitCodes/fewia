import json

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from network import HostingNetwork


class HostingDatabase(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, network: HostingNetwork
    ) -> None:
        super().__init__(scope, construct_id)
        engine = rds.DatabaseInstanceEngine.postgres(
            version=rds.PostgresEngineVersion.of("16.15", "16")
        )
        parameters = rds.ParameterGroup(
            self,
            "Parameters",
            engine=engine,
            parameters={"rds.force_ssl": "1"},
        )
        self.admin_secret: secretsmanager.ISecret = rds.DatabaseSecret(
            self, "AdminSecret", username="fewia_admin"
        )
        self.admin_secret.apply_removal_policy(RemovalPolicy.RETAIN)
        self.instance: rds.DatabaseInstance = rds.DatabaseInstance(
            self,
            "Instance",
            engine=engine,
            credentials=rds.Credentials.from_secret(self.admin_secret),
            instance_type=ec2.InstanceType("t4g.micro"),
            vpc=network.vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=network.vpc.isolated_subnets),
            security_groups=[network.database_security_group],
            multi_az=False,
            database_name="fewia",
            port=5432,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            allocated_storage=20,
            max_allocated_storage=100,
            publicly_accessible=False,
            backup_retention=Duration.days(7),
            copy_tags_to_snapshot=True,
            deletion_protection=True,
            delete_automated_backups=False,
            removal_policy=RemovalPolicy.RETAIN,
            auto_minor_version_upgrade=True,
            allow_major_version_upgrade=False,
            parameter_group=parameters,
        )
        self.application_secret: secretsmanager.Secret = secretsmanager.Secret(
            self,
            "ApplicationSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "fewia_app"}),
                generate_string_key="password",
                password_length=32,
                exclude_punctuation=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
