from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("video_detection", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="videoanalysis",
            name="checkpoint_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="videoanalysis",
            name="checkpoint_path",
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name="videoanalysis",
            name="checkpoint_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="videoanalysis",
            name="preprocessing_config",
            field=models.JSONField(default=dict),
        ),
    ]
