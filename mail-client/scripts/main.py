"""
Mail CLI – main entry point.

Usage:
    mail list     [--folder F] [--limit N] [--unread] [--json]
    mail read     <uid>        [--folder F] [--save-attachments DIR]
    mail send     --to <addr>  --subject <s>  [--body <text>] [--attach <file>]
    mail reply    <uid>        [--body <text>] [--reply-all]
    mail search   [query]      [--from <addr>] [--subject <s>] [--since DATE]
    mail folders  [--counts]   [--json]
    mail manage   move|delete|flag|unflag|mark-read|mark-unread

Password is read from the file in config.yaml → password_file.
It is NEVER printed, logged, or sent to an LLM.
"""

from __future__ import annotations

import click

from scripts.cmd_list    import list_messages
from scripts.cmd_read    import read
from scripts.cmd_send    import send
from scripts.cmd_reply   import reply
from scripts.cmd_search  import search
from scripts.cmd_folders import folders
from scripts.cmd_manage  import manage


@click.group()
@click.version_option("1.0.0", prog_name="mail")
def cli():
    """
    \b
    📧  mail – read and write email via IMAP/SMTP.
    Configuration: config.yaml  |  Password: password_file in config.
    The password is NEVER displayed or sent to any LLM.
    """


cli.add_command(list_messages, name="list")
cli.add_command(read)
cli.add_command(send)
cli.add_command(reply)
cli.add_command(search)
cli.add_command(folders)
cli.add_command(manage)

if __name__ == "__main__":
    cli()
