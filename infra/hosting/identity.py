import re

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_cognito as cognito
from constructs import Construct

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"


def _validate_hostname(hostname: str) -> None:
    if (
        not isinstance(hostname, str)
        or len(hostname) > 253
        or re.fullmatch(rf"{_LABEL}(?:\.{_LABEL})+", hostname) is None
        or re.fullmatch(r"[0-9.]+", hostname) is not None
    ):
        raise ValueError("hostname MUST be a lowercase DNS hostname")


def _validate_prefix(domain_prefix: str) -> None:
    if (
        not isinstance(domain_prefix, str)
        or not 3 <= len(domain_prefix) <= 63
        or re.fullmatch(_LABEL, domain_prefix) is None
        or any(word in domain_prefix for word in ("aws", "amazon", "cognito"))
    ):
        raise ValueError("domain prefix MUST be a valid unreserved Cognito prefix")


class HostingIdentity(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        hostname: str,
        domain_prefix: str,
    ) -> None:
        _validate_hostname(hostname)
        _validate_prefix(domain_prefix)
        super().__init__(scope, construct_id)
        self.user_pool: cognito.UserPool = cognito.UserPool(
            self,
            "UserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            sign_in_case_sensitive=False,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            password_policy=cognito.PasswordPolicy(
                min_length=14,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(3),
            ),
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.client: cognito.UserPoolClient = self.user_pool.add_client(
            "Client",
            generate_secret=True,
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO,
            ],
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID],
                callback_urls=[f"https://{hostname}/oauth2/idpresponse"],
                logout_urls=[f"https://{hostname}/"],
            ),
            auth_flows=cognito.AuthFlow(user_srp=True),
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(1),
        )
        self.domain: cognito.UserPoolDomain = self.user_pool.add_domain(
            "Domain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=domain_prefix),
        )
