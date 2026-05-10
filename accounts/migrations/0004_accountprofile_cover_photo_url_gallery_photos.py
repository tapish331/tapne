from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_accountprofile_avatar_url_accountprofile_travel_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="cover_photo_url",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="gallery_photos",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
