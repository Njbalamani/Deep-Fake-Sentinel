from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audio_detection", "0003_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="audioanalysis",
            name="checkpoint_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
