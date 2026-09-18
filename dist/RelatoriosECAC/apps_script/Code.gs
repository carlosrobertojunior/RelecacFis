/**
 * Consulta Fiscal e-CAC: allowed emails in Dados!A:A, one-time email codes.
 * Deploy as a Web app that executes as the spreadsheet owner.
 */
const AUTH = Object.freeze({
  spreadsheetId: '1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw',
  sheetName: 'Dados',
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
  MailApp.getRemainingDailyQuota();
}

function doGet() {
  return response_({ok: true, service: 'ecac-auth', emailFormat: 'text-only-v1'});
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
      MailApp.sendEmail({
        to: storedEmail,
        subject: 'Seu c\u00f3digo de acesso - Consulta Fiscal e-CAC',
        body: 'Seu c\u00f3digo de acesso \u00e0 Consulta Fiscal e-CAC: ' +
          code + '\nV\u00e1lido por 10 minutos.\n' +
          'Se voc\u00ea n\u00e3o solicitou, ignore esta mensagem. ' +
          'N\u00e3o compartilhe o c\u00f3digo.',
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
