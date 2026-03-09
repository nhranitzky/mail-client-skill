"""
mail folders – List all IMAP folders / mailboxes.

Shows folder name, flags (e.g. \\Noselect, \\HasChildren), and
message counts (total / unread) when --counts is requested.
"""

from __future__ import annotations

import json

import click
from rich.table import Table
from rich import box

from scripts.utils import (
    console,
    load_config,
    imap_connect,
)


@click.command()
@click.option("--counts", "-c", is_flag=True, default=False,
              help="Show total/unread message counts (slower, requires extra IMAP calls).")
@click.option("--json", "as_json", is_flag=True, default=False)
def folders(counts: bool, as_json: bool):
    """
    List all available IMAP folders/mailboxes.

    \b
    Examples:
        mail folders
        mail folders --counts
    """
    cfg    = load_config()
    client = imap_connect(cfg)
    rows   = []

    try:
        folder_list = client.list_folders()

        for flags, delimiter, name in folder_list:
            flag_strs = [f.decode() if isinstance(f, bytes) else str(f) for f in flags]
            row = {"name": name, "flags": flag_strs, "delimiter": delimiter}

            if counts and "\\Noselect" not in flag_strs:
                try:
                    info = client.select_folder(name, readonly=True)
                    row["total"]  = info.get(b"EXISTS", "?")
                    row["unread"] = info.get(b"UNSEEN", "?")
                    client.unselect_folder()
                except Exception:
                    row["total"]  = "?"
                    row["unread"] = "?"

            rows.append(row)
    finally:
        client.logout()

    if as_json:
        print(json.dumps(rows, indent=2))
        return

    table = Table(
        title="📁  IMAP Folders",
        box=box.ROUNDED, show_header=True, header_style="bold cyan",
    )
    table.add_column("#",       justify="right", width=4, style="dim")
    table.add_column("Folder",  min_width=25)
    if counts:
        table.add_column("Total",  justify="right", width=7)
        table.add_column("Unread", justify="right", width=7, style="cyan")
    table.add_column("Flags",   style="dim")

    for i, r in enumerate(rows, 1):
        is_noselect = "\\Noselect" in r["flags"]
        style = "dim" if is_noselect else ""
        name_text = f"[dim]{r['name']}[/]" if is_noselect else r["name"]
        flag_str  = "  ".join(f for f in r["flags"] if f not in ("\\HasNoChildren",))

        row_cells = [str(i), name_text]
        if counts:
            row_cells += [
                str(r.get("total",  "")) if not is_noselect else "",
                str(r.get("unread", "")) if not is_noselect else "",
            ]
        row_cells.append(flag_str)
        table.add_row(*row_cells)

    console.print()
    console.print(table)
    console.print(f"  [dim]{len(rows)} folder(s)[/]\n")
