import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const miniapp = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(miniapp, '..');
const server = join(miniapp, 'dist', 'server');
const botSource = join(repo, 'cloudflare-bot', 'src');
const botTarget = join(server, 'alice-bot');

await mkdir(botTarget, { recursive: true });
for (const name of ['index.js', 'config.js']) {
  await copyFile(join(botSource, name), join(botTarget, name));
}

await writeFile(join(server, 'entry.js'), `import miniapp from './index.js';
import bot from './alice-bot/index.js';

export default {
  async fetch(request, env, context) {
    const path = new URL(request.url).pathname;
    if (path === '/health' || path === '/ops/install' || path.startsWith('/webhook/')) {
      return bot.fetch(request, { ...env, DB: env.BOT_DB }, context);
    }
    return miniapp.fetch(request, env, context);
  },
};
`);

const configPath = join(server, 'wrangler.json');
const config = JSON.parse(await readFile(configPath, 'utf8'));
const botConfig = JSON.parse(await readFile(join(repo, 'cloudflare-bot', 'wrangler.jsonc'), 'utf8'));
config.name = 'alice-bot';
config.main = 'entry.js';
config.d1_databases.push({ ...botConfig.d1_databases[0], binding: 'BOT_DB' });
config.vars = { ...config.vars, ...botConfig.vars, MINIAPP_URL: 'https://alice-bot.lvl3lin4.workers.dev' };
// Scheduling is configured separately; building the combined Worker must not enable it.
config.triggers = {};
await writeFile(configPath, JSON.stringify(config, null, 2) + '\n');
