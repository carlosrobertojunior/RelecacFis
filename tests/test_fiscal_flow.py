from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from fiscal_flow import FISCAL_REPORT_URL, read_status, validate_pdf


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def fire(self, *args):
        for handler in self.handlers:
            handler(*args)


class FakeCore:
    def __init__(self):
        self.ClientCertificateRequested = Event()
        self.NavigationCompleted = Event()
        self.WebMessageReceived = Event()
        self.DownloadStarting = Event()
        self.Source = FISCAL_REPORT_URL
        self.navigated = None
        self.injected = None

    def Navigate(self, url):
        self.navigated = url

    def ExecuteScriptAsync(self, script):
        self.injected = script


class FakeOperation:
    def __init__(self):
        self.MimeType = "application/pdf"
        self.State = "InProgress"
        self.StateChanged = Event()
        self.InterruptReason = ""


class FiscalFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        environment = patch.dict(
            os.environ,
            {"RELATORIOS_ECAC_STATUS_PATH": str(self.path / "state.json")},
        )
        environment.start()
        self.addCleanup(environment.stop)

        self.core = FakeCore()
        control = SimpleNamespace(
            CoreWebView2=self.core,
            CoreWebView2InitializationCompleted=Event(),
        )
        class NativeBrowser:
            def on_download_starting(self, sender, args):
                raise AssertionError("pywebview SaveFileDialog was not removed")
        native_browser = NativeBrowser()
        self.core.DownloadStarting += native_browser.on_download_starting
        self.window = SimpleNamespace(
            events=SimpleNamespace(before_show=Event()),
            native=SimpleNamespace(webview=control, browser=native_browser),
        )
        notification = patch.object(app, "show_download_confirmation")
        self.notification = notification.start()
        self.addCleanup(notification.stop)
        with (
            patch.object(app.webview, "create_window", return_value=self.window),
            patch.object(app.webview, "start", side_effect=self.start_browser),
        ):
            app.open_ecac("ABCD")

    def start_browser(self, **_kwargs):
        self.window.events.before_show.fire()

    def send_analysis(self):
        payload = {
            "kind": "fiscal_analysis",
            "result": "Com pend\u00eancia",
            "portal_analysis": "An\u00e1lise realizada hoje 17/09/2026",
            "taxpayer_name": "Empresa Teste",
            "taxpayer_id": "00.000.000/0001-00",
        }
        message = SimpleNamespace(
            Source=FISCAL_REPORT_URL,
            TryGetWebMessageAsString=lambda: json.dumps(payload),
        )
        self.core.WebMessageReceived.fire(self.core, message)

    def complete_download(self, content=b"%PDF-1.7\n1 0 obj\n"):
        operation = FakeOperation()
        args = SimpleNamespace(
            DownloadOperation=operation,
            ResultFilePath=str(self.path / "suggested.pdf"),
            Handled=False,
        )
        self.core.DownloadStarting.fire(self.core, args)
        self.assertTrue(args.Handled)
        destination = Path(args.ResultFilePath)
        destination.write_bytes(content)
        operation.State = "Completed"
        operation.StateChanged.fire(operation, None)
        return destination

    def test_analysis_and_valid_pdf(self):
        self.assertEqual(self.core.navigated, app.ECAC_AUTH_URL)
        self.core.NavigationCompleted.fire(
            self.core, SimpleNamespace(IsSuccess=True)
        )
        self.assertIn("fiscal_analysis", self.core.injected)
        self.send_analysis()
        destination = self.complete_download()
        result = read_status()
        self.assertEqual(result["result"], "Com pend\u00eancia")
        self.assertEqual(result["download_state"], "concluido")
        self.assertEqual(result["report_path"], str(destination))
        self.notification.assert_called_once_with(self.window, destination)

    def test_download_finishes_before_analysis_message(self):
        destination = self.complete_download()
        self.send_analysis()
        result = read_status()
        self.assertEqual(result["download_state"], "concluido")
        self.assertEqual(result["report_path"], str(destination))

    def test_authentication_challenge_then_report(self):
        self.assertEqual(self.core.navigated, app.ECAC_AUTH_URL)
        for url in (
            "https://cav.receita.fazenda.gov.br/autenticacao/login/index",
            "https://sso.acesso.gov.br/login?client_id=cav.receita.fazenda.gov.br",
            "https://cav.receita.fazenda.gov.br/autenticacao/login/index",
            "https://cav.receita.fazenda.gov.br/ecac/publico/Erros/ErroEcac.aspx",
        ):
            self.core.Source = url
            self.core.NavigationCompleted.fire(
                self.core, SimpleNamespace(IsSuccess=True)
            )
            self.assertEqual(self.core.navigated, app.ECAC_AUTH_URL)
            self.assertIsNone(self.core.injected)
        self.core.Source = "https://cav.receita.fazenda.gov.br/ecac/"
        self.core.NavigationCompleted.fire(
            self.core, SimpleNamespace(IsSuccess=True)
        )
        self.assertEqual(self.core.navigated, FISCAL_REPORT_URL)
        self.core.Source = FISCAL_REPORT_URL
        self.core.NavigationCompleted.fire(
            self.core, SimpleNamespace(IsSuccess=True)
        )
        self.assertIn("fiscal_analysis", self.core.injected)

    def test_navigation_on_other_path_and_probe(self):
        self.core.Source = "https://servicos.receitafederal.gov.br/outra-rota"
        self.core.NavigationCompleted.fire(
            self.core, SimpleNamespace(IsSuccess=True)
        )
        self.assertIn("fiscal_download_requested", self.core.injected)
        payload = {
            "kind": "fiscal_probe",
            "path": "/outra-rota",
            "analysis_found": False,
            "button_found": True,
            "click_attempted": False,
        }
        message = SimpleNamespace(
            Source=self.core.Source,
            TryGetWebMessageAsString=lambda: json.dumps(payload),
        )
        self.core.WebMessageReceived.fire(self.core, message)
        self.assertTrue(read_status()["probe"]["button_found"])

    def test_download_before_analysis_is_recorded(self):
        destination = self.complete_download()
        data = read_status()
        self.assertEqual(data["download_state"], "concluido")
        self.assertEqual(data["report_path"], str(destination))

    def test_invalid_file_is_not_confirmed_as_pdf(self):
        self.send_analysis()
        destination = self.complete_download(b"not a pdf")
        self.assertEqual(read_status()["download_state"], "arquivo_invalido")
        self.assertFalse(validate_pdf(destination))


if __name__ == "__main__":
    unittest.main()

