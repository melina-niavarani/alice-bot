# Alice on Cloudflare

The repository deploys two Workers in the **same Cloudflare account**. The bot
Worker handles Telegram and Bale webhooks, broadcasts, and the delivery queue.
The miniapp Worker serves the public customer app and its private admin API.
Each Worker has its own D1 database.

| Worker | GitHub root directory | Build command | Deploy command |
| --- | --- | --- | --- |
| `alice-bot` | `cloudflare-bot` | none | `npx wrangler deploy` |
| `alice-miniapp` | `miniapp` | `npm run build` | `npx wrangler deploy --config dist/server/wrangler.json` |

Cloudflare must install each directory's `package-lock.json` dependencies.
The D1 names and IDs are already present in each `wrangler.jsonc`. For the
miniapp, the build creates `dist/server/wrangler.json`, which must be used as
the deploy config so the client assets are published too.

## Runtime secrets

Add these as **encrypted runtime secrets**, not GitHub files or build variables:

- `alice-bot`: `TELEGRAM_BOT_TOKEN`, `BALE_BOT_TOKEN`,
  `TELEGRAM_WEBHOOK_SECRET`, `BALE_WEBHOOK_SECRET`, `SETUP_SECRET`.
- `alice-miniapp`: `TELEGRAM_WEBAPP_SECRET` and `BALE_WEBAPP_SECRET`
  (the 64-character hex WebAppData HMAC keys derived from the respective bot
  tokens, **not the raw bot tokens**), `ALICE_OWNER_ID=92655562`,
  `ALICE_BALE_OWNER_ID=1984558572`.

The bot's public miniapp URL and owner IDs are ordinary Wrangler vars. Update
`MINIAPP_URL` if the miniapp's production hostname differs from
`https://alice-miniapp.lvl3lin4.workers.dev`.

Both Workers need their `workers.dev` domains enabled, unless a public custom
domain is connected. The miniapp is public; its admin API checks signed
messenger init data and the owner ID.

## One-time activation

1. Apply the SQL in `cloudflare-bot/migrations/0001_initial.sql` to
   `alice-bot-db`, and `miniapp/drizzle/0000_first_praxagora.sql` to
   `alice-miniapp-db`. The production tables were created on 2026-09-24.
2. Set the runtime secrets and deploy both Workers.
3. Call `POST https://alice-bot.lvl3lin4.workers.dev/ops/install` with
   `Authorization: Bearer <SETUP_SECRET>`. This switches both messenger
   webhooks to Cloudflare and sets the Telegram menu button. The endpoint is
   idempotent and should return `telegram` and `bale` as `registered`.
4. Test `/start` and miniapp opening in both bots, then a small broadcast.

To carry over known recipients from the local SQLite database, generate a
private import file with:

```sh
python3 cloudflare-bot/scripts/export-contacts.py data/alice.sqlite3 data/cloudflare-contacts.sql
```

Import it into `alice-bot-db` after the tables exist. The script exports only
members and explicitly connected destinations. It does **not** replay the old
outbox, which could send duplicate announcements. Keep the generated SQL
private; it contains messenger IDs and names.

Telegram and Bale do not run the bot code themselves. Once the webhooks point
to this Worker, the bot runs on Cloudflare and needs no running laptop.
