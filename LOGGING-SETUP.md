# Logging Setup — `email_log` audit trail

This workflow now writes an **append-only audit log** (one row per lifecycle event) to a new n8n Data Table called `email_log`. Because n8n Data Table columns are created in the n8n UI — not by the workflow JSON — you need to do a little one-time setup before re-importing. Total time: ~10 minutes.

## Step 1 — Create the `email_log` Data Table

In your n8n Cloud project: **Data Tables → Create Data Table → name it `email_log`**, then add these columns **exactly** (names and types must match, or the log nodes won't bind):

| Column | Type |
|---|---|
| `timestamp` | String |
| `event` | String |
| `level` | String |
| `executionId` | String |
| `reportDate` | String |
| `requirePreview` | Boolean |
| `outcome` | String |
| `health` | String |
| `completionPct` | Number |
| `total` | Number |
| `statusCounts` | String |
| `subject` | String |
| `detail` | String |

> n8n always adds a built-in `id` and timestamps of its own — you don't need to create those. Only add the 13 columns above.

## Step 2 — Add one column to the existing `pending_email` table

The approval/discard webhooks run as *separate* executions from the Friday send, so they can't see the original run's data. To let them stamp their log rows with the right week, the workflow now stores `reportDate` in `pending_email`.

Open the existing **`pending_email`** Data Table and add one column:

| Column | Type |
|---|---|
| `reportDate` | String |

## Step 3 — Re-import the workflow

Import `workflows/status-email-notification.json` into n8n (Workflows → ⋯ → Import from File), overwriting the existing one. Editing the file on disk does **not** update the running instance — the re-import is what applies all of this.

## Step 4 — Point the log nodes at the table (one-time)

The five new logging nodes ship with a **placeholder** table reference (`REPLACE_WITH_email_log_TABLE_ID`) because the real table ID doesn't exist until you create it in Step 1. After importing, open each of these nodes and pick **`email_log`** from the Data Table dropdown:

- `Log — Preview Sent`
- `Log — Sent Direct`
- `Log — Sent Approved`
- `Log — Discarded`
- `Log — Errored`

(The `Get row(s)2` node already points at `pending_email` and needs no change.)

## Step 5 — Re-assign credentials if needed

n8n import sometimes drops credential bindings on nodes it sees as new. After import, spot-check that the Gmail, Jira, and Anthropic nodes still have their credentials assigned, and re-wire any that came up blank.

## What gets logged

| Event | When | Where it's written | Metrics included? |
|---|---|---|---|
| `preview_sent` | Preview email sent to you (gate on) | after `Upsert row(s)` | ✅ full |
| `sent` | Sent directly (gate off) | after `Slack - Email Sent` | ✅ full |
| `sent` | Sent after you approved | after `Slack -- Email Approved` | correlate by `reportDate` |
| `discarded` | You discarded the preview | after `Update row(s)1` | correlate by `reportDate` |
| `errored` / `aborted_empty` | Any failure, incl. the empty-Notion guard | after `Slack — Error Alert` | error detail + failing node |

Each row carries `timestamp`, `executionId`, and `outcome`, so you can reconstruct the full lifecycle of any week. The rows written from the scheduled run hold the full metrics (`health`, `completionPct`, `total`, `statusCounts`); the approval/discard rows correlate back to them via the shared `reportDate`.

### Design notes

- **Append-only.** Nothing is ever updated — every event is a new row. This is the standard event-log pattern and avoids cross-execution update races.
- **Best-effort, never fatal.** The log nodes are set to *continue on error* and retry up to 3×, so a logging hiccup can never block or fail an actual email send.
- **`console.log` is dev-only.** The Code nodes also emit `[status-email]` console lines, but on n8n Cloud those only show in the editor during manual runs — the `email_log` table is your real system of record.
- **Growth is a non-issue.** A few rows per week keeps the table tiny for years; no pruning needed.

## Reading the log

In n8n, open the `email_log` Data Table to browse. To find a specific week, filter by `reportDate`. To audit failures, filter `level = error`. To see approval history, filter `event = discarded` or `event = sent`.

## Future upgrades (not done here)

- Promote the in-workflow Error Trigger to a **shared error workflow** once you have more than one workflow (set under Workflow Settings → Error Workflow).
- Add **`retryOnFail`** to the external-call nodes (Notion, Jira, Claude, Gmail) — review item #8.
