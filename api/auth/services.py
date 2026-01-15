import logging

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from api.auth.helpers import verify_password
from api.auth.repositories import UserRepository
from api.auth.exception import UserIsExist, UserNotFound, UserInvalidPassword
from api.auth.schemas import RegisterRequest, LoginResponse, LoginRequest
from api.auth.token import generate_token, generate_jwt, generate_refresh_token

class UserServices:
    def __init__(
            self, 
            conn: AsyncConnection
        ):
        self.conn = conn

    async def register(self, params: RegisterRequest):
        # Check email is exists
        user = await UserRepository().get_user_by_email(conn=self.conn, email=params.email)
        if user == None:
            logging.info(f"Add new user: {params.email}")
            payload = RegisterRequest(
                email=params.email,
                username=params.username,
                password=params.password
            ).transform()
            return await UserRepository().create_user(
                conn=self.conn,
                payload=payload
            )
        raise UserIsExist(message=f"User {params.email} already exists")
        
    async def login(
            self, 
            params: LoginRequest
        ):
        user = await UserRepository().get_user_by_email(conn=self.conn, email=params.email)
        
        if user is None:
            raise UserNotFound(message=f"{params.email} not found")
        
        check_user_password = verify_password(
            password=params.password, hashed_password=user.password
        )

        if not check_user_password:
            raise UserInvalidPassword(message="password is invalid")
        
        login = generate_jwt(
            user_id=user.id,
            email=user.email,
            username=user.username
        )
        refresh = generate_refresh_token(
            user_id=user.id, 
            email=user.email, 
            username=user.username
            # role=user.role
        )
        
        # expires_at = datetime.now() + timedelta(days=7)

        return LoginResponse(
            access_token=login,
            refresh_token=refresh,
            token_type="bearer"
        )
    