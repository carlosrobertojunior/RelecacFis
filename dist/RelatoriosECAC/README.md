# Consulta Fiscal e-CAC

Aplicativo Windows para selecionar um certificado instalado, acessar o e-CAC, ler o resultado de Minhas Dividas e Pendencias e baixar o relatorio PDF. Antes da selecao do certificado, o usuario precisa validar um codigo enviado ao e-mail autorizado na planilha.

## Publicar o servico de login

1. Abra a [planilha de contas](https://docs.google.com/spreadsheets/d/1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw/edit?gid=0#gid=0) na conta Google que enviara os e-mails. Na aba `Dados`, mantenha `EMAIL` em A1 e coloque um endereco autorizado por linha na coluna A.
2. Abra **Extensoes > Apps Script**. Substitua o conteudo de `Code.gs` pelo arquivo [apps_script/Code.gs](apps_script/Code.gs) deste projeto e salve.
3. No editor, selecione `setupAuth`, clique em **Executar** e autorize o acesso a planilha e ao envio de e-mails. Essa etapa cria o segredo de assinatura nas propriedades privadas do script.
O envio usa `MailApp` com a autorizacao da conta Google no Apps Script. Nenhuma senha de app e necessaria ou armazenada no projeto.

4. Clique em **Implantar > Nova implantacao > Aplicativo da Web**. Escolha **Executar como: eu** (a conta proprietaria) e **Quem tem acesso: qualquer pessoa**. Copie a URL terminada em `/exec`. A verificacao dos e-mails e feita apenas pelo script; a planilha nao precisa ser publica.
O link do editor do projeto (`script.google.com/.../home/projects/.../edit`) nao e a URL de acesso do aplicativo. Se o projeto ja estiver publicado, abra **Implantar > Gerenciar implantacoes**, selecione a implantacao ativa do tipo **Aplicativo da Web** e copie a **URL do aplicativo da Web** terminada em `/exec`. A URL `/dev` de teste tambem nao serve para o executavel.

5. A URL informada ja esta em `auth_config.json` na raiz do projeto e ao lado do executavel. Se criar outra implantacao, atualize esses arquivos. `%LOCALAPPDATA%\RelatoriosECAC\auth_config.json`, se existir, tem prioridade; a variavel `RELATORIOS_ECAC_AUTH_URL` tambem pode substituir a URL. O modelo esta em [auth_config.example.json](auth_config.example.json).
6. Feche e abra `RelatoriosECAC.exe`. Informe o e-mail, receba o codigo e digite os seis numeros para acessar a selecao de certificados.

Ao alterar o Apps Script, abra **Implantar > Gerenciar implantacoes**, edite a implantacao ativa, escolha **Nova versao** e publique novamente. A URL `/exec` existente pode continuar a mesma. Codigos expiram em 10 minutos; sessoes duram 8 horas. Remover o e-mail da planilha impede novas validacoes de sessao. O app guarda o resultado da ultima consulta separado por e-mail na maquina.

## Diagnostico do envio e novo modelo

Em 18/09/2026, a URL configurada respondeu com `emailFormat: text-only-v1`. Foram encontrados tres envios para a conta de teste na mesma hora (14:30, 14:38 e 14:43, horario de Fortaleza). A tentativa autorizada das 14:57 retornou a mensagem generica de sucesso, mas nao gerou novo e-mail. Isso corresponde ao bloqueio de tres envios por hora implementado na versao anterior; o contador interno nao estava acessivel para confirmar seu valor. As mensagens anteriores estavam na Lixeira do Gmail.

O [Code.gs](apps_script/Code.gs) corrigido retorna `rate_limited` e `retryAfterSeconds` quando ha bloqueio, em vez de simular sucesso. O aplicativo mostra o tempo de espera e mantem a entrada de um codigo ja recebido disponivel. O limite continua sendo tres envios por hora do relogio e um intervalo de 90 segundos; os codigos duram 10 minutos. Uma falha de envio nao consome a cota por e-mail nem invalida um codigo anterior ainda valido.

O modelo HTML tem cabecalho Carlos Junior, codigo azul destacado e rodape, como na [previa](preview/email_token.png). O codigo da previa e ficticio. O envio inclui texto simples alternativo, sem `inlineImages`, `attachments`, imagens externas ou arquivos. A logo continua nas telas do aplicativo.

### Ativar a correcao

1. Substitua o conteudo do editor do Apps Script por [apps_script/Code.gs](apps_script/Code.gs) e salve.
2. Execute `setupAuth` se precisar autorizar a planilha ou o envio.
3. Abra **Implantar > Gerenciar implantacoes > Editar > Nova versao > Implantar**. Atualize a implantacao da URL ja configurada para preserva-la.
4. Abra `/exec`: a resposta deve mostrar `"emailFormat":"html-code-v2"` e `"version":"auth-v2"`. Se mostrar `text-only-v1`, a nova versao ainda nao esta publicada.
5. Use o executavel atualizado em `dist/validacao_token/RelatoriosECAC/RelatoriosECAC.exe`, com `_internal` e `auth_config.json` na mesma pasta.

A nova implantacao informada em 18/09/2026 respondeu com HTTP 200, `emailFormat: html-code-v2` e `version: auth-v2`. Sua URL foi configurada na raiz e nos tres pacotes distribuidos. Os testes locais validaram limites, falhas e recuperacao do codigo anterior. A entrega real de um e-mail pelo novo modelo ainda nao foi confirmada; esta verificacao da URL nao solicitou token.

### Se continuar sem receber

Execute `diagnoseAuth` no editor como proprietario do script. Essa funcao nao envia e-mail e nao mostra tokens; registra a cota de envio restante, o cadastro do e-mail da conta executora, o numero de envios nesta hora e o tempo ate a liberacao. Nao existe endpoint publico de diagnostico.

- `rate_limited`: aguarde o tempo exibido. Apagar e-mails recebidos nao zera o contador.
- `mail_quota_exceeded`: a conta atingiu a cota diaria do Google; o administrador pode consultar a [documentacao de cotas](https://developers.google.com/apps-script/guides/services/quotas).
- `mail_send_failed`: o Google recusou ou falhou ao enviar; confira as execucoes do Apps Script e tente novamente.
- `configuration_error` ou `setup_required`: confira Dados!A1 = EMAIL, os enderecos na coluna A, as permissoes e execute `setupAuth`.

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
