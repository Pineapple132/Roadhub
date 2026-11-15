"""GUI-Rauchtest unter Xvfb: lädt einen Test-Save, ändert Profil+Auftrag, speichert, liest zurück."""
import os as _os; _os.environ.setdefault("ETS2_SKIP_TUTORIAL", "1")
import os, sys, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.fixtures import make_save_text
from roadhub import sii, editor

root = pathlib.Path(tempfile.mkdtemp())
prof = root / "profiles" / "4D79204E616D65" / "save" / "quicksave"   # hex für "My Name"
prof.mkdir(parents=True)
(prof / "game.sii").write_bytes(sii.encrypt_text(make_save_text().encode()))
os.environ["ETS2_SAVE_ROOT"] = str(root / "profiles")
os.environ["ETS2_BUSCO_FILE"] = str(root / "busfirma.json")

import tkinter as tk
from tkinter import messagebox
messagebox.askokcancel = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: print("INFO:", a[1][:40].replace("\n", " "))
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
messagebox.askyesno = lambda *a, **k: True

from roadhub import gui
app = gui.App()
app.update()
app.after(50)
app._scan_saves(); app.update()
assert len(app.save_entries) == 1 and app.save_entries[0].profile == "My Name", app.save_entries
app._load_selected(); app.update()
assert app.doc is not None
assert app.profile_vars["money_account"].get() == "1234567"
assert len(app.tree.get_children()) == 8

# Profil ändern
app.profile_vars["money_account"].set("5000000"); app.profile_vars["adr"].set("63")
app.profile_vars["bus_experience_points"].set("7777"); app.profile_vars["tight_schedule"].set("2")
assert app.chip_vars["busxp"].get() == "7.777", app.chip_vars["busxp"].get()
assert app.dirty and app.title().startswith("*")

# Auftrag bearbeiten
iid = app.tree.get_children()[0]
app.tree.selection_set(iid); app.update()
offer = app._selected_offer()
dlg = gui.JobDialog(app, offer); app.update()
dlg.target_var.set("sellplan.paris"); dlg._suggest_route(); dlg.cargo_var.set("cement"); dlg._cargo_changed()
dlg.dist_var.set("777"); dlg.urg.current(2); dlg.hours_var.set("24")
dlg._apply(); app.update()
assert app.jobs_dirty

# Screenshot der Aufträge-Ansicht
app.show_page("jobs"); app.geometry("980x640+0+0"); app.update()
try:
    from PIL import ImageGrab
    ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((0,0,980,640)).save("/tmp/gui_jobs.png")
except Exception as e:
    print("kein Screenshot:", e)

app._save(); app.update()
assert not app.dirty

again = sii.load(str(prof / "game.sii"))
p = editor.read_profile(again)
assert p["money_account"] == "5000000" and p["adr"] == "63", p
b = editor.read_bus_fields(again)
assert b["bus_experience_points"] == "7777" and b["tight_schedule"] == "2", b
hit = [o for o in editor.list_offers(again) if o.target_key == "sellplan.paris" and o.values["shortest_distance_km"] == "777"]
assert hit and hit[0].values["urgency"] == "2"
assert any(f.name.startswith("game.sii.backup_") for f in prof.iterdir())
print("GUI SMOKE OK")
app.destroy()
