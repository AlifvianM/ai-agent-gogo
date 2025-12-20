"""create booking table v1

Revision ID: 9bebf0556cac
Revises: 55752adac47f
Create Date: 2025-12-14 12:54:09.344503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from api.models.base import get_audit_columns

# revision identifiers, used by Alembic.
revision: str = '9bebf0556cac'
down_revision: Union[str, Sequence[str], None] = '55752adac47f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bookings_test',
        sa.Column('id', sa.UUID(), primary_key=True),
        # sa.Column('user_id', sa.UUID(), nullable=False),
        # sa.Column('flight_id', sa.UUID(), nullable=False),
        # sa.Column('seat_number', sa.String(length=5), nullable=False),
        # sa.Column('status', sa.String(length=20), nullable=False),
        # sa.Column('created_at', sa.DateTime(), nullable=False),
        # sa.Column('updated_at', sa.DateTime(), nullable=False),
        # sa.ForeignKeyConstraint(
        #     name="fk_booking_user", columns=["user_id"], refcolumns=["users.id"]
        # ),
        # sa.ForeignKeyConstraint(
        #     name="fk_booking_flight", columns=["flight_id"], refcolumns=["flights.id"]
        # ),
        sa.Column('ticket_id', sa.String(length=50), nullable=False),
        sa.Column('confirmed', sa.Boolean(), nullable=False, default=False),
        sa.Column('user_id', sa.String(), nullable=False, default="Test User"),
        *get_audit_columns(),
    )
    


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("bookings_test")
