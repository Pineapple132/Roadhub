"""GUI-Rauchtest Busfirma + Bus-Aufträge + Auszahlung. Aufruf: gui_smoke_company.py <game.sii> [screenshot-dir]"""
import os as _os; _os.environ.setdefault("ETS2_SKIP_TUTORIAL", "1")
import os, sys, shutil, tempfile, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from roadhub import sii, editor, buslines, busco

src = pathlib.Path(sys.argv[1]); shots = sys.argv[2] if len(sys.argv) > 2 else None
root = pathlib.Path(tempfile.mkdtemp())
prof = root / "profiles" / "4D79204E616D65" / "save" / "quicksave"
prof.mkdir(parents=True)
shutil.copy(src, prof / "game.sii")
os.environ["ETS2_SAVE_ROOT"] = str(root / "profiles")
os.environ["ETS2_BUSCO_FILE"] = str(root / "busfirma.json")

from tkinter import messagebox
messagebox.askokcancel = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: print("INFO:", a[1][:60].replace("\n", " "))
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[1]))
messagebox.askyesno = lambda *a, **k: False   # kein automatisches Laden

from roadhub import gui, gui_company, gui_buslines

def shot(app, name):
    app.update()
    if not shots: return
    from PIL import ImageGrab
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).crop((x, y, x + app.winfo_width(), y + app.winfo_height())).save(f"{shots}/{name}.png")

app = gui.App(); app.geometry("1200x780+0+0"); app.update()
app._scan_saves(); app.update()
shot(app, "00_leer")
assert app.company is None
app._load_selected(); app.update()
assert app.company is None and str(app.overview.found_btn.cget("state")) == "normal"   # Save geladen, aber noch nicht gegründet
shot(app, "00b_gruenden")
real_money = app.account_money
app.account_money = lambda: 100_000                       # zu wenig Geld: Gründen geht nicht
app.overview.refresh(); app.update()
assert str(app.overview.found_btn.cget("state")) == "disabled" and "50.000" in app.overview.found_info.cget("text")
assert app._create_company() is False and app.company is None
app.show_page("garages"); assert app.current_page == "overview"
assert not app.nav_buttons["garages"].winfo_ismapped() and app.nav_buttons["overview"].winfo_ismapped()
app.account_money = real_money
assert app._create_company() is True
assert app.company is not None and len(app.company.catalog.routes) > 0
c = app.company; app.update()
assert app.nav_buttons["garages"].winfo_ismapped() and app.nav_buttons["settings"].winfo_ismapped()
assert abs(c.firm_delta() + busco.FOUNDING_COST) < 0.01 and c.fin_total["Firmengründung"] == busco.FOUNDING_COST
shot(app, "01_uebersicht")

# Garage bauen
city = c.catalog.cities()[0]
c.build_garage(city, "mittel"); app.company_changed()
assert city in c.garages
# Bus kaufen und Linie zuweisen
dest = c.catalog.destinations(city)[0][0]
bus = c.buy_bus(city, c.catalog.models[0]); c.assign_route(bus.id, dest); c.assign_driver(c.hire(c.candidates()[0].key).id, bus.id); app.company_changed()
app.show_page("garages"); app.update(); shot(app, "02_garagen")
assert app.garages_page.drv_tree.get_children() and app.garages_page.bus_tree.get_children()
c.advance(3 * 1440); app.company_changed(); app.show_page("finance"); app.update(); shot(app, "02f_finanzen")
assert len(app.finance_page.tree.get_children()) >= 15
app.show_page("settings"); app.update(); shot(app, "02g_einstellungen")
sp = app.settings_page; sp.vars["rate_per_km"].set("20"); sp.vars["fuel_price"].set("2"); sp.apply()
assert app.company.settings.tuning["rate_per_km"] == 20.0 and abs(busco.CONTRACT_RATE_PER_KM - 40.0 * busco.SIM_INCOME_FACTOR) < 1e-9
sp.vars["rate_per_km"].set("13"); sp.vars["fuel_price"].set("1.55"); sp.apply()
assert app.company.settings.tuning == {}
app.show_page("garages")
# Karte
app.show_page("map"); app.update(); app.update()
mp = app.map_page
assert mp.canvas.winfo_width() > 300
lat, lon = busco.mapdata.CITY_COORDS[city]
x, y = mp.to_screen(lat, lon); mp._click(x, y)
assert mp.selected == ("city", city), mp.selected
shot(app, "02b_karte")
# Sehenswürdigkeit anklicken
sight = next(k for k in c.catalog.sights())
sx, sy = mp.to_screen(*busco.mapdata.SIGHT_COORDS[sight]); mp._click(sx + 4, sy - 4)
assert mp.selected == ("sight", sight), mp.selected
# Bus anklicken
for _ in range(2000):
    c.advance(15)
    if c.bus_state(bus)[3] == "unterwegs" and 0.3 < c.bus_state(bus)[2] < 0.7: break
app.company_changed(); app.update()
bx_state = c.bus_state(bus)
a, b_, frac, st = bx_state
pa, pb = busco.mapdata.coords(a), busco.mapdata.coords(b_)
bx, by = mp.to_screen(pa[0] + (pb[0]-pa[0])*frac, pa[1] + (pb[1]-pa[1])*frac); mp._click(bx, by)
assert mp.selected == ("bus", str(bus.id)), (mp.selected, st)
mp.zoom = 60; mp.cx, mp.cy = lon, lat; mp.redraw(); shot(app, "02c_karte_zoom")
mp.reset_view()
# Fahrer
app.show_page("drivers"); drv = next(iter(c.drivers.values()))
app.drivers_page.tree.selection_set(str(drv.id)); shot(app, "02d_fahrer")
from roadhub import gui_drivers
dlg = gui_drivers.HireDialog(app.drivers_page, c); app.update(); shot(app, "02e_einstellen"); assert dlg.tree.get_children(); dlg.destroy()
c.train(drv.id, "eco"); app.company_changed()
tr = gui_drivers.TrainDialog(app.drivers_page, c, drv); app.update(); tr.destroy()
app.show_page("buses"); shot(app, "03_busse")
dlg = gui_company.AssignRouteDialog(app.buses_page, c, bus); app.update()
assert dlg.tree.get_children(); shot(app, "04_linie_zuweisen"); dlg.destroy()

# Eigene Route + Ausflug + Vertrag
c.cash += 3_000_000
from roadhub import gui_routes, gui_contracts
others = [d for d, *_ in c.catalog.destinations(city) if d.startswith("city.") and d != dest][:1]
rd = gui_routes.RouteDialog(app.routes_page, c, preset_start=city); app.update()
rd.name_var.set("Meine Dreierlinie"); rd.rows[0]["var"].set(busco.city_name(dest)); rd._picked(0)
rd.rows[1]["var"].set(busco.city_name(others[0])); rd._picked(1); app.update()
assert rd.rows[0]["km"].get() and rd.rows[1]["km"].get()
assert rd.on_ok(); rd.destroy()
sightkey = next(k for k in c.catalog.sights() if (city, k) in c.catalog.routes)
rd2 = gui_routes.RouteDialog(app.routes_page, c, preset_start=city, preset_stop=sightkey); app.update()
assert rd2.name_var.get().startswith("Ausflug") and rd2.kind.get().startswith("Ausflug")
assert rd2.on_ok(); rd2.destroy()
assert len(c.routes) == 2
app.company_changed(); app.show_page("routes"); shot(app, "02f_routen")
route = next(r for r in c.routes.values() if r.kind == "linie")
bus2 = c.buy_bus(city, c.catalog.models[0]); c.assign_driver(c.hire(c.candidates()[1].key).id, bus2.id)
ad = gui_company.AssignRouteDialog(app.buses_page, c, bus2); app.update()
assert any(k.startswith("route:") for k in ad.tree.get_children())
ad.tree.selection_set(f"route:{route.id}"); assert ad.on_ok(); ad.destroy()
assert bus2.route_id == route.id
bus3 = c.buy_bus(city, c.catalog.models[0]); c.assign_driver(c.hire(c.candidates()[2].key).id, bus3.id)
app.company_changed(); app.show_page("contracts"); app.update()
offers = c.contract_offers(); assert offers, "keine Vertragsangebote"
app.contracts_page.offers.selection_set(offers[0].key)
acc = gui_contracts.AcceptDialog(app.contracts_page, c, offers[0]); app.update(); shot(app, "02g_vertrag_annehmen")
acc.tree.selection_set(str(bus3.id)); assert acc.on_ok(); acc.destroy()
app.company_changed(); shot(app, "02h_vertraege")
# Zeitraffer
app.show_page("overview")
app.overview.jump(30 * 1440); app.update()
assert c.cash > 0 and c.xp_pending > 0, (c.cash, c.xp_pending)
app.overview.toggle_run(); app.overview._carry = 5; app.overview.tick(); app.overview.toggle_run()
shot(app, "05_uebersicht_nach_30_tagen")

# Bus-Aufträge
app.show_page("buslines"); app.update()
offers = [o for o in app.buslines_page.offers() if not o.is_empty]
assert offers
app.buslines_page.tree.selection_set(f"{offers[0].stop_unit}|{offers[0].slot}")
d = gui_buslines.LineDialog(app.buslines_page, app, offers[0]); app.update()
shot(app, "06_linie_dialog")
extra = next(k for k in d.stop_keys if k.startswith("city.") and k not in (d.start_key, offers[0].targets[0]))
d.rows[1]["target"].set(gui_buslines.pretty_stop(extra)); d._target_picked(1)
d.hours_var.set("48"); d.dep_var.set("06:15")
assert d.on_ok(), "Dialog nicht übernommen"
d.destroy(); app.lines_applied(); app.update()
assert app.jobs_dirty

# Auszahlung
money_before = int(app.profile_vars["money_account"].get()); xp_before = int(app.profile_vars["bus_experience_points"].get() or 0)
cash_before, xp_pending = c.cash, c.xp_pending
delta0, xp_d = int(round(c.firm_delta())), c.xp_pending
gui.messagebox.askokcancel = lambda *a, **k: True
app.start_payout(); app.update()
again = sii.load(str(prof / "game.sii"))
assert int(editor.read_profile(again)["money_account"]) == max(0, money_before + delta0)
assert int(editor.read_bus_fields(again)["bus_experience_points"]) == min(99_999_999, xp_before + xp_d)
assert c.xp_pending == 0 and abs(c.firm_delta()) < 0.01
# Linie wurde mitgespeichert
new = [o for o in buslines.list_line_offers(again) if o.stop_unit == offers[0].stop_unit and o.slot == offers[0].slot][0]
assert new.departure == 6 * 60 + 15 and len(new.targets) == 2, new
shot(app, "07_nach_auszahlung")
app.save_company()
assert busco.BusCompany.load(app.company_path).cash == c.cash
print("GUI COMPANY SMOKE OK")
app.destroy()
