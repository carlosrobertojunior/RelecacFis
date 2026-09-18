# Consulta Fiscal e-CAC

Aplicativo Windows para selecionar um certificado instalado, acessar o e-CAC, ler o resultado de Minhas Dividas e Pendencias e baixar o relatorio PDF. Antes da selecao do certificado, o usuario precisa validar um codigo enviado ao e-mail autorizado na planilha.

## Publicar o servico de login

1. Abra a [planilha de contas](https://docs.google.com/spreadsheets/d/1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw/edit?gid=0#gid=0) na conta Google que enviara os e-mails. Na aba `Dados`, mantenha `EMAIL` em A1 e coloque um endereco autorizado por linha na coluna A.
2. Abra **Extensoes > Apps Script**. Substitua o conteudo de `Code.gs` pelo arquivo [apps_script/Code.gs](apps_script/Code.gs) deste projeto e salve.
3. No editor, selecione `setupAuth`, clique em **Executar** e autorize o acesso a planilha, ao arquivo privado da logo no Drive e ao envio de e-mails. Essa etapa cria o segredo de assinatura nas propriedades privadas do script e verifica a logo.
O envio usa `MailApp` com a autorizacao da conta Google no Apps Script. Nenhuma senha de app e necessaria ou armazenada no projeto.

4. Clique em **Implantar > Nova implantacao > Aplicativo da Web**. Escolha **Executar como: eu** (a conta proprietaria) e **Quem tem acesso: qualquer pessoa**. Copie a URL terminada em `/exec`. A verificacao dos e-mails e feita apenas pelo script; a planilha nao precisa ser publica.
O link do editor do projeto (`script.google.com/.../home/projects/.../edit`) nao e a URL de acesso do aplicativo. Se o projeto ja estiver publicado, abra **Implantar > Gerenciar implantacoes**, selecione a implantacao ativa do tipo **Aplicativo da Web** e copie a **URL do aplicativo da Web** terminada em `/exec`. A URL `/dev` de teste tambem nao serve para o executavel.

5. A URL informada ja esta em `auth_config.json` na raiz do projeto e ao lado do executavel. Se criar outra implantacao, atualize esses arquivos. `%LOCALAPPDATA%\RelatoriosECAC\auth_config.json`, se existir, tem prioridade; a variavel `RELATORIOS_ECAC_AUTH_URL` tambem pode substituir a URL. O modelo esta em [auth_config.example.json](auth_config.example.json).
6. Feche e abra `RelatoriosECAC.exe`. Informe o e-mail, receba o codigo e digite os seis numeros para acessar a selecao de certificados.

Ao alterar o Apps Script, abra **Implantar > Gerenciar implantacoes**, edite a implantacao ativa, escolha **Nova versao** e publique novamente. A URL `/exec` existente pode continuar a mesma. Codigos expiram em 10 minutos; sessoes duram 8 horas. Remover o e-mail da planilha impede novas validacoes de sessao. O app guarda o resultado da ultima consulta separado por e-mail na maquina.

A URL `/exec` atual foi configurada e responde sem login Google. Em 18/09/2026, um codigo real foi solicitado para uma conta autorizada e a mensagem chegou a caixa postal: o e-mail continha HTML, validade de 10 minutos, codigo de seis digitos e logo PNG incorporada por `cid:carlosLogo`. O codigo nao foi exibido nem consumido na verificacao; o login completo ainda depende de digitar o codigo no aplicativo.

## E-mail do codigo com a logo

O [novo Code.gs](apps_script/Code.gs) envia uma mensagem HTML no formato da [previa](preview/email_token.png): logo centralizada, codigo destacado, validade de 10 minutos e aviso para nao compartilhar. A previa usa o codigo ficticio `123456`. O texto simples acompanha o HTML para clientes de e-mail que nao o exibem.

A [logo](https://drive.google.com/file/d/1m4AI8LCZmgkzw8rSmn4_CV31rloHmOCs/view?usp=drivesdk) foi guardada no Google Drive como arquivo privado. O script le o arquivo pelo ID e o incorpora ao e-mail com `inlineImages`; nao precisa tornar a imagem publica. A conta que executa o Apps Script precisa ter acesso de leitura a esse arquivo. Depois de colar o novo `Code.gs`, execute `setupAuth` novamente e autorize o acesso ao Drive antes de atualizar a implantacao.

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
