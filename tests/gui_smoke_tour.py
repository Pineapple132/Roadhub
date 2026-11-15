"""Rundgang: beide Touren Schritt für Schritt durchlaufen, Screenshots ablegen, Sprache per ETS2_LANG."""
import os, sys, shutil, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src, shots = sys.argv[1], sys.argv[2]
os.makedirs(shots, exist_ok=True)
tmp = pathlib.Path(tempfile.mkdtemp())
prof = tmp / "profiles" / "4D79204E616D65" / "save" / "quicksave"; prof.mkdir(parents=True)
shutil.copy(src, prof / "game.sii")
os.environ.update(ETS2_SAVE_ROOT=str(tmp / "profiles"), ETS2_BUSCO_FILE=str(tmp / "b.json"), HOME=str(tmp))
os.environ.pop("ETS2_SKIP_TUTORIAL", None)
from tkinter import messagebox
messagebox.askokcancel = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: False
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
from roadhub import gui, i18n, tour
lang = i18n.load_saved_language()
app = gui.App(); app.geometry("1200x780+0+0"); app.update()
assert i18n.has_saved_language()
app._scan_saves(); app._load_selected(); app.update()
from PIL import ImageGrab
def shot(name):
    app.update(); app.update_idletasks()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f"{shots}/{lang}_{name}.png")
import time
def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.update(); time.sleep(0.02)
def run(kind, prefix):
    t = app.tour
    assert t is not None and t.active, "Tour startet nicht von selbst"
    for i in range(len(t.steps)):
        pump(200)
        shot(f"{prefix}{i+1:02d}")
        assert t.card is not None and t.card.winfo_exists(), (kind, i)
        r = t._target_rect(t.steps[i])
        if t.steps[i].target is not None:
            assert r is not None, ("Ziel nicht sichtbar", kind, i, t.steps[i].title)
        if t.steps[i].wait_page:
            app.show_page(t.steps[i].wait_page); pump(500)
            if i + 1 < len(t.steps) and t.active and t.index == i + 1:
                continue
        t.next()
    assert not t.active
pump(1800)
run("intro", "i")
assert i18n.ui_get("tour_done") is True
assert app._create_company()
pump(900)
assert app.tour is not None and app.tour.active, "Firmentour startet nach dem Gründen nicht"
t = app.tour
for i in range(len(t.steps)):
    pump(200)
    shot(f"c{i+1:02d}")
    r = t._target_rect(t.steps[i])
    if t.steps[i].target is not None:
        assert r is not None, ("Ziel nicht sichtbar", i, t.steps[i].title)
    if t.steps[i].wait_page:
        app.show_page(t.steps[i].wait_page); pump(500)
        if t.index == i + 1:
            continue
    t.next()
assert i18n.ui_get("company_tour_done") is True
print("Titel:", app.title_var.get())
print("TOUR SMOKE OK", lang)
