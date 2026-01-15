import json
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.tools import StructuredTool
from pydantic import BaseModel

from sqlalchemy import text

from api.chatbot.repositories import ChatBotRepositories


class RAGInput(BaseModel):
    question: str

class SQLGenInput(BaseModel):
    question: str
    context: str

class SQLExecInput(BaseModel):
    sql_query: str


def create_rag_tool(conn):

    async def rag_func(question: str) -> str:
        embeddings = OpenAIEmbeddings().embed_query(question)
        docs = await ChatBotRepositories().search_similiar_embeddings(conn, embeddings)
        if not docs:
            return ""
        return "\n\n".join([doc.document for doc in docs])

    return StructuredTool.from_function(
        name="rag_search",
        description="Retrieve relevant context for flight-related questions.",
        func=rag_func,
        coroutine=rag_func,
        args_schema=RAGInput
    )

def generate_sql_tool(llm):
    
    def generate_sql(question: str, context: str) -> str:
        prompt = f"""
Kamu adalah ahli SQL untuk database penerbangan.

Gunakan context berikut (jika relevance):
{context}

Berdasarkan pertanyaan berikut:
"{question}"

Berikut informasi tentang database dan tabel yang tersedia:
Database schema:
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

ATURAN PENTING:
1. Return HANYA SQL query
2. Mulai langsung dengan SELECT
3. TIDAK BOLEH ada teks lain, prefix, atau penjelasan
4. TIDAK BOLEH ada "AI:", "answer:", "jawaban:", atau apapun
5. TIDAK BOLEH ada markdown atau code blocks

EXAMPLES:
Question: Cari semua penerbangan
Output: SELECT * FROM flight_prices;

Question: Cari penerbangan Jakarta-Bali tanggal 7 Agustus
Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' AND fp.valid_from >= '2025-08-07';

Question: Cari penerbangan Jakarta-Bali dengan harga termurah
Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' LIMIT 1;

Question: Cari penerbangan dari Jakarta ke Bali pada tanggal 6 Juli 2025 dengan harga dibawah $200.
Output: SELECT fp.* FROM flight_prices fp LEFT JOIN airports a1 ON fp.origin_code = a1.code LEFT JOIN airports a2 ON fp.destination_code = a2.code WHERE a1.city = 'Jakarta' AND a2.city = 'Denpasar' AND fp.valid_from = '2025-07-06' AND fp.base_price + fp.tax + fp.fee < 200 LIMIT 1;            
"""
        sql = llm.invoke(prompt).content.strip()
        return sql.replace("```sql", "").replace("```", "").strip()

    return StructuredTool.from_function(
        name="generate_sql",
        description="Generate SQL query based on natural language and RAG context.",
        func=generate_sql
    )

def create_sql_executor(conn):

    async def execute(sql_query: str) -> str:
        print("DEBUG - Executing SQL:", sql_query)
        try:
            result = await conn.execute(text(sql_query))
            # rows = [dict(r) for r in result.mappings().all()]
            # return json.dumps({"status": "success", "count": len(rows), "data": rows})

            rows = result.mappings().fetchall()
            
            return rows

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    return StructuredTool.from_function(
        name="execute_sql",
        description="Execute SQL query and return JSON",
        func=execute,
        coroutine=execute,
        args_schema=SQLExecInput
    )