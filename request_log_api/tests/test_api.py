# request_log_api/tests/test_api.py
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.utils import timezone

from rest_framework.test import APITestCase

from user_api.models import User

from request_log_api.models import RequestLog, RequestOutcome


REQUEST_LOGS_URL = '/api/v1/request-logs/'


def grant(user, codename):
    """
    Attach a `RequestLog` model permission, the way the other apps'
    permission tests do.
    """
    content_type = ContentType.objects.get_for_model(RequestLog)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=content_type,
            codename=codename,
        )
    )

    return User.objects.get(pk=user.pk)


def make_log(**overrides):
    now = timezone.now()
    values = {
        'request_id': '11111111-1111-1111-1111-111111111111',
        'request_method': 'GET',
        'request_path': '/api/v1/products/',
        'route_pattern': '/api/v1/products/',
        'status_code': 200,
        'started_at': now,
        'completed_at': now,
        'duration_ms': 10,
        'is_success': True,
        'outcome': RequestOutcome.SUCCESS,
        'request_body': {'name': 'Shoe'},
        'response_body': {'results': []},
    }
    values.update(overrides)

    return RequestLog.objects.create(**values)


# Logging is switched off so the fixtures below are the only rows in the
# table; otherwise each test request would log itself and change the
# counts it is asserting on.
@override_settings(REQUEST_LOG_ENABLED=False)
class RequestLogApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ops-staff',
            email='ops-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.superuser = User.objects.create_superuser(
            username='ops-admin',
            email='ops-admin@example.com',
            password='test-pass-123',
        )

    def as_viewer(self):
        self.user = grant(self.user, 'view_requestlog')
        self.client.force_authenticate(user=self.user)

        return self.user


class PermissionTests(RequestLogApiTestCase):
    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get(REQUEST_LOGS_URL).status_code, 401)

    def test_list_requires_the_view_permission(self):
        self.client.force_authenticate(user=self.user)

        self.assertEqual(self.client.get(REQUEST_LOGS_URL).status_code, 403)

    def test_a_permitted_user_can_list(self):
        self.as_viewer()

        self.assertEqual(self.client.get(REQUEST_LOGS_URL).status_code, 200)

    def test_nothing_is_publicly_readable(self):
        make_log()

        self.assertEqual(self.client.get(REQUEST_LOGS_URL).status_code, 401)


class ImmutabilityTests(RequestLogApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.superuser)
        self.log = make_log()

    def test_logs_cannot_be_created_through_the_api(self):
        response = self.client.post(REQUEST_LOGS_URL, {}, format='json')

        self.assertEqual(response.status_code, 405)

    def test_logs_cannot_be_updated_through_the_api(self):
        detail = f'{REQUEST_LOGS_URL}{self.log.pk}/'

        self.assertEqual(
            self.client.patch(detail, {'status_code': 500}).status_code,
            405,
        )
        self.assertEqual(
            self.client.put(detail, {'status_code': 500}).status_code,
            405,
        )

    def test_logs_cannot_be_deleted_through_the_api(self):
        response = self.client.delete(
            f'{REQUEST_LOGS_URL}{self.log.pk}/'
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(RequestLog.objects.filter(pk=self.log.pk).exists())


class ListTests(RequestLogApiTestCase):
    def setUp(self):
        super().setUp()
        self.as_viewer()

    def test_list_is_paginated_in_the_project_shape(self):
        make_log()

        response = self.client.get(REQUEST_LOGS_URL)

        self.assertEqual(response.status_code, 200)
        for key in ['count', 'total_pages', 'current_page', 'results']:
            self.assertIn(key, response.data)

    def test_the_list_row_carries_no_payload(self):
        make_log()

        row = self.client.get(REQUEST_LOGS_URL).data['results'][0]

        self.assertNotIn('request_body', row)
        self.assertNotIn('response_body', row)
        self.assertIn('status_code', row)
        self.assertIn('duration_ms', row)

    def test_newest_first_is_the_default_order(self):
        older = make_log(request_path='/older/')
        newer = make_log(request_path='/newer/')

        results = self.client.get(REQUEST_LOGS_URL).data['results']

        self.assertEqual(
            [row['id'] for row in results],
            [newer.pk, older.pk],
        )

    def test_results_can_be_ordered_by_duration(self):
        fast = make_log(duration_ms=5)
        slow = make_log(duration_ms=900)

        results = self.client.get(
            f'{REQUEST_LOGS_URL}?ordering=-duration_ms'
        ).data['results']

        self.assertEqual(
            [row['id'] for row in results],
            [slow.pk, fast.pk],
        )

    def test_results_can_be_searched(self):
        make_log(request_path='/api/v1/products/')
        wanted = make_log(request_path='/api/v1/categories/')

        results = self.client.get(
            f'{REQUEST_LOGS_URL}?search=categories'
        ).data['results']

        self.assertEqual([row['id'] for row in results], [wanted.pk])


class FilterTests(RequestLogApiTestCase):
    def setUp(self):
        super().setUp()
        self.as_viewer()

        self.ok = make_log(status_code=200, duration_ms=10)
        self.bad = make_log(
            status_code=400,
            is_success=False,
            outcome=RequestOutcome.CLIENT_ERROR,
            duration_ms=50,
            error_message='This field is required.',
        )
        self.broken = make_log(
            status_code=500,
            is_success=False,
            outcome=RequestOutcome.EXCEPTION,
            duration_ms=2000,
            exception_type='RuntimeError',
            error_message='exploded',
        )

    def ids_for(self, query):
        response = self.client.get(f'{REQUEST_LOGS_URL}?{query}')

        self.assertEqual(response.status_code, 200)

        return {row['id'] for row in response.data['results']}

    def test_filter_by_status_code(self):
        self.assertEqual(self.ids_for('status_code=500'), {self.broken.pk})

    def test_filter_by_status_code_range(self):
        self.assertEqual(
            self.ids_for('status_code_min=400&status_code_max=499'),
            {self.bad.pk},
        )

    def test_filter_by_outcome(self):
        self.assertEqual(
            self.ids_for('outcome=EXCEPTION'),
            {self.broken.pk},
        )

    def test_filter_by_success(self):
        self.assertEqual(self.ids_for('is_success=true'), {self.ok.pk})

    def test_filter_slow_requests(self):
        self.assertEqual(
            self.ids_for('min_duration_ms=100'),
            {self.broken.pk},
        )

    def test_filter_by_exception_type(self):
        self.assertEqual(
            self.ids_for('exception_type=RuntimeError'),
            {self.broken.pk},
        )

    def test_filter_by_has_error(self):
        self.assertEqual(
            self.ids_for('has_error=true'),
            {self.bad.pk, self.broken.pk},
        )
        self.assertEqual(self.ids_for('has_error=false'), {self.ok.pk})

    def test_filter_by_route_pattern_and_path(self):
        wanted = make_log(
            request_path='/api/v1/categories/7/',
            route_pattern='/api/v1/categories/{id}/',
        )

        self.assertEqual(
            self.ids_for('route_pattern=/api/v1/categories/{id}/'),
            {wanted.pk},
        )
        self.assertEqual(
            self.ids_for('request_path=categories'),
            {wanted.pk},
        )

    def test_filter_by_user_and_authentication(self):
        mine = make_log(user=self.user, is_authenticated=True)

        self.assertEqual(self.ids_for(f'user={self.user.pk}'), {mine.pk})
        self.assertEqual(self.ids_for('is_authenticated=true'), {mine.pk})

    def test_filter_by_anonymous_id(self):
        wanted = make_log(anonymous_id='anon-9')

        self.assertEqual(self.ids_for('anonymous_id=anon-9'), {wanted.pk})


class DetailFieldPermissionTests(RequestLogApiTestCase):
    def setUp(self):
        super().setUp()
        self.log = make_log(
            status_code=500,
            is_success=False,
            outcome=RequestOutcome.EXCEPTION,
            exception_type='RuntimeError',
            error_message='exploded',
            traceback='Traceback (most recent call last): ...',
            error_details={'email': ['This field is required.']},
            form_fields={'name': 'Shoe'},
        )

    def detail(self):
        response = self.client.get(f'{REQUEST_LOGS_URL}{self.log.pk}/')

        self.assertEqual(response.status_code, 200)

        return response.data

    def test_basic_access_sees_the_technical_picture_only(self):
        self.as_viewer()

        data = self.detail()

        for field in ['status_code', 'duration_ms', 'route_pattern',
                      'error_message', 'exception_type']:
            self.assertIn(field, data)

        for field in ['request_body', 'form_fields', 'response_body',
                      'error_details', 'traceback']:
            self.assertNotIn(field, data)

    def test_the_request_payload_permission_reveals_the_request(self):
        self.as_viewer()
        self.user = grant(self.user, 'view_request_log_request_payload')
        self.client.force_authenticate(user=self.user)

        data = self.detail()

        self.assertIn('request_body', data)
        self.assertIn('form_fields', data)
        self.assertNotIn('response_body', data)

    def test_the_response_payload_permission_reveals_the_response(self):
        self.as_viewer()
        self.user = grant(self.user, 'view_request_log_response_payload')
        self.client.force_authenticate(user=self.user)

        data = self.detail()

        self.assertIn('response_body', data)
        self.assertNotIn('request_body', data)

    def test_the_traceback_permission_reveals_the_traceback(self):
        self.as_viewer()
        self.user = grant(self.user, 'view_request_log_traceback')
        self.client.force_authenticate(user=self.user)

        self.assertIn('traceback', self.detail())

    def test_a_technical_administrator_sees_everything(self):
        self.client.force_authenticate(user=self.superuser)

        data = self.detail()

        for field in ['request_body', 'form_fields', 'response_body',
                      'error_details', 'traceback']:
            self.assertIn(field, data)
