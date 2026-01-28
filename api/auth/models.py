import uuid

from sqlalchemy import Table, Column, String, UUID

from api.models.base import get_audit_columns
from api.database.client import metadata

user = Table(
    "users",
    metadata,
    Column("id", UUID, primary_key=True, default=uuid.uuid4),
    Column("email", String, nullable=True),
    Column("username", String, nullable=True),
    Column("password", String, nullable=True),
    *get_audit_columns(),
)