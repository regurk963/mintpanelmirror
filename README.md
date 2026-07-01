# Cinnamon Panel Mirror

Copy one Cinnamon panel's layout — its applets **and their settings** — onto your
other monitors' panels, so every screen shows the same taskbar. A few clicks
instead of rebuilding each panel by hand.

For **Linux Mint (Cinnamon)**.

## Why this exists

Cinnamon has no built-in "mirror this panel to all monitors". You can copy the
*set* of applets from the panel menu, but that drops them in with **default**
settings. This tool copies each applet **together with the settings you
configured** (the JSON files under `~/.config/cinnamon/spices/`) — so tweaks
like the window list's "show windows from all monitors" carry over instead of
resetting. It also backs up everything first.

## Requirements

- Linux Mint with the **Cinnamon** desktop
- `python3`, `python3-gi`, `gir1.2-gtk-3.0` — all preinstalled on Cinnamon

## Before you start — add an empty panel to each extra monitor (required)

**The tool copies onto panels that already exist; it does not create panels.**
So on every monitor that does not have a panel yet:

1. Right-click an existing panel and choose to add a new panel
   (in some Cinnamon versions: **Panel settings → Add panel**).
2. Click the edge of the monitor where you want the new panel.

Then open the tool (or press **Reload** in it) and that panel appears as a
target. A monitor with **no** panel simply will not show up in the list.

## Install

### Option A — .deb package (recommended)

Download the latest `.deb` from the [Releases](../../releases) page, then either
double-click it (opens the graphical installer) or run:

```bash
sudo apt install ./cinnamon-panel-mirror_1.0.0_all.deb
```

It adds **Cinnamon Panel Mirror** to your application menu — search "panel mirror".

### Option B — run the script directly

No install, just run it:

```bash
python3 cinnamon_panel_mirror.py
```

### Option C — user-level install script

Installs into your home directory (no `sudo`) and adds a menu entry:

```bash
./install.sh              # install
./install.sh --uninstall  # remove
```

## Making it clickable / adding a desktop icon

After installing (Option A or C), the app is in your **application menu** — click
it there or search "panel mirror". Cinnamon does **not** place an icon on the
desktop automatically. To add one:

1. Open the menu, find **Cinnamon Panel Mirror**, right-click it → **Add to desktop**.
2. Right-click the new desktop icon → **Allow Launching**
   (Cinnamon marks new desktop launchers as untrusted until you do this).

## How to use

1. **Source panel** — pick the monitor whose panel you have already set up nicely.
2. **Copy onto these panels** — tick the other monitors' panels.
3. **Applets to copy** — everything is ticked by default; untick any you do not
   want duplicated. The **system tray** is a common one to skip (you usually want
   the tray on one screen only).
4. **Preview** to see exactly what will change, then **Apply**.
5. **Restart Cinnamon** (button, or press `Ctrl+Alt+Esc`) to see the result.

## Safety and undo

Every **Apply** first writes a timestamped backup of your Cinnamon settings to
`~/cinnamon-panel-mirror-backups/`. If a result is not what you wanted, click
**Restore last backup** and restart Cinnamon. You can also back up / restore by
hand:

```bash
dconf dump /org/cinnamon/ > my-cinnamon-backup.dconf   # save
dconf load /org/cinnamon/ < my-cinnamon-backup.dconf   # restore
```

## What happens if I disconnect a monitor?

Short version: the panel on a monitor you unplug **stops being drawn** (its
monitor is gone), but its definition is **not** deleted — Cinnamon simply skips
drawing a panel for a monitor that is not present.

When you plug the monitor back in it **usually** reappears, but Cinnamon's
multi-monitor hotplugging is historically imperfect. Monitor indexes can shift
(especially through docks, or when monitors reconnect in a different order),
which can leave a secondary panel not redrawn, or move the primary taskbar to a
different screen. If your monitors always reconnect in the same arrangement it is
usually fine; docks and mixed connection orders are where it gets unreliable.

If a panel fails to reappear, **restarting Cinnamon** (`Ctrl+Alt+Esc`) normally
brings it back. And if a reconnect scrambles your secondary panels, re-running
this tool (or **Restore last backup**) is exactly how you avoid rebuilding them
by hand.

## Uninstall

```bash
sudo apt remove cinnamon-panel-mirror   # if installed via the .deb
./install.sh --uninstall                # if installed via install.sh
```

Your backups in `~/cinnamon-panel-mirror-backups/` are left in place either way.

## Notes and limitations

- **Cinnamon only** — it uses `org.cinnamon` gsettings and Cinnamon's applet layout.
- "Mirror" **replaces** a target panel's contents with a copy of the source. The
  source panel is never modified.
- A few applets restrict themselves to a single instance and may not duplicate
  cleanly.
- It edits your desktop configuration. It backs up first, but it is provided
  **as-is** — see the license.

## License

MIT — see [LICENSE](LICENSE).
