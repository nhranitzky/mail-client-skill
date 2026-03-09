"""
Shared utilities for the mail CLI.

Provides:
  - load_config()        : read config.yaml and validate
  - get_password()       : read password from file (never echoed or logged)
  - imap_connect()       : return an authenticated IMAPClient
  - smtp_connect()       : return an authenticated smtplib.SMTP
  - parse_message()      : decode a raw RFC-822 message to a dict
  - render_headers_table : Rich panel with message headers
  - console              : shared Rich console
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import os
import re
import smtplib
import ssl
import sys
from email.message import Message
from pathlib import Path
from typing import Any

import io
import yaml
from dateutil import parser as dateparser
from imapclient import IMAPClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

console = Console()

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """
    Load and validate the config file.

    The path is taken from the MAIL_CONFIG_FILE environment variable.
    Raises SystemExit if the variable is unset, the file is missing, or malformed.
    The password is NOT part of the config – it is read separately.
    """
    config_path_str = os.environ.get("MAIL_CONFIG_FILE")
    if not config_path_str:
        console.print(
            "[bold red]MAIL_CONFIG_FILE environment variable is not set.[/]\n"
            "Set it to the path of your config.yaml, e.g.:\n"
            "  [bold]export MAIL_CONFIG_FILE=~/.config/imail/config.yaml[/]"
        )
        sys.exit(1)

    CONFIG_FILE = Path(config_path_str).expanduser().resolve()
    if not CONFIG_FILE.exists():
        console.print(
            f"[bold red]Config file not found:[/] {CONFIG_FILE}\n"
            f"Copy [bold]config.yaml.example[/] to that path and edit it."
        )
        sys.exit(1)

    try:
        cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        console.print(f"[red]Invalid YAML in config.yaml:[/] {exc}")
        sys.exit(1)

    if not isinstance(cfg, dict):
        console.print("[red]config.yaml must be a YAML mapping (key: value pairs).[/]")
        sys.exit(1)

    # Minimal validation
    for section in ("account", "imap", "smtp"):
        if section not in cfg:
            console.print(f"[red]config.yaml is missing the '[bold]{section}[/]' section.[/]")
            sys.exit(1)

    if not cfg.get("password_file"):
        console.print("[red]config.yaml is missing 'password_file'.[/]")
        sys.exit(1)

    return cfg


# ---------------------------------------------------------------------------
# Password – read from file, never logged or echoed
# ---------------------------------------------------------------------------

def get_password(cfg: dict[str, Any]) -> str:
    """
    Read the mail password from the file specified in config.yaml.

    The file path supports ~ expansion. The password is the first line of
    the file (trailing whitespace / newline stripped).

    The password is NEVER printed, logged, or included in any output.
    """
    raw_path = os.path.expanduser(cfg["password_file"])
    path = Path(raw_path)
    if not path.is_absolute():
        config_dir = Path(os.environ["MAIL_CONFIG_FILE"]).expanduser().resolve().parent
        path = config_dir / path

    if not path.exists():
        console.print(
            f"[bold red]Password file not found:[/] {path}\n"
            f"Create it with:\n"
            f"  [bold]echo 'yourpassword' > {path} && chmod 600 {path}[/]"
        )
        sys.exit(1)

    try:
        password = path.read_text(encoding="utf-8").split("\n")[0].rstrip("\r")
    except OSError as exc:
        console.print(f"[red]Cannot read password file {path}:[/] {exc}")
        sys.exit(1)

    if not password:
        console.print(f"[red]Password file is empty:[/] {path}")
        sys.exit(1)

    return password


# ---------------------------------------------------------------------------
# IMAP connection
# ---------------------------------------------------------------------------

def imap_connect(cfg: dict[str, Any] | None = None) -> IMAPClient:
    """
    Open an authenticated IMAP connection.

    Returns an IMAPClient ready for use.  Caller is responsible for calling
    client.logout() or using it as a context manager.
    """
    if cfg is None:
        cfg = load_config()

    password = get_password(cfg)
    icfg     = cfg["imap"]
    host     = icfg["host"]
    port     = int(icfg.get("port", 993))
    use_ssl  = icfg.get("ssl", True)
    starttls = icfg.get("starttls", False)
    username = icfg.get("username") or cfg["account"]["email"]

    try:
        client = IMAPClient(host, port=port, ssl=use_ssl, use_uid=True)
        if starttls:
            client.starttls()
        client.login(username, password)
    except Exception as exc:
        console.print(f"[bold red]IMAP connection failed:[/] {exc}")
        sys.exit(1)
    finally:
        # Ensure password doesn't linger in local scope longer than needed
        del password

    return client


# ---------------------------------------------------------------------------
# SMTP connection
# ---------------------------------------------------------------------------

def smtp_connect(cfg: dict[str, Any] | None = None) -> smtplib.SMTP:
    """
    Open an authenticated SMTP connection.

    Connection mode is determined automatically from the port number,
    with optional overrides in config.yaml:

      Port 587  → STARTTLS  (plain connect, then upgrade via EHLO + STARTTLS)
      Port 465  → SMTPS     (SSL/TLS wrap on connect, aka "implicit TLS")
      Port 25   → plain     (no encryption – not recommended)
      other     → follow explicit ssl / starttls flags in config

    The common error "[SSL: WRONG_VERSION_NUMBER]" happens when the code
    tries to wrap port 587 in SSL immediately.  This function prevents that
    by deriving the mode from the port before consulting config flags.

    Returns an smtplib.SMTP (or SMTP_SSL) instance.
    Caller must call smtp.quit() when done.
    """
    if cfg is None:
        cfg = load_config()

    password = get_password(cfg)
    scfg     = cfg["smtp"]
    host     = scfg["host"]
    port     = int(scfg.get("port", 587))
    username = scfg.get("username") or cfg["account"]["email"]
    timeout  = int(scfg.get("timeout", 30))

    # ── Derive connection mode from port (overrides config flags) ─────────────
    # Port 587: STARTTLS  – never wrap in SSL on connect
    # Port 465: SMTPS     – always wrap in SSL on connect
    # Port 25 : plain     – no TLS (legacy / internal relay)
    # Other   : honour explicit ssl/starttls flags from config
    if port == 587:
        _mode = "starttls"
    elif port == 465:
        _mode = "ssl"
    elif port == 25:
        _mode = "plain"
    else:
        # Fallback: read explicit flags, with sensible defaults
        if scfg.get("ssl"):
            _mode = "ssl"
        elif scfg.get("starttls", True):
            _mode = "starttls"
        else:
            _mode = "plain"

    # Warn if the config explicitly contradicts what we're doing
    cfg_ssl      = scfg.get("ssl",      None)
    cfg_starttls = scfg.get("starttls", None)
    if port == 587 and cfg_ssl is True:
        console.print(
            "[yellow]Warning:[/] config.yaml has [bold]ssl: true[/] "
            "but port 587 requires STARTTLS (plain connect + upgrade).\n"
            "  Using STARTTLS. "
            "Set [bold]ssl: false[/] and [bold]starttls: true[/] to silence this warning."
        )
    if port == 465 and cfg_starttls is True and cfg_ssl is not True:
        console.print(
            "[yellow]Warning:[/] config.yaml has [bold]starttls: true[/] "
            "but port 465 uses implicit SSL/TLS (no STARTTLS handshake).\n"
            "  Using SSL. "
            "Set [bold]ssl: true[/] and [bold]starttls: false[/] to silence this warning."
        )

    ctx = ssl.create_default_context()

    try:
        if _mode == "ssl":
            # Port 465 / implicit TLS: wrap the socket in SSL immediately
            smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout)
            smtp.ehlo()

        elif _mode == "starttls":
            # Port 587 / explicit TLS: plain connect first, then upgrade
            smtp = smtplib.SMTP(host, port, timeout=timeout)
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()   # re-introduce after TLS upgrade

        else:
            # Plain (port 25 / internal relay)
            smtp = smtplib.SMTP(host, port, timeout=timeout)
            smtp.ehlo()

        smtp.login(username, password)

    except smtplib.SMTPAuthenticationError:
        console.print(
            "[bold red]SMTP authentication failed.[/]\n"
            "  • Check username / password in config and password_file.\n"
            "  • Some providers (Gmail, Outlook) require an App Password."
        )
        sys.exit(1)
    except ssl.SSLError as exc:
        console.print(
            f"[bold red]SMTP SSL error:[/] {exc}\n"
            f"  Connected to [bold]{host}:{port}[/] in [bold]{_mode}[/] mode.\n"
            "  Tip: port 587 → starttls: true, ssl: false\n"
            "       port 465 → ssl: true, starttls: false"
        )
        sys.exit(1)
    except (smtplib.SMTPException, OSError) as exc:
        console.print(f"[bold red]SMTP connection failed ({host}:{port}, mode={_mode}):[/] {exc}")
        sys.exit(1)
    finally:
        del password

    return smtp


# ---------------------------------------------------------------------------
# MIME serialisation helpers
# ---------------------------------------------------------------------------

def msg_to_bytes_crlf(msg: "email.message.Message") -> bytes:
    """
    Serialise a MIME message to bytes with CRLF line endings (RFC 5321/5322).

    We first flatten with BytesGenerator (no linesep arg – not supported on
    all Python 3.x versions), then normalise all line endings to CRLF.
    Bare CR or bare LF are both converted; existing CRLF pairs are kept.
    """
    import email.generator
    buf = io.BytesIO()
    gen = email.generator.BytesGenerator(buf, mangle_from_=False)
    gen.flatten(msg)
    raw = buf.getvalue()
    # Normalise to CRLF: collapse any existing \r\n first, then re-add \r
    raw = raw.replace(b"\r\n", b"\n")   # collapse existing CRLF → LF
    raw = raw.replace(b"\r",   b"\n")   # stray CR → LF
    raw = raw.replace(b"\n",   b"\r\n") # all LF → CRLF
    return raw



# ---------------------------------------------------------------------------
# Sent-folder auto-detection
# ---------------------------------------------------------------------------

# Candidate names tried in order (case-insensitive match).
# Covers Vodafone/T-Online, Gmail, Dovecot, Exchange, GMX, etc.
_SENT_CANDIDATES = [
    "Sent",
    "Sent Messages",
    "Sent Items",
    "Gesendete Elemente",
    "Gesendete Objekte",
    "Gesendet",
    "INBOX.Sent",
    "INBOX.Gesendet",
    "[Gmail]/Sent Mail",
    "[Google Mail]/Sent Mail",
]


def find_sent_folder(client: "IMAPClient", preferred: str = "Sent") -> "str | None":
    """
    Return the real name of the Sent folder on the server.

    Resolution order:
    1. ``preferred`` (exact, case-insensitive).
    2. Any folder with IMAP special-use flag \\Sent.
    3. Substring scan against _SENT_CANDIDATES.
    4. None — caller should warn and skip.
    """
    try:
        folders = client.list_folders()
    except Exception:
        return None

    folder_names: list = []   # [(flag_strs, name)]
    for flags, _delim, name in folders:
        flag_strs = [f.decode() if isinstance(f, bytes) else str(f) for f in flags]
        folder_names.append((flag_strs, name))

    # 1. Exact match on preferred name
    for _flags, name in folder_names:
        if name.lower() == preferred.lower():
            return name

    # 2. IMAP special-use \Sent flag
    for flags, name in folder_names:
        if any("sent" in f.lower() for f in flags):
            return name

    # 3. Candidate substring scan
    names_lower = [(n.lower(), n) for _f, n in folder_names]
    for candidate in _SENT_CANDIDATES:
        cl = candidate.lower()
        for nl, name in names_lower:
            if cl == nl or cl in nl:
                return name

    return None


def append_to_sent(cfg: dict, raw_message: bytes, preferred: str = "Sent") -> None:
    """
    Append a sent message to the Sent folder via IMAP (best-effort).
    Auto-detects the folder name; prints a helpful note on failure.
    """
    try:
        client = imap_connect(cfg)
        try:
            folder = find_sent_folder(client, preferred)
            if folder is None:
                console.print(
                    f"  [yellow]Note: no Sent folder found "
                    f"(tried {preferred!r} and common variants).[/]\n"
                    "  Run [bold]mail folders[/] and set "
                    "[bold]defaults.sent_folder[/] in config.yaml."
                )
                return
            client.append(folder, raw_message, flags=[b"\\Seen"])
            console.print(f"  [dim]Saved to {folder}[/]")
        except Exception as exc:
            console.print(
                f"  [yellow]Note: could not save to Sent folder: {exc}[/]\n"
                "  Run [bold]mail folders[/] and set "
                "[bold]defaults.sent_folder[/] in config.yaml."
            )
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception:
        pass   # IMAP failure is non-fatal for sending


# ---------------------------------------------------------------------------
# Message parsing helpers
# ---------------------------------------------------------------------------

def _decode_header(value: str | bytes | None) -> str:
    """Decode a possibly RFC-2047-encoded header value to a plain string."""
    if not value:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = email.header.decode_header(value)
    decoded = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            decoded.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(fragment)
    return "".join(decoded)


def _extract_text(msg: Message) -> tuple[str, str]:
    """
    Walk a MIME message and extract (plain_text, html_text).
    Returns the first text/plain and first text/html parts found.
    """
    plain = ""
    html  = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct   = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ct == "text/plain" and not plain:
                charset = part.get_content_charset() or "utf-8"
                raw = part.get_payload(decode=True)
                plain = raw.decode(charset, errors="replace") if raw else ""
            elif ct == "text/html" and not html:
                charset = part.get_content_charset() or "utf-8"
                raw = part.get_payload(decode=True)
                html = raw.decode(charset, errors="replace") if raw else ""
    else:
        ct      = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        raw     = msg.get_payload(decode=True)
        text    = raw.decode(charset, errors="replace") if raw else ""
        if ct == "text/html":
            html = text
        else:
            plain = text

    return plain, html


def _html_to_text(html: str) -> str:
    """Very lightweight HTML → text strip (no external lib required)."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;",  "&", text)
    text = re.sub(r"&lt;",   "<", text)
    text = re.sub(r"&gt;",   ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get_filename_robust(part: Message) -> str:
    """
    Extract a decoded filename from a MIME part – handles all real-world formats:

    1. RFC 5987  ``filename*=utf-8''url-encoded``  (non-ASCII, modern mailers)
    2. RFC 2047  ``=?charset?enc?text?=``           (older mailers)
    3. Plain     ``filename="..."``                  (ASCII)
    4. Content-Type ``name`` parameter               (fallback)

    Also applies NFC Unicode normalisation so that filenames with decomposed
    characters (e.g. ``a`` + combining umlaut) become the composed form
    (``ä``) – important for saving files on macOS / Linux filesystems.
    """
    import unicodedata
    from urllib.parse import unquote_to_bytes

    disp_raw = part.get("Content-Disposition") or ""

    # ── 1. RFC 5987: filename*=charset''percent-encoded ─────────────────────
    #    Handles multi-line folded headers (whitespace between tokens)
    m5987 = re.search(
        r"filename\*\s*=\s*([A-Za-z0-9_-]*)'([^']*)'\s*(\S+)",
        disp_raw,
        re.IGNORECASE,
    )
    if m5987:
        charset = m5987.group(1) or "utf-8"
        encoded = m5987.group(3).strip().rstrip(";")
        try:
            decoded = unquote_to_bytes(encoded).decode(charset, errors="replace")
            return unicodedata.normalize("NFC", decoded)
        except Exception:
            pass

    # ── 2 & 3. RFC 2047 / plain via get_filename() ───────────────────────────
    fn = part.get_filename()
    if fn:
        result = _decode_header(fn)
        return unicodedata.normalize("NFC", result)

    # ── 4. Content-Type name / name* parameter ────────────────────────────────
    ct_raw = part.get("Content-Type") or ""
    mname = re.search(
        r"name\*\s*=\s*([A-Za-z0-9_-]*)'[^']*'\s*(\S+)",
        ct_raw, re.IGNORECASE,
    )
    if mname:
        charset = mname.group(1) or "utf-8"
        try:
            decoded = unquote_to_bytes(mname.group(2)).decode(charset, errors="replace")
            return unicodedata.normalize("NFC", decoded)
        except Exception:
            pass

    name = part.get_param("name")
    if name:
        return unicodedata.normalize("NFC", _decode_header(name))

    return ""


def _is_attachment(part: Message) -> bool:
    """
    Decide whether a MIME part is an attachment that should be saved/listed.

    Handles:
    - ``Content-Disposition: attachment; filename=...``           (explicit)
    - ``Content-Disposition: inline; filename*=utf-8''...``      (inline + RFC5987 name)
    - ``Content-Disposition: inline; filename="..."``             (inline + plain name)
    - No Content-Disposition but Content-Type has ``name`` param  (old mailers)
    """
    ct   = part.get_content_type()
    disp = (part.get("Content-Disposition") or "").lower()

    # Multipart containers are never attachments themselves
    if ct.startswith("multipart/"):
        return False

    # Explicit attachment disposition – always an attachment
    if disp.lstrip().startswith("attachment"):
        return True

    # Try to get a filename (covers inline+RFC5987, inline+plain, Content-Type name)
    fn = _get_filename_robust(part)
    if fn:
        # Pure body parts: text/plain or text/html with no disposition or bare "inline"
        if ct in ("text/plain", "text/html"):
            # Only skip if there is truly no filename intent
            # (bare "inline" without any filename param = body part)
            if not disp or disp.strip() == "inline":
                return False
        return True

    return False


def _list_attachments(msg: Message) -> list[str]:
    """Return a list of attachment filenames using robust detection."""
    names = []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if _is_attachment(part):
            fn = _get_filename_robust(part)
            if fn:
                names.append(fn)
    return names


def parse_message(raw: bytes) -> dict[str, Any]:
    """
    Parse a raw RFC-822 message bytes into a structured dict.

    Returns:
      {
        subject, from, to, cc, date, date_dt,
        message_id, in_reply_to, references,
        body_plain, body_html, body (best available plain text),
        attachments: [str]
      }
    """
    msg   = email.message_from_bytes(raw)
    plain, html = _extract_text(msg)

    body = plain or (_html_to_text(html) if html else "")

    date_str = _decode_header(msg.get("Date"))
    date_dt  = None
    try:
        date_dt = dateparser.parse(date_str, fuzzy=True)
    except Exception:
        pass

    return {
        "subject":      _decode_header(msg.get("Subject")) or "(no subject)",
        "from":         _decode_header(msg.get("From"))    or "",
        "to":           _decode_header(msg.get("To"))      or "",
        "cc":           _decode_header(msg.get("Cc"))      or "",
        "date":         date_str,
        "date_dt":      date_dt,
        "message_id":   msg.get("Message-ID", ""),
        "in_reply_to":  msg.get("In-Reply-To", ""),
        "references":   msg.get("References", ""),
        "body_plain":   plain,
        "body_html":    html,
        "body":         body,
        "attachments":  _list_attachments(msg),
    }


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------

def fmt_date(m: dict[str, Any]) -> str:
    dt = m.get("date_dt")
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    return (m.get("date") or "")[:16]


def make_list_table(title: str) -> Table:
    """Pre-configured Rich Table for the message listing view."""
    t = Table(title=title, box=box.ROUNDED, show_header=True,
              header_style="bold cyan", show_lines=False)
    t.add_column("UID",     justify="right", width=7,  style="dim")
    t.add_column("",        width=2)                       # flags (★ / ●)
    t.add_column("From",    min_width=20, max_width=28, no_wrap=True)
    t.add_column("Subject", min_width=30, no_wrap=True)
    t.add_column("Date",    width=16, style="dim", no_wrap=True)
    t.add_column("Size",    justify="right", width=7, style="dim")
    return t


def render_message(m: dict[str, Any], uid: int, flags: list, body_width: int = 100) -> None:
    """Render a full message (headers + body) to the console."""
    flag_str = " ".join(str(f) for f in flags)
    seen     = b"\\Seen" in flags or "\\Seen" in flags

    header_grid = Table.grid(padding=(0, 2))
    header_grid.add_column(style="bold dim", no_wrap=True)
    header_grid.add_column()
    header_grid.add_row("From:",    m["from"])
    header_grid.add_row("To:",      m["to"])
    if m["cc"]:
        header_grid.add_row("Cc:", m["cc"])
    header_grid.add_row("Date:",    fmt_date(m))
    header_grid.add_row("Subject:", f"[bold]{m['subject']}[/]")
    if m["attachments"]:
        header_grid.add_row("Attachments:", "  📎 " + ",  📎 ".join(m["attachments"]))
    header_grid.add_row("UID:",     f"{uid}   [dim]{flag_str}[/]")

    console.print()
    console.print(Panel(header_grid, title="[bold cyan]Message[/]", expand=False))

    body = m["body"]
    if body:
        console.print()
        console.print(body)
    else:
        console.print("[dim](no text body)[/]")
    console.print()


def fmt_size(size: int | None) -> str:
    if not size:
        return "–"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size // 1024} KB"
    return f"{size / (1024 * 1024):.1f} MB"
