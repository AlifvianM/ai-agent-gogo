from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse

from api.auth.services import UserServices
from api.auth.schemas import RegisterRequest, RegisterResponse, LoginRequest, LoginResponse

from api.database.database import DBConnection

auth_router = APIRouter(prefix='/api/v1/auth', tags=['Authentications'])

@auth_router.post('/register')
async def register(
    request: Request,
    Response: Response,
    db: DBConnection,
    params: RegisterRequest
):
    await UserServices(conn=db).register(params=params)
    return RegisterResponse(
        message="Success register data",
        data=params
    )

@auth_router.post('/login')
async def login(
    request: Request,
    Response: Response,
    db: DBConnection,
    params: LoginRequest
):
    token = await UserServices(conn=db).login(params=params)
    return LoginResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token
    )