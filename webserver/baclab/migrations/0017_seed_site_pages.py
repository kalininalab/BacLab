from django.conf import settings
from django.db import migrations


TERMS_SECTIONS = [
    {
        'heading': 'How We Use Your Data',
        'body': '<p>We use the data that we collect to provide you results of your selected tool.</p>',
    },
    {
        'heading': 'What We Do With It',
        'body': (
            '<p>In particular, we use data to:</p>'
            '<ul><li>Process your selected tool against your selection database '
            '(could be remote or local)</li></ul>'
        ),
    },
    {
        'heading': 'Data Retention',
        'body': '<p>Your data will be deleted from our servers periodically.</p>',
    },
]


def seed_site_pages(apps, schema_editor):
    SitePage = apps.get_model('baclab', 'SitePage')
    PageSection = apps.get_model('baclab', 'PageSection')

    terms_page, _ = SitePage.objects.get_or_create(
        page_key='terms', defaults={'title': 'Terms and Conditions'}
    )
    for order, section in enumerate(TERMS_SECTIONS):
        PageSection.objects.get_or_create(
            page=terms_page, order=order,
            defaults={'heading': section['heading'], 'body': section['body']},
        )

    admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@example.com')
    contact_page, _ = SitePage.objects.get_or_create(
        page_key='contact', defaults={'title': 'Contact Us'}
    )
    PageSection.objects.get_or_create(
        page=contact_page, order=0,
        defaults={
            'heading': '',
            'body': (
                '<p>If you have questions or feedback about microservices, you can '
                f'contact us via: <a href="mailto:{admin_email}">{admin_email}</a></p>'
            ),
        },
    )


def remove_site_pages(apps, schema_editor):
    SitePage = apps.get_model('baclab', 'SitePage')
    SitePage.objects.filter(page_key__in=['terms', 'contact']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('baclab', '0016_sitepage_pagesection'),
    ]

    operations = [
        migrations.RunPython(seed_site_pages, remove_site_pages),
    ]
