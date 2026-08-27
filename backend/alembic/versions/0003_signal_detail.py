"""Spider Sense 2.0: signals carry their reasoning and a suggested action.

A bare title ("UI/UX Design attendance is 65%") tells a user what happened but
not why it matters or what to do. These columns let a signal explain itself and
point at the one action worth taking, which is also what stops the tray becoming
noise: anything that cannot justify itself does not get raised.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_signal_detail"
down_revision = "0002_hot_path_indexes"
branch_labels = None
depends_on = None

COLUMNS = [
    ("explanation", sa.Text(), ""),
    ("action_label", sa.String(), ""),
    ("action_href", sa.String(), ""),
    ("source", sa.String(), ""),
]


def upgrade():
    for name, type_, default in COLUMNS:
        op.add_column("notifications",
                      sa.Column(name, type_, nullable=True, server_default=default))
    op.add_column("notifications",
                  sa.Column("severity", sa.Integer(), nullable=True, server_default="2"))
    # Existing rows predate the detectors that fill these in; a rescan repopulates
    # them, so they start empty rather than being guessed at here.
    op.create_index("ix_notifications_user_severity", "notifications",
                    ["user_id", "severity"])


def downgrade():
    op.drop_index("ix_notifications_user_severity", table_name="notifications")
    for name, _t, _d in COLUMNS:
        op.drop_column("notifications", name)
    op.drop_column("notifications", "severity")
