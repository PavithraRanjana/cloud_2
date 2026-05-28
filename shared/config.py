import os
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings


class BaseConfig(BaseSettings):
    service_name: str = "aerolink-service"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://aerolink:aerolink@localhost:5432/aerolink"
    database_sync_url: str = "postgresql://aerolink:aerolink@localhost:5432/aerolink"

    @model_validator(mode="after")
    def _interpolate_db_password(self):
        # In production the DB password lives in Secrets Manager and is injected
        # as the DB_PASSWORD env var by ECS. The DATABASE_URL we receive contains
        # the placeholder __DB_PASSWORD__ so that the URL itself never carries a
        # plaintext credential. URL-encode before substituting — RDS-managed
        # passwords can contain reserved URL characters like ?, #, !, [, ].
        pwd = os.environ.get("DB_PASSWORD")
        if not pwd:
            return self
        encoded = quote(pwd, safe="")
        if "__DB_PASSWORD__" in self.database_url:
            self.database_url = self.database_url.replace("__DB_PASSWORD__", encoded)
        if "__DB_PASSWORD__" in self.database_sync_url:
            self.database_sync_url = self.database_sync_url.replace("__DB_PASSWORD__", encoded)
        return self

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "aerolink-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Amazon Cognito (production) — empty strings = local dev HS256 fallback mode
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""

    # AWS / LocalStack
    # In production (ECS) leave these unset — boto3 uses the ECS task IAM role automatically.
    # Set aws_endpoint_url=http://localhost:4566, aws_access_key_id=test,
    # aws_secret_access_key=test in .env to target LocalStack.
    aws_region: str = "eu-west-1"
    aws_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    localstack_auth_token: str = ""

    # EventBridge
    event_bus_name: str = "aerolink-events"

    # Service URLs
    auth_service_url: str = "http://localhost:8001"
    flight_service_url: str = "http://localhost:8002"
    booking_service_url: str = "http://localhost:8003"
    payment_service_url: str = "http://localhost:8004"
    baggage_service_url: str = "http://localhost:8005"
    checkin_service_url: str = "http://localhost:8006"
    passenger_service_url: str = "http://localhost:8007"
    notification_service_url: str = "http://localhost:8008"

    class Config:
        env_file = ".env"
        extra = "allow"
