from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("video_detection", "0002_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="videoanalysis",
            name="checkpoint_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
