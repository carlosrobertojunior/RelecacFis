const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');

const values = ['user@example.com'];
const sent = [];
const cache = new Map();
const properties = new Map();
const now = () => Date.now();
const encode = value => Buffer.from(value).toString('base64url');
const context = {
  Date, JSON, String, Number, Math, Object, Array,
  SpreadsheetApp: {
    openById: id => ({
      getSheetByName: name => {
        assert.equal(id, '1Mgu-DhBg2xPIErCowhh2ftZ9ttYgNY9fEckkgKdnVVw');
        assert.equal(name, 'Dados');
        return {
          getRange: (row, col, count) => ({
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
        if (!item || item.expires < now()) return null;
        return item.value;
      },
      put: (key, value, seconds) => cache.set(key, {
        value, expires: now() + seconds * 1000,
      }),
      remove: key => cache.delete(key),
    }),
  },
  LockService: {
    getScriptLock: () => ({waitLock: () => {}, releaseLock: () => {}}),
  },
  MailApp: {
    getRemainingDailyQuota: () => 100,
    sendEmail: message => sent.push(message),
  },
  ContentService: {
    MimeType: {JSON: 'json'},
    createTextOutput: text => ({
      text,
      setMimeType() { return this; },
    }),
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
    newBlob: bytes => ({
      getDataAsString: () => Buffer.from(bytes).toString('utf8'),
    }),
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('apps_script/Code.gs', 'utf8'), context);
context.setupAuth();
assert.ok(properties.get('ECAC_AUTH_SECRET').length >= 64);
assert.equal(JSON.parse(context.doGet().text).emailFormat, 'text-only-v1');

const post = payload => JSON.parse(context.doPost({
  postData: {contents: JSON.stringify(payload)},
}).text);
assert.equal(post({action: 'request', email: 'other@example.com'}).ok, true);
assert.equal(sent.length, 0);
assert.equal(post({action: 'request', email: ' USER@example.com '}).ok, true);
assert.equal(sent.length, 1);
assert.equal(sent[0].to, 'user@example.com');
assert.equal(sent[0].htmlBody, undefined);
assert.equal(sent[0].inlineImages, undefined);
assert.equal(sent[0].attachments, undefined);
assert.match(sent[0].body, /Seu c\u00f3digo de acesso/);
assert.match(sent[0].body, /10 minutos/);
assert.match(sent[0].body, /\b\d{6}\b/);
assert.doesNotMatch(sent[0].body, /<img|cid:|data:image|https?:\/\//);
assert.equal(post({action: 'request', email: 'user@example.com'}).ok, true);
assert.equal(sent.length, 1);
const code = sent[0].body.match(/\b\d{6}\b/)[0];
assert.equal(post({action: 'verify', email: 'user@example.com', code: '000000'}).ok, false);
const verified = post({action: 'verify', email: 'user@example.com', code});
assert.equal(verified.ok, true);
assert.equal(post({action: 'validate', token: verified.token}).ok, true);
assert.equal(post({action: 'validate', token: verified.token + 'x'}).ok, false);
values.length = 0;
assert.equal(post({action: 'validate', token: verified.token}).ok, false);
console.log('Apps Script: allowlist, mail, cooldown, OTP, session and revocation OK.');
