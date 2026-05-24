# Stakeholder Status Email — RC1

Automated weekly status email for the AI Incident Summarizer project (RC1), powered by n8n and Claude.

## What it does

Every Friday at 4pm ET:
1. Pulls all RC1 tasks from the Notion RC1 Tasks database (filtered to Epic RC1-31)
2. Fetches this week's Jira updates for RC1 child tickets
3. Aggregates and groups tickets by status in a Code node
4. Sends data to Claude to generate an executive summary
5. Combines Claude's summary with pre-built HTML tables into a polished email
6. **If REQUIRE_PREVIEW = true:** sends a preview to Reid's personal email for approval before sending to stakeholders
7. Sends the final email via Gmail to stakeholders
8. Posts a confirmation to Slack #ai-incident-summarizer

## Email format

**Executive Summary** — 2-3 sentences for C-suite, plain English, no jargon

**Project Status** — health indicator, completion %, report date

**Detailed Status Tables** — HTML tables with columns: Ticket, Description, Priority, Assignee:
- 🔄 In Progress
- 👀 In Review
- 🚫 Blocked
- 📋 Up Next
- ✅ Completed This Week

Ticket numbers in tables link directly to Jira.

## Preview & approval gate (RC1-56 — pending)

For sensitive projects (C-suite audience), a human-in-the-loop approval gate can be enabled via the `REQUIRE_PREVIEW` flag.

### How it works

When `REQUIRE_PREVIEW = true`:
1. At 3:45pm ET, a preview email is sent to `hire.reid.collins@gmail.com`
2. The preview email contains three links:
   - **Approve & Send** — triggers the Gmail send to stakeholders
   - **View in browser** — opens the rendered HTML email in your browser
   - **Discard** — cancels the send and posts a Slack notification
3. Clicking Approve or Discard hits an n8n Webhook node
4. If neither is clicked within 45 minutes, the workflow auto-sends anyway

### Mobile approval

The approval links work from any device. Tapping **Approve & Send** in the iPhone Mail app hits the webhook and triggers the send — no special app required.

### REQUIRE_PREVIEW flag

Stored in n8n Variables (not hardcoded), so it can be toggled without code changes:

| Value | Behavior |
|-------|----------|
| `true` | Preview gate active — approval required before stakeholder send |
| `false` | Send directly to stakeholders with no gate |

Set to `true` for C-suite-facing projects. Set to `false` for internal digests.

### Infrastructure requirement

The approval gate requires publicly accessible webhook URLs. This means:
- **n8n Cloud** (recommended) — permanent public URL, works from any device
- **ngrok** — free tunnel to localhost, but URL changes each restart and depends on Mac being on
- **localhost only** — approval links only work when on the same machine as n8n

**Decision: migrate to n8n Cloud (~$20/month)** — see Decision Log in Notion for full rationale.

## Prerequisites

- n8n running (Docker locally or n8n Cloud)
- Jira SW Cloud API credential
- Notion Header Auth credential (Bearer token)
- Anthropic API key (from console.anthropic.com)
- Gmail OAuth2 credential (Google Cloud Console → n8n-gmail OAuth app)
- Slack incoming webhook URL (api.slack.com/apps → Incident Summarizer)

## Setup

### 1. Get your Anthropic API key
Go to console.anthropic.com → API Keys → Create key → name it `n8n-stakeholder-email`

### 2. Set up Gmail OAuth2 in n8n
1. Go to console.cloud.google.com → create project `n8n-gmail`
2. Enable Gmail API
3. Create OAuth consent screen (External, User data)
4. Add scope: `https://www.googleapis.com/auth/gmail.send`
5. Add `hire.reid.collins@gmail.com` as a test user
6. Create OAuth Client ID (Web application)
7. Add redirect URI: `http://localhost:5678/rest/oauth2-credential/callback`
8. In n8n: Credentials → Gmail OAuth2 → paste Client ID and Secret → Sign in with Google

### 3. Import the workflow
In n8n: Workflows → Import from file → select `workflows/stakeholder_status_email.json`

### 4. Wire up credentials
Click each node and assign the correct credential:
- Notion — Get All RC1 Tasks → Header Auth account
- Jira — Get This Week's Updates → Jira SW Cloud account
- Claude — Generate Email → paste Anthropic API key into x-api-key header
- Gmail — Send Status Email → Gmail account
- Slack HTTP Request nodes → no credential needed (webhook URL in body)

### 5. Configure stakeholder emails
In **Gmail — Send Status Email** node, update the **To** field with stakeholder emails.
For testing, set To = `hire.reid.collins@gmail.com` first.

### 6. Test
Manually trigger the workflow and verify:
- Notion returns RC1-31 tickets only (not all RC1 tickets)
- Claude generates a coherent executive summary
- HTML tables are populated with real ticket data
- Gmail sends successfully
- Slack confirmation appears in #ai-incident-summarizer

### 7. Publish
Toggle the workflow to Active — it will run automatically every Friday at 4pm ET.

## Project structure

```
n8n-stakeholder-status-email/
├── docker-compose.yaml         # Notes on using existing n8n instance
├── .env.example                # Environment variable template
├── .env                        # Your local config (not committed)
├── .gitignore
├── README.md
└── workflows/
    └── stakeholder_status_email.json   # Importable n8n workflow
```

## Key design decisions

- **No loop nodes** — workflow fetches all data in one shot, no per-item looping needed
- **Parallel data fetch** — Notion and Jira queried simultaneously from the schedule trigger
- **Code node builds HTML tables** — avoids JSON escaping issues with n8n expressions inside Claude prompt; Claude only writes the executive summary narrative
- **Claude via HTTP Request** — direct Anthropic API call (claude-sonnet-4-6), same pattern as the sync workflow
- **Slack via HTTP Request** — n8n's native Slack node doesn't expose credential field in current version; webhook URL used directly
- **Notion via HTTP Request** — n8n's Notion node missing Update/GetAll operations in current version
- **Epic filter in Code node** — Notion query fetches all RC1 tickets; filtering to RC1-31 happens in the Aggregate & Summarize Data Code node, keeping the Notion query generic and reusable
- **REQUIRE_PREVIEW flag** — stored in n8n Variables for toggle without code changes; enables approval gate for sensitive C-suite-facing projects
- **n8n Cloud migration** — required for REQUIRE_PREVIEW feature so webhook approval links work from any device including mobile

## Known issues & workarounds

| Issue | Workaround |
|-------|------------|
| n8n Notion node missing Update/GetAll | Use HTTP Request nodes for all Notion API calls |
| n8n Slack node missing credential field | Use HTTP Request nodes with Slack incoming webhook URL |
| n8n expressions inside Claude JSON body cause parse errors | Pre-build HTML tables in Code node; pass only scalar values to Claude |
| Schedule trigger interval reverts to Days | Set unit dropdown first, then type value, then Tab away |
| Notion API 502 rate limiting on rapid requests | Add Wait node between loop and Notion API calls |

## Useful commands

```bash
# Start n8n (local Docker)
cd ~/programming/personal/n8n-jira-notion-sync
docker compose up -d

# Stop n8n
docker compose down

# View logs
docker compose logs -f n8n

# Restart n8n
docker compose restart n8n
```

## Related

- [Jira ↔ Notion Sync](../n8n-jira-notion-sync/) — the companion workflow that keeps Notion RC1 Tasks in sync with Jira
- [Notion Stakeholder Email Automation space](https://www.notion.so/36864de5dacd80dc8137db1cd8711a94) — project docs, architecture, runbook, RAID log, decision log
- [RC1-47 Epic](https://hirereidcollins.atlassian.net/browse/RC1-47) — Jira epic tracking all stories for this project
- [RC1-56](https://hirereidcollins.atlassian.net/browse/RC1-56) — Preview & approval gate story