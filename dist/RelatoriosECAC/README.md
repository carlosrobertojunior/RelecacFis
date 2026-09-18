# Consulta Fiscal e-CAC

Aplicativo Windows para selecionar um certificado instalado, acessar o e-CAC, ler o resultado de Minhas Dividas e Pendencias e baixar o relatorio PDF. Antes da selecao do certificado, o usuario precisa validar um codigo enviado ao e-mail autorizado na planilha.

## Publicar o servico de login

1. Abra a [planilha de contas](https://docs.google.com/spreadsheets/d/1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw/edit?gid=0#gid=0) na conta Google que enviara os e-mails. Na aba `Dados`, mantenha `EMAIL` em A1 e coloque um endereco autorizado por linha na coluna A.
2. Abra **Extensoes > Apps Script**. Substitua o conteudo de `Code.gs` pelo arquivo [apps_script/Code.gs](apps_script/Code.gs) deste projeto e salve.
3. No editor, selecione `setupAuth`, clique em **Executar** e autorize o acesso a planilha e envio de e-mails. Essa etapa cria o segredo de assinatura nas propriedades privadas do script.
O envio usa `MailApp` com a autorizacao da conta Google no Apps Script. Nenhuma senha de app e necessaria ou armazenada no projeto.

4. Clique em **Implantar > Nova implantacao > Aplicativo da Web**. Escolha **Executar como: eu** (a conta proprietaria) e **Quem tem acesso: qualquer pessoa**. Copie a URL terminada em `/exec`. A verificacao dos e-mails e feita apenas pelo script; a planilha nao precisa ser publica.
O link do editor do projeto (`script.google.com/.../home/projects/.../edit`) nao e a URL de acesso do aplicativo. Se o projeto ja estiver publicado, abra **Implantar > Gerenciar implantacoes**, selecione a implantacao ativa do tipo **Aplicativo da Web** e copie a **URL do aplicativo da Web** terminada em `/exec`. A URL `/dev` de teste tambem nao serve para o executavel.

5. A URL informada ja esta em `auth_config.json` na raiz do projeto e ao lado do executavel. Se criar outra implantacao, atualize esses arquivos. `%LOCALAPPDATA%\RelatoriosECAC\auth_config.json`, se existir, tem prioridade; a variavel `RELATORIOS_ECAC_AUTH_URL` tambem pode substituir a URL. O modelo esta em [auth_config.example.json](auth_config.example.json).
6. Feche e abra `RelatoriosECAC.exe`. Informe o e-mail, receba o codigo e digite os seis numeros para acessar a selecao de certificados.

Ao alterar o Apps Script, atualize a implantacao publicada para que o aplicativo receba a nova versao. Codigos expiram em 10 minutos; sessoes duram 8 horas. Remover o e-mail da planilha impede novas validacoes de sessao. O app guarda o resultado da ultima consulta separado por e-mail na maquina.

A URL `/exec` atual foi configurada e responde sem login Google: `GET` devolve `{"ok":true,"service":"ecac-auth"}` e um `POST` de teste sem e-mail devolve `{"ok":false,"error":"invalid_request"}`. O envio real de codigo ainda precisa ser confirmado com um e-mail cadastrado na aba `Dados`.

## Gerar executavel

```powershell
py -3.14 -m PyInstaller --noconfirm RelatoriosECAC.spec
```

O executavel fica em `dist\RelatoriosECAC\RelatoriosECAC.exe`. A pasta `_internal` deve acompanhar o executavel. O logo e o icone sao incluidos no pacote.

## Testes locais

```powershell
py -3.14 -m unittest discover -s tests -p "test_*.py"
node tests/auth_backend_smoke.js
node tests/page_script_smoke.js
```

Copyright (c) 2026 CARLOS ROBERTO FELICIO JUNIOR. Todos os direitos reservados.
