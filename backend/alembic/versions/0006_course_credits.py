"""Course credits.

Additive only: one nullable-with-default integer column. Existing rows get 0,
which the UI reads as "not recorded" and simply doesn't display — no course
loses information and nothing needs backfilling.

Revision ID: 0006_course_credits
Revises: 0005_course_workspace
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_course_credits"
down_revision = "0005_course_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("credits", sa.Integer(), server_default="0",
                                       nullable=False))


def downgrade() -> None:
    op.drop_column("courses", "credits")
