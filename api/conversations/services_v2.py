from datetime import datetime
from sqlalchemy.engine.row import RowMapping

from api.database.database import DBConnection
from api.conversations.models import conversation, message, MessageTypeEnum
from api.conversations.schemas import APIMessageParams, CreateConversationRequest, CreateMessageRequest, MessageDataResponse, TicketInformationResponse, TicketConfirmationResponse
from api.conversations.repositories import ConversationRepository, MessageRepository, InMemoryChatMessageHistory, ConversationStateRepository, ConversationState
from api.conversations.entities import ConversationEntities, MessageEntities
from api.conversations.tools.tools import create_rag_tool, generate_sql_tool, create_sql_executor, create_bookings
from api.chatbot.repositories import ChatBotRepositories


from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.messages import AIMessage


SYSTEM_PROMPT = """"
Kamu adalah Flight Search Agent.

Tugasmu:
1. Mengerti pertanyaan user tentang penerbangan.
2. Jika butuh konteks → panggil tool rag_tool.
3. Jika butuh SQL → panggil tool generate_sql.
4. Eksekusi SQL → panggil tool execute_sql.
5. Jika user ingin memesan atau mengonfirmasi tiket yang telah dipilih → panggil tool create_booking.
6. Berikan jawaban akhir dengan bahasa Indonesia yang jelas dan ramah.

Aturan Penting:
- JANGAN generate SQL secara manual di sistem prompt.
- Berikan juga ID tiket ketika akan menampilkan informasi tiket.
Gunakan tools.
"""

class FlightSearchAgent:

    def __init__(self, conn: DBConnection, params: APIMessageParams, user: RowMapping):
        self.conn = conn
        self.model = init_chat_model(
            model="gpt-4o-mini",
            temperature=0,
            stream_usage=True
        )
        self.user = user

        # agent + executor akan di-set saat build()
        self.agent = None
        self.executor = None

        self.params = params
        self.conversation_id = ""

    async def build(self):
        tools = [
            create_rag_tool(self.conn),
            generate_sql_tool(self.model),
            create_sql_executor(self.conn),
            create_bookings(self.conn, self.user)
        ]

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("history"),         # <--- history injected later
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        self.agent = create_openai_functions_agent(
            llm=self.model,
            tools=tools,
            prompt=prompt
        )

        self.executor = AgentExecutor(
            agent=self.agent,
            tools=tools,
            verbose=True
        )
        return self

    async def run(self):
        """
        Run flight search agent with a given user message.
        """
        if self.params.conversation_id == "":
            payload = CreateConversationRequest(
                title=self.params.message,
                created_by=self.user.get("username", "anonymous"),
            ).transform()
            await ConversationRepository().create_conversation(conn=self.conn, payload=payload)
            self.conversation_id = payload.id
            created_by = payload.created_by

        else:
            data = await ConversationRepository().get_conversation_by_id(
                conn=self.conn, 
                payload=ConversationEntities(id=self.params.conversation_id)
            )
            if data.get("id", None):
                # get conversation_id and created_by
                self.conversation_id = self.params.conversation_id
                created_by = data.get("created_by", "")
            else:
                # create new conversation_id when conversation_id is not exists
                payload = CreateConversationRequest(
                    title=self.params.message,
                    created_by=created_by
                ).transform()
                await ConversationRepository().create_conversation(conn=self.conn, payload=payload)

                self.conversation_id = self.params.conversation_id
                created_by = payload.created_by

        # create message from user
        message_payload = CreateMessageRequest(
            conversation_id=self.conversation_id,
            content=self.params.message,
            message_type=MessageTypeEnum.question,
            token_usage={},
            created_by=created_by,
            metadata={}
        ).transform()
        await MessageRepository().create_message(conn=self.conn, payload=message_payload)

        if not self.executor:
            raise RuntimeError("Agent has not been built. Call build() first.")

        # 1. Load memory from DB
        history = InMemoryChatMessageHistory(
            conn=self.conn,
            conversation_id=self.conversation_id
        )
        await history.aget_messages()

        # 2. Function that returns SAME history instance
        def get_session_history(session_id: str):
            return history

        # 3. Wrap executor with memory dynamically — per request
        executor_with_memory = RunnableWithMessageHistory(
            self.executor,
            get_session_history=get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )

        # 4. Run agent
        response = await executor_with_memory.ainvoke(
            {"input": self.params.message},
            config={"configurable": {"session_id": self.conversation_id}},
        )

        # 5. Save AI message
        await history.aadd_message(
            AIMessage(content=response["output"]),
            conversation_id=self.conversation_id
        )

        return MessageDataResponse(
            conversation_id=self.conversation_id,
            content=response.get("output", ""),
            token_usage={},
            created_at=datetime.now()
        )