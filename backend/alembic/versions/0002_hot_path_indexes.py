"""Hot-path indexes and uniqueness constraints.

Why this is separate from the baseline: a database created by the pre-Alembic
bootstrap already has every table and column, so `prestart` stamps it at 0001
rather than re-running the creates — but it does *not* have these indexes. This
revision adds them.

Every statement is `IF NOT EXISTS`, so it is a no-op on a fresh database where
0001 already created them, and it actually does the work on an existing one.
That makes the revision safe to run in either order and safe to re-run.

The unique indexes encode real invariants that were previously enforced only in
application code:
  - a habit is logged at most once per day
  - a goal links to a given row at most once
  - a Spider Sense dedupe_key identifies at most one signal per user
  - a user has at most one row per integration provider and one budget per category
"""
from alembic import op

revision = "0002_hot_path_indexes"
down_revision = "8f892c67f481"
branch_labels = None
depends_on = None

# (index name, table, columns, unique)
INDEXES = [
    ("ix_tasks_user_status",          "tasks",                 "user_id, status",              False),
    ("ix_tasks_user_due",             "tasks",                 "user_id, due_at",              False),
    ("ix_tasks_assignment",           "tasks",                 "assignment_id",                False),
    ("ix_tasks_project_task",         "tasks",                 "project_task_id",              False),
    ("ix_tasks_topic",                "tasks",                 "topic_id",                     False),
    ("ix_tasks_application",          "tasks",                 "application_id",               False),
    ("ix_habit_logs_unique_day",      "habit_logs",            "habit_id, on_date",            True),
    ("ix_habit_logs_user_date",       "habit_logs",            "user_id, on_date",             False),
    ("ix_goal_links_unique",          "goal_links",            "goal_id, ref_type, ref_id",    True),
    ("ix_notifications_user_dedupe",  "notifications",         "user_id, dedupe_key",          True),
    ("ix_notifications_user_active",  "notifications",         "user_id, acknowledged, resolved", False),
    ("ix_integrations_user_provider", "integrations",          "user_id, provider",            True),
    ("ix_jocasta_user_created",       "jocasta_conversations", "user_id, created_at",          False),
    ("ix_assignments_user_status_due","assignments",           "user_id, status, due_at",      False),
    ("ix_classes_user_day",           "classes",               "user_id, day_of_week",         False),
    ("ix_exams_user_date",            "exams",                 "user_id, date",                False),
    ("ix_events_user_type_date",      "academic_events",       "user_id, type, date",          False),
    ("ix_finance_user_date",          "finance_entries",       "user_id, date",                False),
    ("ix_budgets_user_category",      "budgets",               "user_id, category",            True),
    ("ix_memories_user_created",      "memories",              "user_id, created_at",          False),
    ("ix_sessions_user_started",      "learning_sessions",     "user_id, started_at",          False),
]


def upgrade():
    for name, table, cols, unique in INDEXES:
        kind = "UNIQUE INDEX" if unique else "INDEX"
        op.execute(f'CREATE {kind} IF NOT EXISTS {name} ON {table} ({cols})')


def downgrade():
    for name, _table, _cols, _unique in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
