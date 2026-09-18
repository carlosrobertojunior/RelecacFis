from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from pathlib import Path
from urllib.parse import urlparse

import webview

from auth_client import (
    AuthClient, AuthSession, AuthenticationError, normalize_email,
)
from branding import asset_path, set_window_icon
from login_ui import show_login
from fiscal_flow import (
    FISCAL_PAGE_SCRIPT,
    FISCAL_REPORT_URL,
    analysis_from_message,
    update_status,
    validate_pdf,
)
from fiscal_ui import choose_options as show_fiscal_ui


ECAC_AUTH_URL = "https://cav.receita.fazenda.gov.br/autenticacao"


CERTIFICATES_COMMAND = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$now = Get-Date
$items = @(
    Get-ChildItem Cert:\CurrentUser\My |
    Where-Object {
        $_.HasPrivateKey -and
        $_.NotBefore -le $now -and
        $_.NotAfter -gt $now
    } |
    ForEach-Object {
        [PSCustomObject]@{
            thumbprint = $_.Thumbprint
            subject = $_.Subject
            issuer = $_.Issuer
            expires = $_.NotAfter.ToString("dd/MM/yyyy")
        }
    }
)
ConvertTo-Json -InputObject $items -Compress -Depth 3
"""


def normalize_thumbprint(value: str) -> str:
    return re.sub(r"[^0-9A-F]", "", str(value).upper())


def list_certificates() -> list[dict]:
    encoded = base64.b64encode(
        CERTIFICATES_COMMAND.encode("utf-16le")
    ).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Falha ao ler certificados.")
    data = json.loads(result.stdout.strip() or "[]")
    if isinstance(data, dict):
        data = [data]
    return sorted(
        [item for item in data if item.get("thumbprint")],
        key=lambda item: item.get("subject", "").lower(),
    )


def choose_options(session: AuthSession) -> None:
    show_fiscal_ui(list_certificates, normalize_thumbprint, session)


def show_download_confirmation(window, destination: Path) -> None:
    from System.Windows.Forms import MessageBox
    MessageBox.Show(
        window.native,
        "Relat\u00f3rio PDF salvo em:\n" + str(destination),
        "Download conclu\u00eddo",
    )


def official_service(source: object) -> bool:
    try:
        return urlparse(str(source)).hostname == "servicos.receitafederal.gov.br"
    except ValueError:
        return False


def open_ecac(selected_thumbprint: str) -> None:
    chosen = normalize_thumbprint(selected_thumbprint)
    attached = False
    update_status(
        certificate_thumbprint=chosen,
        download_state="aguardando",
        report_path="",
        download_error="",
        probe={},
        automation_error="",
        phase="iniciando",
        portal_host="",
        session_started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    window = webview.create_window(
        "e-CAC \u2014 Consulta Fiscal",
        html="<html><body><h3>Preparando acesso ao e-CAC...</h3></body></html>",
        width=1250, height=850,
    )

    def attach_and_navigate(core) -> None:
        nonlocal attached
        if attached:
            return
        attached = True
        update_status(phase="webview_inicializado")
        run_state = {
            "analysis_seen": False,
            "download_state": "aguardando",
            "report_path": "",
            "click_attempted": False,
            "report_opened": False,
        }

        def on_certificate_requested(sender, args) -> None:
            host = str(args.Host).lower()
            allowed = (
                host == "gov.br" or host.endswith(".gov.br")
                or host == "fazenda.gov.br" or host.endswith(".fazenda.gov.br")
            )
            if not allowed:
                args.Cancel = True
                return
            for certificate in args.MutuallyTrustedCertificates:
                fingerprint = normalize_thumbprint(
                    certificate.ToX509Certificate2().Thumbprint
                )
                if fingerprint == chosen:
                    args.SelectedCertificate = certificate
                    args.Handled = True
                    return
            args.Cancel = True
            from System.Windows.Forms import MessageBox
            MessageBox.Show(
                "O certificado escolhido n\u00e3o est\u00e1 entre os aceitos "
                "nesta etapa do acesso. Nenhum outro foi utilizado.",
                "Certificado n\u00e3o encontrado",
            )

        def inject_script(sender) -> None:
            if not official_service(sender.Source):
                return
            try:
                sender.ExecuteScriptAsync(FISCAL_PAGE_SCRIPT)
            except Exception as exc:
                update_status(automation_error=str(exc)[:300])

        def on_navigation_completed(sender, args) -> None:
            try:
                current = urlparse(str(sender.Source))
                host = current.hostname or ""
                path = current.path.lower()
            except ValueError:
                host, path = "", ""
            if not args.IsSuccess:
                update_status(
                    phase="falha_na_navegacao", portal_host=host[:100]
                )
                return
            if host == "sso.acesso.gov.br":
                phase = "aguardando_login_govbr"
            elif host == "cav.receita.fazenda.gov.br":
                phase = "aguardando_autenticacao_ecac"
            elif host == "servicos.receitafederal.gov.br":
                phase = "consulta_fiscal_aberta"
            else:
                phase = "pagina_aberta"
            update_status(phase=phase, portal_host=host[:100])
            if (
                host == "cav.receita.fazenda.gov.br"
                and path.startswith("/ecac/")
                and not path.startswith("/ecac/publico/")
                and "login" not in path
                and not run_state["report_opened"]
            ):
                run_state["report_opened"] = True
                update_status(phase="abrindo_relatorio_fiscal")
                sender.Navigate(FISCAL_REPORT_URL)
                return
            inject_script(sender)

        def on_web_message_received(sender, args) -> None:
            if not official_service(args.Source):
                return
            try:
                raw = str(args.TryGetWebMessageAsString())
                if len(raw) > 5000:
                    return
                message = json.loads(raw)
            except Exception:
                return
            if not isinstance(message, dict):
                return
            analysis = analysis_from_message(message)
            if analysis is not None:
                run_state["analysis_seen"] = True
                analysis["certificate_thumbprint"] = chosen
                analysis["download_state"] = run_state["download_state"]
                analysis["report_path"] = run_state["report_path"]
                update_status(**analysis)
                return
            kind = message.get("kind")
            if kind == "fiscal_probe":
                probe = {
                    "path": str(message.get("path") or "")[:200],
                    "analysis_found": bool(message.get("analysis_found")),
                    "button_found": bool(message.get("button_found")),
                    "click_attempted": bool(message.get("click_attempted")),
                }
                update_status(probe=probe)
            elif kind == "fiscal_download_requested":
                run_state["click_attempted"] = True
                run_state["download_state"] = "solicitado"
                update_status(download_state="solicitado")
            elif kind == "fiscal_click_error":
                run_state["download_state"] = "erro_clique"
                update_status(
                    download_state="erro_clique",
                    automation_error=str(message.get("error") or "")[:200],
                )

        def on_download_starting(sender, args) -> None:
            operation = args.DownloadOperation
            suggested = str(args.ResultFilePath)
            suggested_path = Path(suggested) if suggested else Path.home() / "Downloads" / "relatorio.pdf"
            destination = suggested_path.with_name(
                f"RelatorioSituacaoFiscal-{datetime.now():%Y%m%d-%H%M%S-%f}.pdf"
            )
            args.ResultFilePath = str(destination)
            args.Cancel = False
            args.Handled = True
            run_state["download_state"] = "baixando"
            run_state["report_path"] = str(destination)
            update_status(download_state="baixando", report_path=str(destination))

            def on_download_state_changed(download, _event) -> None:
                state = str(download.State)
                if state == "Completed":
                    run_state["download_state"] = (
                        "concluido" if validate_pdf(destination)
                        else "arquivo_invalido"
                    )
                elif state == "Interrupted":
                    run_state["download_state"] = "interrompido"
                    run_state["download_error"] = str(download.InterruptReason)
                else:
                    return
                update_status(
                    download_state=run_state["download_state"],
                    report_path=str(destination),
                    download_error=run_state.get("download_error", ""),
                )
                if run_state["download_state"] == "concluido":
                    try:
                        show_download_confirmation(window, destination)
                    except Exception as exc:
                        update_status(notification_error=str(exc)[:200])

            window._download_state_handlers.append(on_download_state_changed)
            operation.StateChanged += on_download_state_changed

        def on_frame_created(sender, args) -> None:
            frame = args.Frame
            handlers = window._frame_handlers
            def on_frame_navigation(frame_sender, frame_args) -> None:
                if frame_args.IsSuccess:
                    inject_script(frame_sender)
            handlers.append(on_frame_navigation)
            frame.NavigationCompleted += on_frame_navigation
            if hasattr(frame, "WebMessageReceived"):
                frame.WebMessageReceived += on_web_message_received
                handlers.append(on_web_message_received)
            inject_script(frame)

        # Keep .NET event handlers alive for the browser session.
        window._certificate_handler = on_certificate_requested
        window._navigation_handler = on_navigation_completed
        window._message_handler = on_web_message_received
        window._download_handler = on_download_starting
        window._frame_handler = on_frame_created
        window._frame_handlers = []
        window._download_state_handlers = []
        # pywebview registers a SaveFileDialog first. Remove it so the
        # report is saved automatically by our DownloadStarting handler.
        native_browser = getattr(window.native, "browser", None)
        if native_browser is not None:
            try:
                core.DownloadStarting -= native_browser.on_download_starting
            except Exception as exc:
                update_status(automation_error=(
                    "Falha ao desativar a janela Salvar como: " + str(exc)
                )[:300])
        core.ClientCertificateRequested += on_certificate_requested
        core.NavigationCompleted += on_navigation_completed
        core.WebMessageReceived += on_web_message_received
        core.DownloadStarting += on_download_starting
        if hasattr(core, "FrameCreated"):
            core.FrameCreated += on_frame_created
        update_status(phase="abrindo_autenticacao_ecac")
        core.Navigate(ECAC_AUTH_URL)

    def on_before_show() -> None:
        # pywebview calls a zero-argument handler for before_show.
        try:
            control = window.native.webview
            update_status(phase="janela_aberta")

            def on_initialized(sender, args) -> None:
                if args.IsSuccess:
                    try:
                        attach_and_navigate(sender.CoreWebView2)
                    except Exception as exc:
                        update_status(
                            phase="erro_ao_navegar",
                            automation_error=str(exc)[:300],
                        )
                else:
                    update_status(
                        phase="falha_webview2",
                        automation_error=str(args.InitializationException)[:300],
                    )
                    from System.Windows.Forms import MessageBox
                    MessageBox.Show(
                        str(args.InitializationException), "Falha ao iniciar WebView2"
                    )

            window._initialization_handler = on_initialized
            control.CoreWebView2InitializationCompleted += on_initialized
            if control.CoreWebView2 is not None:
                on_initialized(
                    control,
                    type("Initialization", (), {"IsSuccess": True})(),
                )
        except Exception as exc:
            update_status(
                phase="erro_ao_abrir_janela",
                automation_error=str(exc)[:300],
            )

    window.events.before_show += on_before_show
    webview.start(
        gui="edgechromium", private_mode=True,
        icon=str(asset_path("favicon.ico")),
    )


def show_startup_error(message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    set_window_icon(root)
    messagebox.showerror("Acesso ao sistema", message, parent=root)
    root.destroy()


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Este aplicativo requer Windows.")
    base_dir = (
        Path(sys.executable).parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    bundled_runtime = base_dir / "WebView2Runtime"
    if bundled_runtime.is_dir():
        webview.settings["WEBVIEW2_RUNTIME_PATH"] = str(bundled_runtime)
    # pywebview must not open its SaveFileDialog before our handler.
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False

    try:
        client = AuthClient.from_config()
    except AuthenticationError as exc:
        show_startup_error(str(exc))
        return

    if len(sys.argv) == 3 and sys.argv[1] == "--browser":
        token = os.environ.pop("RELATORIOS_ECAC_SESSION_TOKEN", "")
        account = normalize_email(
            os.environ.get("RELATORIOS_ECAC_ACCOUNT", "")
        )
        try:
            verified_email = client.validate_session(token)
            if not account or verified_email != account:
                raise AuthenticationError(
                    "A conta do login n\u00e3o corresponde a esta consulta."
                )
        except AuthenticationError as exc:
            update_status(
                phase="login_expirado", probe={},
                automation_error=str(exc),
            )
            show_startup_error(str(exc))
            return
        open_ecac(sys.argv[2])
    else:
        session = show_login(client)
        if session is not None:
            os.environ["RELATORIOS_ECAC_ACCOUNT"] = session.email
            choose_options(session)


if __name__ == "__main__":
    main()
