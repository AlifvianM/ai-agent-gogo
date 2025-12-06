"""create conversations with state

Revision ID: 55752adac47f
Revises: a8f49162d4d7
Create Date: 2025-12-03 23:27:33.974880

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from api.models.base import get_audit_columns


# revision identifiers, used by Alembic.
revision: str = '55752adac47f'
down_revision: Union[str, Sequence[str], None] = 'a8f49162d4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('conversation_states',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        *get_audit_columns(),
        sa.ForeignKeyConstraint(
            name="fk_state_conversation", columns=["conversation_id"], refcolumns=["conversations.id"]
        )
    )
    op.create_index(
        'ix_conversation_states_conversation_id',
        'conversation_states',
        ['conversation_id', 'state'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("conversation_states")
