from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_accountprofile_cover_photo_url_gallery_photos"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="instagram_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
