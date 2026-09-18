from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

import app
import auth_client
from auth_client import AuthClient, AuthSession, AuthenticationError
from fiscal_flow import status_file


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.payload


class LoginTests(unittest.TestCase):
    def test_endpoint_requires_published_script(self):
        with patch.dict(os.environ, {'RELATORIOS_ECAC_AUTH_URL': 'http://example.com/exec'}):
            with self.assertRaises(AuthenticationError):
                auth_client.load_endpoint()

    def test_request_and_verify_code(self):
        client = AuthClient('https://script.google.com/macros/s/test/exec')
        responses = [FakeResponse({'ok': True}), FakeResponse({
            'ok': True, 'email': 'user@example.com', 'token': 'session-token',
        })]
        requests = []

        def send(request, timeout):
            self.assertEqual(timeout, 20)
            requests.append(json.loads(request.data))
            return responses.pop(0)

        with patch.object(auth_client, 'urlopen', side_effect=send):
            client.request_code(' USER@example.com ')
            session = client.verify_code('user@example.com', '123456')
        self.assertEqual(session, AuthSession('user@example.com', 'session-token'))
        self.assertEqual(requests[0], {
            'action': 'request', 'email': 'user@example.com',
        })
        self.assertEqual(requests[1]['code'], '123456')

    def test_invalid_code_does_not_make_session(self):
        client = AuthClient('https://script.google.com/macros/s/test/exec')
        with patch.object(auth_client, 'urlopen', return_value=FakeResponse({
            'ok': False, 'error': 'invalid_code',
        })):
            with self.assertRaises(AuthenticationError):
                client.verify_code('user@example.com', '000000')

    def test_restricted_deployment_has_actionable_error(self):
        client = AuthClient('https://script.google.com/macros/s/test/exec')
        denied = HTTPError(client.endpoint, 401, 'Unauthorized', {}, None)
        with patch.object(auth_client, 'urlopen', side_effect=denied):
            with self.assertRaisesRegex(AuthenticationError, 'Qualquer pessoa'):
                client._post({'action': 'health_probe'})

    def test_missing_deployment_has_actionable_error(self):
        client = AuthClient('https://script.google.com/macros/s/test/exec')
        missing = HTTPError(client.endpoint, 404, 'Not Found', {}, None)
        with patch.object(auth_client, 'urlopen', side_effect=missing):
            with self.assertRaisesRegex(AuthenticationError, 'URL /exec'):
                client._post({'action': 'health_probe'})

    def test_no_certificates_before_login(self):
        client = Mock()
        with (
            patch.object(app.AuthClient, 'from_config', return_value=client),
            patch.object(app, 'show_login', return_value=None),
            patch.object(app, 'choose_options') as options,
            patch.object(app.sys, 'argv', ['app.py']),
        ):
            app.main()
        options.assert_not_called()

    def test_browser_requires_validated_same_account(self):
        client = Mock()
        client.validate_session.return_value = 'other@example.com'
        with (
            patch.object(app.AuthClient, 'from_config', return_value=client),
            patch.object(app, 'open_ecac') as browser,
            patch.object(app, 'show_startup_error') as error,
            patch.object(app, 'update_status'),
            patch.object(app.sys, 'argv', ['app.py', '--browser', 'ABC']),
            patch.dict(os.environ, {
                'RELATORIOS_ECAC_SESSION_TOKEN': 'valid-token',
                'RELATORIOS_ECAC_ACCOUNT': 'user@example.com',
            }),
        ):
            app.main()
        browser.assert_not_called()
        error.assert_called_once()

    def test_browser_opens_after_valid_session(self):
        client = Mock()
        client.validate_session.return_value = 'user@example.com'
        with (
            patch.object(app.AuthClient, 'from_config', return_value=client),
            patch.object(app, 'open_ecac') as browser,
            patch.object(app, 'show_startup_error') as error,
            patch.object(app.sys, 'argv', ['app.py', '--browser', 'ABC']),
            patch.dict(os.environ, {
                'RELATORIOS_ECAC_SESSION_TOKEN': 'valid-token',
                'RELATORIOS_ECAC_ACCOUNT': 'user@example.com',
            }),
        ):
            app.main()
        browser.assert_called_once_with('ABC')
        error.assert_not_called()

    def test_status_history_separated_by_account(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'LOCALAPPDATA': folder}, clear=True):
                os.environ['RELATORIOS_ECAC_ACCOUNT'] = 'a@example.com'
                first = status_file()
                os.environ['RELATORIOS_ECAC_ACCOUNT'] = 'b@example.com'
                second = status_file()
                self.assertNotEqual(first, second)
                self.assertEqual(first.parent, Path(folder) / 'RelatoriosECAC')


if __name__ == '__main__':
    unittest.main()
