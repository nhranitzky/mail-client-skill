#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_ENV="$HOME/.openclaw/.env"

# ---------------------------------------------------------------------------
# 1. Install dependencies
# ---------------------------------------------------------------------------
echo "Installing dependencies with uv sync..."
uv sync --no-dev

echo "Setting execute permissions for bin/mail..."
chmod +x "$SCRIPT_DIR/bin/mail"

# ---------------------------------------------------------------------------
# 2. Check MAIL_CONFIG_FILE in ~/.openclaw/.env
# ---------------------------------------------------------------------------
config_value=""
if [[ -f "$OPENCLAW_ENV" ]]; then
    config_value=$(grep -E '^MAIL_CONFIG_FILE=' "$OPENCLAW_ENV" | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
fi

if [[ -n "$config_value" ]]; then
    echo "MAIL_CONFIG_FILE already set in $OPENCLAW_ENV: $config_value"
    CONFIG_FILE="$(eval echo "$config_value")"
else
    # Ask user for the config file location
    echo ""
    echo "MAIL_CONFIG_FILE is not set in $OPENCLAW_ENV."
    read -rp "Enter the path for your mail config file [~/.config/imail/config.yaml]: " user_input
    user_input="${user_input:-~/.config/imail/config.yaml}"
    CONFIG_FILE="$(eval echo "$user_input")"

    # Persist to ~/.openclaw/.env
    mkdir -p "$(dirname "$OPENCLAW_ENV")"
    touch "$OPENCLAW_ENV"
    echo "MAIL_CONFIG_FILE=\"$user_input\"" >> "$OPENCLAW_ENV"
    echo "Added MAIL_CONFIG_FILE to $OPENCLAW_ENV"
fi

# ---------------------------------------------------------------------------
# 3. Check if config file exists; if not, copy template
# ---------------------------------------------------------------------------
if [[ -f "$CONFIG_FILE" ]]; then
    echo "Config file found: $CONFIG_FILE"
else
    echo ""
    echo "Config file not found: $CONFIG_FILE"
    mkdir -p "$(dirname "$CONFIG_FILE")"
    cp "$SCRIPT_DIR/templates/config.yaml" "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    echo ""
    echo "A template config file has been copied to:"
    echo "  $CONFIG_FILE"
    echo ""
    echo "Please edit it before using the skill:"
    echo "  \$EDITOR $CONFIG_FILE"
    echo ""
    echo "You will need to set:"
    echo "  account.name, account.email"
    echo "  imap.host / imap.port"
    echo "  smtp.host / smtp.port"
    echo "  password_file  (path to a file containing your mail password)"
fi

echo ""
echo "Installation complete."
