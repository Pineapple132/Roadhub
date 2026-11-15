"""Tour through all pages in one language (ETS2_LANG), checks for crashes and reports remaining German texts."""
import os as _os; _os.environ.setdefault("ETS2_SKIP_TUTORIAL", "1")
import os, sys, re, shutil, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src, shots = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
if shots: os.makedirs(shots, exist_ok=True)
tmp = pathlib.Path(tempfile.mkdtemp())
prof = tmp / "profiles" / "4D79204E616D65"; (prof / "save" / "quicksave").mkdir(parents=True)
shutil.copy(src, prof / "save" / "quicksave" / "game.sii")
os.environ["ETS2_SAVE_ROOT"] = str(tmp / "profiles")
os.environ["ETS2_BUSCO_FILE"] = str(tmp / "busfirma.json"); os.environ["HOME"] = str(tmp)
from tkinter import messagebox
messagebox.askokcancel = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
messagebox.askyesno = lambda *a, **k: False
from roadhub import gui, i18n
lang = i18n.load_saved_language()
app = gui.App(); app.geometry("1200x780+0+0"); app.update()
app._scan_saves(); app._load_selected(); app.update()
def shot(name):
    if shots:
        from PIL import ImageGrab
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f"{shots}/{lang}_{name}.png")
shot("00_gruenden")
assert app._create_company(); c = app.company
city = c.catalog.cities()[0]; c.build_garage(city, "medium")
dest = c.catalog.destinations(city)[0][0]
bus = c.buy_bus(city, c.catalog.models[0]); c.assign_route(bus.id, dest); c.assign_driver(c.hire(c.candidates()[0].key).id, bus.id)
c.advance(3 * 1440); app.company_changed()
for key in ("overview", "live", "map", "garages", "buses", "drivers", "routes", "contracts", "finance", "settings", "profile", "jobs", "bus", "buslines"):
    app.show_page(key); app.update(); shot(key)
# collect remaining German texts
import tkinter as tk
from tkinter import ttk
GERMAN = re.compile(r"\b(und|der|die|das|nicht|Bitte|Fahrer|Firma|Konto|Garage|Spielstand|noch|für|wird|eine|einen|auf|mit|Stunden|Tage|Strecke|Bus)\b")
found = set()
def walk(w):
    for ch in w.winfo_children():
        for opt in ("text",):
            try:
                t = ch.cget(opt)
                if isinstance(t, str) and GERMAN.search(t): found.add(t[:90])
            except tk.TclError:
                pass
        walk(ch)
walk(app)
print(lang, "Resttexte:", len(found))
for t in sorted(found)[:40]: print("   ", repr(t))
print("LANG SMOKE OK", lang)
