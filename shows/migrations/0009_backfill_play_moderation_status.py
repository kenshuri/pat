from django.db import migrations


def set_existing_plays_published(apps, schema_editor):
    Play = apps.get_model('shows', 'Play')
    Play.objects.filter(moderation_status='pending').update(moderation_status='published')


class Migration(migrations.Migration):

    dependencies = [
        ('shows', '0008_add_play_moderation'),
    ]

    operations = [
        migrations.RunPython(
            set_existing_plays_published,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
