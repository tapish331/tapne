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


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0006_trip_access_type_trip_draft_form_data_and_more"),
    ]

    operations = [
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
        migrations.RunPython(backfill_trip_status, reverse_backfill),
    ]
