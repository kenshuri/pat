import html
import re

from django.db import migrations


def plain_text_to_html(apps, schema_editor):
    Play = apps.get_model('shows', 'Play')
    for play in Play.objects.exclude(description='').exclude(description__isnull=True):
        text = play.description
        if re.search(r'<(p|div|br[\s/]|br>)', text, re.IGNORECASE):
            continue
        # quote=False : on n'échappe que &, < et > — pas les apostrophes ni guillemets
        text = html.escape(text, quote=False)
        text = re.sub(r'\r\n|\r', '\n', text)
        paragraphs = re.split(r'\n\n+', text)
        parts = []
        for para in paragraphs:
            para = para.strip()
            if para:
                parts.append('<div>' + para.replace('\n', '<br>') + '</div>')
        play.description = '\n'.join(parts) if parts else ''
        play.save(update_fields=['description'])


class Migration(migrations.Migration):

    dependencies = [
        ('shows', '0004_add_cover_image_and_playphoto'),
    ]

    operations = [
        migrations.RunPython(plain_text_to_html, migrations.RunPython.noop),
    ]
