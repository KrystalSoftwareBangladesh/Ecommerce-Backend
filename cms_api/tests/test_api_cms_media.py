# cms_api/tests/test_api_cms_media.py
"""CMS media management (docs/cms-architecture.md 5.6, 6, 8, 11)."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from PIL import Image as PILImage

from rest_framework.test import APITestCase

from wagtail.documents.models import Document
from wagtail.images.models import Image

from cms_api.models import CmsMediaConfig
from cms_api.tests import factories


CONFIG_URL = '/api/v1/cms/media-config/'
IMAGES_URL = '/api/v1/cms/media/images/'
DOCUMENTS_URL = '/api/v1/cms/media/documents/'


def image_detail_url(image):
    return f'{IMAGES_URL}{image.id}/'


def document_detail_url(document):
    return f'{DOCUMENTS_URL}{document.id}/'


class CmsMediaTestCase(APITestCase):
    def setUp(self):
        self.manager = factories.grant(
            factories.user('media-manager'),
            CmsMediaConfig,
            'manage_cms_media',
        )
        self.stranger = factories.user('media-stranger')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.manager)


class MediaConfigTests(CmsMediaTestCase):
    def test_get_solo_creates_the_singleton_with_defaults(self):
        self.assertFalse(CmsMediaConfig.objects.exists())

        config = CmsMediaConfig.get_solo()

        self.assertEqual(config.pk, CmsMediaConfig.SINGLETON_PK)
        self.assertEqual(CmsMediaConfig.objects.count(), 1)
        self.assertEqual(
            config.allowed_image_extensions,
            ['jpg', 'jpeg', 'png', 'webp'],
        )
        self.assertEqual(config.allowed_document_extensions, ['pdf'])

    def test_get_solo_is_idempotent(self):
        first = CmsMediaConfig.get_solo()
        second = CmsMediaConfig.get_solo()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CmsMediaConfig.objects.count(), 1)

    def test_a_second_row_is_rejected_at_the_database_level(self):
        CmsMediaConfig.get_solo()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CmsMediaConfig.objects.bulk_create([
                    CmsMediaConfig(
                        pk=2, max_image_upload_size=1, max_image_pixels=1,
                        max_document_upload_size=1,
                    ),
                ])

    def test_save_always_targets_the_singleton_pk(self):
        config = CmsMediaConfig(pk=999, max_image_upload_size=1)

        config.save()

        self.assertEqual(config.pk, CmsMediaConfig.SINGLETON_PK)
        self.assertEqual(CmsMediaConfig.objects.count(), 1)

    def test_get_requires_manage_cms_media(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.get(CONFIG_URL)

        self.assertEqual(response.status_code, 403)

    def test_get_returns_the_config(self):
        self.authenticate()

        response = self.client.get(CONFIG_URL)

        self.assertEqual(response.status_code, 200)
        self.assertIn('max_image_upload_size', response.data)

    def test_patch_updates_the_config(self):
        self.authenticate()

        response = self.client.patch(
            CONFIG_URL,
            {
                'max_image_upload_size': 2048,
                'allowed_image_extensions': ['png'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['max_image_upload_size'], 2048)
        config = CmsMediaConfig.get_solo()
        self.assertEqual(config.allowed_image_extensions, ['png'])


class ImageCrudTests(CmsMediaTestCase):
    def test_create_requires_manage_cms_media(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.post(
            IMAGES_URL,
            {'title': 'Pic', 'image': factories.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 403)

    def test_create_an_image(self):
        self.authenticate()

        response = self.client.post(
            IMAGES_URL,
            {
                'title': 'Hero banner',
                'alt_text': 'A red square',
                'image': factories.image_upload(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Hero banner')
        self.assertEqual(response.data['alt_text'], 'A red square')
        self.assertTrue(response.data['image'])
        image = Image.objects.get(pk=response.data['id'])
        self.assertEqual(image.description, 'A red square')
        self.assertEqual(image.width, 10)
        self.assertEqual(image.height, 10)

    def test_title_defaults_to_the_filename(self):
        self.authenticate()

        response = self.client.post(
            IMAGES_URL,
            {'image': factories.image_upload(name='banner.png')},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'banner.png')

    def test_list_images(self):
        self.authenticate()
        factories.cms_image()

        response = self.client.get(IMAGES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_update_metadata_without_a_new_file(self):
        self.authenticate()
        image = factories.cms_image(title='Old')

        response = self.client.patch(
            image_detail_url(image),
            {'title': 'New', 'alt_text': 'New alt'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'New')
        image.refresh_from_db()
        self.assertEqual(image.description, 'New alt')

    def test_update_replaces_the_file(self):
        self.authenticate()
        image = factories.cms_image()

        response = self.client.patch(
            image_detail_url(image),
            {'image': factories.image_upload(size=(20, 20))},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.width, 20)
        self.assertEqual(image.height, 20)

    def test_delete_an_unreferenced_image(self):
        self.authenticate()
        image = factories.cms_image()

        response = self.client.delete(image_detail_url(image))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Image.objects.filter(pk=image.pk).exists())

    def test_delete_a_referenced_image_is_rejected(self):
        self.authenticate()
        image = factories.cms_image()
        factories.reference_to(image)

        response = self.client.delete(image_detail_url(image))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.data['errors']['dependencies']), 1)
        self.assertTrue(Image.objects.filter(pk=image.pk).exists())


class ImageValidationTests(CmsMediaTestCase):
    def test_rejects_an_oversized_image(self):
        self.authenticate()
        factories.media_config(max_image_upload_size=10)

        response = self.client.post(
            IMAGES_URL,
            {'image': factories.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.data['errors'])

    def test_rejects_a_disallowed_extension(self):
        self.authenticate()
        factories.media_config(allowed_image_extensions=['webp'])

        response = self.client.post(
            IMAGES_URL,
            {'image': factories.image_upload(name='pic.png')},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_rejects_a_file_whose_content_does_not_match_its_extension(
        self,
    ):
        """A renamed non-image file must be rejected on real content,
        never on the filename extension or the browser-supplied
        content_type alone."""
        self.authenticate()
        fake = SimpleUploadedFile(
            'fake.png', b'not actually a png', content_type='image/png',
        )

        response = self.client.post(
            IMAGES_URL, {'image': fake}, format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_rejects_a_format_extension_mismatch(self):
        """A real JPEG renamed to .png: Pillow decodes it, but the
        decoded format must still match the claimed extension."""
        self.authenticate()
        factories.media_config(
            allowed_image_extensions=['png', 'jpg', 'jpeg'],
        )
        buffer = io.BytesIO()
        PILImage.new('RGB', (10, 10)).save(buffer, format='JPEG')
        buffer.seek(0)
        mismatched = SimpleUploadedFile(
            'picture.png', buffer.read(), content_type='image/png',
        )

        response = self.client.post(
            IMAGES_URL, {'image': mismatched}, format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_rejects_too_many_pixels(self):
        self.authenticate()
        factories.media_config(max_image_pixels=50)

        response = self.client.post(
            IMAGES_URL,
            {'image': factories.image_upload(size=(10, 10))},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_accepts_within_all_limits(self):
        self.authenticate()

        response = self.client.post(
            IMAGES_URL,
            {'image': factories.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)


class DocumentCrudTests(CmsMediaTestCase):
    def test_create_requires_manage_cms_media(self):
        self.client.force_authenticate(user=self.stranger)

        response = self.client.post(
            DOCUMENTS_URL,
            {'title': 'Doc', 'file': factories.document_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 403)

    def test_create_a_document(self):
        self.authenticate()

        response = self.client.post(
            DOCUMENTS_URL,
            {'title': 'Brochure', 'file': factories.document_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Brochure')

    def test_list_documents(self):
        self.authenticate()
        factories.cms_document()

        response = self.client.get(DOCUMENTS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_update_title(self):
        self.authenticate()
        document = factories.cms_document(title='Old')

        response = self.client.patch(
            document_detail_url(document), {'title': 'New'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'New')

    def test_delete_an_unreferenced_document(self):
        self.authenticate()
        document = factories.cms_document()

        response = self.client.delete(document_detail_url(document))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Document.objects.filter(pk=document.pk).exists()
        )

    def test_delete_a_referenced_document_is_rejected(self):
        self.authenticate()
        document = factories.cms_document()
        factories.reference_to(document)

        response = self.client.delete(document_detail_url(document))

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())


class DocumentValidationTests(CmsMediaTestCase):
    def test_rejects_an_oversized_document(self):
        self.authenticate()
        factories.media_config(max_document_upload_size=5)

        response = self.client.post(
            DOCUMENTS_URL,
            {'file': factories.document_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_rejects_a_disallowed_extension(self):
        self.authenticate()

        response = self.client.post(
            DOCUMENTS_URL,
            {
                'file': factories.document_upload(
                    name='notes.exe', content=b'anything',
                ),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)

    def test_accepts_an_allowed_document(self):
        self.authenticate()

        response = self.client.post(
            DOCUMENTS_URL,
            {'file': factories.document_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
