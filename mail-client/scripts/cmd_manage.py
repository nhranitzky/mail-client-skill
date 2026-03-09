"""
mail manage – Manage messages: move, delete, flag, mark read/unread.

Groups several message-management actions under one command group
to keep the top-level CLI clean.
"""

from __future__ import annotations

import sys

import click
from imapclient import IMAPClient

from scripts.utils import (
    console,
    load_config,
    imap_connect,
)


@click.group()
def manage():
    """Manage messages: move, delete, flag, mark."""


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------

@manage.command()
@click.argument("uid", type=int)
@click.option("--to",   "-t", "dest_folder", required=True, help="Destination folder name.")
@click.option("--from", "-f", "src_folder",  default=None,  help="Source folder (default: INBOX).")
def move(uid: int, dest_folder: str, src_folder: str | None):
    """
    Move message UID from one folder to another.

    \b
    Examples:
        mail manage move 42 --to Archive
        mail manage move 42 --from Spam --to INBOX
    """
    cfg    = load_config()
    folder = src_folder or cfg.get("defaults", {}).get("inbox", "INBOX")

    client = imap_connect(cfg)
    try:
        client.select_folder(folder)
        client.move([uid], dest_folder)
    except Exception as exc:
        console.print(f"[red]Move failed:[/] {exc}")
        sys.exit(1)
    finally:
        client.logout()

    console.print(f"[green]✅  UID {uid} moved[/] from [bold]{folder}[/] → [bold]{dest_folder}[/]")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@manage.command()
@click.argument("uid", type=int)
@click.option("--folder", "-f", default=None, help="Folder containing the message.")
@click.option("--permanent", is_flag=True, default=False,
              help="Permanently expunge instead of moving to Trash.")
def delete(uid: int, folder: str | None, permanent: bool):
    """
    Delete (trash or expunge) message UID.

    By default moves the message to the Trash folder configured in
    config.yaml. Use --permanent to expunge immediately.

    \b
    Examples:
        mail manage delete 42
        mail manage delete 42 --permanent
    """
    cfg       = load_config()
    defaults  = cfg.get("defaults", {})
    folder    = folder or defaults.get("inbox", "INBOX")
    trash     = defaults.get("trash_folder", "Trash")

    client = imap_connect(cfg)
    try:
        client.select_folder(folder)
        if permanent:
            client.add_flags([uid], [b"\\Deleted"])
            client.expunge([uid])
            console.print(f"[green]✅  UID {uid} permanently deleted from {folder}[/]")
        else:
            client.move([uid], trash)
            console.print(f"[green]✅  UID {uid} moved to {trash}[/]")
    except Exception as exc:
        console.print(f"[red]Delete failed:[/] {exc}")
        sys.exit(1)
    finally:
        client.logout()


# ---------------------------------------------------------------------------
# flag / unflag
# ---------------------------------------------------------------------------

@manage.command()
@click.argument("uid", type=int)
@click.option("--folder", "-f", default=None)
def flag(uid: int, folder: str | None):
    """Flag (star) message UID."""
    _set_flag(uid, folder, b"\\Flagged", add=True, label="flagged ⭐")


@manage.command()
@click.argument("uid", type=int)
@click.option("--folder", "-f", default=None)
def unflag(uid: int, folder: str | None):
    """Remove flag (star) from message UID."""
    _set_flag(uid, folder, b"\\Flagged", add=False, label="unflagged")


# ---------------------------------------------------------------------------
# mark-read / mark-unread
# ---------------------------------------------------------------------------

@manage.command("mark-read")
@click.argument("uid", type=int)
@click.option("--folder", "-f", default=None)
def mark_read(uid: int, folder: str | None):
    """Mark message UID as read."""
    _set_flag(uid, folder, b"\\Seen", add=True, label="marked read")


@manage.command("mark-unread")
@click.argument("uid", type=int)
@click.option("--folder", "-f", default=None)
def mark_unread(uid: int, folder: str | None):
    """Mark message UID as unread."""
    _set_flag(uid, folder, b"\\Seen", add=False, label="marked unread")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _set_flag(uid: int, folder: str | None, flag_name: bytes,
              add: bool, label: str) -> None:
    cfg    = load_config()
    folder = folder or cfg.get("defaults", {}).get("inbox", "INBOX")
    client = imap_connect(cfg)
    try:
        client.select_folder(folder)
        if add:
            client.add_flags([uid], [flag_name])
        else:
            client.remove_flags([uid], [flag_name])
    except Exception as exc:
        console.print(f"[red]Flag operation failed:[/] {exc}")
        sys.exit(1)
    finally:
        client.logout()
    console.print(f"[green]✅  UID {uid} {label}[/]")
