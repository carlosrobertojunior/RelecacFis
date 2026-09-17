from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


FISCAL_REPORT_URL = "https://servicos.receitafederal.gov.br/servico/pendencias/"

FISCAL_PAGE_SCRIPT = r"""
(() => {
    if (window.__relatoriosEcacFiscalObserver) return;

    const normalize = value => (value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();

    const linesFromPage = () => (document.body?.innerText || "")
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(Boolean);

    const valueAfter = (lines, label) => {
        const index = lines.findIndex(line => normalize(line).startsWith(label));
        return index >= 0 ? (lines[index + 1] || "") : "";
    };

    const readAnalysis = () => {
        const lines = linesFromPage();
        const resultIndex = lines.findIndex(
            line => normalize(line) === "resultado da analise"
        );
        if (resultIndex < 0) return null;

        const analysisLines = lines.slice(resultIndex + 1, resultIndex + 20);
        const result = analysisLines.find(line => {
            const text = normalize(line);
            return text === "com pendencia" || text === "sem pendencia";
        });
        if (!result) return null;

        const dataIndex = lines.findIndex(
            line => normalize(line) === "dados cadastrais"
        );
        const dataLines = dataIndex < 0 ? [] : lines.slice(
            dataIndex + 1,
            resultIndex > dataIndex ? resultIndex : dataIndex + 20
        );
        const analysisTime = analysisLines.find(
            line => normalize(line).startsWith("analise realizada")
        ) || "";
        const summary = analysisLines.find(line => {
            const text = normalize(line);
            return text.startsWith("existe pendencia") ||
                text.startsWith("nao existe pendencia");
        }) || "";

        return {
            kind: "fiscal_analysis",
            result,
            portal_analysis: analysisTime,
            summary,
            taxpayer_name: valueAfter(dataLines, "nome"),
            taxpayer_id: valueAfter(dataLines, "cnpj") ||
                valueAfter(dataLines, "cpf"),
            registration_status: valueAfter(dataLines, "situacao cadastral")
        };
    };

    const send = data => {
        if (window.chrome?.webview) {
            window.chrome.webview.postMessage(JSON.stringify(data));
        }
    };

    let lastAnalysis = "";
    const scan = () => {
        const analysis = readAnalysis();
        if (analysis) {
            const fingerprint = JSON.stringify(analysis);
            if (fingerprint !== lastAnalysis) {
                lastAnalysis = fingerprint;
                send(analysis);
            }
        }

        if (!analysis) return;
        if (sessionStorage.getItem("relatoriosEcacFiscalDownloaded")) return;
        const controls = document.querySelectorAll(
            'button, a, input[type="button"], input[type="submit"], [role="button"]'
        );
        for (const control of controls) {
            const label = normalize(
                control.innerText || control.textContent ||
                control.value || control.getAttribute("aria-label")
            );
            if (label === "baixar relatorio" && !control.disabled) {
                sessionStorage.setItem("relatoriosEcacFiscalDownloaded", "1");
                send({kind: "fiscal_download_requested"});
                control.click();
                return;
            }
        }
    };

    const observer = new MutationObserver(scan);
    window.__relatoriosEcacFiscalObserver = observer;
    observer.observe(document.documentElement, {
        childList: true, subtree: true, characterData: true, attributes: true
    });
    scan();
})();
"""


def status_file() -> Path:
    override = os.environ.get("RELATORIOS_ECAC_STATUS_PATH")
    if override:
        return Path(override)
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "RelatoriosECAC" / "ultimo_fiscal.json"


def read_status() -> dict:
    try:
        data = json.loads(status_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_status(**changes: str) -> dict:
    data = read_status()
    data.update(changes)
    path = status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
    return data


def analysis_from_message(message: object) -> dict | None:
    if not isinstance(message, dict) or message.get("kind") != "fiscal_analysis":
        return None
    result = message.get("result")
    if result not in ("Com pendência", "Sem pendência"):
        return None

    fields = (
        "portal_analysis",
        "summary",
        "taxpayer_name",
        "taxpayer_id",
        "registration_status",
    )
    analysis = {key: str(message.get(key) or "")[:300] for key in fields}
    analysis["result"] = result
    analysis["captured_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    analysis["download_state"] = "aguardando"
    analysis["report_path"] = ""
    return analysis


def validate_pdf(path: Path) -> bool:
    try:
        if path.stat().st_size < 5:
            return False
        with path.open("rb") as stream:
            return b"%PDF-" in stream.read(1024)
    except OSError:
        return False

