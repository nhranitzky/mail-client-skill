---
name: mail-client
description: Read and write emails via IMAP/SMTP from the terminal. Use this skill whenever the user wants to check their inbox, read a specific email, send a new message, reply to an email, search for messages, manage folders, move or delete messages, or flag/star emails. Also trigger for  "check my mail", "read my emails", "send an email" "what's in my inbox"
metadata: { "openclaw": {"emoji": "📧" } } 
---
 
# Mail Client Skill

Read and write email via **IMAP** (reading) and **SMTP** (sending).
Config file path set via `MAIL_CONFIG_FILE` environment variable; password loaded from a local file.

## ⚠️ Password Security


**Openclaw must NEVER:**
- Ask the user to paste or display their password
- Include the password in any response or log output
- Echo the value of `password_file` contents

 

## Available Commands

| Command | Description |
|---------|-------------|
| `{baseDir}/bin/mail list` | List messages newest-first (paginated) |
| `{baseDir}/bin/mail list --unread` | Only unread messages |
| `{baseDir}/bin/mail read <uid>` | Display full message (headers + body) |
| `{baseDir}/bin/mail read <uid> --save-attachments DIR` | Also save attachments |
| `{baseDir}/bin/mail send --to <addr> --subject <s>` | Compose and send a new message |
| `{baseDir}/bin/mail reply <uid>` | Reply to a message (sets In-Reply-To / References) |
| `{baseDir}/bin/mail reply <uid> --reply-all` | Reply to all recipients |
| `{baseDir}/bin/mail search <query>` | Full-text search (server-side IMAP SEARCH) |
| `{baseDir}/bin/mail search --from <addr> --unread` | Structured search with filters |
| `{baseDir}/bin/mail folders` | List all IMAP folders |
| `{baseDir}/bin/mail folders --counts` | Include total/unread counts per folder |
| `{baseDir}/bin/mail manage move <uid> --to <folder>` | Move message to another folder |
| `{baseDir}/bin/mail manage delete <uid>` | Move to Trash |
| `{baseDir}/bin/mail manage delete <uid> --permanent` | Expunge immediately |
| `{baseDir}/bin/mail manage flag <uid>` | Star / flag a message |
| `{baseDir}/bin/mail manage unflag <uid>` | Remove star |
| `{baseDir}/bin/mail manage mark-read <uid>` | Mark as read |
| `{baseDir}/bin/mail manage mark-unread <uid>` | Mark as unread |

All commands accept `--json` for machine-readable output (except manage).

## Key Options

| Option | Description |
|--------|-------------|
| `--folder / -f` | Override default folder (default: INBOX from config) |
| `--limit / -n` | Cap result count |
| `--offset / -o` | Pagination offset |
| `--json` | Emit JSON instead of Rich table |
| `--no-mark-read` | Read without marking `\Seen` |

 

## How Claude Should Use This Skill

1. Identify intent: list / read / send / reply / search / manage.
2. Extract parameters (UID, folder, recipient, subject, body text).
3. Run `{baseDir}/bin/mail <command> [options]` via the shell.
4. Parse and summarise the output — **never display or relay the password**.
5. For JSON mode (`--json`), extract the relevant fields and present them clearly.



## Example Invocations

```bash
# Check inbox
{baseDir}/bin/mail list
{baseDir}/bin/mail list --unread --limit 10

# Read + save attachments
{baseDir}/bin/mail read 42
{baseDir}/bin/mail read 42 --save-attachments ~/Downloads

# Send
{baseDir}/bin/mail send --to alice@example.com --subject "Hello" --body "Hi!"
{baseDir}/bin/mail send --to alice@example.com --subject "Hello" --body-file filename.txt 
{baseDir}/bin/mail send --to team@co.com --subject "Report Q3" --attach report.pdf

# Reply
{baseDir}/bin/mail reply 42 --body "Thanks, got it."
{baseDir}/bin/mail reply 42 --reply-all

# Search
{baseDir}/bin/mail search invoice
{baseDir}/bin/mail search --from boss@example.com --since 2024-06-01 --unread
{baseDir}/bin/mail search --subject "meeting" --folder Work

# Manage
{baseDir}/bin/mail folders --counts
{baseDir}/bin/mail manage move 42 --to Archive
{baseDir}/bin/mail manage delete 42
{baseDir}/bin/mail manage flag 42
{baseDir}/bin/mail manage mark-unread 42
```
## Troubleshooting

| Error / Symptom | What to do |
|-----------------|------------|
| `MAIL_CONFIG_FILE environment variable is not set` | The env var is missing. Tell the user to set it | 
| `Config file not found` | The path in `MAIL_CONFIG_FILE` does not exist. Ask the user to verify the path or run `install-skill.sh` to create it from the template. |
| `config.yaml is missing the '...' section` | The config file is incomplete. Tell the user to open `$MAIL_CONFIG_FILE` and add the missing section (`account`, `imap`, or `smtp`). |
| `password_file not set` | The config file has no `password_file` key. Ask the user to add it pointing to a file with their mail password. |
| `Password file not found` | The file referenced by `password_file` does not exist. Guide the user: `echo 'yourpassword' > <path> && chmod 600 <path>`. Never display the password. |
| `Password file is empty` | The password file exists but has no content. Ask the user to write their password into it. |
| `IMAP connection failed` | Wrong `imap.host`, `imap.port`, or `imap.ssl` setting, or bad credentials. Ask the user to double-check the config. |
| `SMTP connection failed` | Wrong `smtp.host`, `smtp.port`, or `smtp.starttls` setting. Some providers require an App Password (e.g. Gmail). |
| `Authentication failed` | Credentials are wrong. For Gmail/Outlook, an App Password is required when 2FA is enabled. |
| `Message UID not found` | UIDs can shift after a folder expunge. Re-run `mail list` to get fresh UIDs before retrying. |
| `Could not save to Sent` | The `defaults.sent_folder` name in the config does not match an existing IMAP folder. Run `mail folders` to list valid names and update the config. |
| Folder name contains spaces | Wrap the folder name in quotes: `--folder "Sent Items"`. |
| No messages returned | The folder may be empty or the filter is too restrictive. Try without `--unread` or widen the `--since` date range. |