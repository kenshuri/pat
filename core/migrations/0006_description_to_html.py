import html
import re

from django.db import migrations


def plain_text_to_html(apps, schema_editor):
    Offer = apps.get_model('core', 'Offer')
    for offer in Offer.objects.exclude(description='').exclude(description__isnull=True):
        text = offer.description
        # Skip descriptions that already look like HTML
        if re.search(r'<(p|div|br\s*/?>)', text, re.IGNORECASE):
            continue
        # Escape entities, normalize line endings
        text = html.escape(text)
        text = re.sub(r'\r\n|\r', '\n', text)
        # Each paragraph (separated by blank lines) becomes a <div>
        paragraphs = re.split(r'\n\n+', text)
        parts = []
        for para in paragraphs:
            para = para.strip()
            if para:
                parts.append('<div>' + para.replace('\n', '<br>') + '</div>')
        offer.description = '\n'.join(parts) if parts else ''
        offer.save(update_fields=['description'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_offer_cover_image_offerphoto'),
    ]

    operations = [
        migrations.RunPython(plain_text_to_html, migrations.RunPython.noop),
    ]
