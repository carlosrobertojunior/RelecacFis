from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from auth_client import AuthClient, AuthSession, AuthenticationError, normalize_email
from branding import asset_path, set_window_icon


NAVY = "#193a61"
BLUE = "#24558d"
MUTED = "#607286"
RED = "#bd3030"
GREEN = "#21824b"
COPYRIGHT = "\u00a9 2026 CARLOS ROBERTO FELICIO JUNIOR. Todos os direitos reservados."


def show_login(client: AuthClient) -> AuthSession | None:
    root = tk.Tk()
    root.title("Acesso - Consulta Fiscal e-CAC")
    root.geometry("540x700")
    root.minsize(480, 650)
    root.configure(bg="#eef3fa")
    set_window_icon(root)

    result: AuthSession | None = None
    requested_email = ""
    pending: queue.Queue = queue.Queue()
    busy = False

    shell = tk.Frame(root, bg="white", padx=38, pady=24,
                     highlightbackground="#d9e1ea", highlightthickness=1)
    shell.pack(fill="both", expand=True, padx=32, pady=26)

    try:
        logo = tk.PhotoImage(file=str(asset_path("logo.png"))).subsample(3, 3)
        root.logo_image = logo
        tk.Label(shell, image=logo, bg="white").pack(pady=(0, 8))
    except tk.TclError:
        pass

    tk.Label(shell, text="ACESSO AO SISTEMA", bg="white", fg=NAVY,
             font=("Segoe UI", 17, "bold")).pack(pady=(0, 6))
    tk.Label(
        shell,
        text="Informe o e-mail cadastrado para receber um c\u00f3digo tempor\u00e1rio.",
        bg="white", fg=MUTED, font=("Segoe UI", 10),
        wraplength=410, justify="center",
    ).pack(pady=(0, 24))

    form = tk.Frame(shell, bg="white")
    form.pack(fill="x")
    tk.Label(form, text="E-mail", bg="white", fg=NAVY,
             font=("Segoe UI", 10, "bold")).pack(anchor="w")
    email_var = tk.StringVar()
    email_entry = ttk.Entry(form, textvariable=email_var, font=("Segoe UI", 11))
    email_entry.pack(fill="x", pady=(7, 13), ipady=6)

    send_button = tk.Button(form, text="ENVIAR C\u00d3DIGO",
                            bg=NAVY, fg="white", activebackground=BLUE,
                            activeforeground="white", relief="flat",
                            font=("Segoe UI", 10, "bold"), pady=10,
                            cursor="hand2")
    send_button.pack(fill="x")

    code_frame = tk.Frame(form, bg="white")
    tk.Label(code_frame, text="C\u00f3digo de 6 d\u00edgitos",
             bg="white", fg=NAVY,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(20, 0))
    code_var = tk.StringVar()
    code_entry = ttk.Entry(code_frame, textvariable=code_var,
                           font=("Segoe UI", 13), justify="center")
    code_entry.pack(fill="x", pady=(7, 12), ipady=6)
    enter_button = tk.Button(code_frame, text="VALIDAR E ENTRAR",
                             bg=GREEN, fg="white", activebackground="#176b3b",
                             activeforeground="white", relief="flat",
                             font=("Segoe UI", 10, "bold"), pady=10,
                             cursor="hand2")
    enter_button.pack(fill="x")
    change_button = tk.Button(code_frame, text="Usar outro e-mail",
                              bg="white", fg=BLUE, relief="flat",
                              font=("Segoe UI", 9), pady=8,
                              cursor="hand2")
    change_button.pack()

    message_var = tk.StringVar()
    message_label = tk.Label(
        shell, textvariable=message_var, bg="white", fg=MUTED,
        font=("Segoe UI", 9), wraplength=410, justify="center",
    )
    message_label.pack(pady=(16, 0))

    tk.Label(
        root, text=COPYRIGHT, bg="#eef3fa", fg=MUTED,
        font=("Segoe UI", 8),
    ).pack(pady=(0, 10))

    def set_busy(value: bool) -> None:
        nonlocal busy
        busy = value
        state = "disabled" if value else "normal"
        send_button.config(state=state)
        enter_button.config(state=state)
        change_button.config(state=state)

    def run_background(kind: str, action) -> None:
        if busy:
            return
        set_busy(True)
        message_var.set("Aguarde...")
        message_label.config(fg=MUTED)

        def worker() -> None:
            try:
                value = action()
                pending.put((kind, value, None))
            except Exception as exc:
                pending.put((kind, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def send_code() -> None:
        nonlocal requested_email
        email = normalize_email(email_var.get())
        if not email:
            message_var.set("Informe um e-mail v\u00e1lido.")
            message_label.config(fg=RED)
            return
        requested_email = email
        run_background("sent", lambda: client.request_code(email))

    def verify_code() -> None:
        if not requested_email:
            return
        code = code_var.get().strip()
        run_background("verified", lambda: client.verify_code(requested_email, code))

    def change_email() -> None:
        nonlocal requested_email
        requested_email = ""
        code_var.set("")
        code_frame.pack_forget()
        email_entry.config(state="normal")
        email_entry.focus_set()
        message_var.set("")

    def poll_queue() -> None:
        nonlocal result
        try:
            while True:
                kind, value, error = pending.get_nowait()
                set_busy(False)
                if error is not None:
                    message_var.set(
                        str(error) if isinstance(error, AuthenticationError)
                        else "Falha inesperada no servi\u00e7o de login."
                    )
                    message_label.config(fg=RED)
                elif kind == "sent":
                    email_entry.config(state="disabled")
                    if not code_frame.winfo_manager():
                        code_frame.pack(fill="x")
                    message_var.set(
                        "Se o e-mail estiver autorizado, o c\u00f3digo chegar\u00e1 "
                        "em alguns instantes. Verifique tamb\u00e9m o spam."
                    )
                    message_label.config(fg=GREEN)
                    code_entry.focus_set()
                elif kind == "verified":
                    result = value
                    root.destroy()
                    return
        except queue.Empty:
            pass
        if root.winfo_exists():
            root.after(100, poll_queue)

    send_button.config(command=send_code)
    enter_button.config(command=verify_code)
    change_button.config(command=change_email)
    email_entry.bind("<Return>", lambda _event: send_code())
    code_entry.bind("<Return>", lambda _event: verify_code())
    root.after(100, poll_queue)
    email_entry.focus_set()
    root.mainloop()
    return result
