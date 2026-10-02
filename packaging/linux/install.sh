#!/bin/sh
# Installs Minecraft Mod Updater for the current user (no root needed).
# Run from the extracted folder:  ./install.sh
# Uninstall with:                 ./install.sh --uninstall
set -e

APP_DIR="$HOME/.local/share/minecraft-mod-updater"
DESKTOP_FILE="$HOME/.local/share/applications/minecraft-mod-updater.desktop"
BIN_LINK="$HOME/.local/bin/minecraft-mod-updater"

if [ "$1" = "--uninstall" ]; then
    rm -rf "$APP_DIR" "$DESKTOP_FILE" "$BIN_LINK"
    echo "Minecraft Mod Updater uninstalled."
    exit 0
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$(dirname "$DESKTOP_FILE")" "$(dirname "$BIN_LINK")"
cp -r "$SRC_DIR/mod_updater" "$APP_DIR/"
chmod +x "$APP_DIR/mod_updater/mod_updater"
ln -sf "$APP_DIR/mod_updater/mod_updater" "$BIN_LINK"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Minecraft Mod Updater
Comment=Keep your Minecraft mods up to date from Modrinth
Exec=$APP_DIR/mod_updater/mod_updater
Icon=$APP_DIR/mod_updater/_internal/updater-logo.png
Terminal=false
Categories=Game;Utility;
EOF

echo "Minecraft Mod Updater installed. Find it in your applications menu or run: minecraft-mod-updater"
