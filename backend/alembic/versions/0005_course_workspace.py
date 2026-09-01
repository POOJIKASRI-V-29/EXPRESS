"""Course workspace: counted attendance, modules, topics, Drive link.

Attendance moves from a typed percentage to a counted pair. Existing rows are
backfilled as attended = <old percent>, total = 100, which preserves every
course's displayed percentage exactly while giving the counters a truthful
starting point the user can correct.

The old `attendance` column is kept and maintained as a cached percent (the
same pattern `habits.streak` uses) rather than dropped — dropping it would be
a destructive change for no benefit.
"""
from alembic import op
import sqlalchemy as sa

import app.core.database

revision = "0005_course_workspace"
down_revision = "0004_integration_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courses", sa.Column("attended_classes", sa.Integer(),
                                       nullable=True, server_default="0"))
    op.add_column("courses", sa.Column("total_classes", sa.Integer(),
                                       nullable=True, server_default="0"))
    op.add_column("courses", sa.Column("drive_url", sa.String(),
                                       nullable=True, server_default=""))

    # Backfill so no course loses its percentage: 82% becomes 82/100.
    op.execute("""
        UPDATE courses
           SET attended_classes = COALESCE(attendance, 0),
               total_classes    = 100
         WHERE COALESCE(total_classes, 0) = 0
    """)

    op.create_table(
        "course_modules",
        sa.Column("id", app.core.database.GUID(), nullable=False),
        sa.Column("user_id", app.core.database.GUID(), nullable=False),
        sa.Column("course_id", app.core.database.GUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("module_order", sa.Integer(), nullable=True),
        sa.Column("created_at", app.core.database.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.core.database.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_modules_course_id", "course_modules", ["course_id"])
    op.create_index("ix_course_modules_user_id", "course_modules", ["user_id"])
    op.create_index("ix_course_modules_course_order", "course_modules",
                    ["course_id", "module_order"])

    op.create_table(
        "course_topics",
        sa.Column("id", app.core.database.GUID(), nullable=False),
        sa.Column("user_id", app.core.database.GUID(), nullable=False),
        sa.Column("module_id", app.core.database.GUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("topic_order", sa.Integer(), nullable=True),
        sa.Column("completed_at", app.core.database.UTCDateTime(), nullable=True),
        sa.Column("created_at", app.core.database.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.core.database.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["course_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_topics_module_id", "course_topics", ["module_id"])
    op.create_index("ix_course_topics_user_id", "course_topics", ["user_id"])
    op.create_index("ix_course_topics_module_order", "course_topics",
                    ["module_id", "topic_order"])


def downgrade():
    op.drop_table("course_topics")
    op.drop_table("course_modules")
    op.drop_column("courses", "drive_url")
    op.drop_column("courses", "total_classes")
    op.drop_column("courses", "attended_classes")
