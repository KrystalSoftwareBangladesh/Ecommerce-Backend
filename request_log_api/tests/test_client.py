# request_log_api/tests/test_client.py
from django.test import RequestFactory, SimpleTestCase, override_settings

from request_log_api.models.choices import ClientType, DeviceType
from request_log_api.services.client import (
    parse_user_agent,
    resolve_client_type,
    resolve_ip_address,
)


CHROME_WINDOWS = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
SAFARI_IPHONE = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 '
    'Mobile/15E148 Safari/604.1'
)
SAFARI_IPAD = (
    'Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/604.1'
)
EDGE_WINDOWS = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
)
GOOGLEBOT = (
    'Mozilla/5.0 (compatible; Googlebot/2.1; '
    '+http://www.google.com/bot.html)'
)


class ParseUserAgentTests(SimpleTestCase):
    def test_chrome_on_windows(self):
        parsed = parse_user_agent(CHROME_WINDOWS)

        self.assertEqual(parsed['browser'], 'Chrome')
        self.assertEqual(parsed['browser_version'], '120.0.0.0')
        self.assertEqual(parsed['operating_system'], 'Windows')
        self.assertEqual(parsed['operating_system_version'], '10')
        self.assertEqual(parsed['device_type'], DeviceType.DESKTOP)
        self.assertFalse(parsed['is_mobile'])
        self.assertFalse(parsed['is_bot'])

    def test_edge_is_not_reported_as_chrome(self):
        self.assertEqual(parse_user_agent(EDGE_WINDOWS)['browser'], 'Edge')

    def test_safari_on_iphone_is_mobile(self):
        parsed = parse_user_agent(SAFARI_IPHONE)

        self.assertEqual(parsed['browser'], 'Safari')
        self.assertEqual(parsed['operating_system'], 'iOS')
        self.assertEqual(parsed['operating_system_version'], '17.2')
        self.assertEqual(parsed['device_type'], DeviceType.MOBILE)
        self.assertTrue(parsed['is_mobile'])

    def test_ipad_is_a_tablet_not_a_phone(self):
        parsed = parse_user_agent(SAFARI_IPAD)

        self.assertEqual(parsed['device_type'], DeviceType.TABLET)
        self.assertFalse(parsed['is_mobile'])

    def test_googlebot_is_detected(self):
        parsed = parse_user_agent(GOOGLEBOT)

        self.assertTrue(parsed['is_bot'])
        self.assertEqual(parsed['bot_name'], 'Googlebot')
        self.assertEqual(parsed['device_type'], DeviceType.BOT)

    def test_command_line_client_is_a_bot(self):
        parsed = parse_user_agent('curl/8.5.0')

        self.assertTrue(parsed['is_bot'])
        self.assertEqual(parsed['bot_name'], 'curl')

    def test_empty_user_agent_is_unknown_not_guessed(self):
        parsed = parse_user_agent('')

        self.assertEqual(parsed['browser'], '')
        self.assertEqual(parsed['operating_system'], '')
        self.assertEqual(parsed['device_type'], DeviceType.UNKNOWN)
        self.assertFalse(parsed['is_bot'])


class ResolveIpAddressTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, **headers):
        return self.factory.get('/probe/', **headers)

    def test_remote_addr_is_used_by_default(self):
        request = self._request(
            REMOTE_ADDR='10.0.0.9',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
        )

        self.assertEqual(resolve_ip_address(request), '10.0.0.9')

    @override_settings(REQUEST_LOG_TRUSTED_PROXY_COUNT=1)
    def test_one_trusted_proxy_reads_the_last_forwarded_entry(self):
        request = self._request(
            REMOTE_ADDR='10.0.0.9',
            HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8',
        )

        self.assertEqual(resolve_ip_address(request), '5.6.7.8')

    @override_settings(REQUEST_LOG_TRUSTED_PROXY_COUNT=2)
    def test_two_trusted_proxies_read_further_left(self):
        request = self._request(
            REMOTE_ADDR='10.0.0.9',
            HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8',
        )

        self.assertEqual(resolve_ip_address(request), '1.2.3.4')

    @override_settings(REQUEST_LOG_TRUSTED_PROXY_COUNT=2)
    def test_a_short_forwarded_chain_falls_back_to_remote_addr(self):
        request = self._request(
            REMOTE_ADDR='10.0.0.9',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
        )

        self.assertEqual(resolve_ip_address(request), '10.0.0.9')


class ResolveClientTypeTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_declared_client_type_is_used(self):
        request = self.factory.get('/probe/', HTTP_X_CLIENT_TYPE='mobile')

        self.assertEqual(resolve_client_type(request), ClientType.MOBILE)

    def test_unknown_value_is_not_guessed(self):
        request = self.factory.get('/probe/', HTTP_X_CLIENT_TYPE='wat')

        self.assertEqual(resolve_client_type(request), ClientType.UNKNOWN)

    def test_missing_header_is_unknown(self):
        self.assertEqual(
            resolve_client_type(self.factory.get('/probe/')),
            ClientType.UNKNOWN,
        )
