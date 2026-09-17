from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

import webview

from fiscal_flow import (
    FISCAL_PAGE_SCRIPT,
    FISCAL_REPORT_URL,
    analysis_from_message,
    read_status,
    update_status,
    validate_pdf,
)


ECAC_URL = "https://cav.receita.fazenda.gov.br/eCAC/publico/login.aspx"
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
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Falha ao ler certificados.")

    data = json.loads(result.stdout.strip() or "[]")
    if isinstance(data, dict):
        data = [data]

    return sorted(
        [
            item
            for item in data
            if item.get("thumbprint")
        ],
        key=lambda item: item.get("subject", "").lower(),
    )


def choose_options() -> None:
    root = tk.Tk()
    root.title("Relatórios e-CAC")
    root.geometry("950x730")
    root.minsize(800, 630)

    area = tk.StringVar(value="Fiscal")
    browser_process: subprocess.Popen | None = None
    previous_capture = ""

    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame, text="Relatórios e-CAC", font=("Segoe UI", 20, "bold")
    ).pack(anchor="w")

    ttk.Label(
        frame, text="1. Escolha um certificado instalado no Windows"
    ).pack(anchor="w", pady=(16, 8))

    columns = ("subject", "expires", "issuer")
    table = ttk.Treeview(frame, columns=columns, show="headings", height=7)
    table.heading("subject", text="Titular")
    table.heading("expires", text="Validade")
    table.heading("issuer", text="Emissor")
    table.column("subject", width=430)
    table.column("expires", width=95, anchor="center")
    table.column("issuer", width=270)
    table.pack(fill="both", expand=True)

    certificate_status = tk.StringVar(value="Carregando certificados...")
    ttk.Label(frame, textvariable=certificate_status).pack(
        anchor="w", pady=(6, 0)
    )

    def refresh() -> None:
        for item_id in table.get_children():
            table.delete(item_id)

        try:
            certificates = list_certificates()
        except Exception as exc:
            certificate_status.set("Não foi possível ler os certificados.")
            messagebox.showerror("Certificados", str(exc), parent=root)
            return

        for certificate in certificates:
            table.insert(
                "",
                "end",
                iid=normalize_thumbprint(certificate["thumbprint"]),
                values=(
                    certificate.get("subject", ""),
                    certificate.get("expires", ""),
                    certificate.get("issuer", ""),
                ),
            )
        certificate_status.set(
            f"{len(certificates)} certificado(s) válido(s) com chave privada."
        )

    ttk.Button(frame, text="Atualizar lista", command=refresh).pack(
        anchor="w", pady=(8, 12)
    )

    ttk.Label(frame, text="2. Escolha a área").pack(anchor="w")
    areas = ttk.Frame(frame)
    areas.pack(anchor="w", pady=(8, 10))
    for name in ("Fiscal", "Contábil", "Jurídico"):
        ttk.Radiobutton(
            areas, text=name, value=name, variable=area
        ).pack(side="left", padx=(0, 20))

    report_description = tk.StringVar()
    action_label = tk.StringVar()
    ttk.Label(frame, textvariable=report_description).pack(
        anchor="w", pady=(0, 6)
    )

    summary_frame = ttk.LabelFrame(
        frame, text="Última verificação fiscal", padding=14
    )
    summary_frame.pack(fill="x", pady=(8, 12))

    taxpayer_var = tk.StringVar()
    registration_var = tk.StringVar()
    checked_var = tk.StringVar()
    portal_var = tk.StringVar()
    detail_var = tk.StringVar()
    caveat_var = tk.StringVar()
    download_var = tk.StringVar()
    file_var = tk.StringVar()
    activity_var = tk.StringVar(value="")

    ttk.Label(summary_frame, textvariable=taxpayer_var).pack(anchor="w")
    ttk.Label(summary_frame, textvariable=registration_var).pack(anchor="w")
    ttk.Label(
        summary_frame, text="Resultado da Análise",
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", pady=(8, 0))
    result_label = tk.Label(
        summary_frame, text="Sem verificação", anchor="w",
        font=("Segoe UI", 15, "bold"), fg="#555555"
    )
    result_label.pack(anchor="w", pady=(8, 4))
    for variable in (
        checked_var, portal_var, detail_var, caveat_var, download_var, file_var
    ):
        ttk.Label(
            summary_frame, textvariable=variable, wraplength=830
        ).pack(anchor="w", pady=(2, 0))

    def display_fiscal_status() -> None:
        data = read_status()
        result = data.get("result")
        if result not in ("Com pendência", "Sem pendência"):
            taxpayer_var.set("Nenhuma análise fiscal registrada neste computador.")
            registration_var.set("")
            result_label.config(text="Sem verificação", fg="#555555")
            checked_var.set("")
            portal_var.set("")
            detail_var.set("")
            caveat_var.set("")
            download_var.set("")
            file_var.set("")
            return

        name = data.get("taxpayer_name") or "Contribuinte não identificado"
        identifier = data.get("taxpayer_id") or ""
        taxpayer_var.set(f"{name}  {identifier}".strip())
        registration = data.get("registration_status") or ""
        registration_var.set(
            f"Situação cadastral: {registration}" if registration else ""
        )
        result_label.config(
            text=result,
            fg="#c62828" if result == "Com pendência" else "#188038",
        )
        checked_at = data.get("captured_at") or ""
        try:
            checked_at = datetime.fromisoformat(checked_at).strftime(
                "%d/%m/%Y %H:%M"
            )
        except ValueError:
            pass
        checked_var.set(f"Última consulta do aplicativo: {checked_at}")
        portal = data.get("portal_analysis") or ""
        portal_var.set(
            f"Análise exibida pelo portal na consulta: {portal}"
            if portal else ""
        )
        detail_var.set(data.get("summary") or "")
        caveat_var.set(
            "Esta análise não mostra fiscalizações em andamento, "
            "como a revisão de declarações (malha fiscal)."
        )

        download_text = {
            "aguardando": "PDF: aguardando acionamento do relatório.",
            "solicitado": "PDF: solicitação enviada ao portal.",
            "baixando": "PDF: download em andamento.",
            "concluido": "PDF: download concluído e arquivo validado.",
            "arquivo_invalido": "PDF: arquivo recebido sem cabeçalho PDF válido.",
            "interrompido": "PDF: download interrompido.",
        }
        download_state = data.get("download_state")
        download_message = download_text.get(
            download_state, "PDF: não verificado."
        )
        if download_state == "interrompido" and data.get("download_error"):
            download_message += f" Motivo: {data['download_error']}"
        download_var.set(download_message)
        report_path = data.get("report_path") or ""
        file_var.set(f"Arquivo: {report_path}" if report_path else "")

    def update_area_description(*_args) -> None:
        if area.get() == "Fiscal":
            action_label.set("Buscar relatório fiscal com este certificado")
            report_description.set(
                "Após o login, o aplicativo lê a análise e baixa o PDF."
            )
            if not summary_frame.winfo_manager():
                summary_frame.pack(fill="x", pady=(8, 12), before=action_button)
        else:
            action_label.set("Abrir e-CAC com este certificado")
            report_description.set(
                "Os relatórios desta área ainda precisam ser definidos."
            )
            summary_frame.pack_forget()

    def poll_browser() -> None:
        nonlocal browser_process
        display_fiscal_status()
        if browser_process is not None and browser_process.poll() is None:
            root.after(1000, poll_browser)
            return
        if browser_process is not None:
            code = browser_process.returncode
            latest = read_status().get("captured_at")
            if code:
                activity_var.set(f"Navegador encerrado com erro (código {code}).")
            elif latest and latest != previous_capture:
                activity_var.set("Consulta fiscal encerrada. Resultado atualizado.")
            else:
                activity_var.set("Navegador fechado sem nova análise fiscal.")
            browser_process = None
            action_button.state(["!disabled"])

    def confirm() -> None:
        nonlocal browser_process, previous_capture
        selection = table.selection()
        if not selection:
            messagebox.showwarning(
                "Certificado",
                "Selecione um certificado antes de continuar.",
                parent=root,
            )
            return

        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).resolve()))
        command.extend(("--browser", selection[0], area.get()))
        try:
            browser_process = subprocess.Popen(
                command, creationflags=subprocess.CREATE_NO_WINDOW
            )
        except OSError as exc:
            messagebox.showerror("Navegador", str(exc), parent=root)
            return

        previous_capture = read_status().get("captured_at") or ""
        activity_var.set(
            "Navegador aberto. Conclua a autenticação no portal."
        )
        action_button.state(["disabled"])
        root.after(1000, poll_browser)

    action_button = ttk.Button(
        frame, textvariable=action_label, command=confirm
    )
    action_button.pack(anchor="e")
    ttk.Label(frame, textvariable=activity_var).pack(
        anchor="w", pady=(8, 0)
    )

    area.trace_add("write", update_area_description)
    update_area_description()
    display_fiscal_status()
    refresh()
    root.mainloop()


def open_ecac(selected_thumbprint: str, area: str) -> None:
    chosen = normalize_thumbprint(selected_thumbprint)
    attached = False
    target_url = FISCAL_REPORT_URL if area == "Fiscal" else ECAC_URL

    window = webview.create_window(
        f"e-CAC — {area}",
        html="<html><body><h3>Preparando acesso ao e-CAC...</h3></body></html>",
        width=1250,
        height=850,
    )

    def attach_and_navigate(core) -> None:
        nonlocal attached
        if attached:
            return
        attached = True
        run_state = {
            "analysis_seen": False,
            "download_state": "",
            "report_path": "",
        }

        def on_certificate_requested(sender, args) -> None:
            host = str(args.Host).lower()
            allowed = (
                host == "gov.br"
                or host.endswith(".gov.br")
                or host == "fazenda.gov.br"
                or host.endswith(".fazenda.gov.br")
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
                "O certificado escolhido não está entre os aceitos "
                "nesta etapa do acesso. Nenhum outro foi utilizado.",
                "Certificado não encontrado",
            )

        def on_navigation_completed(sender, args) -> None:
            if area != "Fiscal" or not args.IsSuccess:
                return
            current = urlparse(str(sender.Source))
            if (
                current.hostname == "servicos.receitafederal.gov.br"
                and current.path.startswith("/servico/pendencias")
            ):
                sender.ExecuteScriptAsync(FISCAL_PAGE_SCRIPT)

        def on_web_message_received(sender, args) -> None:
            if area != "Fiscal":
                return
            current = urlparse(str(args.Source))
            if (
                current.hostname != "servicos.receitafederal.gov.br"
                or not current.path.startswith("/servico/pendencias")
            ):
                return
            try:
                raw = str(args.TryGetWebMessageAsString())
                if len(raw) > 5000:
                    return
                message = json.loads(raw)
            except Exception:
                return
            analysis = analysis_from_message(message)
            if analysis is not None:
                run_state["analysis_seen"] = True
                if run_state["download_state"]:
                    analysis["download_state"] = run_state["download_state"]
                    analysis["report_path"] = run_state["report_path"]
                update_status(**analysis)
            elif isinstance(message, dict) and message.get("kind") == (
                "fiscal_download_requested"
            ):
                run_state["download_state"] = "solicitado"
                if run_state["analysis_seen"]:
                    update_status(download_state="solicitado")

        def on_download_starting(sender, args) -> None:
            if area != "Fiscal":
                return
            operation = args.DownloadOperation
            mime_type = str(operation.MimeType).split(";", 1)[0].lower()
            suggested_path = Path(str(args.ResultFilePath))
            if (
                mime_type != "application/pdf"
                and suggested_path.suffix.lower() != ".pdf"
            ):
                return

            filename = (
                "RelatorioSituacaoFiscal-"
                f"{datetime.now():%Y%m%d-%H%M%S-%f}.pdf"
            )
            destination = suggested_path.with_name(filename)
            args.ResultFilePath = str(destination)
            args.Handled = True
            run_state["download_state"] = "baixando"
            run_state["report_path"] = str(destination)
            if run_state["analysis_seen"]:
                update_status(
                    download_state="baixando", report_path=str(destination)
                )

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
                if run_state["analysis_seen"]:
                    update_status(
                        download_state=run_state["download_state"],
                        report_path=str(destination),
                        download_error=run_state.get("download_error", ""),
                    )

            window._download_state_handlers.append(on_download_state_changed)
            operation.StateChanged += on_download_state_changed

        # Keep .NET event handlers alive for the browser session.
        window._certificate_handler = on_certificate_requested
        window._navigation_handler = on_navigation_completed
        window._message_handler = on_web_message_received
        window._download_handler = on_download_starting
        window._download_state_handlers = []
        core.ClientCertificateRequested += on_certificate_requested
        core.NavigationCompleted += on_navigation_completed
        core.WebMessageReceived += on_web_message_received
        core.DownloadStarting += on_download_starting
        core.Navigate(target_url)

    def on_before_show(browser_window) -> None:
        control = browser_window.native.webview

        def on_initialized(sender, args) -> None:
            if args.IsSuccess:
                attach_and_navigate(sender.CoreWebView2)
            else:
                from System.Windows.Forms import MessageBox

                MessageBox.Show(
                    str(args.InitializationException),
                    "Falha ao iniciar WebView2",
                )

        window._initialization_handler = on_initialized
        control.CoreWebView2InitializationCompleted += on_initialized

        if control.CoreWebView2 is not None:
            attach_and_navigate(control.CoreWebView2)

    window.events.before_show += on_before_show
    webview.start(gui="edgechromium", private_mode=True)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Este aplicativo requer Windows.")

    base_dir = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    bundled_runtime = base_dir / "WebView2Runtime"

    if bundled_runtime.is_dir():
        webview.settings["WEBVIEW2_RUNTIME_PATH"] = str(bundled_runtime)

    webview.settings["ALLOW_DOWNLOADS"] = True

    if len(sys.argv) == 4 and sys.argv[1] == "--browser":
        open_ecac(sys.argv[2], sys.argv[3])
    else:
        choose_options()


if __name__ == "__main__":
    main()