/**
 * Consulta Fiscal e-CAC: allowed emails in Dados!A:A, one-time email codes.
 * Deploy as a Web app that executes as the spreadsheet owner.
 */
const AUTH = Object.freeze({
  spreadsheetId: '1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw',
  sheetName: 'Dados',
  logoDriveFileId: '1m4AI8LCZmgkzw8rSmn4_CV31rloHmOCs',
  codeSeconds: 600,
  cooldownSeconds: 90,
  maxCodesPerHour: 3,
  maxAttempts: 5,
  maxRequestsPerMinute: 100,
  sessionMilliseconds: 8 * 60 * 60 * 1000,
});
const GENERIC_MESSAGE =
  'Se o e-mail estiver cadastrado, um c\u00f3digo ser\u00e1 enviado.';

/** Run once in the Apps Script editor, then deploy the Web app. */
function setupAuth() {
  const sheet = SpreadsheetApp.openById(AUTH.spreadsheetId)
    .getSheetByName(AUTH.sheetName);
  if (!sheet || String(sheet.getRange(1, 1).getDisplayValue())
      .trim().toUpperCase() !== 'EMAIL') {
    throw new Error('A aba Dados precisa ter EMAIL na c\u00e9lula A1.');
  }
  const properties = PropertiesService.getScriptProperties();
  if (!properties.getProperty('ECAC_AUTH_SECRET')) {
    properties.setProperty(
      'ECAC_AUTH_SECRET',
      [Utilities.getUuid(), Utilities.getUuid(),
       Utilities.getUuid(), Utilities.getUuid()].join('')
    );
  }
  const logo = DriveApp.getFileById(AUTH.logoDriveFileId);
  if (logo.getMimeType() !== 'image/png') {
    throw new Error('A logo do e-mail precisa ser um arquivo PNG.');
  }
  logo.getBlob();
  MailApp.getRemainingDailyQuota();
}

function doGet() {
  return response_({ok: true, service: 'ecac-auth'});
}

function doPost(event) {
  try {
    const body = event && event.postData && event.postData.contents;
    if (!body || body.length > 4096) {
      return response_({ok: false, error: 'invalid_request'});
    }
    const request = JSON.parse(body);
    const action = String(request.action || '');
    if (action === 'request') {
      return response_(requestCode_(request.email));
    }
    if (action === 'verify') {
      return response_(verifyCode_(request.email, request.code));
    }
    if (action === 'validate') {
      return response_(validateSession_(request.token));
    }
    return response_({ok: false, error: 'invalid_request'});
  } catch (_error) {
    return response_({ok: false, error: 'service_unavailable'});
  }
}

function response_(body) {
  return ContentService.createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}

function secret_() {
  const value = PropertiesService.getScriptProperties()
    .getProperty('ECAC_AUTH_SECRET');
  if (!value || value.length < 64) {
    throw new Error('Execute setupAuth no editor antes de publicar.');
  }
  return value;
}

function normalizeEmail_(value) {
  const email = String(value || '').trim().toLowerCase();
  return email.length <= 254 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : '';
}

function authorizedEmail_(email) {
  const sheet = SpreadsheetApp.openById(AUTH.spreadsheetId)
    .getSheetByName(AUTH.sheetName);
  if (!sheet) {
    throw new Error('Aba de autoriza\u00e7\u00e3o n\u00e3o encontrada.');
  }
  const last = sheet.getLastRow();
  if (last < 2) return '';
  const rows = sheet.getRange(2, 1, last - 1, 1).getDisplayValues();
  for (const row of rows) {
    const stored = String(row[0] || '').trim();
    if (normalizeEmail_(stored) === email) return stored;
  }
  return '';
}

function signature_(value, secret) {
  return Utilities.base64EncodeWebSafe(
    Utilities.computeHmacSha256Signature(value, secret)
  ).replace(/=+$/g, '');
}

function equal_(left, right) {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) {
    diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return diff === 0;
}

function code_() {
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    Utilities.getUuid() + Utilities.getUuid() + String(Date.now())
  );
  const number = (
    ((bytes[0] & 255) << 24) |
    ((bytes[1] & 255) << 16) |
    ((bytes[2] & 255) << 8) |
    (bytes[3] & 255)
  ) >>> 0;
  return String(number % 1000000).padStart(6, '0');
}

function accessEmailHtml_(code) {
  return [
    '<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"></head>',
    '<body style="margin:0;padding:0;background:#f4f7fb;',
    'font-family:Arial,Helvetica,sans-serif;color:#263548;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0"',
    ' width="100%" style="background:#f4f7fb;"><tr><td align="center"',
    ' style="padding:24px 12px;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0"',
    ' width="100%" style="max-width:680px;background:#ffffff;',
    'border:1px solid #e3e9f1;">',
    '<tr><td align="center" style="padding:28px 24px 6px;">',
    '<img src="cid:carlosLogo" alt="Carlos Junior - Tecnologia e Desenvolvimento',
    ' de Software" width="180" style="display:block;width:180px;',
    'max-width:100%;height:auto;border:0;"></td></tr>',
    '<tr><td align="center" style="padding:8px 24px 25px;',
    'font-size:16px;color:#43546b;">Portal de Consulta Fiscal e-CAC</td></tr>',
    '<tr><td style="padding:0 28px 12px;font-size:18px;',
    'font-weight:700;color:#193a61;">Seu c\u00f3digo de acesso</td></tr>',
    '<tr><td style="padding:0 28px 8px;font-size:15px;line-height:1.6;">',
    'Voc\u00ea solicitou acesso ao sistema de Consulta Fiscal e-CAC.',
    ' Use o c\u00f3digo abaixo para entrar.</td></tr>',
    '<tr><td style="padding:0 28px 24px;font-size:15px;',
    'line-height:1.6;font-weight:700;">Este c\u00f3digo',
    ' \u00e9 v\u00e1lido por 10 minutos.</td></tr>',
    '<tr><td align="center" style="padding:0 24px 30px;">',
    '<table role="presentation" cellpadding="0" cellspacing="0"',
    ' border="0" style="background:#f6f9ff;border:1px dashed #1769e0;',
    'border-radius:8px;"><tr><td align="center"',
    ' style="padding:17px 26px;color:#1769e0;font-size:34px;',
    'font-weight:700;letter-spacing:7px;white-space:nowrap;">',
    code,
    '</td></tr></table></td></tr>',
    '<tr><td style="padding:0 28px;"><div style="border-top:',
    '1px solid #dfe5ed;"></div></td></tr>',
    '<tr><td align="center" style="padding:22px 28px 10px;',
    'font-size:13px;line-height:1.6;color:#637186;">',
    'Se voc\u00ea n\u00e3o solicitou este c\u00f3digo, ignore este e-mail.',
    ' N\u00e3o compartilhe o c\u00f3digo com ningu\u00e9m.</td></tr>',
    '<tr><td align="center" style="padding:0 28px 26px;',
    'font-size:11px;color:#8490a0;">',
    '\u00a9 2026 CARLOS ROBERTO FELICIO JUNIOR.',
    ' Todos os direitos reservados.</td></tr>',
    '</table></td></tr></table></body></html>',
  ].join('');
}

function requestCode_(input) {
  const email = normalizeEmail_(input);
  if (!email) return {ok: false, error: 'invalid_email'};
  const secret = secret_();
  const id = signature_(email, secret).slice(0, 32);
  const cache = CacheService.getScriptCache();
  const lock = LockService.getScriptLock();
  const generic = {ok: true, message: GENERIC_MESSAGE};
  lock.waitLock(5000);
  try {
    const minuteKey = 'global:' + Math.floor(Date.now() / 60000);
    const globalCount = Number(cache.get(minuteKey) || 0);
    if (globalCount >= AUTH.maxRequestsPerMinute) return generic;
    cache.put(minuteKey, String(globalCount + 1), 60);

    const storedEmail = authorizedEmail_(email);
    if (!storedEmail) return generic;

    const hourKey = 'hour:' + id + ':' + Math.floor(Date.now() / 3600000);
    const count = Number(cache.get(hourKey) || 0);
    if (count >= AUTH.maxCodesPerHour || cache.get('cooldown:' + id)) {
      return generic;
    }

    const code = code_();
    const record = {
      hash: signature_(email + ':' + code, secret),
      attempts: 0,
      expires: Date.now() + AUTH.codeSeconds * 1000,
    };
    cache.put('otp:' + id, JSON.stringify(record), AUTH.codeSeconds);
    cache.put('cooldown:' + id, '1', AUTH.cooldownSeconds);
    cache.put(hourKey, String(count + 1), 3600);
    try {
      const logo = DriveApp.getFileById(AUTH.logoDriveFileId).getBlob();
      MailApp.sendEmail({
        to: storedEmail,
        subject: 'Seu c\u00f3digo de acesso - Consulta Fiscal e-CAC',
        body: 'Seu c\u00f3digo de acesso \u00e0 Consulta Fiscal e-CAC \u00e9 ' +
          code + '. Ele expira em 10 minutos. Se voc\u00ea n\u00e3o solicitou, ' +
          'ignore esta mensagem e n\u00e3o compartilhe o c\u00f3digo.',
        htmlBody: accessEmailHtml_(code),
        inlineImages: {carlosLogo: logo},
        name: 'Carlos Junior - Consulta Fiscal',
      });
    } catch (_error) {
      cache.remove('otp:' + id);
      cache.remove('cooldown:' + id);
      throw _error;
    }
    return generic;
  } finally {
    lock.releaseLock();
  }
}

function verifyCode_(inputEmail, inputCode) {
  const email = normalizeEmail_(inputEmail);
  const code = String(inputCode || '').trim();
  if (!email || !/^\d{6}$/.test(code)) {
    return {ok: false, error: 'invalid_code'};
  }
  const secret = secret_();
  const id = signature_(email, secret).slice(0, 32);
  const cache = CacheService.getScriptCache();
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const raw = cache.get('otp:' + id);
    if (!raw) return {ok: false, error: 'invalid_code'};
    const record = JSON.parse(raw);
    const remaining = Math.ceil((record.expires - Date.now()) / 1000);
    if (remaining < 1 || record.attempts >= AUTH.maxAttempts) {
      cache.remove('otp:' + id);
      return {ok: false, error: 'invalid_code'};
    }
    if (!equal_(record.hash, signature_(email + ':' + code, secret))) {
      record.attempts++;
      if (record.attempts >= AUTH.maxAttempts) {
        cache.remove('otp:' + id);
      } else {
        cache.put('otp:' + id, JSON.stringify(record), remaining);
      }
      return {ok: false, error: 'invalid_code'};
    }
    cache.remove('otp:' + id);
    if (!authorizedEmail_(email)) {
      return {ok: false, error: 'unauthorized'};
    }
    const payload = Utilities.base64EncodeWebSafe(JSON.stringify({
      email: email,
      expires: Date.now() + AUTH.sessionMilliseconds,
      nonce: Utilities.getUuid(),
    })).replace(/=+$/g, '');
    return {
      ok: true,
      email: email,
      token: payload + '.' + signature_(payload, secret),
    };
  } finally {
    lock.releaseLock();
  }
}

function validateSession_(inputToken) {
  const token = String(inputToken || '');
  if (token.length > 2048) return {ok: false, error: 'unauthorized'};
  const parts = token.split('.');
  if (parts.length !== 2 ||
      !equal_(parts[1], signature_(parts[0], secret_()))) {
    return {ok: false, error: 'unauthorized'};
  }
  try {
    const bytes = Utilities.base64DecodeWebSafe(parts[0]);
    const payload = JSON.parse(
      Utilities.newBlob(bytes).getDataAsString('UTF-8')
    );
    const email = normalizeEmail_(payload.email);
    if (!email || !Number.isFinite(payload.expires) ||
        payload.expires <= Date.now() || !authorizedEmail_(email)) {
      return {ok: false, error: 'unauthorized'};
    }
    return {ok: true, email: email};
  } catch (_error) {
    return {ok: false, error: 'unauthorized'};
  }
}
