from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


FISCAL_REPORT_URL = "https://servicos.receitafederal.gov.br/servico/pendencias/"

FISCAL_PAGE_SCRIPT = r"""
(() => {
    if (window.__relatoriosEcacFiscalObserver) return;

    const normalize = value => String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();

    const send = data => {
        if (window.chrome?.webview) {
            window.chrome.webview.postMessage(JSON.stringify(data));
        }
    };
    const linesFromPage = () => (document.body?.innerText || "")
        .split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const valueAfter = (lines, label) => {
        const index = lines.findIndex(line => normalize(line).startsWith(label));
        return index >= 0 ? (lines[index + 1] || "") : "";
    };
    const readAnalysis = () => {
        const lines = linesFromPage();
        const resultIndex = lines.findIndex(
            line => normalize(line).includes("resultado da analise")
        );
        if (resultIndex < 0) return null;
        const analysisLines = lines.slice(resultIndex + 1, resultIndex + 24);
        const resultLine = analysisLines.find(line => {
            const text = normalize(line);
            return text === "com pendencia" || text === "sem pendencia";
        });
        if (!resultLine) return null;
        const result = normalize(resultLine) === "com pendencia"
            ? "Com pend\u00eancia" : "Sem pend\u00eancia";
        const dataIndex = lines.findIndex(
            line => normalize(line).includes("dados cadastrais")
        );
        const dataLines = dataIndex < 0 ? [] : lines.slice(
            dataIndex + 1, resultIndex > dataIndex ? resultIndex : dataIndex + 20
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
    const findDownloadButton = () => {
        const controls = document.querySelectorAll(
            'button, a, input[type="button"], input[type="submit"], [role="button"]'
        );
        for (const control of controls) {
            const labels = [
                control.innerText, control.textContent, control.value,
                control.getAttribute("aria-label"), control.getAttribute("title")
            ];
            if (labels.some(label => normalize(label).includes("baixar relatorio"))) {
                return control;
            }
        }
        return null;
    };

    let lastAnalysis = "";
    let lastProbe = "";
    let clicked = false;
    const scan = () => {
        const analysis = readAnalysis();
        if (analysis) {
            const fingerprint = JSON.stringify(analysis);
            if (fingerprint !== lastAnalysis) {
                lastAnalysis = fingerprint;
                send(analysis);
            }
        }
        const button = findDownloadButton();
        const probe = {
            kind: "fiscal_probe",
            path: location.pathname,
            analysis_found: Boolean(analysis),
            button_found: Boolean(button),
            click_attempted: clicked
        };
        const probeKey = JSON.stringify(probe);
        if (probeKey !== lastProbe) {
            lastProbe = probeKey;
            send(probe);
        }
        if (!button || button.disabled || clicked) return;
        clicked = true;
        send({kind: "fiscal_download_requested", path: location.pathname});
        try {
            button.click();
        } catch (error) {
            send({kind: "fiscal_click_error", error: String(error).slice(0, 200)});
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
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    account = os.environ.get("RELATORIOS_ECAC_ACCOUNT", "").strip().lower()
    if account:
        digest = hashlib.sha256(account.encode("utf-8")).hexdigest()[:20]
        return base / "RelatoriosECAC" / f"ultimo_fiscal-{digest}.json"
    return base / "RelatoriosECAC" / "ultimo_fiscal.json"


def read_status() -> dict:
    try:
        data = json.loads(status_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_status(**changes) -> dict:
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
    if result not in ("Com pend\u00eancia", "Sem pend\u00eancia"):
        return None
    fields = (
        "portal_analysis", "summary", "taxpayer_name",
        "taxpayer_id", "registration_status",
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
            return stream.read(5) == b"%PDF-"
    except OSError:
        return False
