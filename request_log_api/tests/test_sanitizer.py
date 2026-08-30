# request_log_api/tests/test_sanitizer.py
import json

from django.test import SimpleTestCase, override_settings

from request_log_api.constants import (
    REDACTED_MARKER,
    TRUNCATED_MARKER,
)
from request_log_api.services.sanitizer import (
    is_sensitive_key,
    sanitize,
    sanitize_body,
    sanitize_text,
    sanitize_traceback,
)


class SensitiveKeyTests(SimpleTestCase):
    def test_password_variants_are_sensitive(self):
        for key in [
            'password',
            'Password',
            'new_password',
            'password_confirmation',
            'current_password',
            'passwd',
        ]:
            self.assertTrue(is_sensitive_key(key), key)

    def test_token_and_secret_variants_are_sensitive(self):
        for key in [
            'access',
            'refresh',
            'token',
            'access_token',
            'refresh_token',
            'authorization',
            'api_key',
            'X-Api-Key',
            'secret_key',
            'client_secret',
            'card_number',
            'cvv',
        ]:
            self.assertTrue(is_sensitive_key(key), key)

    def test_innocent_keys_are_not_sensitive(self):
        for key in [
            'accessible',
            'email',
            'name',
            'price',
            'credential',
            'is_active',
        ]:
            self.assertFalse(is_sensitive_key(key), key)

    def test_non_string_key_is_not_sensitive(self):
        self.assertFalse(is_sensitive_key(10))


class SanitizeTests(SimpleTestCase):
    def test_top_level_value_is_redacted(self):
        self.assertEqual(
            sanitize({'email': 'a@b.c', 'password': 'secret'}),
            {'email': 'a@b.c', 'password': REDACTED_MARKER},
        )

    def test_sanitization_is_recursive(self):
        payload = {
            'user': {
                'profile': {'password': 'secret', 'city': 'Dhaka'},
            },
        }

        self.assertEqual(
            sanitize(payload),
            {
                'user': {
                    'profile': {
                        'password': REDACTED_MARKER,
                        'city': 'Dhaka',
                    },
                },
            },
        )

    def test_sanitization_walks_into_lists(self):
        payload = {'users': [{'name': 'a', 'api_key': 'k'}]}

        self.assertEqual(
            sanitize(payload),
            {'users': [{'name': 'a', 'api_key': REDACTED_MARKER}]},
        )

    def test_structure_is_preserved_not_removed(self):
        sanitized = sanitize({'password': 'secret'})

        self.assertIn('password', sanitized)

    def test_scalars_pass_through(self):
        self.assertEqual(sanitize('plain'), 'plain')
        self.assertEqual(sanitize(7), 7)
        self.assertIsNone(sanitize(None))

    def test_excessive_nesting_is_truncated_not_recursed(self):
        payload = current = {}

        for _ in range(40):
            child = {}
            current['next'] = child
            current = child

        rendered = json.dumps(sanitize(payload))

        self.assertIn(TRUNCATED_MARKER, rendered)

    @override_settings(REQUEST_LOG_SENSITIVE_KEY_FRAGMENTS=['nickname'])
    def test_sensitive_keys_are_configurable(self):
        self.assertEqual(
            sanitize({'nickname': 'zed', 'password': 'secret'}),
            {'nickname': REDACTED_MARKER, 'password': 'secret'},
        )


class SanitizeTextTests(SimpleTestCase):
    def test_key_value_pairs_are_redacted(self):
        self.assertNotIn('hunter2', sanitize_text("password='hunter2'"))

    def test_colon_separated_pairs_are_redacted(self):
        self.assertNotIn(
            'abc.def',
            sanitize_text('Authorization: Bearer abc.def'),
        )

    def test_unrelated_text_survives(self):
        self.assertEqual(sanitize_text('city=Dhaka'), 'city=Dhaka')

    def test_empty_text_is_empty(self):
        self.assertEqual(sanitize_text(''), '')

    @override_settings(REQUEST_LOG_MAX_TRACEBACK_LENGTH=50)
    def test_traceback_is_capped(self):
        capped = sanitize_traceback('x' * 500)

        self.assertIn(TRUNCATED_MARKER, capped)
        self.assertLess(len(capped), 500)


class SanitizeBodyTests(SimpleTestCase):
    def test_json_body_is_decoded_and_sanitized(self):
        body = b'{"name": "Shoe", "token": "abc"}'

        self.assertEqual(
            sanitize_body(body, 'application/json', 1024),
            {'name': 'Shoe', 'token': REDACTED_MARKER},
        )

    def test_oversized_body_is_replaced_by_a_marker(self):
        body = b'{"name": "Shoe"}'

        self.assertEqual(
            sanitize_body(body, 'application/json', 4),
            {'detail': TRUNCATED_MARKER, 'size_bytes': len(body)},
        )

    def test_non_json_body_is_not_stored(self):
        self.assertIsNone(sanitize_body(b'<html></html>', 'text/html', 1024))

    def test_malformed_json_is_not_stored(self):
        self.assertIsNone(sanitize_body(b'{oops', 'application/json', 1024))

    def test_empty_body_is_not_stored(self):
        self.assertIsNone(sanitize_body(b'', 'application/json', 1024))
