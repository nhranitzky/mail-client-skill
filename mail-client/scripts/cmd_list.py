"""
mail list – List messages in a mailbox folder.

Shows UID, sender, subject, date, and size in a Rich table.
Supports filtering by unread-only, and pagination via --offset.
"""

from __future__ import annotations

import json
import sys

import click
from imapclient import IMAPClient

from scripts.utils import (
    console,
    load_config,
    imap_connect,
    parse_message,
    make_list_table,
    fmt_date,
    fmt_size,
)
from rich.text import Text


@click.command("list")
@click.option("--folder", "-f", default=None,
              help="Mailbox folder (default: INBOX from config).")
@click.option("--limit",  "-n", default=None, type=int,
              help="Maximum messages to show (default: page_size from config).")
@click.option("--offset", "-o", default=0, show_default=True, type=int,
              help="Skip N most-recent messages (for pagination).")
@click.option("--unread", "-u", is_flag=True, default=False,
              help="Show only unread messages.")
@click.option("--json",   "as_json", is_flag=True, default=False,
              help="Output JSON array instead of table.")
def list_messages(folder: str | None, limit: int | None, offset: int,
                  unread: bool, as_json: bool):
    """
    List messages in a mailbox FOLDER.

    Messages are shown newest-first. Use --offset for pagination.

    \b
    Examples:
        mail list
        mail list --folder Sent --limit 10
        mail list --unread
        mail list --offset 20 --limit 20
    """
    cfg     = load_config()
    defaults = cfg.get("defaults", {})
    folder  = folder or defaults.get("inbox", "INBOX")
    limit   = limit  or defaults.get("page_size", 20)

    client = imap_connect(cfg)
    try:
        client.select_folder(folder, readonly=True)
        criteria = ["UNSEEN"] if unread else ["ALL"]
        uids: list[int] = client.search(criteria)
        uids = list(reversed(uids))          # newest first
        total = len(uids)
        uids  = uids[offset : offset + limit]

        if not uids:
            console.print(f"\n[yellow]No{'unread ' if unread else ' '}messages in {folder}.[/]\n")
            return

        # Fetch envelope + size (no body download)
        fetch_data = client.fetch(uids, ["ENVELOPE", "RFC822.SIZE", "FLAGS"])

        rows = []
        for uid in uids:
            data     = fetch_data.get(uid, {})
            env      = data.get(b"ENVELOPE")
            flags    = data.get(b"FLAGS", [])
            size     = data.get(b"RFC822.SIZE")
            seen     = b"\\Seen" in flags

            if env:
                subject = _decode_env_str(env.subject)
                sender  = _format_addr(env.from_)
                date_str = str(env.date or "")
            else:
                subject = "(unknown)"
                sender  = "(unknown)"
                date_str = ""

            rows.append({
                "uid":     uid,
                "seen":    seen,
                "subject": subject,
                "from":    sender,
                "date":    date_str[:16],
                "size":    size,
                "flags":   [f.decode() if isinstance(f, bytes) else str(f) for f in flags],
            })

    finally:
        client.logout()

    if as_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    title = f"📬  {folder}  ({total} message{'s' if total != 1 else ''}"
    if unread:
        title += ", unread only"
    title += f")  –  showing {offset + 1}–{offset + len(rows)}"

    table = make_list_table(title)
    for r in rows:
        flag_icon = "●" if not r["seen"] else " "
        flag_style = "bold white" if not r["seen"] else "dim"
        table.add_row(
            str(r["uid"]),
            Text(flag_icon, style="cyan" if not r["seen"] else "dim"),
            Text(r["from"],    style=flag_style, overflow="ellipsis"),
            Text(r["subject"], style=flag_style, overflow="ellipsis"),
            Text(r["date"],    style="dim"),
            Text(fmt_size(r["size"]), style="dim"),
        )

    console.print()
    console.print(table)
    remaining = total - offset - len(rows)
    if remaining > 0:
        console.print(
            f"  [dim]… {remaining} more. Use [/][bold]--offset {offset + len(rows)}[/]"
            f"[dim] for the next page.[/]"
        )
    console.print()


# ---------------------------------------------------------------------------
# Envelope decoding helpers (imapclient returns structured objects)
# ---------------------------------------------------------------------------

def _decode_env_str(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        import email.header
        parts = email.header.decode_header(value.decode("utf-8", errors="replace"))
        out = []
        for fragment, charset in parts:
            if isinstance(fragment, bytes):
                out.append(fragment.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(fragment)
        return "".join(out)
    return str(value)


def _format_addr(addr_list: list | None) -> str:
    if not addr_list:
        return ""
    a = addr_list[0]
    name  = _decode_env_str(a.name)
    mbox  = _decode_env_str(a.mailbox) if a.mailbox else ""
    host  = _decode_env_str(a.host)    if a.host    else ""
    email_addr = f"{mbox}@{host}" if mbox and host else ""
    if name:
        return f"{name} <{email_addr}>" if email_addr else name
    return email_addr or "(unknown)"
