#!/bin/sh
# User-level installer for Cinnamon Panel Mirror (no sudo required).
# Installs into ~/.local so it shows up in your application menu.
set -e

APP_DIR="$HOME/.local/share/cinnamon-panel-mirror"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

uninstall() {
    rm -f "$BIN_DIR/cinnamon-panel-mirror"
    rm -f "$DESKTOP_DIR/cinnamon-panel-mirror.desktop"
    rm -f "$ICON_DIR/cinnamon-panel-mirror.svg"
    rm -rf "$APP_DIR"
    update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true
    echo "Uninstalled. (Backups in ~/cinnamon-panel-mirror-backups were kept.)"
}

if [ "$1" = "--uninstall" ] || [ "$1" = "-u" ]; then
    uninstall
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

install -m 644 "$SCRIPT_DIR/cinnamon_panel_mirror.py" "$APP_DIR/cinnamon_panel_mirror.py"
[ -f "$SCRIPT_DIR/cinnamon-panel-mirror.svg" ] && \
    install -m 644 "$SCRIPT_DIR/cinnamon-panel-mirror.svg" "$ICON_DIR/cinnamon-panel-mirror.svg"

# Launcher (absolute path so it works even if ~/.local/bin is not on PATH).
cat > "$BIN_DIR/cinnamon-panel-mirror" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/cinnamon_panel_mirror.py" "\$@"
EOF
chmod 755 "$BIN_DIR/cinnamon-panel-mirror"

# Desktop entry with the Exec pointed at the absolute launcher path.
sed "s|^Exec=.*|Exec=$BIN_DIR/cinnamon-panel-mirror|" \
    "$SCRIPT_DIR/cinnamon-panel-mirror.desktop" \
    > "$DESKTOP_DIR/cinnamon-panel-mirror.desktop"

update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true

echo "Installed. Look for 'Cinnamon Panel Mirror' in your menu."
echo "(If it doesn't appear right away, restart Cinnamon with Ctrl+Alt+Esc.)"
