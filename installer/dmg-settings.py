# Einstellungen fuer dmgbuild: DMG-Fenster mit der App links, dem Ordner Programme
# rechts und einem Pfeil dazwischen (assets/dmg-background*.png).
# Aufruf:  dmgbuild -s installer/dmg-settings.py "Christinas Mail-Sync 1.2.3" dist/Christinas-Mail-Sync.dmg
import os.path

APP = "Christinas Mail-Sync.app"
app_path = defines.get("app", os.path.join("dist", APP))  # noqa: F821 (von dmgbuild gesetzt)

format = "UDZO"
filesystem = "HFS+"
files = [app_path]
symlinks = {"Programme": "/Applications"}
icon = "assets/MailSync.icns"
background = "assets/dmg-background.png"

window_rect = ((200, 160), (600, 380))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 112
text_size = 13
icon_locations = {APP: (160, 170), "Programme": (440, 170)}
