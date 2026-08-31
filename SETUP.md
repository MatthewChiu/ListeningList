# Discord Bot Setup

Three commands: `/recommend [prompt]`, `/add [prompt]`, `/listened [composer] [title]`.

Flow: Discord → Cloudflare Worker (verifies + acks instantly) → GitHub Action
(`agent.py` runs, commits to `docs/`) → Worker's deferred reply gets edited with
the result.

## 1. Create the Discord app

1. Go to https://discord.com/developers/applications → **New Application**.
2. Under **General Information**, copy the **Public Key** and **Application ID**.
3. Under **Bot**, click **Reset Token** and copy the **Bot Token** (needed once,
   for registering commands).
4. Under **Bot**, disable "Public Bot" if you don't want strangers adding it,
   or just don't share the invite link.
5. Under **OAuth2 → URL Generator**, check scope `bot` and permission
   `Send Messages`, then use the generated URL to invite it to your server.

## 2. Register the slash commands

```bash
export DISCORD_APPLICATION_ID=...
export DISCORD_BOT_TOKEN=...
pip install requests
python scripts/register_commands.py
```

## 3. Deploy the Cloudflare Worker

```bash
cd cloudflare-worker
npm install
npx wrangler login

# Edit wrangler.toml: set GITHUB_REPO to "your-username/your-repo"

npx wrangler secret put DISCORD_PUBLIC_KEY   # paste the Public Key from step 1
npx wrangler secret put GITHUB_TOKEN         # a GitHub fine-grained PAT, see step 4

npx wrangler deploy
```

Wrangler prints a URL like `https://listening-log-bot.<you>.workers.dev`.

## 4. GitHub token for the Worker

Create a **fine-grained personal access token**
(https://github.com/settings/personal-access-tokens/new) scoped to just this
repo, with **Contents: Read and write** permission (that's what lets it fire
`repository_dispatch`). Use this as `GITHUB_TOKEN` in step 3.

## 5. Point Discord at the Worker

Back in the Discord Developer Portal → **General Information** →
**Interactions Endpoint URL** → paste your Worker URL from step 3, then Save.
Discord will send a test ping immediately; if the Worker is deployed with the
right public key it'll verify and save successfully.

## 6. GitHub repo secrets

In your repo → **Settings → Secrets and variables → Actions**, make sure you
have:

- `GEMINI_API_KEY` (already needed by `agent.py`)
- `DISCORD_WEBHOOK_URL` — only needed for the daily cron post, *not* the
  slash commands. Create one in your Discord channel: **Channel Settings →
  Integrations → Webhooks → New Webhook**, copy its URL.

## 7. Try it

In your Discord server: `/recommend calm and reflective`,
`/add Brahms Symphony No. 4`, `/listened composer:Moszkowski title:Piano Concerto`.

Each should show "thinking..." for a few seconds (the GitHub Action running),
then the bot edits its own message with the result.

## Notes / things to double check

- `chat_interface.yml` (the old GitHub-Issues-based interface) is left in
  place but now redundant — delete it once you've confirmed Discord works, or
  keep it as a backup input method; they don't conflict.
- The daily cron in `daily_recommend.yml` runs at 13:00 UTC (9am ET) —
  adjust for your timezone/DST.
- `add_listening()` asks the model to identify the composer/piece from your
  prompt, so oddly-phrased requests may occasionally misfire — the bot will
  tell you what it added, so you can catch a wrong guess and fix the markdown
  by hand.
