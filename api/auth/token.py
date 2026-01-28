import jwt

from datetime import datetime, timedelta
from uuid import UUID

from api.auth.schemas import TokenPayload
from api.config import settings

def generate_token(
    user_id: UUID, 
    email: str, 
    username: str
    # full_name: str, 
    # role: RoleEnum, 
    # token_type: TokenType = TokenType.ACCESS
) -> str:
    """
    Generate a JWT token with the given parameters.

    Args:
        user_id: The user's ID
        email: The user's email
        username: The user's username
        role: The user's role
        token_type: The type of token to generate (access or refresh)

    Returns:
        The generated JWT token
    """
    # # Set expiration based on token type
    # expiration = datetime.now() + timedelta(
    #     days=7 if token_type == TokenType.REFRESH else 1
    # )

    expiration = datetime.now() + timedelta(days=7)

    # Create token payload
    payload = TokenPayload(
        user_id=str(user_id),
        username=username,
        email=email,
        # role=role,
        exp=expiration
    )

    # Encode and return the token
    token = jwt.encode(payload.model_dump(exclude_none=True), settings.SECRET_KEY, algorithm="HS256")
    return token

def generate_jwt(
        user_id: UUID, 
        email: str, 
        username: str, 
        # role: RoleEnum
    ) -> str:
    return generate_token(
        user_id, 
        email, 
        username
    )

def generate_refresh_token(
        user_id: UUID, 
        email: str, 
        username: str
    ):
    return generate_token(
        user_id, 
        email, 
        username
    )


def decode_jwt(token: str) -> TokenPayload:
    decode_token = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return TokenPayload(**decode_token, refresh_token=token)