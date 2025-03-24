# Generated by Django 5.1.6 on 2025-03-24 12:32

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_offer_contact_details_offer_contact_email_and_more'),
        ('moderation', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='moderation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers', to='moderation.moderationresult'),
        ),
        migrations.AlterField(
            model_name='offer',
            name='show_author_mail',
            field=models.BooleanField(default=False),
        ),
    ]
