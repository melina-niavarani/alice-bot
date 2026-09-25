# Alice on Cloudflare

Alice uses **one Cloudflare Worker**, `alice-bot`, for both Telegram/Bale webhooks and the customer/admin miniapp. Both parts live in this GitHub repository. The miniapp build copies the bot handler into its Worker entry and attaches both D1 databases without moving or deleting their data.

| Worker | GitHub root directory | Build command | Deploy command |
| --- | --- | --- | --- |
| `alice-bot` | `miniapp` | `npm run build` | `npx wrangler deploy --config dist/server/wrangler.json` |

Cloudflare installs `miniapp/package-lock.json`. The generated config includes the public miniapp assets, `alice-miniapp-db` as `DB`, and `alice-bot-db` as `BOT_DB`. There is no recurring cron trigger configured.

## Runtime secrets

Configure these as encrypted **runtime secrets** on `alice-bot`, not GitHub files or build variables:

- Bot delivery: `TELEGRAM_BOT_TOKEN`, `BALE_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `BALE_WEBHOOK_SECRET`, `SETUP_SECRET`.
- Miniapp sign-in: `TELEGRAM_WEBAPP_SECRET`, `BALE_WEBAPP_SECRET` (64-character hex WebAppData HMAC keys derived from the respective bot tokens, **not raw tokens**), `ALICE_OWNER_ID=92655562`, `ALICE_BALE_OWNER_ID=1984558572`.

The Worker also has `TELEGRAM_OWNER_ID`, `BALE_OWNER_ID`, and `MINIAPP_URL` as ordinary variables. The public miniapp URL is `https://alice-bot.lvl3lin4.workers.dev/`. Its admin API checks signed messenger init data and the owner ID.

## One-time activation

1. Apply `cloudflare-bot/migrations/0001_initial.sql` to `alice-bot-db` and `miniapp/drizzle/0000_first_praxagora.sql` to `alice-miniapp-db`. Both production tables were created on 2026-09-24.
2. Save the runtime secrets and deploy `alice-bot`.
3. Call `POST https://alice-bot.lvl3lin4.workers.dev/ops/install` with `Authorization: Bearer <SETUP_SECRET>`. This installs both messenger webhooks and points the Telegram menu to the miniapp on the same Worker. The call is idempotent.
4. Test `/start` and miniapp opening in both bots, then a small broadcast.

To carry over known recipients from a local SQLite database, generate a private import file with:

```sh
python3 cloudflare-bot/scripts/export-contacts.py data/alice.sqlite3 data/cloudflare-contacts.sql
```

Import into `alice-bot-db` after the tables exist. This exports members and explicitly connected destinations, but does not replay old messages. Keep the SQL private because it contains messenger IDs and names.

Telegram and Bale do not run the bot code themselves. The Worker runs on Cloudflare without a running laptop.
