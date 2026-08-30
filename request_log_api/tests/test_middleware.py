# request_log_api/tests/test_middleware.py
import uuid
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from rest_framework.test import APITestCase

from user_api.models import User

from request_log_api.constants import REDACTED_MARKER
from request_log_api.models import RequestLog, RequestOutcome


@override_settings(ROOT_URLCONF='request_log_api.tests.urls')
class RequestLogMiddlewareTestCase(APITestCase):
    """
    Base case for the middleware, mounted on the probe endpoints.
    """

    def last_log(self):
        return RequestLog.objects.order_by('-id').first()


class RequestCaptureTests(RequestLogMiddlewareTestCase):
    def test_every_request_creates_one_record(self):
        self.client.post('/probe/echo/', {'a': 1}, format='json')

        self.assertEqual(RequestLog.objects.count(), 1)

    def test_repeated_requests_are_not_deduplicated(self):
        for _ in range(10):
            self.client.post('/probe/echo/', {'a': 1}, format='json')

        self.assertEqual(RequestLog.objects.count(), 10)

    def test_request_metadata_is_captured(self):
        self.client.post(
            '/probe/echo/?page=2&search=iphone',
            {'name': 'Shoe'},
            format='json',
            HTTP_USER_AGENT='curl/8.5.0',
            HTTP_X_ANONYMOUS_ID='anon-123',
            HTTP_X_CLIENT_TYPE='WEB',
            HTTP_X_CLIENT_ROUTE='/products/nike',
            HTTP_ORIGIN='https://shop.example',
            HTTP_REFERER='https://shop.example/products',
        )

        log = self.last_log()

        self.assertEqual(log.request_method, 'POST')
        self.assertEqual(log.request_path, '/probe/echo/')
        self.assertEqual(log.route_pattern, '/probe/echo/')
        self.assertEqual(
            log.query_parameters,
            {'page': '2', 'search': 'iphone'},
        )
        self.assertIn('page=2', log.query_string)
        self.assertEqual(log.anonymous_id, 'anon-123')
        self.assertEqual(log.client_type, 'WEB')
        self.assertEqual(log.frontend_route, '/products/nike')
        self.assertEqual(log.origin, 'https://shop.example')
        self.assertEqual(log.referer, 'https://shop.example/products')
        self.assertEqual(log.user_agent, 'curl/8.5.0')
        self.assertTrue(log.is_bot)
        self.assertGreater(log.request_size_bytes, 0)
        self.assertGreater(log.response_size_bytes, 0)
        self.assertEqual(log.headers.get('Content-Type'), 'application/json')

    def test_route_pattern_generalises_a_detail_path(self):
        self.client.post('/probe/items/42/', {'a': 1}, format='json')

        log = self.last_log()

        self.assertEqual(log.request_path, '/probe/items/42/')
        self.assertEqual(log.route_pattern, '/probe/items/{pk}/')

    def test_duration_and_timestamps_are_recorded(self):
        self.client.post('/probe/echo/', {'a': 1}, format='json')

        log = self.last_log()

        self.assertIsNotNone(log.started_at)
        self.assertIsNotNone(log.completed_at)
        self.assertGreaterEqual(log.duration_ms, 0)
        self.assertGreaterEqual(log.completed_at, log.started_at)

    def test_excluded_paths_are_not_logged(self):
        self.client.post('/static/probe/', {'a': 1}, format='json')

        self.assertEqual(RequestLog.objects.count(), 0)

    @override_settings(REQUEST_LOG_ENABLED=False)
    def test_logging_can_be_switched_off(self):
        self.client.post('/probe/echo/', {'a': 1}, format='json')

        self.assertEqual(RequestLog.objects.count(), 0)


class RequestIdTests(RequestLogMiddlewareTestCase):
    def test_request_id_is_generated_and_returned_to_the_client(self):
        response = self.client.post('/probe/echo/', {}, format='json')

        self.assertEqual(
            response['X-Request-ID'],
            self.last_log().request_id,
        )

    def test_a_valid_client_request_id_is_reused(self):
        supplied = str(uuid.uuid4())

        response = self.client.post(
            '/probe/echo/',
            {},
            format='json',
            HTTP_X_REQUEST_ID=supplied,
        )

        self.assertEqual(self.last_log().request_id, supplied)
        self.assertEqual(response['X-Request-ID'], supplied)

    def test_an_invalid_client_request_id_is_replaced(self):
        self.client.post(
            '/probe/echo/',
            {},
            format='json',
            HTTP_X_REQUEST_ID='not-a-uuid; DROP TABLE',
        )

        log = self.last_log()

        self.assertNotEqual(log.request_id, 'not-a-uuid; DROP TABLE')
        self.assertEqual(str(uuid.UUID(log.request_id)), log.request_id)


class IdentityTests(RequestLogMiddlewareTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='observer',
            email='observer@example.com',
            password='test-pass-123',
        )

    def test_anonymous_request_is_recorded_without_a_user(self):
        self.client.post('/probe/echo/', {}, format='json')

        log = self.last_log()

        self.assertIsNone(log.user)
        self.assertFalse(log.is_authenticated)

    def test_authenticated_user_is_recorded(self):
        self.client.force_authenticate(user=self.user)
        self.client.post('/probe/echo/', {}, format='json')

        log = self.last_log()

        self.assertEqual(log.user, self.user)
        self.assertTrue(log.is_authenticated)

    def test_a_failed_authentication_still_logs_the_request(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')
        response = self.client.post('/probe/echo/', {}, format='json')

        log = self.last_log()

        self.assertEqual(log.status_code, response.status_code)
        self.assertIsNone(log.user)
        self.assertFalse(log.is_authenticated)

    def test_the_log_survives_deletion_of_its_user(self):
        self.client.force_authenticate(user=self.user)
        self.client.post('/probe/echo/', {}, format='json')

        log_id = self.last_log().pk
        self.user.delete()

        self.assertIsNone(RequestLog.objects.get(pk=log_id).user)


class SanitizationTests(RequestLogMiddlewareTestCase):
    def test_request_payload_is_sanitized(self):
        self.client.post(
            '/probe/echo/',
            {
                'email': 'user@example.com',
                'password': 'hunter2',
                'profile': {'api_key': 'abc'},
            },
            format='json',
        )

        body = self.last_log().request_body

        self.assertEqual(body['email'], 'user@example.com')
        self.assertEqual(body['password'], REDACTED_MARKER)
        self.assertEqual(body['profile']['api_key'], REDACTED_MARKER)

    def test_response_payload_is_sanitized(self):
        self.client.post('/probe/echo/', {'a': 1}, format='json')

        self.assertEqual(
            self.last_log().response_body['access_token'],
            REDACTED_MARKER,
        )

    def test_query_parameters_are_sanitized(self):
        self.client.post('/probe/echo/?token=abc&page=1', {}, format='json')

        self.assertEqual(
            self.last_log().query_parameters,
            {'token': REDACTED_MARKER, 'page': '1'},
        )

    def test_authorization_and_cookie_headers_are_never_stored(self):
        self.client.cookies['sessionid'] = 'a-session-value'
        self.client.post(
            '/probe/echo/',
            {},
            format='json',
            HTTP_AUTHORIZATION='Bearer super-secret-token',
        )

        log = self.last_log()
        stored = str(log.headers)

        self.assertNotIn('Authorization', log.headers)
        self.assertNotIn('Cookie', log.headers)
        self.assertNotIn('super-secret-token', stored)
        self.assertNotIn('a-session-value', stored)


class MultipartTests(RequestLogMiddlewareTestCase):
    def _upload(self):
        return self.client.post(
            '/probe/upload/',
            {
                'name': 'Nike Shoe',
                'password': 'hunter2',
                'image': SimpleUploadedFile(
                    'shoe.jpg',
                    b'binary-image-bytes',
                    content_type='image/jpeg',
                ),
            },
            format='multipart',
        )

    def test_the_upload_still_reaches_the_view(self):
        response = self._upload()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'files': ['image']})

    def test_file_metadata_is_recorded_without_the_binary(self):
        self._upload()

        log = self.last_log()

        self.assertTrue(log.is_multipart)
        self.assertEqual(log.file_count, 1)
        self.assertEqual(log.total_file_size_bytes, len(b'binary-image-bytes'))
        self.assertEqual(
            log.files,
            [{
                'field_name': 'image',
                'filename': 'shoe.jpg',
                'content_type': 'image/jpeg',
                'size_bytes': len(b'binary-image-bytes'),
            }],
        )
        self.assertNotIn('binary-image-bytes', str(log.files))

    def test_form_fields_are_captured_and_sanitized(self):
        self._upload()

        log = self.last_log()

        self.assertEqual(log.form_fields['name'], 'Nike Shoe')
        self.assertEqual(log.form_fields['password'], REDACTED_MARKER)


class OutcomeAndErrorTests(RequestLogMiddlewareTestCase):
    def test_a_successful_request_has_no_error_information(self):
        self.client.post('/probe/echo/', {}, format='json')

        log = self.last_log()

        self.assertEqual(log.outcome, RequestOutcome.SUCCESS)
        self.assertTrue(log.is_success)
        self.assertEqual(log.error_message, '')
        self.assertEqual(log.exception_type, '')
        self.assertEqual(log.traceback, '')
        self.assertIsNone(log.error_details)

    def test_a_not_found_is_logged_as_a_client_error(self):
        self.client.get('/probe/missing/')

        log = self.last_log()

        self.assertEqual(log.status_code, 404)
        self.assertEqual(log.outcome, RequestOutcome.CLIENT_ERROR)
        self.assertFalse(log.is_success)
        self.assertEqual(log.route_pattern, '')

    def test_an_unhandled_exception_is_recorded_with_its_traceback(self):
        self.client.raise_request_exception = False

        response = self.client.get('/probe/boom/')

        log = self.last_log()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(log.status_code, 500)
        self.assertEqual(log.outcome, RequestOutcome.EXCEPTION)
        self.assertEqual(log.exception_type, 'RuntimeError')
        self.assertIn('exploded', log.error_message)
        self.assertIn('Traceback', log.traceback)

    def test_a_traceback_is_sanitized(self):
        self.client.raise_request_exception = False

        self.client.get('/probe/boom/')

        self.assertNotIn('hunter2', self.last_log().traceback)


class LoggingFailureTests(RequestLogMiddlewareTestCase):
    def test_a_storage_failure_never_affects_the_response(self):
        target = 'request_log_api.services.storage.get_storage'

        with mock.patch(target, side_effect=RuntimeError('log db down')):
            response = self.client.post(
                '/probe/echo/',
                {'a': 1},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['received'], {'a': 1})
        self.assertEqual(RequestLog.objects.count(), 0)

    def test_a_capture_failure_never_affects_the_response(self):
        target = (
            'request_log_api.services.builder.collect_request_context'
        )

        with mock.patch(target, side_effect=RuntimeError('capture broke')):
            response = self.client.post(
                '/probe/echo/',
                {'a': 1},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestLog.objects.count(), 0)

    def test_a_build_failure_never_affects_the_response(self):
        target = 'request_log_api.services.builder.build_event'

        with mock.patch(target, side_effect=RuntimeError('build broke')):
            response = self.client.post(
                '/probe/echo/',
                {'a': 1},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestLog.objects.count(), 0)
