from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("enrollment", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="enrollmentrequest",
            name="message",
            field=models.TextField(
                blank=True,
                help_text="Optional member note shown to the host in hosting inbox.",
            ),
        ),
    ]
