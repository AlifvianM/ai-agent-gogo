from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse

from api.conversations.services import ChatBotAI
# from api.conversations.services_v2 import ChatBotAI as ChatBotAIV2
from api.conversations.services_v2 import FlightSearchAgent as ChatBotAIV2
from api.conversations.schemas import APIMessageParams, ChatModelResponse, ChatModelErrorResponse
from api.database.database import DBConnection
from api.auth.dependencies import AnyAuthenticatedUser

conversation_router = APIRouter(prefix='/api/v1/conversations', tags=["Conversations"])

@conversation_router.post("/")
async def chat_v2(
    request: Request,
    response:Response,
    db: DBConnection,
    params: APIMessageParams
):
    try:
        chat = await ChatBotAI(params=params).create_conversation(conn=db)
        return ChatModelResponse(resp=chat)
    except HTTPException as ex:
        response.status_code = ex.status_code
        return ChatModelErrorResponse(
            message=ex.detail
        )
    except Exception as ex:
        response.status_code = 500
        return ChatModelErrorResponse(
            message=str("Failed asking the model.\n" + str(ex))
        )
    
@conversation_router.post("/v2")
async def chat_v2(
    request: Request,
    response:Response,
    db: DBConnection,
    token: AnyAuthenticatedUser,
    params: APIMessageParams
):
    bot = await ChatBotAIV2(conn=db, params=params).build()
    try:
        result = await bot.run()
    except HTTPException as ex:
        response.status_code = ex.status_code
        return ChatModelErrorResponse(
            message=ex.detail
        )
    except Exception as ex:
        response.status_code = 500
        return ChatModelErrorResponse(
            message=str("Failed asking the model.\n" + str(ex))
        )
    return ChatModelResponse(resp=result)