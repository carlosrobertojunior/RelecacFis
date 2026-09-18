const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');

let clock = Date.UTC(2026, 8, 18, 17, 0, 0);
class ClockDate extends Date {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
}
let values = ['user@example.com'];
let quota = 100;
let failSend = false;
let sheetAvailable = true;
let lockAvailable = true;
const sent = [];
const logs = [];
const cache = new Map();
const properties = new Map();
const encode = value => Buffer.from(value).toString('base64url');
const context = {
  Date: ClockDate, JSON, String, Number, Math, Object, Array,
  console: {log: value => logs.push(value), error: value => logs.push(value)},
  Session: {getEffectiveUser: () => ({getEmail: () => 'user@example.com'})},
  SpreadsheetApp: {
    openById: id => ({
      getSheetByName: name => {
        assert.equal(id, '1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw');
        assert.equal(name, 'Dados');
        if (!sheetAvailable) return null;
        return {
          getRange: (_row, _col, count) => ({
            getDisplayValue: () => 'EMAIL',
            getDisplayValues: () => values.slice(0, count).map(x => [x]),
          }),
          getLastRow: () => values.length + 1,
        };
      },
    }),
  },
  PropertiesService: {
    getScriptProperties: () => ({
      getProperty: key => properties.get(key) || null,
      setProperty: (key, value) => properties.set(key, value),
    }),
  },
  CacheService: {
    getScriptCache: () => ({
      get: key => {
        const item = cache.get(key);
        return !item || item.expires <= clock ? null : item.value;
      },
      put: (key, value, seconds) => cache.set(key, {
        value, expires: clock + seconds * 1000,
      }),
      remove: key => cache.delete(key),
    }),
  },
  LockService: {
    getScriptLock: () => ({
      tryLock: () => lockAvailable, waitLock: () => {}, releaseLock: () => {},
    }),
  },
  MailApp: {
    getRemainingDailyQuota: () => quota,
    sendEmail: message => {
      if (failSend) throw new Error('Simulated mail transport failure');
      sent.push(message);
    },
  },
  ContentService: {
    MimeType: {JSON: 'json'},
    createTextOutput: text => ({text, setMimeType() { return this; }}),
  },
  Utilities: {
    getUuid: () => crypto.randomUUID(),
    computeHmacSha256Signature: (value, key) =>
      [...crypto.createHmac('sha256', key).update(value).digest()],
    computeDigest: (_algorithm, value) =>
      [...crypto.createHash('sha256').update(value).digest()],
    DigestAlgorithm: {SHA_256: 'sha256'},
    base64EncodeWebSafe: value => encode(
      typeof value === 'string' ? value : Buffer.from(value)
    ),
    base64DecodeWebSafe: value => [...Buffer.from(value, 'base64url')],
    newBlob: bytes => ({getDataAsString: () => Buffer.from(bytes).toString('utf8')}),
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('apps_script/Code.gs', 'utf8'), context);
const post = payload => JSON.parse(context.doPost({
  postData: {contents: JSON.stringify(payload)},
}).text);
const request = (email = 'user@example.com') => post({action: 'request', email});
const lastCode = () => sent.at(-1).body.match(/\b\d{6}\b/)[0];
function reset() {
  clock = Date.UTC(2026, 8, 18, 17, 0, 0);
  values = ['user@example.com'];
  quota = 100; failSend = false; sheetAvailable = true; lockAvailable = true;
  sent.length = 0; logs.length = 0; cache.clear(); properties.clear();
  context.setupAuth();
}
const advance = seconds => { clock += seconds * 1000; };
reset();
assert.ok(properties.get('ECAC_AUTH_SECRET').length >= 64);
assert.equal(JSON.parse(context.doGet().text).emailFormat, 'html-code-v2');
assert.equal(JSON.parse(context.doGet().text).version, 'auth-v2');
assert.equal(request('other@example.com').ok, true);
assert.equal(sent.length, 0);
const unknownLimited = request('other@example.com');
assert.equal(request(' USER@example.com ').ok, true);
assert.equal(sent.length, 1);
assert.equal(sent[0].to, 'user@example.com');
assert.equal(sent[0].inlineImages, undefined);
assert.equal(sent[0].attachments, undefined);
assert.match(sent[0].htmlBody, /border:1px dashed/);
assert.match(sent[0].htmlBody, /CARLOS JUNIOR/);
assert.match(sent[0].htmlBody, /10 minutos/);
assert.match(sent[0].htmlBody, /Seu c\u00f3digo/);
assert.match(sent[0].subject, /Seu c\u00f3digo/);
assert.match(sent[0].body, /V\u00e1lido/);
assert.doesNotMatch(sent[0].htmlBody, /c[?]digo|voc[?]|n[?]o/i);
assert.doesNotMatch(sent[0].htmlBody, /<img|cid:|data:image|https?:\/\//);
assert.ok(sent[0].htmlBody.includes(lastCode()));
assert.throws(() => context.accessEmailHtml_('<img>'));
assert.deepEqual(request(), unknownLimited);
assert.equal(request().retryAfterSeconds, 90);
advance(89);
assert.equal(request().retryAfterSeconds, 1);
advance(1);
assert.equal(request().ok, true);
advance(90);
assert.equal(request().ok, true);
advance(90);
const limited = request();
assert.equal(limited.ok, false);
assert.equal(limited.error, 'rate_limited');
assert.equal(limited.retryAfterSeconds, 3330);
assert.equal(sent.length, 3);
const diagnostic = context.diagnoseAuth();
assert.equal(diagnostic.codesThisHour, 3);
assert.equal(diagnostic.ownerAuthorized, true);
assert.equal(diagnostic.remainingMailQuota, 100);
assert.equal(sent.length, 3); // The editor diagnostic never sends a message.
advance(3330);
assert.equal(request().ok, true);
assert.equal(sent.length, 4);

// Verify delivered codes, rejection of tampering/reuse, and removal from the list.
const code = lastCode();
const wrong = code === '000000' ? '000001' : '000000';
assert.equal(post({action: 'verify', email: 'user@example.com', code: wrong}).ok, false);
const verified = post({action: 'verify', email: 'user@example.com', code});
assert.equal(verified.ok, true);
assert.equal(post({action: 'verify', email: 'user@example.com', code}).ok, false);
assert.equal(post({action: 'validate', token: verified.token}).ok, true);
assert.equal(post({action: 'validate', token: verified.token + 'x'}).ok, false);
values.length = 0;
assert.equal(post({action: 'validate', token: verified.token}).ok, false);

// No silent success when the account cannot send mail; retries remain possible.
reset();
quota = 0;
assert.equal(request().error, 'mail_quota_exceeded');
assert.equal(sent.length, 0);
quota = 100;
failSend = true;
assert.equal(request().error, 'mail_send_failed');
failSend = false;
assert.equal(request().ok, true);
const previousCode = lastCode();
advance(90);
failSend = true;
assert.equal(request().error, 'mail_send_failed');
assert.equal(context.diagnoseAuth().codesThisHour, 1);
assert.equal(context.diagnoseAuth().cooldownSeconds, 0);
assert.equal(post({action: 'verify', email: 'user@example.com', code: previousCode}).ok, true);
failSend = false;
assert.equal(request().ok, true);

reset();
request();
const expiredCode = lastCode();
advance(601);
assert.equal(post({action: 'verify', email: 'user@example.com', code: expiredCode}).ok, false);
reset();
request();
const lockedCode = lastCode();
const bad = lockedCode === '000000' ? '000001' : '000000';
for (let i = 0; i < 5; i++) {
  assert.equal(post({action: 'verify', email: 'user@example.com', code: bad}).ok, false);
}
assert.equal(post({action: 'verify', email: 'user@example.com', code: lockedCode}).ok, false);

reset();
properties.clear();
assert.equal(request().error, 'setup_required');
reset();
sheetAvailable = false;
assert.equal(request().error, 'configuration_error');
reset();
lockAvailable = false;
assert.equal(request().error, 'service_busy');
reset();
for (let i = 0; i < 100; i++) assert.equal(request(`unknown${i}@example.com`).ok, true);
assert.equal(request().error, 'rate_limited');
assert.equal(request().retryAfterSeconds, 60);
assert.equal(sent.length, 0);

// Respect limits already stored by text-only-v1 during deployment upgrades.
reset();
const id = context.signature_('user@example.com', context.secret_()).slice(0, 32);
cache.set('cooldown:' + id, {value: '1', expires: clock + 90000});
assert.equal(request().retryAfterSeconds, 90);
console.log('Apps Script: HTML without images, rate limits, hourly reset, quota, failed resend recovery, OTP and sessions OK.');
