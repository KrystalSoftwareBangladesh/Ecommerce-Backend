# cms_api/tests/factories.py
"""
Small builders for the CMS test suite.

Deliberately thin (blog_api/tests/factories.py pattern): they call
``Model.objects.create(...)`` directly and only exist so a test can
say what it cares about.
"""
import uuid

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from wagtail.models import Page, ReferenceIndex

from user_api.models import User

from cms_api.models import CmsPage, CmsPageSection, CmsSection


def user(username, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='test-pass-123',
        **kwargs,
    )


def superuser(username='cms-admin'):
    return User.objects.create_superuser(
        username=username,
        email=f'{username}@example.com',
        password='test-pass-123',
    )


def grant(target, model, *codenames):
    """
    Give a user the named permissions on `model` and return a freshly
    loaded user so Django's permission cache is not stale.
    """
    content_type = ContentType.objects.get_for_model(model)

    for codename in codenames:
        target.user_permissions.add(
            Permission.objects.get(
                content_type=content_type,
                codename=codename,
            )
        )

    return User.objects.get(pk=target.pk)


def hero_content(heading='Welcome'):
    return [{
        'type': 'hero_banner',
        'value': {
            'heading': heading,
            'subheading': '',
            'image': None,
            'cta_label': '',
            'cta_url': '',
        },
    }]


def section(name='Home hero', section_type='hero_banner',
            content=None, user=None, **kwargs):
    instance = CmsSection.objects.create(
        name=name,
        section_type=section_type,
        content=(
            content if content is not None else hero_content()
        ),
        **kwargs,
    )
    if user is not None:
        instance.save_revision(user=user)
    return instance


def root_page():
    return Page.objects.get(depth=1)


def page(user, slug='page', title='Page', parent=None, **kwargs):
    """Create a draft CmsPage under the root (or a given parent)."""
    if parent is None:
        parent = root_page()
    instance = CmsPage(
        title=title,
        slug=slug,
        live=False,
        owner=user,
        **kwargs,
    )
    parent.add_child(instance=instance)
    instance.save_revision(user=user)
    return instance


def page_row(name='Row', content=None, global_section=None):
    """One composition row payload (services input shape)."""
    row = {'name': name, 'archived': False}
    if global_section is not None:
        row['global_section'] = global_section
    else:
        row['content'] = content or hero_content()
    return row


def page_section(page, user, **kwargs):
    """Attach one composition row to a page and snapshot a revision.

    Appends (does not replace existing rows). ``global_section`` may
    be given as a pk; it is resolved to a ``CmsSection`` instance.
    """
    global_section = kwargs.get('global_section')
    if isinstance(global_section, int):
        kwargs['global_section'] = CmsSection.objects.get(
            pk=global_section,
        )
    content = kwargs.get('content')
    row = CmsPageSection.objects.create(
        page=page,
        name=kwargs.get('name', 'Row'),
        global_section=kwargs.get('global_section'),
        content=(
            content if content is not None
            else (None if kwargs.get('global_section')
                  else hero_content())
        ),
        sort_order=page.sections.count(),
    )
    page.save_revision(user=user)
    return row


def reference_to(target, source=None):
    """
    Record a ReferenceIndex row where `source` (another CmsSection by
    default) references `target`, as if published content pointed at
    it. ``created_by`` is used as the source field because it is a
    real field on CmsSection.
    """
    source = source or section(name='Referencing section')
    target_ct = ContentType.objects.get_for_model(type(target))
    source_ct = ContentType.objects.get_for_model(type(source))
    return ReferenceIndex.objects.create(
        content_type=source_ct,
        base_content_type=source_ct,
        object_id=str(source.pk),
        to_content_type=target_ct,
        to_object_id=str(target.pk),
        model_path='created_by',
        content_path='created_by',
        content_path_hash=uuid.uuid4(),
    )
