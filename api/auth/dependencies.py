import jwt
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import RowMapping

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param

from api.auth.token import decode_jwt
from api.auth.repositories import UserRepository
from api.config import settings
from api.database.database import get_connection, DBConnection
from api.auth.exception import InvalidAuthentication, TokenExpired
from api.auth.schemas import TokenPayload

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/api/v1/auth/login")
oauth2_scheme = HTTPBearer()


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DBConnection) -> RowMapping:
    try:
        payload = decode_jwt(token)
        print("Payload:", payload)
        user = await UserRepository().get_user_by_email(
            conn=db,
            email=payload.email
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
class Auth(HTTPBearer):
    def __init__(self):
        super().__init__()

    async def __call__(
            self, 
            request: Request, 
            response: Response = None,
            db: AsyncConnection = Depends(get_connection)
        ):
        authorization = request.headers.get("Authorization")
        
        scheme, credentials = get_authorization_scheme_param(authorization)
        if not (scheme and credentials):
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            token = decode_jwt(credentials)
            request.state.email = token.email
            user = await UserRepository().get_user_by_email(
                conn=db,
                email=token.email
            )
            if user is None:
                raise HTTPException(
                    status_code=401,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user
        except jwt.ExpiredSignatureError:
            response.status_code = 401
            return {
                "message": "Invalid authentication credentials"
            }
        # except jwt.InvalidTokenError:
        #     raise TokenInvalid(message="Invalid token")

        # return token

AnyAuthenticatedUser = Annotated[TokenPayload, Depends(Auth())]