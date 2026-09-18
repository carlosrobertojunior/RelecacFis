const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');

const values = ['user@example.com'];
const sent = [];
const logoBlob = {name: 'RelatoriosECAC-logo.png'};
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
  DriveApp: {
    getFileById: id => {
      assert.equal(id, '1m4AI8LCZmgkzw8rSmn4_CV31rloHmOCs');
      return {
        getMimeType: () => 'image/png',
        getBlob: () => logoBlob,
      };
    },
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

const post = payload => JSON.parse(context.doPost({
  postData: {contents: JSON.stringify(payload)},
}).text);
assert.equal(post({action: 'request', email: 'other@example.com'}).ok, true);
assert.equal(sent.length, 0);
assert.equal(post({action: 'request', email: ' USER@example.com '}).ok, true);
assert.equal(sent.length, 1);
assert.equal(sent[0].to, 'user@example.com');
assert.equal(sent[0].inlineImages.carlosLogo, logoBlob);
assert.match(sent[0].htmlBody, /src="cid:carlosLogo"/);
assert.match(sent[0].htmlBody, /Este c\u00f3digo/);
assert.match(sent[0].htmlBody, /10 minutos/);
assert.match(sent[0].htmlBody, /CARLOS ROBERTO FELICIO JUNIOR/);
assert.match(sent[0].htmlBody, /\d{6}/);
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
