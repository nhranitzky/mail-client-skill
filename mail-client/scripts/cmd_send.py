"""
mail send – Compose and send an email via SMTP.

The message body can be provided inline (--body), read from a file
(--body-file), or typed interactively if neither is given.
After sending the message is optionally appended to the Sent folder.
"""

from __future__ import annotations

import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import click

from scripts.utils import (
    console,
    load_config,
    imap_connect,
    smtp_connect,
    append_to_sent,
    msg_to_bytes_crlf,
)


def _build_mime(
    from_addr: str,
    to_list: list[str],
    cc_list: list[str],
    subject: str,
    body: str,
    attachments: list[Path],
    reply_to_msgid: str = "",
    references: str = "",
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(to_list)
    if cc_list:
        msg["Cc"]  = ", ".join(cc_list)
    msg["Subject"] = subject

    if reply_to_msgid:
        msg["In-Reply-To"] = reply_to_msgid
        refs = f"{references} {reply_to_msgid}".strip()
        msg["References"]  = refs

    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachments:
        with path.open("rb") as fh:
            part = MIMEApplication(fh.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)

    return msg


@click.command()
@click.option("--to",        "-t", "to_addrs", multiple=True, required=True,
              help="Recipient address (repeat for multiple).")
@click.option("--cc",        "-c", "cc_addrs", multiple=True,
              help="CC address (repeat for multiple).")
@click.option("--subject",   "-s", required=True, help="Message subject.")
@click.option("--body",      "-b", default=None,
              help="Message body text (inline).")
@click.option("--body-file", "-B", "body_file",
              type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Read body text from this file.")
@click.option("--attach",    "-a", "attach_files", multiple=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="File to attach (repeat for multiple).")
@click.option("--from-name", default=None,
              help="Override the display name in From: (default: account.name from config).")
def send(to_addrs: tuple[str, ...], cc_addrs: tuple[str, ...], subject: str,
         body: str | None, body_file: Path | None, attach_files: tuple[Path, ...],
         from_name: str | None):
    """
    Compose and SEND a new email.

    If neither --body nor --body-file is given, you will be prompted to
    type the message body (end with a line containing only a dot '.').

    \b
    Examples:
        mail send --to alice@example.com --subject "Hello" --body "Hi there!"
        mail send --to bob@example.com --subject "Report" --body-file report.txt
        mail send --to team@company.com --subject "Q3" --attach q3.pdf --attach data.xlsx
    """
    cfg      = load_config()
    account  = cfg["account"]
    name     = from_name or account.get("name", "")
    email_addr = account["email"]
    from_addr  = f"{name} <{email_addr}>" if name else email_addr

    # ── Resolve body ──────────────────────────────────────────────────────────
    if body_file:
        body_text = body_file.read_text(encoding="utf-8")
    elif body:
        body_text = body
    else:
        console.print("[dim]Enter message body. Type a single '.' on a line to finish:[/]")
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

    if not body_text.strip():
        console.print("[yellow]Warning: sending empty message body.[/]")

    msg = _build_mime(
        from_addr  = from_addr,
        to_list    = list(to_addrs),
        cc_list    = list(cc_addrs),
        subject    = subject,
        body       = body_text,
        attachments = list(attach_files),
    )

    # ── Send ──────────────────────────────────────────────────────────────────
    all_recipients = list(to_addrs) + list(cc_addrs)
    smtp = smtp_connect(cfg)
    try:
        # send_message() uses the correct CRLF line endings required by SMTP
        # (RFC 5321). msg.as_bytes() can produce bare LF on some platforms,
        # which causes "5.5.2 bare <LF> received" rejections.
        smtp.send_message(msg)
    except Exception as exc:
        console.print(f"[red]Send failed:[/] {exc}")
        sys.exit(1)
    finally:
        # Some servers (e.g. port 465 / SMTPS) close the connection immediately
        # after accepting the message.  Suppress the resulting disconnect error
        # so it doesn't mask a successful send.
        try:
            smtp.quit()
        except Exception:
            pass

    console.print(f"\n[bold green]✅  Message sent[/] → {', '.join(to_addrs)}")


    # ── Append to Sent folder (best-effort, auto-detects folder name) ──────────
    defaults    = cfg.get("defaults", {})
    sent_folder = defaults.get("sent_folder", "Sent")
    append_to_sent(cfg, msg_to_bytes_crlf(msg), preferred=sent_folder)

    console.print()
