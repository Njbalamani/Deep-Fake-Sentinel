from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("image_detection", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="imageanalysis",
            name="checkpoint_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="imageanalysis",
            name="checkpoint_path",
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name="imageanalysis",
            name="checkpoint_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="imageanalysis",
            name="preprocessing_config",
            field=models.JSONField(default=dict),
        ),
    ]
