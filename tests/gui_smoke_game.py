"""Simulates 'ETS2 is running / exits' with a stand-in process. Usage: gui_smoke_game.py <game.sii> [shot-dir]"""
import os as _os; _os.environ.setdefault("ETS2_SKIP_TUTORIAL", "1")
import os, sys, shutil, tempfile, pathlib, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from roadhub import sii, editor

src = pathlib.Path(sys.argv[1]); shots = sys.argv[2] if len(sys.argv) > 2 else None
root = pathlib.Path(tempfile.mkdtemp())
old = root / "profiles" / "4D79204E616D65" / "save" / "1"; old.mkdir(parents=True)
new = root / "profiles" / "4D79204E616D65" / "save" / "quicksave"; new.mkdir(parents=True)
shutil.copy(src, old / "game.sii"); shutil.copy(src, new / "game.sii")
os.utime(old / "game.sii", (1_000_000_000, 1_000_000_000))          # older file
os.environ["ETS2_SAVE_ROOT"] = str(root / "profiles")
os.environ["ETS2_BUSCO_FILE"] = str(root / "busfirma.json")
os.environ["ETS2_PROCESS_NAME"] = "sleep"

from tkinter import messagebox
messages = []
messagebox.askokcancel = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: messages.append(a[1])
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
messagebox.askyesno = lambda *a, **k: False

from roadhub import gui, gamewatch
assert not gamewatch.is_game_running()
app = gui.App(); app.geometry("1200x780+0+0"); app.update()
app.GAME_POLL_MS = 200
app._scan_saves(); app._load_selected(); app.update()
assert app._create_company(); c = app.company
city = c.catalog.cities()[0]; c.build_garage(city, "medium")
dest = c.catalog.destinations(city)[0][0]
bus = c.buy_bus(city, c.catalog.models[0]); c.assign_route(bus.id, dest); c.assign_driver(c.hire(c.candidates()[0].key).id, bus.id)
app.show_page("overview")
ov = app.overview
ov.follow_var.set(True); ov.autopay_var.set(True); ov.game_speed.current(4)
ov._settings_changed(); app.update()
assert c.settings.follow_game and c.settings.auto_payout and c.settings.game_speed == 144
app.save_editor_loaded = None
# game is not running -> company pauses
t0 = c.now
for _ in range(10): ov.tick()
assert c.now == t0
# game starts
proc = subprocess.Popen(["sleep", "60"])
end = time.time() + 5
while not app.game_running and time.time() < end: app.update(); time.sleep(0.05)
assert app.game_running
end = time.time() + 6
while c.now - t0 < 600 and time.time() < end: app.update(); time.sleep(0.05)
assert c.now - t0 >= 600, c.now - t0
assert "läuft" in ov.game_state.cget("text")
if shots:
    from PIL import ImageGrab
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f"{shots}/08_mitlaufen.png")
cash, xp = c.cash, c.xp_pending
assert xp > 0 and abs(c.firm_delta()) > 0
money_before = int(editor.read_profile(sii.load(str(new / "game.sii")))["money_account"])
old_money = int(editor.read_profile(sii.load(str(old / "game.sii")))["money_account"])
# game exits -> automatic payout
proc.kill(); proc.wait()
end = time.time() + 20
while not messages and time.time() < end: app.update(); time.sleep(0.05)
assert messages, "keine Auszahlung"
after_new = int(editor.read_profile(sii.load(str(new / "game.sii")))["money_account"])
after_old = int(editor.read_profile(sii.load(str(old / "game.sii")))["money_account"])
assert after_new == int(c.cash) and after_old == old_money, (after_new, money_before, c.cash)
assert after_new < money_before          # garage and bus were paid with ETS2 money
assert abs(c.firm_delta()) < 1000 and c.xp_pending < xp
print(messages[0].splitlines()[0:6])
print("GUI GAME SMOKE OK")
app.destroy()
