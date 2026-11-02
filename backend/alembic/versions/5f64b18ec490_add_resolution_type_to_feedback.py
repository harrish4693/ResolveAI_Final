"""Add resolution_type to feedback

Revision ID: 5f64b18ec490
Revises: 3044c41fba2d
Create Date: 2026-09-07 20:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f64b18ec490'
down_revision = '3044c41fba2d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add resolution_type column with default 'ai' to not break existing data
    op.add_column('feedback', sa.Column('resolution_type', sa.String(length=30), nullable=True))
    op.execute("UPDATE feedback SET resolution_type = 'ai' WHERE resolution_type IS NULL")
    
    # SQLite alter column nullable=False is tricky in pure SQL, but we're likely using PostgreSQL or SQLAlchemy handles it. Wait, the project uses SQLite!
    # SQLite does NOT support alter_column to change nullable to False easily with Alembic unless batch_alter_table is used.
    # To be safe with SQLite, we'll use batch_alter_table.
    with op.batch_alter_table('feedback') as batch_op:
        batch_op.alter_column('resolution_type', nullable=False)
        batch_op.create_unique_constraint('uix_feedback_conversation_customer', ['conversation_id', 'customer_id'])


def downgrade() -> None:
    with op.batch_alter_table('feedback') as batch_op:
        batch_op.drop_constraint('uix_feedback_conversation_customer', type_='unique')
        batch_op.drop_column('resolution_type')
