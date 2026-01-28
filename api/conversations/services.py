import re

from datetime import datetime

from api.conversations.models import conversation, message, MessageTypeEnum
from api.conversations.schemas import APIMessageParams, CreateConversationRequest, CreateMessageRequest, MessageDataResponse, TicketInformationResponse, TicketConfirmationResponse
from api.conversations.repositories import ConversationRepository, MessageRepository, InMemoryChatMessageHistory, ConversationStateRepository, ConversationState
from api.conversations.entities import ConversationEntities, MessageEntities
from api.chatbot.repositories import ChatBotRepositories

from langchain_openai import OpenAIEmbeddings, OpenAI
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser

from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import RowMapping, select, func, cast, insert, desc
from sqlalchemy.sql.operators import eq
from sqlalchemy.sql import text
from sqlalchemy.exc import ProgrammingError

NOW = datetime.now()

PARSER = PydanticOutputParser(pydantic_object=TicketInformationResponse)
TICKET_PARSER = PydanticOutputParser(pydantic_object=TicketConfirmationResponse)

class ChatBotAI:
    def __init__(
            self,
            params: APIMessageParams,
        ):
        self.params = params
        self.llm = OpenAI(temperature = 0)
        self.model = init_chat_model(
            model="gpt-4o-mini",
            stream_usage=True,
        )
        self.conversation_id = ""

    async def language_detection(self) -> str:
        prompt_template = """
You are a language detection model. Your task is to identify the language of the given text.

Identify the language of the following text and respond with the language name only (e.g., English, Spanish, French, etc.):

Text: Halo siapa nama kamu?
Answer: Indonesian

Text: Hello What is your name?
Answer: English

Text: {text}
"""
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["text"]
        )
        formatted_prompt = prompt.format(text=self.params.message)
        response = self.model.invoke(formatted_prompt)

        return response.content.strip()

    async def clean_sql(self, sql_output: str):
        sql_output = sql_output.replace("\\n", "\n").replace("\\t", "\t")
    
        # Remove common prefixes (case insensitive)
        prefixes_to_remove = [
            "answer:", "sql:", "query:", "result:", 
            "here is the sql:", "the query is:",
            "```sql", "```", "A:", "AI:", "System:"
        ]
        
        sql_lower = sql_output.lower().strip()
        for prefix in prefixes_to_remove:
            if sql_lower.startswith(prefix):
                sql_output = sql_output[len(prefix):].strip()
                sql_lower = sql_output.lower().strip()
        
        # Remove trailing markdown
        if sql_output.endswith("```"):
            sql_output = sql_output[:-3].strip()
        
        # Remove multiple newlines at start
        sql_output = sql_output.lstrip("\n").strip()
        
        # Ensure it starts with a SQL keyword
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
        if not any(sql_output.upper().startswith(kw) for kw in sql_keywords):
            # Try to find the SQL part
            for keyword in sql_keywords:
                if keyword in sql_output.upper():
                    idx = sql_output.upper().index(keyword)
                    sql_output = sql_output[idx:].strip()
                    break
        
        return sql_output

    def validate_sql_output(self, sql: str) -> bool:
        """Validasi apakah output benar-benar SQL query"""
        
        sql_upper = sql.upper().strip()
        
        # Must start with SQL keyword
        valid_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
        if not any(sql_upper.startswith(kw) for kw in valid_keywords):
            print(f"❌ Invalid SQL: doesn't start with SQL keyword")
            return False
        
        # Should not contain conversational words
        conversational_words = ["AI:", "ASSISTANT:", "JAWABAN:", "TIKET PALING MAHAL ADALAH"]
        for word in conversational_words:
            if word in sql_upper:
                print(f"❌ Invalid SQL: contains conversational text '{word}'")
                return False
        
        return True

    async def create_conversation(
            self,
            conn: AsyncConnection,
        ):
        if self.params.conversation_id == "":
            payload = CreateConversationRequest(
                title=self.params.message,
                created_by="user",
            ).transform()
            await ConversationRepository().create_conversation(conn=conn, payload=payload)
            self.conversation_id = payload.id
            created_by = payload.created_by

            #create conversation IDLE state 
            await ConversationStateRepository().set_conversation_state(
                conn=conn, 
                conversation_id=self.conversation_id,
                state=ConversationState.IDLE,
                created_by=created_by
            )

        else:
            data = await ConversationRepository().get_conversation_by_id(
                conn=conn, 
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
                await ConversationRepository().create_conversation(conn=conn, payload=payload)

                self.conversation_id = self.params.conversation_id
                created_by = payload.created_by

                #create conversation IDLE state 
                await ConversationStateRepository().set_conversation_state(
                    conn=conn, 
                    conversation_id=self.conversation_id,
                    state=ConversationState.IDLE,
                    created_by=created_by
                )

        # get current state
        current_state = await ConversationStateRepository().get_latest_conversation_state(
            conn=conn, 
            conversation_id=self.conversation_id
        )

        # create message from user
        message_payload = CreateMessageRequest(
            conversation_id=self.conversation_id,
            content=self.params.message,
            message_type=MessageTypeEnum.question,
            token_usage={},
            created_by=created_by,
            metadata={}
        ).transform()
        await MessageRepository().create_message(conn=conn, payload=message_payload)

        if current_state.value in ['idle', 'searching']:
            # proceed to search

            query_embeddings = OpenAIEmbeddings().embed_query(
                    self.params.message
                )
                
            results = await ChatBotRepositories().search_similiar_embeddings(
                conn=conn,
                message=query_embeddings
            )
            context = "\n\n".join([doc.document for doc in results])

            structured_output_prompt ="""
    You are a data extraction expert. Always output valid JSON. Extract ticket information from the user's query.

    {format_instructions}

    CRITICAL: Output ONLY valid JSON. No other text.

    EXAMPLE:
    {{"date": "2025-08-07", "origin": "Jakarta", "destination": "Bali", "amount": "150.00 USD", "ticket_type": "economy"}}
    """

            understanding_prompt = """
    Kamu adalah SQL analyst assistant. Tugasmu adalah memahami pertanyaan user dan context sebelumnya.

    TANGGAL HARI INI: {current_date}

    DATABASE SCHEMA:
    {context}

    INFORMASI TABEL:
    Table: flight_prices
    id: ID unik untuk setiap row
    flight_number: nomor penerbangan yang dikombinasikan dengan huruf. contoh GA123
    "class": tipe kelas dari penerbangan tsb
    base_price: harga sebelum dikenakan pajak
    tax: nominal besar pajak
    fee: biaya admin yang dikenakan
    currency: mata uang yang dipakai
    valid_from: waktu awal tersedia 
    valid_to: waktu akhir tersedia atau kadaluarsanya
    created_at: kapan data diubuat
    updated_at: kapan data diubah
    origin_code: kode penanda tempat pemberangkatan
    destination_code: kode penanda tempat tujuan

    Table: airports 
    code: kode 3 huruf yang menandakan suatu bandara
    name: nama bandara
    city: kota dimana bandara berada
    country: negara dimana bandara berada
    timezone: waktu setempat bandara
    created_at: data dibuat
    updated_at: data diubah

    Tugasmu:
    1. Jika user bertanya follow-up (seperti "yang paling murah?", "berapa harganya?"), identifikasi apa yang dimaksud dari percakapan sebelumnya
    2. Reformulasi pertanyaan menjadi pertanyaan lengkap yang bisa dijawab dengan SQL
    3. Output harus dalam format: "QUERY_INTENT: [penjelasan singkat apa yang harus di-query]"

    Contoh:
    User sebelumnya tanya: "Ada penerbangan Jakarta-Bali tanggal 7 Agustus?"
    User sekarang tanya: "Yang paling murah?"
    Output: "QUERY_INTENT: Cari penerbangan Jakarta-Bali tanggal 7 Agustus dengan harga paling murah"
    """

            sql_prompt = """
    Kamu adalah expert SQL generator. Generate ONLY valid PostgreSQL query.

    DATABASE SCHEMA:
    {context}

    ATURAN KRITIS:
    1. Return HANYA SQL query
    2. Mulai langsung dengan SELECT
    3. TIDAK BOLEH ada teks lain, prefix, atau penjelasan
    4. TIDAK BOLEH ada "AI:", "answer:", "jawaban:", atau apapun
    5. TIDAK BOLEH ada markdown atau code blocks

    EXAMPLES:
    Intent: Cari semua penerbangan
    Output: SELECT * FROM flight_prices;

    Intent: Cari penerbangan Jakarta-Bali tanggal 7 Agustus
    Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' AND fp.valid_from >= '2025-08-07';

    Intent: Cari penerbangan Jakarta-Bali dengan harga termurah
    Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' LIMIT 1;

    Intent: Cari penerbangan dari Jakarta ke Bali pada tanggal 6 Juli 2025 dengan harga dibawah $200.
    Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' AND fp.valid_from = '2025-07-06' AND fp.base_price + fp.tax + fp.fee < 200 LIMIT 1;
    """
            # === Prepare Template ===
            structured_output_prompt_ = ChatPromptTemplate.from_messages([
                ("system",structured_output_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human","{question}")
            ])
 
            understanding_prompt_ = ChatPromptTemplate.from_messages([
                ("system",understanding_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human","{question}")
            ])

            sql_prompt_ = ChatPromptTemplate.from_messages([
                ("system",sql_prompt),
                ("human", "Intent: {intent}\n\nGenerate SQL:")
            ])

            # === ✅ Buat instance history di luar agar bisa di-load dulu ===
            history = InMemoryChatMessageHistory(
                conn=conn, 
                conversation_id=self.conversation_id
            )
            print("Success Get History")
            
            # === Load messages ke cache sebelum invoke ===
            await history.aget_messages()
            print("Success Load Message History")

            def get_session_history(session_id: str):
                """Harus return instance yang sama"""
                return history
            
            # === Cek Informasi dari User ===
            information_chain = structured_output_prompt_ | self.model | PARSER
            
            information_chain_ = RunnableWithMessageHistory(
                information_chain,
                get_session_history=get_session_history,
                input_messages_key="question",
                history_messages_key="history",
            )
            information_chain_output = await information_chain_.ainvoke({
                "question":self.params.message,
                "format_instructions":PARSER.get_format_instructions()
            }, config={"configurable": {"session_id": self.params.conversation_id}})
            print(f"🎟 Ticket Information: {information_chain_output}")


            ### CHECK SCHEMA IF NULL
            if (information_chain_output.date == "" or information_chain_output.origin == "" or information_chain_output.destination == "" ):
                extracted_response = await self.extract_ticket_information(
                    session_history=get_session_history,
                    information=information_chain_output
                )
                await history.aadd_message(AIMessage(content=extracted_response), conversation_id=self.conversation_id)
                print(f"Response: {extracted_response}")

                #create conversation SEARCHING state 
                await ConversationStateRepository().set_conversation_state(
                    conn=conn, 
                    conversation_id=self.conversation_id,
                    state=ConversationState.SEARCHING,
                    created_by=created_by
                )

                return MessageDataResponse(
                    conversation_id=self.conversation_id,
                    content=extracted_response,
                    token_usage={},
                    created_at=datetime.now()
                )
            else:
                #create conversation SEARCHING state 
                await ConversationStateRepository().set_conversation_state(
                    conn=conn, 
                    conversation_id=self.conversation_id,
                    state=ConversationState.SELECTING,
                    created_by=created_by
                )
            

            # === Create Query Intent Sebelum Eksekusi SQL ===
            chain = understanding_prompt_ | self.llm | StrOutputParser()
            understanding_chain = RunnableWithMessageHistory(
                chain,
                get_session_history=get_session_history,
                input_messages_key="question",
                history_messages_key="history",
            )
            
            intent_output = await understanding_chain.ainvoke(
                {
                    "question": self.params.message,
                    "context": context,
                    "current_date": NOW.strftime("%Y-%m-%d")
                },
                config={"configurable": {"session_id": self.params.conversation_id}}
            )
            
            print(f"🧠 Intent: {intent_output}")
            
            # Extract intent
            if "QUERY_INTENT:" in intent_output:
                intent = intent_output.split("QUERY_INTENT:")[1].strip()
            else:
                intent = intent_output
            
            # Chain 2: Generate SQL tanpa memory (pure generation)
            print("Generating SQL...")
            sql_chain = sql_prompt_ | self.llm | StrOutputParser()
            raw_sql = await sql_chain.ainvoke({
                "intent": intent,
                "context": context
            })
            
            print(f"🔍 Raw SQL: {raw_sql}")
            
            # Clean and validate
            clean_sql = await self.clean_sql(raw_sql)
            
            if not self.validate_sql_output(clean_sql):
                raise ValueError(f"Invalid SQL generated: {raw_sql}")
            
            print(f"✅ Clean SQL: {clean_sql}")

            try:
                # Execute SQL query
                results = await self.execute_query(conn=conn, sql_query=clean_sql)
                print("Success executing SQL")

                # # Language Detection
                # language = await self.language_detection()
                # print("Success collect Language")

                # Report Agent
                report = await self.report_agent(question=self.params.message, result_query=results, conn=conn)
                print(f"REPORT: {report}")
                return report
            
            except ProgrammingError as e:
                await conn.rollback() 
                print("---------ERROR---------")
                str_error = str(e)

                prompt_template = """
    Kamu adalah data analyst yang ahli yang dimana kamu bekerja untuk suatu pelayanan penerbangan. Kamu akan diberikan suatu error log dan pertanyaan dari user.
    Berikan informasi kepada user mengapa kesalahan dapat terjadi. Bisa jadi user bertanya diluar batas pengetahuanmu.

    contoh:
    question: siapa presiden singapura
    answer: maaf kami tidak mengetahui jawaban mengenai permintaan anda. silahkan bertanya seputar tiket dan penerbangan yang kamu mau tahu ya.

    INSTRUKSI:
    1. JAWAB pertanyaan user secara LANGSUNG. Kamu boleh memodifikasi jawaban dengan lebih natural dan enak dibaca oleh user

    question: {question}
    error message: {error_message}
                """

                prompt = PromptTemplate(
                    template=prompt_template,
                    input_variables=["question", "error_message"]
                )
                formatted_prompt = prompt.format(question=self.params.message, error_message=str_error)
                report = self.model.invoke(formatted_prompt)
                
                message_payload = CreateMessageRequest(
                    conversation_id=self.conversation_id,
                    content=report.content,
                    message_type=MessageTypeEnum.answer,
                    token_usage={},
                    created_by=created_by,
                    metadata={}

                ).transform()
                await MessageRepository().create_message(conn=conn, payload=message_payload)

                return MessageDataResponse(
                    content=report.content,
                    token_usage=report.response_metadata.get("token_usage", {}),
                    created_at=datetime.now()
                )
            
        elif current_state.value == 'selecting':
            print("NOW SELECTING TICKET!")
            
            confirming_response = await self.confirm_ticket(
                conn=conn,
            )
            print(f"CONFIRMING RESPONSE: {confirming_response}")

            extract_response = await self.extract_confirmed_ticket(confirming_response=confirming_response, conn=conn)

            if extract_response.confirmed:
                # save to booking table
                booking_payload = {
                    "ticket_id": extract_response.ticket_id,
                    "confirmed": "true",
                    "user_id": created_by,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                await conn.execute(
                    insert("bookings_test").values(booking_payload)
                )
                await conn.commit()

                #create conversation IDLE state 
                await ConversationStateRepository().set_conversation_state(
                    conn=conn, 
                    conversation_id=self.conversation_id,
                    state=ConversationState.IDLE,
                    created_by=created_by
                )

                response_text = f"Terima kasih telah memilih tiket dengan ID {extract_response.ticket_id}. Tiket Anda telah dikonfirmasi."
                message_payload = CreateMessageRequest(
                    conversation_id=self.conversation_id,
                    content=response_text,
                    message_type=MessageTypeEnum.answer,
                    token_usage={},
                    created_by=created_by,
                    metadata={}
                ).transform()
                await MessageRepository().create_message(conn=conn, payload=message_payload)

                return MessageDataResponse(
                    conversation_id=self.conversation_id,
                    content=response_text,
                    token_usage={},
                    created_at=datetime.now()
                )
            else:
                response_text = "Baik, silakan beri tahu saya jika Anda ingin mencari tiket lain atau mengubah preferensi Anda."
                message_payload = CreateMessageRequest(
                    conversation_id=self.conversation_id,
                    content=response_text,
                    message_type=MessageTypeEnum.answer,
                    token_usage={},
                    created_by=created_by,
                    metadata={}
                ).transform()
                await MessageRepository().create_message(conn=conn, payload=message_payload)

                return MessageDataResponse(
                    conversation_id=self.conversation_id,
                    content=response_text,
                    token_usage={},
                    created_at=datetime.now()
                )

    async def confirm_ticket(
            self,
            conn: AsyncConnection,
        ):

        confirming_prompt = """
Kamu adalah seorang teller penjualan tiket pesawat. Anda adalah asisten pelaporan yang ramah dan menarik yang bekerja untuk perusahaan penerbangan. 
Tugas Anda adalah mengonfirmasi apakah customer sudah memilih tiket yang sesuai atau tidak.

INSTRUKSI:
1. Gunakan data terstruktur tersebut sebagai niat dan kebutuhan pelanggan.
2. Berbicaralah seperti teller tiket pesawat yang sopan, hangat, dan membantu.
3. Jangan pernah menampilkan atau menyebutkan JSON tersebut kepada pengguna.
4. Jawaban harus pendek, jelas, dan terasa seperti percakapan langsung.
5. Berikan informasi ID penerbangan setiap kali customer telah yakin memilih penerbangannya. Ingat, ini sifat nya WAJIB!

EXAMPLE:
question: Saya sudah pilih tiket dengan ID TICKET12345, tolong proses ya
answer: Terima kasih telah memilih tiket dengan ID TICKET12345. Saya akan segera memprosesnya untuk Anda.

question: Saya belum yakin dengan tiketnya, tolong carikan lagi
answer: Tentu, saya mengerti. Bisa tolong beritahu saya apa yang ingin Anda ubah atau cari lagi?

question: Kalau begitu saya memilih tiket termurah saja
answer: Baik, tiket dengan ID TICKET67890 adalah tiket termurah yang tersedia untuk Anda. Saya akan segera memprosesnya.

question: {question}
"""
        confirming_prompt_ = ChatPromptTemplate.from_messages([
            ("system",confirming_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}")
        ])

        def get_session_history(session_id: str):
            """Harus return instance yang sama"""
            return history

        history = InMemoryChatMessageHistory(
                conn=conn, 
                conversation_id=self.conversation_id
        )
        print("Success Get History")

        confirming_chain = confirming_prompt_ | self.model | StrOutputParser()
        confirming_chain_ = RunnableWithMessageHistory(
                confirming_chain,
                get_session_history=get_session_history,
                input_messages_key="question",
                history_messages_key="history",
            )
        confirming_chain_output = await confirming_chain_.ainvoke({
                "question":self.params.message,
                # "format_instructions":TICKET_PARSER.get_format_instructions()
            }, config={"configurable": {"session_id": self.params.conversation_id}})
        print(f"🎟 Confirming Text: {confirming_chain_output}")

        await history.aadd_message(AIMessage(content=confirming_chain_output), conversation_id=self.conversation_id)
        return confirming_chain_output

    
    async def extract_confirmed_ticket(
        self,
        conn: AsyncConnection,
        confirming_response: str
    ):
        confirmed_ticket_prompt ="""
You are a data extraction expert. Always output valid JSON. Extract ticket information from the user's query. 
In this case you need to get ticket id from a reponse and put it into ticket_id key.

{format_instructions}

CRITICAL: Output ONLY valid JSON. No other text.

EXAMPLE:
response: Baik, saya akan memproses tiket dengan ID GA123 sebagai tiket termurah yang tersedia untuk Anda. Total harga tiket adalah $185. Saya akan segera melanjutkan prosesnya untuk Anda!
json: {{"ticket_id": "TICKET12345", "confirmed": "true"}}

response: Tentu, saya mengerti. Apa yang ingin Anda ubah atau cari lagi? Apakah Anda mencari pilihan harga yang berbeda, waktu penerbangan lainnya, atau kelas yang berbeda? Saya siap membantu!
json: {{"ticket_id": "", "confirmed": "false"}}
"""
        confirmed_ticket_prompt_ = ChatPromptTemplate.from_messages([
            ("system",confirmed_ticket_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{response}")
        ])

        def get_session_history(session_id: str):
            """Harus return instance yang sama"""
            return history

        history = InMemoryChatMessageHistory(
                conn=conn, 
                conversation_id=self.conversation_id
        )
        print("Success Get History")

        confirming_chain = confirmed_ticket_prompt_ | self.model | TICKET_PARSER
        confirming_chain_ = RunnableWithMessageHistory(
                confirming_chain,
                get_session_history=get_session_history,
                input_messages_key="response",
                history_messages_key="history",
            )
        confirming_chain_output = await confirming_chain_.ainvoke({
                "response":confirming_response,
                "format_instructions":TICKET_PARSER.get_format_instructions()
            }, config={"configurable": {"session_id": self.params.conversation_id}})
        print(f"🎟 EXTRACTED TICKET ID: {confirming_chain_output}")
        return confirming_chain_output

    async def execute_query(
        self,
        conn: AsyncConnection,
        sql_query: str
    ):
        try:
            # Execute paginated query
            result = await conn.execute(text(sql_query))
            return result.mappings().fetchall()
        except Exception as e:
            raise e
        
    async def extract_ticket_information(
            self,
            session_history,
            information: TicketInformationResponse
    ):
        frontline_prompt = """
Kamu adalah seorang teller penjualan tiket pesawat. 
Tugasmu adalah menyambut pelanggan, memahami kebutuhan mereka, dan menanyakan informasi yang belum lengkap dengan cara yang ramah dan alami.

Kamu akan menerima data terstruktur hasil ekstraksi dari input pengguna dalam format:

{{"date": "<string>","origin": "<string>","destination": "<string>","amount": <integer>,"ticket_type": "<string>", ""price_min": <float>, "price_max": <float>}}

Instruksi utama:

1. Gunakan data terstruktur tersebut sebagai niat dan kebutuhan pelanggan.
2. Berbicaralah seperti teller tiket pesawat yang sopan, hangat, dan membantu.
3. Jika ada informasi yang belum lengkap (tanggal, jumlah tiket, lokasi keberangkatan, tujuan, atau jenis tiket), tanyakan dengan sopan dan natural.
4. Jangan pernah menampilkan atau menyebutkan JSON tersebut kepada pengguna.
5. Jangan mengarang informasi yang tidak diberikan pengguna — lebih baik bertanya.
6. Jika semua informasi sudah lengkap, katakan bahwa kamu akan membantu mencarikan tiket terbaik.
7. Jawaban harus pendek, jelas, dan terasa seperti percakapan langsung.

Panduan bertanya:
- Jika “amount” kosong atau 0 → “Untuk berapa orang tiket yang Anda butuhkan?”
- Jika “date” kosong → “Kapan tanggal keberangkatannya?”
- Jika “origin” kosong → “Dari kota mana Anda akan berangkat?”
- Jika “destination” kosong → “Tujuan penerbangannya ke mana?”
- Jika semuanya lengkap → “Baik, saya akan bantu mencarikan tiket yang sesuai untuk Anda.”

Output kamu **hanya** berupa respon teller tersebut, bukan JSON.

Data terstruktur:
{ticket_data}
"""
        teller_prompt = ChatPromptTemplate.from_messages([
            ("system",frontline_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human","{ticket_data}")
        ])

        chain = teller_prompt | self.model | StrOutputParser()
        teller_chain = RunnableWithMessageHistory(
            chain,
            get_session_history=session_history,
            input_messages_key="question",
            history_messages_key="history",
        )

        response = await teller_chain.ainvoke({
            "ticket_data": information.json()
        }, config={"configurable": {"session_id": self.params.conversation_id}})
        return response

    async def report_agent(
            self,
            question: str,
            conn: AsyncConnection,
            result_query: list
    ):
        prompt_template = """
Kamu adalah seorang teller penjualan tiket pesawat. Anda adalah asisten pelaporan yang ramah dan menarik yang bekerja untuk perusahaan penerbangan. Tugas Anda adalah mengubah hasil mentah menjadi penjelasan yang lancar, alami, dan sedikit playful yang mendorong pengguna untuk menjelajahi lebih lanjut.

PERTANYAAN PENGGUNA:
{question}

JAWABAN MENTAH / DATA:
{result_query}

TUGAS:
1. Tulis ulang jawaban dengan nada ramah dan santai — seolah-olah Anda sedang menjelaskan kepada teman.
2. Pastikan semua angka dan fakta akurat. Jangan membuat data palsu.
3. Gunakan bahasa yang sederhana dan jelas. Tambahkan sedikit kepribadian untuk membuatnya terasa menyenangkan dan mudah didekati.
4. Jika data kosong, berikan tanggapan yang sopan dan dorong pengguna untuk mencoba bertanya hal lain.
5. Akhiri jawaban Anda dengan pertanyaan lanjutan yang ringan dan menarik untuk mendorong pengguna melanjutkan eksplorasi.
6. Jangan tambahkan prefiks seperti “\n”, “AI:”, “Answer:”, “Report:”, “\n\nSystem:”, dll. Berikan JAWABAN AKHIR LANGSUNG.

BAHASA TANGGAPAN:
- Bahasa Indonesia

OUTPUT:Kembalikan hanya tanggapan akhir, tanpa pengantar atau label.
"""

        # === ✅ Buat instance history di luar agar bisa di-load dulu ===
        history = InMemoryChatMessageHistory(
            conn=conn, 
            conversation_id=self.conversation_id
        )
        print("Success Get History")
        
        # === ✅ Load messages ke cache sebelum invoke ===
        await history.aget_messages()
        print("Success Load Message History")

        def get_session_history(session_id: str):
            """Harus return instance yang sama"""
            return history

        prompt = ChatPromptTemplate.from_messages([
            ("system",prompt_template),
            MessagesPlaceholder(variable_name="history"),
            ("human","{question}")
        ])

        chain = prompt | self.model| StrOutputParser()

        chain_with_history = RunnableWithMessageHistory(
            chain,
            get_session_history=get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )

        print(f"Generating Report...")
        response = await chain_with_history.ainvoke(
            {
                "question": question,
                "result_query": result_query,
            },
            config={"configurable": {"session_id": self.params.conversation_id}}
        )

        # Clean up response
        response = response.replace("\\n", "\n")
        response = re.sub(r'^[\n\s]*(System|AI|Assistant|Answer|Report|Response|Human):\s*', '', response, flags=re.IGNORECASE)
        response = response.lstrip("\n").lstrip()

        # 💾 Simpan response AI
        await history.aadd_message(AIMessage(content=response), conversation_id=self.conversation_id)

        return MessageDataResponse(
            conversation_id=self.conversation_id,
            content=response,
            token_usage={},
            created_at=datetime.now()
        )