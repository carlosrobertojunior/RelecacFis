from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from auth_client import AuthSession
from branding import asset_path, set_window_icon
from fiscal_flow import read_status, validate_pdf


NAVY = "#193a61"
BLUE = "#24558d"
PALE = "#eef3fa"
TEXT = "#172b42"
MUTED = "#607286"
GREEN = "#21824b"
RED = "#bd3030"


def certificate_name(subject: str) -> str:
    match = re.search(r"(?:^|,)\s*CN=([^,]+)", subject, re.IGNORECASE)
    return match.group(1).strip() if match else subject


def certificate_id(subject: str) -> str:
    match = re.search(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", subject)
    return match.group(0) if match else ""


def display_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return value or ""


def choose_options(list_certificates, normalize_thumbprint,
                   session: AuthSession) -> None:
    root = tk.Tk()
    root.title("Consulta Fiscal e-CAC")
    root.geometry("1430x830")
    root.minsize(1120, 700)
    root.configure(bg=PALE)
    set_window_icon(root)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Certificates.Treeview", font=("Segoe UI", 10),
                    rowheight=42, background="white", fieldbackground="white",
                    foreground=TEXT, borderwidth=0)
    style.configure("Certificates.Treeview.Heading", font=("Segoe UI", 10, "bold"),
                    background="#edf2f8", foreground=TEXT, relief="flat")
    style.map("Certificates.Treeview", background=[("selected", BLUE)],
              foreground=[("selected", "white")])

    certificates: list[dict] = []
    browser_process: subprocess.Popen | None = None
    previous_capture = ""

    def close_app() -> None:
        if browser_process is not None and browser_process.poll() is None:
            browser_process.terminate()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_app)
    header = tk.Frame(root, bg=NAVY, height=88)
    header.pack(fill="x")
    header.pack_propagate(False)
    try:
        logo = tk.PhotoImage(file=str(asset_path("logo.png"))).subsample(6, 6)
        root.header_logo_image = logo
        tk.Label(header, image=logo, bg="white", padx=3, pady=3).pack(
            side="left", padx=(24, 0))
    except tk.TclError:
        pass
    tk.Label(header, text="CONSULTA FISCAL e-CAC", bg=NAVY, fg="white",
             font=("Segoe UI", 20, "bold")).pack(side="left", padx=(14, 0))
    tk.Button(header, text="Sair", command=close_app, bg=NAVY,
              fg="white", activebackground=BLUE, activeforeground="white",
              relief="flat", font=("Segoe UI", 10, "bold"),
              cursor="hand2").pack(side="right", padx=(0, 24))
    tk.Label(header, text=datetime.now().strftime("%d/%m/%Y"),
             bg=NAVY, fg="#e5eef8", font=("Segoe UI", 11)).pack(
                 side="right", padx=(0, 24))
    tk.Label(header, text=session.email, bg=NAVY, fg="#e5eef8",
             font=("Segoe UI", 10)).pack(side="right", padx=(0, 24))

    body = tk.Frame(root, bg=PALE)
    body.pack(fill="both", expand=True)

    sidebar = tk.Frame(body, bg="#e5edf8", width=190)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    tk.Frame(sidebar, bg=BLUE, height=5).pack(fill="x")
    tk.Label(sidebar, text="CONSULTA FISCAL", bg="#e5edf8", fg=NAVY,
             font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(28, 18))

    main = tk.Frame(body, bg=PALE, padx=24, pady=22)
    main.pack(side="left", fill="both", expand=True)
    main.grid_columnconfigure(0, weight=11, uniform="cards")
    main.grid_columnconfigure(1, weight=10, uniform="cards")
    main.grid_rowconfigure(1, weight=1)

    def nav_button(label: str, target) -> None:
        tk.Button(sidebar, text=label, command=target, anchor="w",
                  bg="#e5edf8", fg=NAVY, activebackground="#d1dff0",
                  relief="flat", font=("Segoe UI", 11), padx=20, pady=14,
                  cursor="hand2").pack(fill="x")

    tk.Label(main, text="CERTIFICADOS INSTALADOS NA MÁQUINA", bg=PALE,
             fg=TEXT, font=("Segoe UI", 15, "bold")).grid(
                 row=0, column=0, sticky="w", pady=(0, 10))
    tk.Label(main, text="RESULTADO DA ANÁLISE e-CAC", bg=PALE,
             fg=TEXT, font=("Segoe UI", 15, "bold")).grid(
                 row=0, column=1, sticky="w", padx=(18, 0), pady=(0, 10))

    left = tk.Frame(main, bg="white", highlightbackground="#d9e1ea",
                    highlightthickness=1, padx=20, pady=20)
    left.grid(row=1, column=0, sticky="nsew")
    right = tk.Frame(main, bg="white", highlightbackground="#d9e1ea",
                     highlightthickness=1, padx=22, pady=20)
    right.grid(row=1, column=1, sticky="nsew", padx=(18, 0))
    left.grid_columnconfigure(0, weight=1)
    left.grid_rowconfigure(3, weight=1)

    tk.Label(left, text="Selecione o certificado para consultar a Receita Federal",
             bg="white", fg=MUTED, font=("Segoe UI", 10)).grid(
                 row=0, column=0, sticky="w")
    search_var = tk.StringVar()
    search = tk.Entry(left, textvariable=search_var, font=("Segoe UI", 11),
                      relief="solid", bd=1)
    search.grid(row=1, column=0, sticky="ew", pady=(14, 12), ipady=8)
    search.insert(0, "")
    table_frame = tk.Frame(left, bg="white")
    table_frame.grid(row=3, column=0, sticky="nsew")
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    columns = ("subject", "identifier", "expires", "status")
    table = ttk.Treeview(table_frame, columns=columns, show="headings",
                         selectmode="browse", style="Certificates.Treeview")
    for key, title, width in (
        ("subject", "Titular", 245), ("identifier", "CNPJ/CPF", 145),
        ("expires", "Vencimento", 100), ("status", "Status", 75),
    ):
        table.heading(key, text=title)
        table.column(key, width=width, minwidth=70,
                     anchor="w" if key == "subject" else "center",
                     stretch=key == "subject")
    scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")

    certificate_status = tk.StringVar(value="Carregando certificados...")
    tk.Label(left, textvariable=certificate_status, bg="white", fg=MUTED,
             font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w",
                                         pady=(10, 3))
    selected_detail = tk.StringVar(value="Nenhum certificado selecionado.")
    tk.Label(left, textvariable=selected_detail, bg="white", fg=MUTED,
             wraplength=590, justify="left", font=("Segoe UI", 9)).grid(
                 row=5, column=0, sticky="w", pady=(0, 12))
    actions = tk.Frame(left, bg="white")
    actions.grid(row=6, column=0, sticky="ew")
    actions.grid_columnconfigure(0, weight=1)
    consult_button = tk.Button(actions, text="ANALISAR CERTIFICADO SELECIONADO",
                               bg=NAVY, fg="white", activebackground=BLUE,
                               activeforeground="white", relief="flat",
                               font=("Segoe UI", 10, "bold"), padx=14, pady=11,
                               cursor="hand2")
    consult_button.grid(row=0, column=0, sticky="ew")
    refresh_button = tk.Button(actions, text="Atualizar lista", bg="#e7eef7",
                               fg=NAVY, relief="flat", padx=12, pady=10,
                               font=("Segoe UI", 9), cursor="hand2")
    refresh_button.grid(row=0, column=1, padx=(9, 0))

    right.grid_columnconfigure(0, weight=1)
    tk.Label(right, text="DETALHES DO CERTIFICADO", bg="white", fg=TEXT,
             font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    cert_detail_var = tk.StringVar(value="Selecione um certificado na lista.")
    tk.Label(right, textvariable=cert_detail_var, bg="white", fg=MUTED,
             font=("Segoe UI", 10), wraplength=610, justify="left").grid(
                 row=1, column=0, sticky="w", pady=(10, 15))
    tk.Frame(right, bg="#dce4ed", height=1).grid(row=2, column=0, sticky="ew")
    tk.Label(right, text="STATUS E CONSULTA e-CAC", bg="white", fg=TEXT,
             font=("Segoe UI", 15, "bold")).grid(row=3, column=0,
                                                sticky="w", pady=(20, 10))
    result_label = tk.Label(right, text="Sem verificação", bg="white",
                            fg=MUTED, font=("Segoe UI", 20, "bold"))
    result_label.grid(row=4, column=0, sticky="w")
    taxpayer_var = tk.StringVar(value="Nenhuma análise fiscal registrada neste computador.")
    tk.Label(right, textvariable=taxpayer_var, bg="white", fg=TEXT,
             wraplength=610, justify="left", font=("Segoe UI", 11)).grid(
                 row=5, column=0, sticky="w", pady=(8, 4))
    registration_var = tk.StringVar()
    tk.Label(right, textvariable=registration_var, bg="white", fg=MUTED,
             font=("Segoe UI", 10)).grid(row=6, column=0, sticky="w")

    status_card = tk.Frame(right, bg="#f5f8fc", highlightbackground="#dce4ed",
                           highlightthickness=1, padx=17, pady=14)
    status_card.grid(row=7, column=0, sticky="ew", pady=(20, 12))
    status_card.grid_columnconfigure(0, weight=1)
    tk.Label(status_card, text="DADOS DA ÚLTIMA CONSULTA NO e-CAC",
             bg="#f5f8fc", fg=TEXT, font=("Segoe UI", 11, "bold")).grid(
                 row=0, column=0, sticky="w")
    checked_var = tk.StringVar(value="Ainda não consultado")
    tk.Label(status_card, textvariable=checked_var, bg="#f5f8fc", fg=NAVY,
             font=("Segoe UI", 16, "bold")).grid(row=1, column=0,
                                                sticky="w", pady=(8, 3))
    portal_var = tk.StringVar()
    summary_var = tk.StringVar()
    for row, variable in ((2, portal_var), (3, summary_var)):
        tk.Label(status_card, textvariable=variable, bg="#f5f8fc",
                 fg=TEXT, wraplength=570, justify="left",
                 font=("Segoe UI", 10)).grid(row=row, column=0,
                                             sticky="w", pady=(3, 0))

    download_var = tk.StringVar(value="PDF: ainda não verificado.")
    tk.Label(right, textvariable=download_var, bg="white", fg=TEXT,
             wraplength=610, justify="left", font=("Segoe UI", 10, "bold")).grid(
                 row=8, column=0, sticky="w", pady=(4, 3))
    probe_var = tk.StringVar()
    tk.Label(right, textvariable=probe_var, bg="white", fg=MUTED,
             wraplength=610, justify="left", font=("Segoe UI", 9)).grid(
                 row=9, column=0, sticky="w")
    file_var = tk.StringVar()
    tk.Label(right, textvariable=file_var, bg="white", fg=MUTED,
             wraplength=610, justify="left", font=("Segoe UI", 9)).grid(
                 row=10, column=0, sticky="w", pady=(5, 0))
    tk.Label(right, text="A análise não mostra fiscalizações em andamento, como a malha fiscal.",
             bg="white", fg=MUTED, wraplength=610, justify="left",
             font=("Segoe UI", 9)).grid(row=11, column=0,
                                        sticky="w", pady=(18, 0))
    right.grid_rowconfigure(12, weight=1)
    pdf_actions = tk.Frame(right, bg="white")
    pdf_actions.grid(row=13, column=0, sticky="e")
    folder_button = tk.Button(pdf_actions, text="ABRIR PASTA DO PDF",
                              bg="#e7eef7", fg=NAVY, relief="flat",
                              font=("Segoe UI", 10, "bold"),
                              padx=13, pady=10, cursor="hand2")
    folder_button.pack(side="left", padx=(0, 8))
    open_pdf_button = tk.Button(pdf_actions, text="ABRIR PDF",
                                bg=NAVY, fg="white", activebackground=BLUE,
                                activeforeground="white", relief="flat",
                                font=("Segoe UI", 10, "bold"),
                                padx=15, pady=10, cursor="hand2")
    open_pdf_button.pack(side="left")

    activity_var = tk.StringVar(value="Selecione um certificado e inicie a consulta.")
    tk.Label(main, textvariable=activity_var, bg=PALE, fg=MUTED,
             font=("Segoe UI", 9)).grid(row=2, column=0, columnspan=2,
                                        sticky="w", pady=(12, 0))

    tk.Label(
        root,
        text="\u00a9 2026 CARLOS ROBERTO FELICIO JUNIOR. Todos os direitos reservados.",
        bg=PALE, fg=MUTED, font=("Segoe UI", 8),
    ).pack(pady=(0, 8))

    def selected_certificate() -> dict | None:
        selection = table.selection()
        return next((item for item in certificates
                     if normalize_thumbprint(item["thumbprint"]) ==
                     (selection[0] if selection else "")), None)

    def show_selected(_event=None) -> None:
        item = selected_certificate()
        if not item:
            selected_detail.set("Nenhum certificado selecionado.")
            cert_detail_var.set("Selecione um certificado na lista.")
            return
        name = certificate_name(item.get("subject", ""))
        issuer = certificate_name(item.get("issuer", ""))
        selected_detail.set(f"Titular: {name}\nEmissor: {issuer}")
        cert_detail_var.set(
            f"Titular: {name}\nCNPJ/CPF: {certificate_id(item.get('subject', '')) or 'Não identificado'}"
            f"     Validade: {item.get('expires', '')}\nEmissor: {issuer}"
        )

    def apply_filter(*_args) -> None:
        selected = table.selection()
        for iid in table.get_children():
            table.delete(iid)
        query = search_var.get().casefold().strip()
        for item in certificates:
            subject = item.get("subject", "")
            issuer = item.get("issuer", "")
            identifier = certificate_id(subject)
            if query and query not in f"{subject} {issuer} {identifier}".casefold():
                continue
            iid = normalize_thumbprint(item["thumbprint"])
            table.insert("", "end", iid=iid, values=(
                certificate_name(subject), identifier,
                item.get("expires", ""), "Válido",
            ))
        if selected and table.exists(selected[0]):
            table.selection_set(selected[0])
        show_selected()

    def refresh() -> None:
        nonlocal certificates
        try:
            certificates = list_certificates()
        except Exception as exc:
            certificate_status.set("Não foi possível ler os certificados.")
            messagebox.showerror("Certificados", str(exc), parent=root)
            return
        apply_filter()
        certificate_status.set(
            f"{len(certificates)} certificado(s) válido(s) com chave privada."
        )

    def display_status() -> None:
        data = read_status()
        result = data.get("result")
        if result in ("Com pendência", "Sem pendência"):
            result_label.configure(text=result,
                                   fg=RED if result == "Com pendência" else GREEN)
            taxpayer_var.set(
                f"{data.get('taxpayer_name') or 'Contribuinte não identificado'}  "
                f"{data.get('taxpayer_id') or ''}".strip()
            )
            registration = data.get("registration_status") or ""
            registration_var.set(
                f"Situação cadastral: {registration}" if registration else ""
            )
            checked_var.set(display_date(data.get("captured_at", "")))
            portal_var.set(data.get("portal_analysis") or "")
            summary_var.set(data.get("summary") or "")
        else:
            result_label.configure(text="Sem verificação", fg=MUTED)
            taxpayer_var.set("Nenhuma análise fiscal registrada neste computador.")
            registration_var.set("")
            checked_var.set("Ainda não consultado")
            portal_var.set("")
            summary_var.set("")

        download_state = data.get("download_state")
        messages = {
            "aguardando": "PDF: aguardando o botão do relatório.",
            "solicitado": "PDF: botão acionado; aguardando o download.",
            "baixando": "PDF: download em andamento.",
            "concluido": "PDF: download concluído e arquivo validado.",
            "arquivo_invalido": "PDF: arquivo recebido, mas não é um PDF válido.",
            "interrompido": "PDF: download interrompido.",
            "erro_clique": "PDF: não foi possível acionar o botão.",
        }
        download_var.set(messages.get(download_state, "PDF: ainda não verificado."))
        probe = data.get("probe") or {}
        if probe:
            button_text = "encontrado" if probe.get("button_found") else "não encontrado"
            analysis_text = "lida" if probe.get("analysis_found") else "ainda não lida"
            probe_var.set(
                f"Portal: botão {button_text}; análise {analysis_text}. "
                f"Página: {probe.get('path') or '/'}"
            )
        else:
            stage_messages = {
                "abrindo_autenticacao_ecac": "Abrindo autentica\u00e7\u00e3o do e-CAC.",
                "aguardando_autenticacao_ecac": (
                    "Conclua a verifica\u00e7\u00e3o de seguran\u00e7a e entre com gov.br."
                ),
                "aguardando_login_govbr": (
                    "Conclua o login no gov.br e selecione o certificado."
                ),
                "abrindo_relatorio_fiscal": (
                    "Acesso conclu\u00eddo. Abrindo Minhas D\u00edvidas e Pend\u00eancias."
                ),
                "consulta_fiscal_aberta": "Aguardando an\u00e1lise e relat\u00f3rio fiscal.",
                "falha_na_navegacao": "A p\u00e1gina n\u00e3o abriu. Verifique a conex\u00e3o.",
            }
            probe_var.set(stage_messages.get(data.get("phase"), ""))
        if data.get("automation_error"):
            probe_var.set(
                f"{probe_var.get()} Erro de automa\u00e7\u00e3o: "
                f"{data['automation_error']}"
            )
        report_path = data.get("report_path") or ""
        file_var.set(f"Arquivo: {report_path}" if report_path else "")
        valid = download_state == "concluido" and validate_pdf(Path(report_path))
        open_pdf_button.config(state="normal" if valid else "disabled")
        folder_button.config(state="normal" if valid else "disabled")
        if download_state == "interrompido" and data.get("download_error"):
            activity_var.set(f"Download interrompido: {data['download_error']}")

    def open_pdf() -> None:
        path = Path(read_status().get("report_path") or "")
        if validate_pdf(path):
            os.startfile(path)

    def open_folder() -> None:
        path = Path(read_status().get("report_path") or "")
        if validate_pdf(path):
            os.startfile(path.parent)

    def poll_browser() -> None:
        nonlocal browser_process
        display_status()
        if browser_process is not None and browser_process.poll() is None:
            root.after(1000, poll_browser)
            return
        if browser_process is not None:
            code = browser_process.returncode
            data = read_status()
            if code:
                activity_var.set(f"Navegador encerrado com erro (código {code}).")
            elif data.get("download_state") == "concluido":
                activity_var.set("Consulta encerrada. PDF validado e disponível.")
            elif data.get("captured_at") != previous_capture:
                activity_var.set("Análise atualizada. O PDF ainda não foi validado.")
            else:
                activity_var.set("Navegador fechado sem nova análise fiscal.")
            browser_process = None
            consult_button.config(state="normal")

    def consult() -> None:
        nonlocal browser_process, previous_capture
        item = selected_certificate()
        if item is None:
            messagebox.showwarning("Certificado",
                                   "Selecione um certificado antes de continuar.",
                                   parent=root)
            return
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).resolve().parent / "app.py"))
        command.extend(("--browser", normalize_thumbprint(item["thumbprint"])))
        try:
            environment = os.environ.copy()
            environment["RELATORIOS_ECAC_SESSION_TOKEN"] = session.token
            environment["RELATORIOS_ECAC_ACCOUNT"] = session.email
            browser_process = subprocess.Popen(
                command, creationflags=subprocess.CREATE_NO_WINDOW,
                env=environment,
            )
        except OSError as exc:
            messagebox.showerror("Navegador", str(exc), parent=root)
            return
        previous_capture = read_status().get("captured_at") or ""
        activity_var.set("Navegador aberto. Conclua a autenticação no portal.")
        consult_button.config(state="disabled")
        root.after(1000, poll_browser)

    search_var.trace_add("write", apply_filter)
    table.bind("<<TreeviewSelect>>", show_selected)
    refresh_button.config(command=refresh)
    consult_button.config(command=consult)
    open_pdf_button.config(command=open_pdf, state="disabled")
    folder_button.config(command=open_folder, state="disabled")
    nav_button("Buscar certificados", search.focus_set)
    nav_button("Análise e status", lambda: result_label.focus_set())
    display_status()
    refresh()
    root.mainloop()
