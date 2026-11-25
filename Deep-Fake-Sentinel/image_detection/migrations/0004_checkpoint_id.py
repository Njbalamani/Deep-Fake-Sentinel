from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("image_detection", "0003_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="imageanalysis",
            name="checkpoint_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
