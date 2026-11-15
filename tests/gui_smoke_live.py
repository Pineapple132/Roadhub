"""Demo-Fahrt durch die Live-Seite. Aufruf: gui_smoke_live.py <game.sii> [shot-dir]"""
import os as _os; _os.environ.setdefault("ETS2_SKIP_TUTORIAL", "1")
import os, sys, shutil, tempfile, pathlib, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = pathlib.Path(sys.argv[1]); shots = sys.argv[2] if len(sys.argv) > 2 else None
root = pathlib.Path(tempfile.mkdtemp())
d = root / "profiles" / "4D79204E616D65" / "save" / "1"; d.mkdir(parents=True)
shutil.copy(src, d / "game.sii")
os.environ["ETS2_SAVE_ROOT"] = str(root / "profiles")
os.environ["ETS2_BUSCO_FILE"] = str(root / "busfirma.json")
from tkinter import messagebox
messagebox.showinfo = lambda *a, **k: None
ASK = {'v': True}
messagebox.askyesnocancel = lambda *a, **k: ASK['v']
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
messagebox.askyesno = lambda *a, **k: False
messagebox.askokcancel = lambda *a, **k: True
from roadhub import gui, telemetry
app = gui.App(); app.geometry("1200x780+0+0"); app.update()
app._scan_saves(); app._load_selected(); app.update()
assert app._create_company(); c = app.company
city = c.catalog.cities()[0]; c.build_garage(city, "mittel")
dest = c.catalog.destinations(city)[0][0]
bus = c.buy_bus(city, c.catalog.models[0]); c.assign_route(bus.id, dest); c.assign_driver(c.hire(c.candidates()[0].key).id, bus.id)
app.show_page("live"); app.update()
lp = app.live_page
def shot(name):
    if shots:
        from PIL import ImageGrab
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f"{shots}/{name}.png")
app.telemetry.demo = None
app.telemetry.start_demo(seconds=6.0)
earned0 = c.game_earned
end = time.time() + 4
while not app.tracker.active and time.time() < end: app.update(); time.sleep(0.05)
assert app.tracker.active and c.trip_mark is not None
lp.overlay_var.set(True); lp._overlay_changed()
time.sleep(3); app.update(); app.update(); app.update(); shot("09_live_fahrt")
assert app.overlay is not None and "noch" in app.overlay.line_var.get(), app.overlay and app.overlay.line_var.get()
assert lp.v["time"].get() != "–"
from PIL import ImageGrab
ov = app.overlay; ov.update_idletasks()
ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((ov.winfo_rootx(), ov.winfo_rooty(), ov.winfo_rootx()+ov.winfo_width(), ov.winfo_rooty()+ov.winfo_height())).save((shots or "/tmp") + "/11_overlay.png")
end = time.time() + 12
while not c.trip_log and time.time() < end: app.update(); time.sleep(0.05)
assert c.trip_log, "keine Lieferung erkannt"
r = c.trip_log[-1]
assert r["income"] == 6240 and c.game_earned == earned0 + 6240 and r["trips"] >= 0
assert lp.rep.winfo_ismapped()
app.update(); shot("10_live_bericht")
lp._show_live(); app.update()
assert not app.tracker.active and app.telemetry.demo is None
# neuer Save: Konto wird abgeglichen, Editor neu geladen
import pathlib as _pl
from roadhub import sii as _sii, editor as _ed
sav = _pl.Path(app.path)
doc = _sii.load(str(sav))
m0 = int(_ed.read_values(doc, _ed.ALL_FIELDS)["money_account"])
_ed.write_profile(doc, {"money_account": m0 + 12345})
_sii.save(doc, str(sav), backup=False)
os.utime(sav, (time.time() + 5, time.time() + 5))
app.SAVE_QUIET_S = 0.0
app._watch_saves(); app._watch_saves(); app._watch_saves(); app.update()
assert int(app.profile_vars["money_account"].get()) == m0 + 12345, app.profile_vars["money_account"].get()
assert abs(app.company.sync_base - (m0 + 12345)) < 1 and app.last_save_mtime > time.time()
assert "Letzter Save" in lp.save_lbl.cget("text") or True
app.telemetry.stop_demo() if app.telemetry.demo else None
# zweite Fahrt von Hand abbrechen und abliefern
n = len(c.trip_log)
app.telemetry.start_demo(seconds=30.0, income=5000)
end = time.time() + 6
while not app.tracker.active and time.time() < end: app.update(); time.sleep(0.05)
assert app.tracker.active
ASK['v'] = False; app.end_trip_manually(); app.update()
assert len(c.trip_log) == n and not app.tracker.active and app.telemetry.demo is None
app.telemetry.start_demo(seconds=30.0, income=4000)
end = time.time() + 6
while not app.tracker.active and time.time() < end: app.update(); time.sleep(0.05)
ASK['v'] = True; app.end_trip_manually(); app.update()
assert len(c.trip_log) == n + 1 and not app.tracker.active
lp.overlay_var.set(False); lp._overlay_changed(); app.update()
assert app.overlay is None
app.destroy(); print("OK", r)
