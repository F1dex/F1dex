# Generated by Django 5.1.4 on 2025-05-10 13:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bd_models", "0019_alter_ball_season"),
    ]

    operations = [
        migrations.AlterField(
            model_name="packs",
            name="rewards",
            field=models.TextField(max_length=10000),
        ),
    ]
