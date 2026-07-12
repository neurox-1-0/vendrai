"""baseline

Revision ID: fa2f4a40b692
Revises: 
Create Date: 2026-07-12 15:05:42.850171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa2f4a40b692'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import os

def upgrade() -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "../../../../db/schema.sql")
    with open(schema_path, "r") as f:
        sql = f.read()
    op.execute(sql)

def downgrade() -> None:
    pass

