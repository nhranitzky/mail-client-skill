"""
mail reply – Reply to an existing message by UID.

Fetches the original message, builds a proper reply (sets In-Reply-To,
References, Re: subject prefix) and sends it via SMTP.
"""

from __future__ import annotations

import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from textwrap import indent

import click

from scripts.utils import (
    console,
    load_config,
    imap_connect,
    smtp_connect,
    append_to_sent,
    msg_to_bytes_crlf,
    parse_message,
    fmt_date,
)


def _quote_body(m: dict) -> str:
    """Build a quoted-reply body from the original message."""
    date_from  = fmt_date(m)
    sender     = m.get("from", "")
    lines      = m.get("body", "").splitlines()
    quoted     = indent("\n".join(lines), "> ")
    return f"\n\n---\nOn {date_from}, {sender} wrote:\n{quoted}\n"


@click.command()
@click.argument("uid", type=int)
@click.option("--folder",    "-f", default=None,
              help="Folder containing the original message (default: INBOX).")
@click.option("--body",      "-b", default=None, help="Reply body text (inline).")
@click.option("--body-file", "-B", "body_file",
              type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Read reply body from this file.")
@click.option("--reply-all", is_flag=True, default=False,
              help="Reply to all recipients (To + Cc).")
@click.option("--cc",        "-c", "extra_cc", multiple=True,
              help="Additional Cc addresses.")
def reply(uid: int, folder: str | None, body: str | None, body_file: Path | None,
          reply_all: bool, extra_cc: tuple[str, ...]):
    """
    Reply to message UID.

    \b
    Examples:
        mail reply 42
        mail reply 42 --body "Thanks, will do!"
        mail reply 42 --reply-all --body-file response.txt
    """
    cfg      = load_config()
    defaults  = cfg.get("defaults", {})
    folder   = folder or defaults.get("inbox", "INBOX")
    account  = cfg["account"]
    my_email = account["email"]
    my_name  = account.get("name", "")
    from_addr = f"{my_name} <{my_email}>" if my_name else my_email

    # ── Fetch original ────────────────────────────────────────────────────────
    client = imap_connect(cfg)
    try:
        client.select_folder(folder, readonly=True)
        data = client.fetch([uid], ["RFC822"])
        if uid not in data:
            console.print(f"[red]Message UID {uid} not found in {folder}.[/]")
            sys.exit(1)
        raw = data[uid][b"RFC822"]
    finally:
        client.logout()

    original = parse_message(raw)

    # ── Determine recipients ──────────────────────────────────────────────────
    # Reply-To takes precedence over From
    import email as email_lib
    msg_obj = email_lib.message_from_bytes(raw)
    reply_to_hdr = msg_obj.get("Reply-To") or msg_obj.get("From") or ""
    _, reply_to_addr = parseaddr(reply_to_hdr)
    to_list = [reply_to_addr or original["from"]]

    cc_list = list(extra_cc)
    if reply_all:
        # Add original To/Cc, excluding ourselves
        for field in (original["to"], original["cc"]):
            if not field:
                continue
            for part in field.split(","):
                _, addr = parseaddr(part.strip())
                if addr and addr.lower() != my_email.lower() and addr not in to_list:
                    cc_list.append(addr)

    # ── Subject ───────────────────────────────────────────────────────────────
    orig_subj = original["subject"]
    subject   = orig_subj if orig_subj.lower().startswith("re:") else f"Re: {orig_subj}"

    # ── Body ─────────────────────────────────────────────────────────────────
    if body_file:
        body_text = body_file.read_text(encoding="utf-8")
    elif body:
        body_text = body
    else:
        console.print("[dim]Enter reply body. Type a single '.' on a line to finish:[/]")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == ".":
                break
            lines.append(line)
        body_text = "\n".join(lines)

    full_body = body_text + _quote_body(original)

    # ── Build MIME ────────────────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"]       = from_addr
    msg["To"]         = ", ".join(to_list)
    if cc_list:
        msg["Cc"]     = ", ".join(cc_list)
    msg["Subject"]    = subject
    msg["In-Reply-To"] = original["message_id"]
    refs = f"{original.get('references', '')} {original['message_id']}".strip()
    msg["References"] = refs
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    # ── Send ──────────────────────────────────────────────────────────────────
    all_recipients = to_list + cc_list
    smtp = smtp_connect(cfg)
    try:
        # send_message() ensures CRLF line endings (RFC 5321).
        # Using sendmail()+as_bytes() can produce bare LF → "5.5.2" rejection.
        smtp.send_message(msg)
    except Exception as exc:
        console.print(f"[red]Send failed:[/] {exc}")
        sys.exit(1)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass

    console.print(f"\n[bold green]✅  Reply sent[/] → {', '.join(to_list)}")

    # Append to Sent (best-effort, auto-detects folder name)
    sent_folder = defaults.get("sent_folder", "Sent")
    append_to_sent(cfg, msg_to_bytes_crlf(msg), preferred=sent_folder)

    console.print()
