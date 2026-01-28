from datetime import datetime
from uuid import UUID

from typing import Optional
from pydantic import BaseModel, Field

from api.conversations.entities import ConversationEntities
from api.conversations.helpers import generate_uuid, generate_time_now
from api.conversations.models import MessageTypeEnum
from api.conversations.entities import MessageEntities, BookingEntities


class APIMessageParams(BaseModel):
    """
    Request query params with api key and message
    """
    
    message: str
    conversation_id: Optional[str] = ""
    

class CreateConversationRequest(BaseModel):
    title: str
    created_by: str

    def transform(self):
        return ConversationEntities(
            id=generate_uuid(),
            title=self.title,
            created_by=self.created_by,
        )
    
class CreateMessageRequest(BaseModel):
    conversation_id: UUID
    content: str | None = None
    message_type: MessageTypeEnum
    token_usage: dict
    created_by: str
    metadata: dict | None = None

    def transform(self):
        return MessageEntities(
            id=generate_uuid(),
            conversation_id=self.conversation_id,
            content=self.content,
            message_type=self.message_type,
            token_usage=self.token_usage,
            created_by=self.created_by,
            metadata=self.metadata,
            created_at=generate_time_now()
        )
    
class MessageDataResponse(BaseModel):
    """
    Response model for getting the list with pagination
    """
    conversation_id: UUID
    content: str
    metadata: dict | None = None
    token_usage: dict | None = None
    created_at: datetime
    
class ChatModelResponse(BaseModel):
    resp: MessageDataResponse

class ChatModelErrorResponse(BaseModel):
    message: str

class TicketInformationResponse(BaseModel):
    """Simplified schema tanpa alias"""
    date: str = Field("", description="Date of the trip in YYYY-MM-DD format")
    origin: str = Field("", description="Departure location")  # ✅ Changed from 'from_'
    destination: str = Field("", description="Destination location")
    amount: int = Field(description="Amount paid for the ticket", default=1)
    ticket_type: str = Field(description="Type of the ticket, e.g., business, economy", default="all")
    price_min: float = Field(description="Minimum price of the ticket", default=0.0)
    price_max: float = Field(description="Maximum price of the ticket", default=0.0)

class TicketConfirmationResponse(BaseModel):
    """Schema for ticket confirmation response"""
    ticket_id: str = Field("", description="Unique identifier for the ticket")
    confirmed: bool = Field(False, description="Indicates if the ticket is confirmed")

class BookingRequest(BaseModel):
    ticket_id: UUID
    confirmed: bool = False
    user_id: str
    created_by: str
    created_at: datetime | None = None

    def transform(self):
        return BookingEntities(
            id=generate_uuid(),
            ticket_id=str(self.ticket_id),
            confirmed=False,
            user_id=self.user_id,
            created_by=self.created_by,
            created_at=generate_time_now()
        )