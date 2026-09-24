import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';
import { menu, miniappUrl } from '../src/config.js';

const env = {
  MINIAPP_URL: 'https://alice-miniapp.example.workers.dev',
  TELEGRAM_OWNER_ID: '92655562',
  BALE_OWNER_ID: '1984558572',
  TELEGRAM_WEBHOOK_SECRET: 'telegram-secret',
  BALE_WEBHOOK_SECRET: 'bale-secret',
};
const ctx = { waitUntil() {} };

test('miniapp opens in both messengers and management stays owner-only', () => {
  assert.equal(miniappUrl(env, 'telegram'), env.MINIAPP_URL + '/');
  assert.equal(new URL(miniappUrl(env, 'bale')).searchParams.get('platform'), 'bale');
  assert.equal(menu(env, 'telegram', 1).flat().some(x => x === 'مدیریت ارسال'), false);
  assert.equal(menu(env, 'telegram', 92655562).flat().includes('مدیریت ارسال'), true);
});

test('health is public; webhook updates require the platform secret', async () => {
  const health = await worker.fetch(new Request('https://example.com/health'), env, ctx);
  assert.equal(health.status, 200);
  const telegram = await worker.fetch(new Request('https://example.com/webhook/telegram', { method: 'POST', body: '{}' }), env, ctx);
  assert.equal(telegram.status, 403);
  const bale = await worker.fetch(new Request('https://example.com/webhook/bale/wrong', { method: 'POST', body: '{}' }), env, ctx);
  assert.equal(bale.status, 403);
});

test('webhook installation refuses missing credentials before changing either bot', async () => {
  const response = await worker.fetch(new Request('https://example.com/ops/install', { method: 'POST', headers: { authorization: 'Bearer setup-secret' } }), { ...env, SETUP_SECRET: 'setup-secret' }, ctx);
  assert.equal(response.status, 500);
  assert.match((await response.json()).error, /Bot tokens/);
});
