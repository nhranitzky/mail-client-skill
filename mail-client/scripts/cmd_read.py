"""
mail read – Display a single message by UID.

Downloads the full RFC-822 message and renders headers + body in
the terminal. Optionally saves attachments.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from scripts.utils import (
    console,
    load_config,
    imap_connect,
    parse_message,
    _is_attachment,
    _decode_header,
    _get_filename_robust,
    render_message,
)


@click.command()
@click.argument("uid", type=int)
@click.option("--folder",  "-f", default=None,
              help="Mailbox folder containing the message (default: INBOX).")
@click.option("--save-attachments", "-a", "save_dir", default=None,
              type=click.Path(file_okay=False),
              help="Directory to save attachments to.")
@click.option("--no-mark-read", is_flag=True, default=False,
              help="Do NOT mark the message as read (keep \\Unseen flag).")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output parsed message as JSON.")
def read(uid: int, folder: str | None, save_dir: str | None,
         no_mark_read: bool, as_json: bool):
    """
    Display message UID in full (headers + body).

    \b
    Examples:
        mail read 42
        mail read 42 --folder Sent
        mail read 42 --save-attachments ~/Downloads
        mail read 42 --no-mark-read --json
    """
    cfg     = load_config()
    defaults = cfg.get("defaults", {})
    folder  = folder or defaults.get("inbox", "INBOX")

    client = imap_connect(cfg)
    try:
        client.select_folder(folder, readonly=no_mark_read)

        data = client.fetch([uid], ["RFC822", "FLAGS"])
        if uid not in data:
            console.print(f"[red]Message UID {uid} not found in {folder}.[/]")
            sys.exit(1)

        raw   = data[uid][b"RFC822"]
        flags = data[uid].get(b"FLAGS", [])

        if not no_mark_read:
            client.add_flags([uid], [b"\\Seen"])

    finally:
        client.logout()

    m = parse_message(raw)

    if as_json:
        out = {k: v for k, v in m.items() if k not in ("body_html",)}
        out["date_dt"] = str(out.get("date_dt") or "")
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    render_message(m, uid, flags)

    # ── Save attachments ──────────────────────────────────────────────────────
    if save_dir:
        import email as email_lib
        msg_obj = email_lib.message_from_bytes(raw)
        dest    = Path(save_dir)
        dest.mkdir(parents=True, exist_ok=True)
        saved   = []

        for part in (msg_obj.walk() if msg_obj.is_multipart() else [msg_obj]):
            if not _is_attachment(part):
                continue
            fn = _get_filename_robust(part)
            if not fn:
                # Fallback: derive name from Content-Type subtype
                import mimetypes
                ext = mimetypes.guess_extension(part.get_content_type()) or ".bin"
                fn = f"attachment{ext}" 
            payload = part.get_payload(decode=True)
            if payload:
                # Avoid overwriting existing files
                target = dest / fn
                if target.exists():
                    stem, suffix = target.stem, target.suffix
                    counter = 1
                    while target.exists():
                        target = dest / f"{stem}_{counter}{suffix}"
                        counter += 1
                target.write_bytes(payload)
                saved.append(str(target))

        if saved:
            console.print(f"[green]Saved {len(saved)} attachment(s):[/]")
            for s in saved:
                console.print(f"  📎 {s}")
            console.print()
        elif save_dir:
            console.print("[yellow]No attachments found in this message.[/]")
