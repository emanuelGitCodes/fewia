from botocore.config import Config  # type: ignore[import-untyped]


def aws_client_config(read_timeout: int, *, local: bool) -> Config:
    return Config(
        connect_timeout=3,
        read_timeout=read_timeout,
        retries={"total_max_attempts": 1},
        **({"proxies": {}} if local else {}),
    )
