"""
mail search – Server-side IMAP search across a mailbox folder.

Supports simple text search (subject/from/body) and structured
criteria like date ranges, sender, flags, and size.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import click
from imapclient import IMAPClient

from scripts.utils import (
    console,
    load_config,
    imap_connect,
    make_list_table,
    fmt_date,
    fmt_size,
)
from rich.text import Text
from scripts.cmd_list import _decode_env_str, _format_addr


@click.command()
@click.argument("query", nargs=-1, required=False)
@click.option("--folder", "-f",  default=None, help="Folder to search (default: INBOX).")
@click.option("--from",   "from_addr",   default=None, help="Sender address or name.")
@click.option("--to",     "to_addr",     default=None, help="Recipient address or name.")
@click.option("--subject",               default=None, help="Subject contains.")
@click.option("--since",                 default=None, metavar="YYYY-MM-DD",
              help="Messages since this date.")
@click.option("--before",                default=None, metavar="YYYY-MM-DD",
              help="Messages before this date.")
@click.option("--unread", is_flag=True,  default=False, help="Only unread messages.")
@click.option("--flagged",is_flag=True,  default=False, help="Only flagged (starred) messages.")
@click.option("--larger", default=None,  type=int, metavar="KB",
              help="Messages larger than N KB.")
@click.option("--limit",  "-n", default=50, show_default=True, help="Max results.")
@click.option("--json",  "as_json", is_flag=True, default=False)
def search(query: tuple[str, ...], folder: str | None, from_addr: str | None,
           to_addr: str | None, subject: str | None, since: str | None,
           before: str | None, unread: bool, flagged: bool,
           larger: int | None, limit: int, as_json: bool):
    """
    Search messages using IMAP server-side search.

    A free-text QUERY searches the full message text (BODY).
    All options are combined with AND logic.

    \b
    Examples:
        mail search invoice
        mail search --from boss@company.com --unread
        mail search --subject "Meeting" --since 2024-01-01
        mail search report --since 2024-06-01 --before 2024-07-01
        mail search --flagged --folder Work
    """
    cfg     = load_config()
    defaults = cfg.get("defaults", {})
    folder  = folder or defaults.get("inbox", "INBOX")

    # ── Build IMAP search criteria ────────────────────────────────────────────
    criteria: list = []

    if unread:
        criteria.append("UNSEEN")
    if flagged:
        criteria.append("FLAGGED")
    if from_addr:
        criteria += ["FROM", from_addr]
    if to_addr:
        criteria += ["TO", to_addr]
    if subject:
        criteria += ["SUBJECT", subject]
    if query:
        criteria += ["BODY", " ".join(query)]
    if since:
        try:
            d = date.fromisoformat(since)
            criteria += ["SINCE", d.strftime("%d-%b-%Y")]
        except ValueError:
            console.print(f"[red]Invalid --since date:[/] {since!r} (use YYYY-MM-DD)")
            sys.exit(1)
    if before:
        try:
            d = date.fromisoformat(before)
            criteria += ["BEFORE", d.strftime("%d-%b-%Y")]
        except ValueError:
            console.print(f"[red]Invalid --before date:[/] {before!r} (use YYYY-MM-DD)")
            sys.exit(1)
    if larger:
        criteria += ["LARGER", larger * 1024]

    if not criteria:
        criteria = ["ALL"]

    client = imap_connect(cfg)
    try:
        client.select_folder(folder, readonly=True)
        uids: list[int] = client.search(criteria)
        uids = list(reversed(uids))[:limit]

        if not uids:
            console.print(f"\n[yellow]No messages matched in {folder}.[/]\n")
            return

        fetch_data = client.fetch(uids, ["ENVELOPE", "RFC822.SIZE", "FLAGS"])
    finally:
        client.logout()

    rows = []
    for uid in uids:
        data  = fetch_data.get(uid, {})
        env   = data.get(b"ENVELOPE")
        flags = data.get(b"FLAGS", [])
        size  = data.get(b"RFC822.SIZE")
        seen  = b"\\Seen" in flags

        if env:
            subj   = _decode_env_str(env.subject)
            sender = _format_addr(env.from_)
            date_s = str(env.date or "")[:16]
        else:
            subj = sender = date_s = "?"

        rows.append({
            "uid": uid, "seen": seen, "subject": subj,
            "from": sender, "date": date_s, "size": size,
            "flags": [f.decode() if isinstance(f, bytes) else str(f) for f in flags],
        })

    if as_json:
        print(json.dumps(rows, indent=2, default=str))
        return

    summary = " + ".join(
        filter(None, [
            f"query={' '.join(query)!r}" if query else "",
            f"from={from_addr!r}" if from_addr else "",
            f"subject={subject!r}" if subject else "",
            "unread" if unread else "",
            "flagged" if flagged else "",
        ])
    ) or "all"

    table = make_list_table(f"🔍  Search: {summary}  [{len(rows)} result(s) in {folder}]")
    for r in rows:
        flag_style = "bold white" if not r["seen"] else "dim"
        table.add_row(
            str(r["uid"]),
            Text("●" if not r["seen"] else " ", style="cyan" if not r["seen"] else "dim"),
            Text(r["from"],    style=flag_style, overflow="ellipsis"),
            Text(r["subject"], style=flag_style, overflow="ellipsis"),
            Text(r["date"],    style="dim"),
            Text(fmt_size(r["size"]), style="dim"),
        )

    console.print()
    console.print(table)
    console.print()
