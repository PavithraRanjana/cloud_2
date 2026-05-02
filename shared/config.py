from pydantic_settings import BaseSettings


class BaseConfig(BaseSettings):
    service_name: str = "aerolink-service"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://aerolink:aerolink@localhost:5432/aerolink"
    database_sync_url: str = "postgresql://aerolink:aerolink@localhost:5432/aerolink"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "aerolink-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # AWS / LocalStack
    aws_region: str = "eu-west-1"
    aws_endpoint_url: str = "http://localhost:4566"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
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
