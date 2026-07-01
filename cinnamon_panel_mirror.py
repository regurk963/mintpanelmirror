#!/usr/bin/env python3
"""
Cinnamon Panel Mirror
=====================

A small GTK app for Linux Mint (Cinnamon) that copies the contents of one
panel onto one or more other panels -- so you can get the same taskbar on
every monitor with a few clicks instead of rebuilding each panel by hand.

What it does
------------
* Reads your current panels and applets from `org.cinnamon` via gsettings.
* Lets you pick a SOURCE panel and one or more TARGET panels.
* Lets you untick individual applets you DON'T want copied (e.g. the system
  tray, which you usually only want on one screen).
* Copies each chosen applet -- including the settings you configured in its
  Configure dialog (the JSON files under ~/.config/cinnamon/spices/).
* Makes a full `dconf` backup of /org/cinnamon/ BEFORE it changes anything,
  and gives you a one-click Restore.

Safety
------
Nothing is written until you click "Apply". Apply always takes a timestamped
backup first (saved in ~/cinnamon-panel-mirror-backups/). If a mirror doesn't
look right, click "Restore last backup" and restart Cinnamon.

Run it
------
    python3 cinnamon_panel_mirror.py

Requires python3-gi + gir1.2-gtk-3.0, which are already present on Cinnamon.
"""

import os
import ast
import shutil
import subprocess
from datetime import datetime

SCHEMA = "org.cinnamon"
KEY_PANELS = "panels-enabled"
KEY_APPLETS = "enabled-applets"
BACKUP_DIR = os.path.expanduser("~/cinnamon-panel-mirror-backups")

# GTK is only needed for the GUI. Guard the import so the pure-logic functions
# below can be imported/tested in environments without GTK.
HAVE_GTK = True
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Pango
except Exception:  # pragma: no cover - depends on the host
    HAVE_GTK = False


# ---------------------------------------------------------------------------
# Pure logic (no GTK, no system calls) -- this is the part that is unit-tested.
# ---------------------------------------------------------------------------

def parse_gsettings_list(raw):
    """Turn a gsettings 'as' value like "['a', 'b']" into ['a', 'b']."""
    raw = (raw or "").strip()
    if raw in ("", "@as []", "[]"):
        return []
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, (list, tuple)):
            return [str(x) for x in val]
    except Exception:
        pass
    return []


def parse_panels_enabled(raw):
    """Parse panels-enabled entries "<id>:<monitor>:<position>".

    Returns dicts with id, ref ("panel<id>"), monitor, position, raw.
    """
    panels = []
    for item in parse_gsettings_list(raw):
        parts = item.split(":")
        if len(parts) >= 3:
            pid = parts[0]
            panels.append({
                "id": pid,
                "ref": "panel" + pid,
                "monitor": parts[1],
                "position": ":".join(parts[2:]),
                "raw": item,
            })
    return panels


def parse_enabled_applets(raw):
    """Parse enabled-applets entries "<panel>:<zone>:<order>:<uuid>:<instance>".

    The uuid never contains a colon in practice, but we join defensively so a
    stray one wouldn't corrupt the instance id (which is always the last field).
    """
    applets = []
    for item in parse_gsettings_list(raw):
        parts = item.split(":")
        if len(parts) >= 5:
            applets.append({
                "panel": parts[0],
                "zone": parts[1],
                "order": parts[2],
                "uuid": ":".join(parts[3:-1]),
                "instance": parts[-1],
                "raw": item,
            })
    return applets


def max_instance(applets):
    """Highest numeric instance id in use (0 if none)."""
    m = 0
    for a in applets:
        try:
            m = max(m, int(a["instance"]))
        except (ValueError, KeyError):
            pass
    return m


def _entry(panel, zone, order, uuid, instance):
    return "%s:%s:%s:%s:%s" % (panel, zone, order, uuid, instance)


def build_mirror(applets, source_ref, target_refs, include_instances=None):
    """Compute the new applet layout that mirrors source onto each target.

    * Applets on the source panel are left untouched.
    * Applets on any panel that is neither source nor target are left untouched.
    * Each target panel's existing applets are removed and replaced with copies
      of the (chosen) source applets, each given a fresh unique instance id.

    include_instances: optional iterable of source instance ids to copy; None
    means copy them all.

    Returns (new_applet_dicts, copy_ops) where copy_ops is a list of
    (uuid, source_instance, new_instance) describing config files to duplicate.
    """
    targets = [t for t in target_refs if t and t != source_ref]

    source_applets = [a for a in applets if a["panel"] == source_ref]
    if include_instances is not None:
        wanted = set(include_instances)
        source_applets = [a for a in source_applets if a["instance"] in wanted]

    # Keep everything that isn't on a target panel (this includes the source).
    kept = [a for a in applets if a["panel"] not in targets]

    next_id = max_instance(applets) + 1
    new_entries = []
    copy_ops = []
    for tref in targets:
        for a in source_applets:
            inst = str(next_id)
            next_id += 1
            new_entries.append({
                "panel": tref,
                "zone": a["zone"],
                "order": a["order"],
                "uuid": a["uuid"],
                "instance": inst,
                "raw": _entry(tref, a["zone"], a["order"], a["uuid"], inst),
            })
            copy_ops.append((a["uuid"], a["instance"], inst))

    return kept + new_entries, copy_ops


def serialize_enabled_applets(applets):
    """Build a gsettings-compatible 'as' literal from applet dicts."""
    entries = [a["raw"] for a in applets]
    if not entries:
        return "@as []"
    return "[" + ", ".join("'" + e + "'" for e in entries) + "]"


# ---------------------------------------------------------------------------
# System helpers (talk to gsettings / dconf / the filesystem).
# ---------------------------------------------------------------------------

def get_setting(key):
    r = subprocess.run(["gsettings", "get", SCHEMA, key],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def set_setting(key, value):
    r = subprocess.run(["gsettings", "set", SCHEMA, key, value],
                       capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip()


def spices_dir():
    """Locate the folder holding per-applet JSON settings for this version."""
    for candidate in ("~/.config/cinnamon/spices", "~/.cinnamon/configs"):
        p = os.path.expanduser(candidate)
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~/.config/cinnamon/spices")


def copy_applet_config(base, uuid, src_instance, new_instance):
    """Duplicate an applet's settings file. Returns True if a file was copied."""
    src = os.path.join(base, uuid, "%s.json" % src_instance)
    dst = os.path.join(base, uuid, "%s.json" % new_instance)
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def make_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(BACKUP_DIR, "cinnamon-%s.dconf" % ts)
    with open(path, "w") as f:
        r = subprocess.run(["dconf", "dump", "/org/cinnamon/"],
                           stdout=f, text=True)
    return path if r.returncode == 0 else None


def latest_backup():
    if not os.path.isdir(BACKUP_DIR):
        return None
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".dconf"))
    return os.path.join(BACKUP_DIR, files[-1]) if files else None


def restore_backup(path):
    with open(path) as f:
        r = subprocess.run(["dconf", "load", "/org/cinnamon/"],
                           stdin=f, text=True)
    return r.returncode == 0


def restart_cinnamon():
    subprocess.Popen(["cinnamon", "--replace"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def applet_display_name(a):
    name = a["uuid"].split("@")[0]
    return "%s  ·  %s" % (name, a["zone"])


def panel_display_name(p, applet_count):
    return "Panel %s   ·   monitor %s   ·   %s   (%d applets)" % (
        p["id"], p["monitor"], p["position"], applet_count)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def launch_gui():
    class MirrorWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title="Cinnamon Panel Mirror")
            self.set_default_size(560, 640)
            self.set_border_width(12)

            self.panels = []
            self.applets = []
            self.source_buttons = []     # (radio, panel_ref)
            self.target_buttons = {}     # panel_ref -> checkbutton
            self.applet_buttons = []     # (checkbutton, source_instance)

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(outer)

            intro = Gtk.Label(xalign=0)
            intro.set_line_wrap(True)
            intro.set_markup(
                "<b>Copy one panel onto the others.</b>\n"
                "Pick a source panel, tick the panels to mirror it onto, and "
                "click Apply. A full backup is taken automatically first.")
            outer.pack_start(intro, False, False, 0)

            # Source panel
            outer.pack_start(self._frame("1 · Source panel — the one to copy from",
                                         self._source_box()), False, False, 0)
            # Target panels
            outer.pack_start(self._frame("2 · Copy onto these panels",
                                         self._target_box()), False, False, 0)
            # Applets
            outer.pack_start(self._frame("3 · Applets to copy (untick any to skip)",
                                         self._applet_scroller()), True, True, 0)

            # Buttons
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            self._add_button(btn_row, "Preview", self.on_preview)
            self._add_button(btn_row, "Apply", self.on_apply)
            self._add_button(btn_row, "Restore last backup", self.on_restore)
            self._add_button(btn_row, "Restart Cinnamon", self.on_restart)
            self._add_button(btn_row, "Reload", self.on_reload)
            outer.pack_start(btn_row, False, False, 0)

            # Log
            self.log_buffer = Gtk.TextBuffer()
            log_view = Gtk.TextView(buffer=self.log_buffer)
            log_view.set_editable(False)
            log_view.set_monospace(True)
            log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            log_scroll = Gtk.ScrolledWindow()
            log_scroll.set_min_content_height(150)
            log_scroll.add(log_view)
            outer.pack_start(self._frame("Log", log_scroll), True, True, 0)

            self.reload_data()

        # -- small layout helpers ------------------------------------------
        def _frame(self, title, child):
            frame = Gtk.Frame(label=title)
            frame.set_label_align(0.02, 0.5)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.set_border_width(8)
            box.pack_start(child, True, True, 0)
            frame.add(box)
            return frame

        def _source_box(self):
            self._source_container = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2)
            return self._source_container

        def _target_box(self):
            self._target_container = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2)
            return self._target_container

        def _applet_scroller(self):
            self._applet_container = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2)
            scroll = Gtk.ScrolledWindow()
            scroll.set_min_content_height(150)
            scroll.add(self._applet_container)
            return scroll

        def _add_button(self, row, label, handler):
            b = Gtk.Button(label=label)
            b.connect("clicked", handler)
            row.pack_start(b, True, True, 0)

        def log(self, msg):
            end = self.log_buffer.get_end_iter()
            self.log_buffer.insert(end, msg + "\n")

        # -- data loading ---------------------------------------------------
        def reload_data(self):
            self.panels = parse_panels_enabled(get_setting(KEY_PANELS))
            self.applets = parse_enabled_applets(get_setting(KEY_APPLETS))
            self._rebuild_source()
            self._rebuild_targets()
            self._rebuild_applets()
            if not self.panels:
                self.log("No panels found. Are you running Cinnamon? If a "
                         "monitor has no panel yet, right-click an existing "
                         "panel > add a new panel first, then click Reload.")
            else:
                self.log("Loaded %d panel(s) and %d applet(s)."
                         % (len(self.panels), len(self.applets)))

        def _count_applets(self, ref):
            return sum(1 for a in self.applets if a["panel"] == ref)

        def _clear(self, container):
            for c in container.get_children():
                container.remove(c)

        def _rebuild_source(self):
            self._clear(self._source_container)
            self.source_buttons = []
            group = None
            for p in self.panels:
                label = panel_display_name(p, self._count_applets(p["ref"]))
                rb = Gtk.RadioButton.new_with_label_from_widget(group, label)
                if group is None:
                    group = rb
                rb.connect("toggled", self.on_source_toggled)
                self._source_container.pack_start(rb, False, False, 0)
                self.source_buttons.append((rb, p["ref"]))
            self._source_container.show_all()

        def _selected_source(self):
            for rb, ref in self.source_buttons:
                if rb.get_active():
                    return ref
            return None

        def _rebuild_targets(self):
            self._clear(self._target_container)
            self.target_buttons = {}
            source = self._selected_source()
            for p in self.panels:
                if p["ref"] == source:
                    continue
                label = panel_display_name(p, self._count_applets(p["ref"]))
                cb = Gtk.CheckButton(label=label)
                self._target_container.pack_start(cb, False, False, 0)
                self.target_buttons[p["ref"]] = cb
            self._target_container.show_all()

        def _rebuild_applets(self):
            self._clear(self._applet_container)
            self.applet_buttons = []
            source = self._selected_source()
            src_applets = [a for a in self.applets if a["panel"] == source]
            src_applets.sort(key=lambda a: (a["zone"], _safe_int(a["order"])))
            for a in src_applets:
                cb = Gtk.CheckButton(label=applet_display_name(a))
                cb.set_active(True)
                self._applet_container.pack_start(cb, False, False, 0)
                self.applet_buttons.append((cb, a["instance"]))
            self._applet_container.show_all()

        # -- signal handlers ------------------------------------------------
        def on_source_toggled(self, widget):
            if widget.get_active():
                self._rebuild_targets()
                self._rebuild_applets()

        def _gather_plan(self):
            source = self._selected_source()
            if source is None:
                self.log("Pick a source panel first.")
                return None
            targets = [ref for ref, cb in self.target_buttons.items()
                       if cb.get_active()]
            if not targets:
                self.log("Tick at least one panel to copy onto.")
                return None
            include = [inst for cb, inst in self.applet_buttons if cb.get_active()]
            if not include:
                self.log("No applets ticked — nothing to copy.")
                return None
            new_applets, copy_ops = build_mirror(
                self.applets, source, targets, include_instances=include)
            return {"source": source, "targets": targets,
                    "new_applets": new_applets, "copy_ops": copy_ops}

        def on_preview(self, _btn):
            plan = self._gather_plan()
            if not plan:
                return
            self.log("── Preview ──")
            self.log("Copy %s onto: %s"
                     % (plan["source"], ", ".join(plan["targets"])))
            self.log("%d applet copies, %d settings files to duplicate."
                     % (len(plan["copy_ops"]), len(plan["copy_ops"])))
            self.log("Nothing has been changed yet. Click Apply to do it.")

        def on_apply(self, _btn):
            plan = self._gather_plan()
            if not plan:
                return
            dialog = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Mirror panels?")
            dialog.format_secondary_text(
                "This replaces the contents of %s with a copy of %s.\n\n"
                "A full backup is taken first. You can undo with "
                "'Restore last backup'." % (", ".join(plan["targets"]),
                                            plan["source"]))
            resp = dialog.run()
            dialog.destroy()
            if resp != Gtk.ResponseType.OK:
                return

            backup = make_backup()
            if backup:
                self.log("Backup saved: %s" % backup)
            else:
                self.log("WARNING: backup failed — stopping. Nothing changed.")
                return

            base = spices_dir()
            copied = 0
            for uuid, src_inst, new_inst in plan["copy_ops"]:
                if copy_applet_config(base, uuid, src_inst, new_inst):
                    copied += 1
            self.log("Duplicated %d applet settings file(s) in %s."
                     % (copied, base))

            value = serialize_enabled_applets(plan["new_applets"])
            ok, err = set_setting(KEY_APPLETS, value)
            if ok:
                self.log("Applied. Now click 'Restart Cinnamon' (or press "
                         "Ctrl+Alt+Esc) to see the mirrored panels.")
                self.reload_data()
            else:
                self.log("Failed to write applets: %s" % err)
                self.log("Your setup is unchanged; restore the backup if needed.")

        def on_restore(self, _btn):
            path = latest_backup()
            if not path:
                self.log("No backup found yet.")
                return
            if restore_backup(path):
                self.log("Restored %s. Restart Cinnamon to apply." % path)
                self.reload_data()
            else:
                self.log("Restore failed for %s." % path)

        def on_restart(self, _btn):
            self.log("Restarting Cinnamon…")
            restart_cinnamon()

        def on_reload(self, _btn):
            self.reload_data()

    def _safe_int(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return 0

    win = MirrorWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


def main():
    if not HAVE_GTK:
        print("GTK (python3-gi + gir1.2-gtk-3.0) is required to run the GUI.")
        print("On Linux Mint it's already installed. Install with:")
        print("  sudo apt install python3-gi gir1.2-gtk-3.0")
        return
    launch_gui()


if __name__ == "__main__":
    main()
