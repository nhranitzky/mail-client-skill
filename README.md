# Mail CLI

A terminal email client that reads and writes email via **IMAP** and **SMTP**.
Configured through a YAML file; password stored securely in a local file
that is never echoed, logged, or transmitted to any third party other than
your mail server.

---

## Requirements

| Tool | Version | Install |
|------|---------|---------|
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | ≥ 3.11 | managed automatically by `uv` |

---

## Installation

### 1 – Get the project

```bash
git clone https://github.com/your-org/mail-skill.git
cd mail-skill
```

### 2 – Create the configuration file

```bash
cp mail-client/config.yaml.example ~/.config/imail/config.yaml
```

Edit the file with your mail provider details:

```yaml
account:
  name: "Max Mustermann"
  email: "max@vodafone.de"

password_file: "~/.vodafonemail"

imap:
  host: "imap.vodafone.de"
  port: 993
  ssl: true

smtp:
  host: "smtp.vodafone.de"
  port: 587
  starttls: true

defaults:
  inbox: "INBOX"
  sent_folder: "Sent"
  trash_folder: "Trash"
  page_size: 20
```

### 3 – Store your password securely

```bash
echo 'your-mail-password' > ~/.vodafonemail
chmod 600 ~/.vodafonemail
```

The file must be readable only by you (`chmod 600`). The password is the
first line of the file (trailing newline is stripped automatically).

> **Security:** The password is read by the Python process and sent only to
> your IMAP/SMTP server over an encrypted TLS connection. It is never printed,
> logged, or transmitted to any LLM or third-party service.

### 4 – Set the config path environment variable

```bash
export MAIL_CONFIG_FILE=~/.config/imail/config.yaml
# Add to ~/.bashrc or ~/.zshrc to persist
```

### 5 – Install dependencies

```bash
cd mail-client && uv sync
```

### 6 – Make the launcher executable

```bash
chmod +x mail-client/bin/mail
```

### 7 – (Optional) Add to PATH

```bash
ln -s "$(pwd)/mail-client/bin/mail" ~/.local/bin/mail
# or
echo 'export PATH="$PATH:/path/to/mail-client-skill/mail-client/bin"' >> ~/.bashrc
source ~/.bashrc
```

---

## Common Mail Provider Settings

### Vodafone (Germany)

```yaml
imap:
  host: "imap.vodafone.de"
  port: 993
  ssl: true
smtp:
  host: "smtp.vodafone.de"
  port: 587
  starttls: true
```

### Gmail (requires App Password)

```yaml
imap:
  host: "imap.gmail.com"
  port: 993
  ssl: true
smtp:
  host: "smtp.gmail.com"
  port: 587
  starttls: true
```

> **Gmail:** Enable IMAP in Settings → See all settings → Forwarding and POP/IMAP.
> Use an [App Password](https://myaccount.google.com/apppasswords) if 2FA is enabled.

### GMX / Web.de

```yaml
imap:
  host: "imap.gmx.net"    # or imap.web.de
  port: 993
  ssl: true
smtp:
  host: "mail.gmx.net"    # or smtp.web.de
  port: 587
  starttls: true
```

### Outlook / Hotmail

```yaml
imap:
  host: "outlook.office365.com"
  port: 993
  ssl: true
smtp:
  host: "smtp.office365.com"
  port: 587
  starttls: true
```

---

## Usage

### List messages

```bash
# Show newest 20 messages in INBOX (default)
mail list

# Unread only
mail list --unread

# Different folder, custom limit
mail list --folder Sent --limit 10

# Pagination
mail list --offset 20 --limit 20

# JSON output
mail list --json | jq '.[].subject'
```

### Read a message

```bash
# Display headers + body (marks as read)
mail read 42

# Read without marking as read
mail read 42 --no-mark-read

# Save attachments
mail read 42 --save-attachments ~/Downloads

# From a non-default folder
mail read 7 --folder Sent

# JSON output
mail read 42 --json
```

### Send a new message

```bash
# Inline body
mail send --to alice@example.com --subject "Hello" --body "Hi there!"

# Body from file
mail send --to bob@example.com --subject "Report" --body-file report.txt

# Multiple recipients + attachment
mail send \
  --to alice@example.com \
  --to bob@example.com \
  --cc manager@example.com \
  --subject "Q3 Numbers" \
  --body "Please find attached." \
  --attach q3.pdf \
  --attach data.xlsx

# Interactive body entry (end with a single '.' line)
mail send --to alice@example.com --subject "Quick note"
```

### Reply to a message

```bash
# Reply to UID 42 (prompts for body)
mail reply 42

# Inline body
mail reply 42 --body "Thanks, will do!"

# Reply-all
mail reply 42 --reply-all --body "Sounds good to everyone?"

# Reply from a different folder
mail reply 7 --folder Sent --body "Resending…"
```

### Search messages

```bash
# Full-text search (body)
mail search invoice

# Structured filters
mail search --from boss@company.com --unread
mail search --subject "Meeting" --since 2024-01-01
mail search --since 2024-06-01 --before 2024-07-01

# Combine text + filters
mail search report --since 2024-06-01 --before 2024-07-01

# Search in a specific folder
mail search --folder Archive --subject "receipt"

# Flagged messages larger than 5 MB
mail search --flagged --larger 5000

# JSON output
mail search invoice --json | jq '.[].uid'
```

### Browse folders

```bash
# List all folders
mail folders

# Include message counts (slower)
mail folders --counts

# JSON
mail folders --json
```

### Manage messages

```bash
# Move to a folder
mail manage move 42 --to Archive
mail manage move 42 --from Spam --to INBOX

# Trash (move to Trash folder)
mail manage delete 42

# Permanent delete (expunge immediately)
mail manage delete 42 --permanent

# Flag / unflag
mail manage flag 42
mail manage unflag 42

# Mark read / unread
mail manage mark-read 42
mail manage mark-unread 42
```

---

## Running Without Adding to PATH

```bash
# From inside the project root
uv run python -m scripts.main list

# From anywhere
uv run --project /path/to/mail-skill python -m scripts.main list --unread
```

---

## Project Structure

```
mail-skill/
├── SKILL.md              ← Claude skill metadata
├── pyproject.toml        ← Python project / uv config
├── README.md             ← this file
├── config.yaml           ← your configuration (created from .example)
├── config.yaml.example   ← configuration template
├── bin/
│   └── mail             ← shell launcher
└── scripts/
    ├── __init__.py
    ├── main.py           ← CLI entry point
    ├── utils.py          ← config, password, IMAP/SMTP, message parsing
    ├── cmd_list.py       ← `mail list`
    ├── cmd_read.py       ← `mail read`
    ├── cmd_send.py       ← `mail send`
    ├── cmd_reply.py      ← `mail reply`
    ├── cmd_search.py     ← `mail search`
    ├── cmd_folders.py    ← `mail folders`
    └── cmd_manage.py     ← `mail manage`
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `MAIL_CONFIG_FILE not set` | `export MAIL_CONFIG_FILE=~/.config/imail/config.yaml` |
| `Config file not found` | Copy `config.yaml.example` to the path set in `MAIL_CONFIG_FILE` |
| `Password file not found` | Run `echo 'password' > ~/.vodafonemail && chmod 600 ~/.vodafonemail` |
| `IMAP connection failed` | Check host/port/ssl settings; verify credentials |
| `SMTP connection failed` | Check smtp settings; some providers require App Passwords |
| `Message UID not found` | UIDs can change after expunge; re-run `mail list` to refresh |
| `Could not save to Sent` | Check `defaults.sent_folder` name in config.yaml |
| `Authentication failed (Gmail)` | Use an App Password and ensure IMAP is enabled |

---

## Security Notes

- The config file path is set via `MAIL_CONFIG_FILE` — keep it outside the repository.
- The password file (e.g. `~/.vodafonemail`) should **never** be committed.
- Keep `chmod 600` on both the config and password files so only your user can read them.
- All IMAP/SMTP connections use TLS (SSL or STARTTLS as configured).

## Development Notes
Parts of this codebase were generated or assisted by Claude Code  Sonnet 4.6  
All generated code has been reviewed and tested by human developers.
---

## License

MIT
