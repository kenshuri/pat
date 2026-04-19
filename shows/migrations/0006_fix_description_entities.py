from django.db import migrations


def fix_escaped_quotes(apps, schema_editor):
    """
    La migration 0005 a utilisé html.escape() avec quote=True (défaut),
    ce qui a transformé les apostrophes et guillemets en entités HTML
    inutiles dans du contenu (&#x27; et &quot;). On les restaure.
    En prod cette migration sera un no-op (0005 corrigé n'échappe plus les quotes).
    """
    Play = apps.get_model('shows', 'Play')
    for play in Play.objects.filter(description__contains='&#x27;') | \
                Play.objects.filter(description__contains='&quot;'):
        play.description = (
            play.description
            .replace('&#x27;', "'")
            .replace('&quot;', '"')
        )
        play.save(update_fields=['description'])


class Migration(migrations.Migration):

    dependencies = [
        ('shows', '0005_description_to_html'),
    ]

    operations = [
        migrations.RunPython(fix_escaped_quotes, migrations.RunPython.noop),
    ]
