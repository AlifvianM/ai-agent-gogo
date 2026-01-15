"""change user column name

Revision ID: a9bb5a759eca
Revises: cf770f0b94ee
Create Date: 2026-01-11 05:40:25.740810

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9bb5a759eca'
down_revision: Union[str, Sequence[str], None] = 'cf770f0b94ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('name', new_column_name='username')
        batch_op.alter_column('hashed_password', new_column_name='password')
    


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('username', new_column_name='name')
        batch_op.alter_column('password', new_column_name='hashed_password')
    