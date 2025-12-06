from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

from enum import Enum
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import RowMapping, select, func, cast, insert, desc, String, delete
from sqlalchemy.sql.operators import eq

from api.conversations.interface import ConversationInterFace, MessageInterFace
from api.conversations.models import conversation, message, MessageTypeEnum, conversation_states
from api.conversations.entities import ConversationEntities, MessageEntities
from api.conversations.schemas import APIMessageParams, CreateConversationRequest, CreateMessageRequest, MessageDataResponse, ChatModelResponse


class ConversationState(str, Enum):
    IDLE = "idle"
    SEARCHING = "searching"
    SELECTING = "selecting"
    CONFIRMING = "confirming"
    BOOKING = "booking"
    COMPLETED = "completed"
    COMPLETED_WITH_NO_TICKET = "completed_with_no_ticket"


class ConversationRepository(ConversationInterFace):
    async def create_conversation(self, conn: AsyncConnection, payload: ConversationEntities):
        stmt = insert(conversation).values(**payload.model_dump(exclude_unset=True)).returning(conversation.c.id)
        try:
            await conn.execute(statement=stmt)
            await conn.commit()
        except Exception as e:
            raise e
        return payload
    
    async def get_conversations(self, conn: AsyncConnection) -> Sequence[RowMapping]:
        stmt = (
            select(conversation)
            .order_by(desc(conversation.c.created_at))
        )
        result = await conn.execute(statement=stmt)
        return result.fetchall()
    
    async def get_conversation_by_id(self, conn: AsyncConnection, payload: ConversationEntities) -> Sequence[RowMapping]:
        messages_cte = (
            select(
                message.c.conversation_id,
                func.jsonb_agg(
                    func.jsonb_build_object(
                        'id', message.c.id,
                        'content', message.c.content,
                        'message_type', cast(message.c.message_type, String),
                        'token_usage', message.c.token_usage,
                        'metadata', message.c.metadata,
                        'created_at', message.c.created_at,
                        'created_by', message.c.created_by
                    )
                ).label('messages')
            )
            .where(eq(message.c.conversation_id, payload.id))
            .group_by(message.c.conversation_id)
            .cte('messages_cte')
        )

        stmt = (
            select(
                conversation,
                messages_cte.c.messages
            )
            .join(messages_cte, conversation.c.id == messages_cte.c.conversation_id)
            .where(eq(conversation.c.id, payload.id))
        )
        try:
            result = await conn.execute(statement=stmt)
            return result.mappings().first()
        except Exception as e:
            raise e
    
class MessageRepository(MessageInterFace):
    async def create_message(self, conn: AsyncConnection, payload: MessageEntities):
        stmt = insert(message).values(**payload.model_dump(exclude_unset=True)).returning(message.c.id)
        try:
            await conn.execute(statement=stmt)
            await conn.commit()
        except Exception as e:
            raise e
        return payload
    
    async def delete_message(self, conn: AsyncConnection, payload: MessageEntities):
        stmt = delete(message).where(eq(message.c.id, payload.id))
        try:
            await conn.execute(statement=stmt)
            await conn.commit()
        except Exception as e:
            raise e
        return payload


class InMemoryChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, conn, conversation_id: str):
        self.conn = conn
        self.conversation_id = conversation_id
        self._messages_cache = []

    @property
    def messages(self):
        """
        Langchain membutuhkan property sinkron ini.
        Karena kita di context async, kita return cache atau empty list.
        """
        return self._messages_cache

    async def aget_messages(self):
        """Load messages dari DB"""

        if self.conversation_id != '':
            # ✅ Selalu load fresh dari DB
            data = await ConversationRepository().get_conversation_by_id(
                conn=self.conn,
                payload=ConversationEntities(id=self.conversation_id)
            )

            msgs = []
            for r in data.get("messages", []):
                if r["message_type"] == "question":
                    msgs.append(HumanMessage(content=r["content"]))
                else:
                    msgs.append(AIMessage(content=r["content"]))
            
            self._messages_cache = msgs
            self._loaded = True
            
            print(f"📜 Loaded {len(msgs)} messages for conversation {self.conversation_id}")  # ✅ Debug
            return msgs
        else:
            print(f"📜 New conversation detection")  # ✅ Debug
            return []

    async def aadd_message(self, message: BaseMessage, conversation_id: str | None = None):
        if isinstance(message, HumanMessage):
            message_type = MessageTypeEnum.question
        else:
            message_type = MessageTypeEnum.answer
        
        print(f"💾 Saving message: {message_type.value} - {message.content[:50]}...")  # ✅ Debug

        await MessageRepository().create_message(
            conn=self.conn,
            payload=CreateMessageRequest(
                conversation_id=conversation_id,
                content=message.content,
                message_type=message_type,
                token_usage={},
                created_by="system",
                metadata={}
            ).transform()
        )
        
        # ✅ Update cache juga
        if self._messages_cache is not None:
            self._messages_cache.append(message)

    # === ✅ Method sinkron untuk add (fallback) ===
    def add_message(self, message: BaseMessage):
        """Fallback sinkron jika diperlukan"""
        self._messages_cache.append(message)

    # === ✅ Method async untuk clear ===
    async def aclear(self):
        await MessageRepository().delete_message(
            conn=self.conn,
            payload=MessageEntities(conversation_id=self.conversation_id)
        )
        self._messages_cache = []

    # === ✅ Method sinkron untuk clear (fallback) ===
    def clear(self):
        """Fallback sinkron jika diperlukan"""
        self._messages_cache = []

class ConversationStateRepository:
    async def set_conversation_state(
            self, 
            conn: AsyncConnection, 
            conversation_id: str, 
            state: ConversationState,
            created_by: str
        ):

        # Masukkan state baru
        try:
            insert_stmt = insert(conversation_states).values(
                conversation_id=conversation_id,
                state=state.value,
                created_by=created_by
            )
            await conn.execute(statement=insert_stmt)
            await conn.commit()
        except Exception as e:
            raise e

    async def get_latest_conversation_state(
            self, 
            conn: AsyncConnection, 
            conversation_id: str
        ) -> ConversationState | None:
        try:
            stmt = (
                select(conversation_states.c.state)
                .where(conversation_states.c.conversation_id == conversation_id)
                .order_by(desc(conversation_states.c.created_at))
            )
            result = await conn.execute(statement=stmt)
            row = result.mappings().first()
            if row:
                return ConversationState(row.state)
            return None
        except Exception as e:
            raise e