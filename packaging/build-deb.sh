#!/bin/sh
# Build the Cinnamon Panel Mirror .deb from the repo files.
# Usage:  packaging/build-deb.sh
# Output: cinnamon-panel-mirror_<version>_all.deb in the repo root.
#
# Before publishing a release, edit the Maintainer line below to your own
# name and email.
set -e

VERSION=1.0.0
PKG=cinnamon-panel-mirror
MAINTAINER="Your Name <you@example.com>"   # <-- edit before a public release

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$(mktemp -d)"
DEST="$BUILD/${PKG}_${VERSION}_all"

mkdir -p "$DEST/DEBIAN" \
         "$DEST/usr/bin" \
         "$DEST/usr/share/applications" \
         "$DEST/usr/share/$PKG" \
         "$DEST/usr/share/icons/hicolor/scalable/apps" \
         "$DEST/usr/share/doc/$PKG"

install -m 644 "$ROOT/cinnamon_panel_mirror.py"     "$DEST/usr/share/$PKG/cinnamon_panel_mirror.py"
install -m 644 "$ROOT/cinnamon-panel-mirror.desktop" "$DEST/usr/share/applications/$PKG.desktop"
install -m 644 "$ROOT/cinnamon-panel-mirror.svg"     "$DEST/usr/share/icons/hicolor/scalable/apps/$PKG.svg"
install -m 644 "$ROOT/LICENSE"                       "$DEST/usr/share/doc/$PKG/copyright"

cat > "$DEST/usr/bin/$PKG" <<EOF
#!/bin/sh
exec python3 /usr/share/$PKG/cinnamon_panel_mirror.py "\$@"
EOF
chmod 755 "$DEST/usr/bin/$PKG"

cat > "$DEST/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0
Maintainer: $MAINTAINER
Description: Mirror a Cinnamon panel across all monitors
 A small GTK tool for Linux Mint (Cinnamon) that copies the contents of one
 panel -- applets and their settings -- onto other panels, so every monitor
 shows the same taskbar. It backs up your Cinnamon settings before making any
 change and offers one-click restore.
EOF

cat > "$DEST/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$DEST/DEBIAN/postinst"

dpkg-deb --root-owner-group --build "$DEST" "$ROOT/${PKG}_${VERSION}_all.deb"
rm -rf "$BUILD"
echo "Built: $ROOT/${PKG}_${VERSION}_all.deb"
