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
  return response_({ok: true, service: 'ecac-auth', emailFormat: 'html-code-v2', version: 'auth-v2'});
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
  } catch (error) {
    const code = error.authCode || 'service_unavailable';
    console.error(JSON.stringify({event: 'auth_failure', code: code}));
    return response_({ok: false, error: code});
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
    throw authError_('setup_required');
  }
  return value;
}

function normalizeEmail_(value) {
  const email = String(value || '').trim().toLowerCase();
  return email.length <= 254 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : '';
}

function authError_(code) {
  const error = new Error(code);
  error.authCode = code;
  return error;
}

function authorizationSheet_() {
  try {
    const sheet = SpreadsheetApp.openById(AUTH.spreadsheetId)
      .getSheetByName(AUTH.sheetName);
    if (!sheet || String(sheet.getRange(1, 1).getDisplayValue())
        .trim().toUpperCase() !== 'EMAIL') {
      throw new Error('Invalid authorization sheet');
    }
    return sheet;
  } catch (_error) {
    throw authError_('configuration_error');
  }
}

function authorizedEmail_(email) {
  const sheet = authorizationSheet_();
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
  if (!/^\d{6}$/.test(String(code))) throw new Error('Invalid email code');
  return [
    '<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"></head>',
    '<body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#263548;">',
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">',
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;background:#fff;border:1px solid #e3e9f1;">',
    '<tr><td align="center" style="padding:30px 24px 6px;color:#193a61;font-size:26px;font-weight:bold;">CARLOS JUNIOR</td></tr>',
    '<tr><td align="center" style="padding:8px 24px 30px;font-size:16px;color:#43546b;">Portal de Consulta Fiscal e-CAC</td></tr>',
    '<tr><td style="padding:0 28px 16px;font-size:18px;font-weight:bold;">Seu c\u00f3digo de acesso</td></tr>',
    '<tr><td style="padding:0 28px 8px;font-size:15px;line-height:1.6;">Voc\u00ea solicitou acesso \u00e0 Consulta Fiscal e-CAC. Utilize o c\u00f3digo abaixo para entrar no sistema.</td></tr>',
    '<tr><td style="padding:0 28px 24px;font-size:15px;font-weight:bold;">Este c\u00f3digo \u00e9 v\u00e1lido por ', String(AUTH.codeSeconds / 60), ' minutos.</td></tr>',
    '<tr><td align="center" style="padding:0 24px 32px;"><table role="presentation" cellpadding="0" cellspacing="0" style="background:#f2f7ff;border:1px dashed #1769e0;border-radius:8px;">',
    '<tr><td align="center" style="padding:18px 28px;color:#1769e0;font-size:36px;font-weight:bold;letter-spacing:7px;white-space:nowrap;">',
    code, '</td></tr></table></td></tr>',
    '<tr><td style="padding:0 28px;"><div style="border-top:1px solid #e3e9f1;"></div></td></tr>',
    '<tr><td align="center" style="padding:22px 28px 12px;font-size:13px;line-height:1.6;color:#637186;">Se voc\u00ea n\u00e3o solicitou este c\u00f3digo, ignore este e-mail. N\u00e3o compartilhe o c\u00f3digo com ningu\u00e9m.</td></tr>',
    '<tr><td align="center" style="padding:0 24px 26px;font-size:11px;color:#637186;">&copy; ', String(new Date().getFullYear()),
    ' CARLOS ROBERTO FELICIO JUNIOR. Todos os direitos reservados.</td></tr>',
    '</table></td></tr></table></body></html>',
  ].join('');
}

function retryResponse_(seconds) {
  return {ok: false, error: 'rate_limited',
    retryAfterSeconds: Math.max(1, Math.ceil(seconds))};
}

function cooldownRemaining_(cache, id) {
  const raw = cache.get('cooldown:' + id);
  if (!raw) return 0;
  // Compatibility with the boolean cache entry used by the previous deployment.
  if (raw === '1') return AUTH.cooldownSeconds;
  return Math.max(0, Math.ceil((Number(raw) - Date.now()) / 1000));
}

/** Run in the editor as the owner. Does not send email or expose an OTP. */
function diagnoseAuth() {
  const email = normalizeEmail_(Session.getEffectiveUser().getEmail());
  const secret = secret_();
  const cache = CacheService.getScriptCache();
  const id = signature_(email, secret).slice(0, 32);
  const hour = Math.floor(Date.now() / 3600000);
  const report = {
    version: 'auth-v2',
    ownerEmailAvailable: Boolean(email),
    ownerAuthorized: Boolean(email && authorizedEmail_(email)),
    remainingMailQuota: MailApp.getRemainingDailyQuota(),
    codesThisHour: Number(cache.get('hour:' + id + ':' + hour) || 0),
    maxCodesPerHour: AUTH.maxCodesPerHour,
    cooldownSeconds: cooldownRemaining_(cache, id),
    secondsUntilNextHour: Math.ceil(((hour + 1) * 3600000 - Date.now()) / 1000),
  };
  console.log(JSON.stringify(report));
  return report;
}

function requestCode_(input) {
  const email = normalizeEmail_(input);
  if (!email) return {ok: false, error: 'invalid_email'};
  const secret = secret_();
  const id = signature_(email, secret).slice(0, 32);
  const cache = CacheService.getScriptCache();
  const lock = LockService.getScriptLock();
  const generic = {ok: true, message: GENERIC_MESSAGE,
    retryAfterSeconds: AUTH.cooldownSeconds};
  if (!lock.tryLock(5000)) return {ok: false, error: 'service_busy'};
  try {
    const now = Date.now();
    const minute = Math.floor(now / 60000);
    const minuteKey = 'global:' + minute;
    const globalCount = Number(cache.get(minuteKey) || 0);
    if (globalCount >= AUTH.maxRequestsPerMinute) {
      return retryResponse_(((minute + 1) * 60000 - now) / 1000);
    }
    cache.put(minuteKey, String(globalCount + 1), 60);

    const hour = Math.floor(now / 3600000);
    const hourKey = 'hour:' + id + ':' + hour;
    const count = Number(cache.get(hourKey) || 0);
    const cooldown = cooldownRemaining_(cache, id);
    const hourlyWait = count >= AUTH.maxCodesPerHour
      ? ((hour + 1) * 3600000 - now) / 1000 : 0;
    if (cooldown > 0 || hourlyWait > 0) {
      return retryResponse_(Math.max(cooldown, hourlyWait));
    }
    // Check global mail availability for every address before consulting the list.
    if (MailApp.getRemainingDailyQuota() < 1) {
      return {ok: false, error: 'mail_quota_exceeded'};
    }
    const storedEmail = authorizedEmail_(email);
    if (storedEmail) {
      const code = code_();
      const key = 'otp:' + id;
      const previous = cache.get(key);
      const record = {
        hash: signature_(email + ':' + code, secret),
        attempts: 0,
        expires: Date.now() + AUTH.codeSeconds * 1000,
      };
      cache.put(key, JSON.stringify(record), AUTH.codeSeconds);
      try {
        MailApp.sendEmail({
          to: storedEmail,
          subject: 'Seu c\u00f3digo de acesso - Consulta Fiscal e-CAC',
          body: 'Seu c\u00f3digo de acesso \u00e0 Consulta Fiscal e-CAC: ' +
            code + '\nV\u00e1lido por 10 minutos.\n' +
            'Se voc\u00ea n\u00e3o solicitou, ignore esta mensagem. ' +
            'N\u00e3o compartilhe o c\u00f3digo.',
          htmlBody: accessEmailHtml_(code),
          name: 'Carlos Junior - Consulta Fiscal',
        });
      } catch (_error) {
        cache.remove(key);
        // A failed resend must not invalidate a previously delivered code.
        if (previous) {
          const remaining = Math.ceil((JSON.parse(previous).expires - Date.now()) / 1000);
          if (remaining > 0) cache.put(key, previous, remaining);
        }
        console.error(JSON.stringify({event: 'auth_failure', code: 'mail_send_failed'}));
        return {ok: false, error: 'mail_send_failed'};
      }
    }
    // Unknown emails follow the same limits and responses as registered emails.
    // Failed sends never consume an email slot or start a new cooldown.
    cache.put('cooldown:' + id, String(Date.now() + AUTH.cooldownSeconds * 1000),
      AUTH.cooldownSeconds);
    cache.put(hourKey, String(count + 1), 3600);
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
