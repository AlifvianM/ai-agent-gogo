from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

# from api.chatbot.views import chat_router
from api.flights.views import flights_router
from api.conversations.views import conversation_router
from api.auth.views import auth_router
# from api.auth.dependencies import get_current_user

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, limit this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(chat_router)
app.include_router(flights_router)
app.include_router(conversation_router)
app.include_router(auth_router)

@app.get("/health")
def health_check():
    return "Health Chek is success"