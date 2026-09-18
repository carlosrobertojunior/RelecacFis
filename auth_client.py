from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw/edit"
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CODE_PATTERN = re.compile(r"^\d{6}$")
MAX_RESPONSE_BYTES = 16_384


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSession:
    email: str
    token: str


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    return email if len(email) <= 254 and EMAIL_PATTERN.fullmatch(email) else ""


def auth_config_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        path = Path(local) / "RelatoriosECAC" / "auth_config.json"
        if path.is_file():
            return path
    program = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    return program / "auth_config.json"


def load_endpoint() -> str:
    value = os.environ.get("RELATORIOS_ECAC_AUTH_URL", "").strip()
    if not value:
        path = auth_config_path()
        try:
            value = str(
                json.loads(path.read_text(encoding="utf-8-sig"))
                .get("web_app_url", "")
            ).strip()
        except (FileNotFoundError, OSError, ValueError, AttributeError):
            raise AuthenticationError(
                "Login ainda n\u00e3o configurado. Publique apps_script/Code.gs "
                "e informe a URL /exec em auth_config.json."
            ) from None
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "script.google.com"
        or not re.fullmatch(r"/macros/s/[A-Za-z0-9_-]+/exec", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise AuthenticationError(
            "A URL de autentica\u00e7\u00e3o deve ser a URL /exec "
            "publicada pelo Google Apps Script."
        )
    return value


class AuthClient:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    @classmethod
    def from_config(cls) -> "AuthClient":
        return cls(load_endpoint())

    def _post(self, payload: dict) -> dict:
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_host = urlparse(
                    str(getattr(response, "url", self.endpoint))
                ).hostname
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthenticationError(
                    "O Apps Script exige login Google. Na implanta\u00e7\u00e3o, "
                    "defina Quem tem acesso: Qualquer pessoa."
                ) from exc
            if exc.code == 404:
                raise AuthenticationError(
                    "Implanta\u00e7\u00e3o do Apps Script n\u00e3o encontrada. "
                    "Confira se a URL /exec foi copiada integralmente "
                    "e se a implanta\u00e7\u00e3o est\u00e1 ativa."
                ) from exc
            raise AuthenticationError(
                "N\u00e3o foi poss\u00edvel contatar o servi\u00e7o de login."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise AuthenticationError(
                "N\u00e3o foi poss\u00edvel contatar o servi\u00e7o de login."
            ) from exc
        if response_host == "accounts.google.com":
            raise AuthenticationError(
                "O Apps Script exige login Google. Na implanta\u00e7\u00e3o, "
                "defina Quem tem acesso: Qualquer pessoa."
            )
        if len(body) > MAX_RESPONSE_BYTES:
            raise AuthenticationError("Resposta de login maior que o esperado.")
        try:
            result = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise AuthenticationError(
                "A URL de login n\u00e3o retornou dados v\u00e1lidos. "
                "Confira a implanta\u00e7\u00e3o do Apps Script."
            ) from exc
        if not isinstance(result, dict):
            raise AuthenticationError("Resposta de login inv\u00e1lida.")
        return result

    def request_code(self, email: str) -> None:
        email = normalize_email(email)
        if not email:
            raise AuthenticationError("Informe um e-mail v\u00e1lido.")
        result = self._post({"action": "request", "email": email})
        if not result.get("ok"):
            error = result.get("error")
            if error == "invalid_email":
                raise AuthenticationError("Informe um e-mail v\u00e1lido.")
            raise AuthenticationError(
                "O servi\u00e7o de login n\u00e3o conseguiu enviar o c\u00f3digo."
            )

    def verify_code(self, email: str, code: str) -> AuthSession:
        email = normalize_email(email)
        code = str(code or "").strip()
        if not email or not CODE_PATTERN.fullmatch(code):
            raise AuthenticationError("Digite o c\u00f3digo de 6 d\u00edgitos.")
        result = self._post({
            "action": "verify", "email": email, "code": code,
        })
        if not result.get("ok"):
            raise AuthenticationError(
                "C\u00f3digo inv\u00e1lido ou expirado. Solicite outro se necess\u00e1rio."
            )
        token = result.get("token")
        returned_email = normalize_email(result.get("email", ""))
        if not isinstance(token, str) or not token or returned_email != email:
            raise AuthenticationError("Resposta de verifica\u00e7\u00e3o inv\u00e1lida.")
        return AuthSession(email=email, token=token)

    def validate_session(self, token: str) -> str:
        if not token or len(token) > 2048:
            raise AuthenticationError("Fa\u00e7a login antes de consultar o e-CAC.")
        result = self._post({"action": "validate", "token": token})
        email = normalize_email(result.get("email", ""))
        if not result.get("ok") or not email:
            raise AuthenticationError(
                "A sess\u00e3o expirou ou a conta perdeu acesso. Fa\u00e7a login novamente."
            )
        return email
