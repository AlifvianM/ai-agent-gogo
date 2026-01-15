from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, EmailStr

from api.auth.helpers import hash_password
from api.auth.entities import UserEntities

timezone = ZoneInfo("Asia/Jakarta")

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    

    def transform(self) -> UserEntities:
        hashed_password = hash_password(self.password)
        return UserEntities(
            email=self.email,
            username=self.username,
            password=hashed_password,
            created_by="system",
            created_at=datetime.now(tz=timezone),
        )
    
class RegisterResponse(BaseModel):
    message: str
    data: RegisterRequest

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class TokenPayload(BaseModel):
    user_id: str
    username: str
    email: str
    # role: str
    exp: datetime

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"