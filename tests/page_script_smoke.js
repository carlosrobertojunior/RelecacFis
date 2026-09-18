const assert = require("node:assert/strict");
const vm = require("node:vm");
const {execFileSync} = require("node:child_process");

const script = execFileSync("py", ["-3.14", "-c",
  "from fiscal_flow import FISCAL_PAGE_SCRIPT; print(FISCAL_PAGE_SCRIPT)"
], {encoding: "utf8"});

function run(bodyText) {
  const messages = [];
  let clicks = 0;
  const button = {
    innerText: "Baixar Relat\u00f3rio",
    textContent: "",
    value: "",
    disabled: false,
    getAttribute: () => null,
    click: () => { clicks++; }
  };
  const context = {
    window: {chrome: {webview: {postMessage: x => messages.push(JSON.parse(x))}}},
    document: {
      body: {innerText: bodyText},
      documentElement: {},
      querySelectorAll: () => [button]
    },
    location: {pathname: "/pagina-autenticada"},
    MutationObserver: class { observe() {} }
  };
  vm.runInNewContext(script, context);
  return {messages, clicks};
}

const withoutAnalysis = run("Minha p\u00e1gina");
assert.equal(withoutAnalysis.clicks, 1);
assert.ok(withoutAnalysis.messages.some(x => x.kind === "fiscal_download_requested"));
assert.ok(withoutAnalysis.messages.some(x => x.kind === "fiscal_probe" && x.button_found));

const withAnalysis = run(
  "Dados Cadastrais\nNome\nEmpresa Teste\nCNPJ\n00.000.000/0001-00\n" +
  "Resultado da An\u00e1lise\nCom pend\u00eancia\nAn\u00e1lise realizada hoje\n"
);
assert.equal(withAnalysis.clicks, 1);
assert.ok(withAnalysis.messages.some(x =>
  x.kind === "fiscal_analysis" && x.result === "Com pend\u00eancia"
));
console.log("Page script: button clicked with and without readable analysis.");
