"""change user id integer type to UUID

Revision ID: e5187c5074de
Revises: a9bb5a759eca
Create Date: 2026-01-11 05:49:59.212798

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from api.models.base import get_audit_columns

# revision identifiers, used by Alembic.
revision: str = 'e5187c5074de'
down_revision: Union[str, Sequence[str], None] = 'a9bb5a759eca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('users')

    # Create fresh users table with correct UUID PK
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        *get_audit_columns(),
    )


def downgrade() -> None:
    # CAUTION: MAYBE IT WILL CAUSE ERROR WHILE DOWNGRADING
    pass
