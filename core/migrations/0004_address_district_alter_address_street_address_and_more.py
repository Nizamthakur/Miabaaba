# Generated by Django 5.1.6 on 2025-03-09 23:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_address_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='district',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='address',
            name='street_address',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='address',
            name='thana',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
