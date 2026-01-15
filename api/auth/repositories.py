from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

from enum import Enum
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import RowMapping, select, func, cast, insert, desc, String, delete
from sqlalchemy.sql.operators import eq

from api.auth.interface import AuthInterFace
from api.auth.models import user
from api.auth.entities import UserEntities

class UserRepository(AuthInterFace):
    async def create_user(self, conn: AsyncConnection, payload: UserEntities):
        stmt = insert(user).values(**payload.model_dump(exclude_unset=True)).returning(user.c.id)
        try:
            await conn.execute(statement=stmt)
            await conn.commit()
        except Exception as e:
            raise e
        return payload
    
    async def get_user_by_email(self, conn: AsyncConnection, email: str) -> Sequence[RowMapping]:
        stmt = (
            select(user)
            .where(eq(user.c.email, email))
        )
        result = await conn.execute(statement=stmt)
        return result.mappings().first()