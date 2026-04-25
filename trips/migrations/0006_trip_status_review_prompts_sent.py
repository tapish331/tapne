from django.db import migrations, models
from django.utils import timezone


def backfill_trip_status(apps, schema_editor):
    Trip = apps.get_model("trips", "Trip")
    now = timezone.now()

    # Drafts: is_published=False
    Trip.objects.filter(is_published=False).update(status="draft")

    # Completed: is_published=True AND starts_at < now (ongoing + past both qualify)
    Trip.objects.filter(is_published=True, starts_at__lt=now).update(status="completed")

    # Published: is_published=True AND starts_at >= now
    Trip.objects.filter(is_published=True, starts_at__gte=now).update(status="published")


def reverse_backfill(apps, schema_editor):
    # Nothing to unwind — is_published was left in place.
    pass


def _add_status_columns_idempotent(apps, schema_editor):
    """Apply the status/review_prompts_sent columns only if they don't already exist.

    This migration is a parallel branch to 0007_trip_status_review_prompts_sent
    (which sits in the 0006_trip_access_type branch).  On a fresh database both
    branches are applied in sequence; without this guard the second to run would
    fail with "column already exists" / "index already exists".
    """
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        cols = {col.name for col in schema_editor.connection.introspection.get_table_description(cursor, "trips_trip")}

    if "status" not in cols:
        if vendor == "sqlite":
            schema_editor.execute(
                "ALTER TABLE trips_trip ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'published'"
            )
        else:
            schema_editor.execute(
                "ALTER TABLE trips_trip ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'published'"
            )

    if "review_prompts_sent" not in cols:
        if vendor == "sqlite":
            schema_editor.execute(
                "ALTER TABLE trips_trip ADD COLUMN review_prompts_sent BOOLEAN NOT NULL DEFAULT 0"
            )
        else:
            schema_editor.execute(
                "ALTER TABLE trips_trip ADD COLUMN IF NOT EXISTS review_prompts_sent BOOLEAN NOT NULL DEFAULT FALSE"
            )

    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS trip_status_start_idx ON trips_trip (status, starts_at)"
    )

    backfill_trip_status(apps, schema_editor)


def _remove_status_columns(apps, schema_editor):
    # Intentional no-op reverse: the merge migration and its sibling branch own
    # the reverse path; removing columns here would be destructive and is not
    # needed for the test-suite rollback case.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0005_trip_general_policies_and_contact_preference_multi"),
    ]

    operations = [
        # SeparateDatabaseAndState lets Django track the full field/index state
        # (state_operations) while the actual DDL (database_operations) uses
        # IF NOT EXISTS guards so this migration is safe regardless of whether
        # the parallel 0007_trip_status_review_prompts_sent branch ran first.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="trip",
                    name="status",
                    field=models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("published", "Published"),
                            ("completed", "Completed"),
                        ],
                        db_index=True,
                        default="published",
                        max_length=16,
                    ),
                ),
                migrations.AddField(
                    model_name="trip",
                    name="review_prompts_sent",
                    field=models.BooleanField(db_index=True, default=False),
                ),
                migrations.AddIndex(
                    model_name="trip",
                    index=models.Index(fields=["status", "starts_at"], name="trip_status_start_idx"),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_status_columns_idempotent, _remove_status_columns),
            ],
        ),
    ]
