"""
Immutable audit logging for compliance (PCI-DSS, GDPR).
Logs are structured JSON and stored in both the database and stdout.
In production, these would go to CloudWatch Logs with tamper-proof retention.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from shared.database import Base
import structlog

logger = structlog.get_logger()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    service = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    actor_id = Column(String(255), nullable=True, index=True)
    actor_role = Column(String(50), nullable=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    status = Column(String(20), nullable=False, default="success")


async def record_audit(db, service: str, action: str, resource_type: str,
                       resource_id: str = None, actor_id: str = None,
                       actor_role: str = None, detail: str = None,
                       ip_address: str = None, status: str = "success"):
    """Record an audit log entry (immutable, append-only)."""
    entry = AuditLog(
        service=service,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        status=status,
    )
    db.add(entry)
    await db.flush()

    logger.info("audit_log",
                service=service, action=action,
                resource_type=resource_type, resource_id=resource_id,
                actor_id=actor_id, status=status)
