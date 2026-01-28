from api.database.base import AuditBaseModel
from api.conversations.models import MessageTypeEnum

class UserEntities(AuditBaseModel):
    id: str | None = None
    username: str | None = None
    email: str | None = None
    password: str | None = None