from typing import Protocol, Sequence

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import RowMapping

from api.auth.entities import UserEntities

class AuthInterFace(Protocol):
    async def create_user(self, conn: AsyncConnection, payload: UserEntities): ...

    async def get_user_by_email(self, conn: AsyncConnection, email: str) -> Sequence[RowMapping]: ...
    