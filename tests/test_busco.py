import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from roadhub import busco, sii  # noqa: E402
from roadhub.busco import DAY, BusCatalog, BusCompany, CompanyError  # noqa: E402
from tests.fixtures import make_save_text  # noqa: E402

MODEL_A = "man_lions_24_139h6_520"
MODEL_DD = "volvo_9700_23_143d6_500"


def catalog():
    routes = {
        ("city.a", "city.b"): (300, 280),
        ("city.a", "city.c"): (120, 110),
        ("city.b", "city.c"): (180, 170),
        ("city.a", "city.d"): (1100, 1000),
    }
    for (x, y), v in list(routes.items()):
        routes.setdefault((y, x), v)
    return BusCatalog(routes, [MODEL_A, MODEL_DD])


def hire(c):
    return c.hire(c.candidates()[0].key)


def company(cash=5_000_000, buses=3, dest="city.b", model=MODEL_DD, **kw):
    c = BusCompany(catalog(), cash, seed=7, **kw)
    c.build_garage("city.a", "medium")
    for _ in range(buses):
        bus = c.buy_bus("city.a", model)
        c.assign_route(bus.id, dest)
        c.assign_driver(hire(c).id, bus.id)
    return c


# ---- Models / catalog ------------------------------------------------------

def test_model_specs_from_real_names():
    dd = busco.model_spec(MODEL_DD)
    assert dd.seats == 82 and dd.length_m == 14.3 and "Doppeldecker" in dd.label
    lions = busco.model_spec(MODEL_A)
    assert lions.seats == round(13.9 * 3.9) and "MAN" in lions.label and lions.price > 200_000
    odd = busco.model_spec("irgendwas")
    assert odd.seats == round(12.5 * 3.9) and odd.price > 0       # fallback values


def test_catalog_from_doc_and_roundtrip():
    doc = sii.SiiDocument.from_bytes(make_save_text().encode())
    cat = BusCatalog.from_doc(doc)
    assert cat.routes[("city.zurich", "city.bern")] == (116, 100)
    assert cat.routes[("city.bern", "city.zurich")] == (116, 100)       # return direction added
    assert cat.routes[("city.bern", "city.basel")] == (90, 80)          # second leg
    assert MODEL_A in cat.models
    again = BusCatalog.from_dict(json.loads(json.dumps(cat.to_dict())))
    assert again.routes == cat.routes and again.models == cat.models
    assert [d for d, *_ in cat.destinations("city.bern")] == ["city.basel", "city.zurich"]


# ---- Actions and errors ------------------------------------------------------

def test_purchases_pay_and_validate():
    c = BusCompany(catalog(), 3_000_000, seed=1)
    with pytest.raises(CompanyError):
        c.buy_bus("city.a", MODEL_A)                      # no garage
    c.build_garage("city.a", "small")
    assert c.cash == 3_000_000 - 250_000
    with pytest.raises(CompanyError):
        c.build_garage("city.a", "small")                 # duplicate
    with pytest.raises(CompanyError):
        c.build_garage("city.zzz", "small")               # no routes there
    for _ in range(3):
        c.buy_bus("city.a", MODEL_A)
    with pytest.raises(CompanyError):
        c.buy_bus("city.a", MODEL_A)                      # garage full
    c.upgrade_garage("city.a")
    c.buy_bus("city.a", MODEL_A)
    with pytest.raises(CompanyError):
        c.buy_bus("city.a", "nicht_bekannt")


def test_not_enough_money_changes_nothing():
    c = BusCompany(catalog(), 100_000, seed=1)
    before = c.to_dict()
    with pytest.raises(CompanyError, match="fehlt Geld") as exc:
        c.build_garage("city.a", "small")
    assert "250.000 €, auf deinem Konto sind 100.000 €" in str(exc.value)
    assert c.to_dict() == before


def test_assign_route_validation_and_sell():
    c = company(buses=1)
    bus = next(iter(c.buses.values()))
    with pytest.raises(CompanyError):
        c.assign_route(bus.id, "city.nowhere")
    c.assign_route(bus.id, None)
    assert c.active_buses() == 0
    cash = c.cash
    value = c.sell_bus(bus.id)
    assert c.cash == cash + value and value > 0 and not c.buses
    with pytest.raises(CompanyError):
        c.sell_bus(bus.id)


# ---- Simulation ---------------------------------------------------------------

def test_deterministic_independent_of_chunking():
    a, b, d = company(), company(), company()
    a.advance(7 * DAY)
    for _ in range(7):
        b.advance(DAY)
    for _ in range(7 * 24):
        d.advance(60)
    da, db, dd = a.to_dict(), b.to_dict(), d.to_dict()
    ta, tb, td = da.pop("totals"), db.pop("totals"), dd.pop("totals")
    assert da == db == dd
    for k in ta:                       # totals: only the order of the floating-point addition differs
        assert abs(ta[k] - tb[k]) < 1e-6 and abs(ta[k] - td[k]) < 1e-6


def test_cash_equals_ledger_and_purchases():
    c = company()
    start = c.cash
    c.advance(10 * DAY + 400)
    revenue = sum(e["revenue"] for e in c.ledger.values())
    costs = sum(e["costs"] for e in c.ledger.values())
    assert c.cash == pytest.approx(start + revenue - costs, rel=1e-9)
    assert c.xp_total == c.xp_pending > 0


def test_idle_company_only_pays_daily_costs():
    c = BusCompany(catalog(), 1_000_000, seed=1)
    c.build_garage("city.a", "small")
    cash = c.cash
    c.advance(3 * DAY)
    assert c.cash == pytest.approx(cash - 3 * 120.0)


def test_plausible_monthly_profit_per_bus():
    c = company(buses=3)
    c.advance(30 * DAY)
    per_bus = (sum(e["revenue"] - e["costs"] for e in c.ledger.values())) / 3
    assert 50_000 < per_bus < 700_000, per_bus
    assert all(0 <= b.condition <= 100 for b in c.buses.values())
    assert all(b.next_free % DAY >= busco.OPERATING_START for b in c.buses.values())
    trips = sum(b.trips for b in c.buses.values())
    assert 3 * 30 * 1 < trips < 3 * 30 * 12                        # fewer trips per bus and day with the driving-time limit


def test_profit_multiplier_scales_revenue_only():
    base, boosted = company(), company()
    boosted.set_settings(profit_multiplier=2.0)
    base.advance(5 * DAY)
    boosted.advance(5 * DAY)
    rev = lambda c: sum(e["revenue"] for e in c.ledger.values())      # noqa: E731
    cost = lambda c: sum(e["costs"] for e in c.ledger.values())       # noqa: E731
    assert rev(boosted) == pytest.approx(2 * rev(base), rel=1e-9)
    assert cost(boosted) == pytest.approx(cost(base), rel=1e-9)


def test_auto_service_toggle():
    on, off = company(), company()
    off.set_settings(auto_service=False)
    on.advance(40 * DAY)
    off.advance(40 * DAY)
    assert any("automatisch gewartet" in t for _, t in on.log)
    assert min(b.condition for b in off.buses.values()) < min(b.condition for b in on.buses.values())
    assert any("Panne" in t for _, t in off.log)                    # without service breakdowns happen sooner or later


def test_manual_service():
    c = company(buses=1)
    bus = next(iter(c.buses.values()))
    with pytest.raises(CompanyError):
        c.service_bus(bus.id)                                       # already perfect
    c.advance(2 * DAY)
    assert bus.condition < 100
    cash = c.cash
    cost = c.service_bus(bus.id)
    assert bus.condition == 100.0 and c.cash == cash - cost


def test_longer_routes_pay_less_per_km_and_never_negative_pax():
    c = company(buses=1, dest="city.d")
    c.advance(20 * DAY)
    bus = next(iter(c.buses.values()))
    assert bus.trips > 0 and bus.pax >= 0 and bus.revenue > 0


# ---- Payout -----------------------------------------------------------------

def test_shared_account_sync_and_written():
    c = company(cash=20_000_000)
    c.sync_base = c.cash                 # initial state: account = save game, nothing pending
    c.advance(5 * DAY)
    delta = c.firm_delta()
    assert delta != 0
    # sync with the game: balance is taken over, the company change is kept
    c.sync_to_game(2_000_000)
    assert abs(c.firm_delta() - delta) < 0.01 and abs(c.cash - (2_000_000 + delta)) < 0.01
    c.build_garage("city.b", "small")                       # purchase is deducted from the account
    assert abs(c.firm_delta() - (delta - 250_000)) < 0.01
    xp = c.xp_pending
    c.mark_written(c.firm_delta(), 1_234_567, xp)
    assert c.cash == c.sync_base == 1_234_567 and c.firm_delta() == 0 and c.xp_pending == 0
    assert c.game_earned == 0


def test_save_load_resume_equals_uninterrupted(tmp_path):
    a = company()
    a.advance(4 * DAY)
    path = str(tmp_path / "busfirma.json")
    a.save(path)
    b = BusCompany.load(path)
    assert b.to_dict() == a.to_dict()
    a.advance(3 * DAY)
    b.advance(3 * DAY)
    assert a.to_dict() == b.to_dict()
    a.save(path)                                                    # a second save creates a .bak
    assert os.path.exists(path + ".bak")


def test_load_rejects_garbage(tmp_path):
    path = tmp_path / "x.json"
    path.write_text("{ not json")
    with pytest.raises(CompanyError):
        BusCompany.load(str(path))
    path.write_text(json.dumps({"version": 99}))
    with pytest.raises(CompanyError):
        BusCompany.load(str(path))


REAL = os.environ.get("ETS2_REAL_SAVE")


@pytest.mark.skipif(not REAL or not os.path.exists(REAL or ""), reason="kein echter Save angegeben")
def test_real_catalog_runs_a_year():
    doc = sii.SiiDocument.from_bytes(sii.decrypt_bytes(open(REAL, "rb").read()))
    cat = BusCatalog.from_doc(doc)
    assert len(cat.cities()) > 100 and len(cat.models) >= 3
    c = BusCompany(cat, 5_000_000, seed=3)
    c.build_garage("city.berlin", "large")
    for i, (dest, km, _) in enumerate(cat.destinations("city.berlin")[:8]):
        bus = c.buy_bus("city.berlin", cat.models[i % len(cat.models)])
        c.assign_route(bus.id, dest)
        c.assign_driver(hire(c).id, bus.id)
    c.advance(365 * DAY)
    assert c.cash > 5_000_000 and len(c.ledger) <= busco.LEDGER_DAYS + 1
    assert len(c.log) <= busco.LOG_LIMIT


def test_daily_profit_estimate_is_close_to_simulation():
    c = company(buses=1, dest="city.b")
    c.advance(30 * DAY)
    sim = sum(e["revenue"] - e["costs"] for e in c.ledger.values()) / 30
    est = busco.estimate_daily_profit(MODEL_DD, 300, 280)
    assert 0.6 * sim < est < 1.4 * sim, (est, sim)
    assert busco.estimate_daily_profit(MODEL_DD, 300, 280, 2.0) > est


def test_gamewatch_payout_into_save(tmp_path):
    from roadhub import gamewatch, sii as _sii, editor as _ed
    from tests.fixtures import make_save_text
    save = tmp_path / "game.sii"
    save.write_bytes(make_save_text().encode())
    before = _ed.read_values(_sii.load(str(save)), _ed.ALL_FIELDS)
    c = company(buses=1, dest="city.b")
    c.sync_to_game(int(before["money_account"]))
    c.advance(10 * DAY)
    delta, xp0 = gamewatch.payout_amounts(c)
    res = gamewatch.payout_into_save(c, str(save))
    assert res and res.euros == delta and res.xp == xp0
    assert c.xp_pending == 0 and c.firm_delta() == 0
    after = _ed.read_values(_sii.load(str(save)), _ed.ALL_FIELDS)
    assert int(after["money_account"]) == int(before["money_account"]) + delta == res.new_money == int(c.cash)
    assert int(after["bus_experience_points"]) == min(99_999_999, int(before["bus_experience_points"]) + res.xp)
    assert res.backup and gamewatch.payout_into_save(c, str(save)) is None


def test_settings_roundtrip_and_old_state():
    c = company(buses=1, dest="city.b")
    c.set_settings(follow_game=True, auto_payout=True, reserve=5, game_speed=6)
    d = c.to_dict()
    again = busco.BusCompany.from_dict(d)
    assert again.settings.follow_game and again.settings.auto_payout and again.settings.reserve == 5
    d["settings"] = {"profit_multiplier": 2.0, "auto_service": False}    # old state without new fields
    old = busco.BusCompany.from_dict(d)
    assert old.settings.reserve == 300_000 and not old.settings.follow_game


# ---- Drivers, training, tourism, map ---------------------------------------

def test_bus_without_driver_does_not_run():
    c = BusCompany(catalog(), 5_000_000, seed=7)
    c.build_garage("city.a", "small")
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_route(bus.id, "city.b")
    c.advance(5 * DAY)
    assert bus.trips == 0
    c.assign_driver(hire(c).id, bus.id)
    c.advance(5 * DAY)
    assert bus.trips > 0


def test_candidates_are_stable_and_hiring_removes_them():
    c = company(buses=0)
    first = c.candidates()
    assert [x.key for x in first] == [x.key for x in c.candidates()] and len(first) == busco.CANDIDATES_PER_WEEK
    cash = c.cash
    d = c.hire(first[0].key)
    assert c.cash == cash - first[0].fee and d.name == first[0].name
    assert first[0].key not in [x.key for x in c.candidates()]
    with pytest.raises(CompanyError):
        c.hire(first[0].key)
    c.advance(8 * DAY)
    assert {x.key for x in c.candidates()}.isdisjoint({x.key for x in first})     # new week, new applicants


def test_training_takes_time_then_raises_skill():
    c = company(buses=1)
    driver = next(iter(c.drivers.values()))
    old = driver.eco
    cash = c.cash
    cost = c.train(driver.id, "eco")
    assert cost == busco.TRAINING_COST * (old + 1) and c.cash == cash - cost
    with pytest.raises(CompanyError):
        c.train(driver.id, "safety")           # a training is already running
    bus = c.buses[driver.bus_id]
    trips = bus.trips
    c.advance(busco.TRAINING_DAYS * DAY - 60)
    assert bus.trips == trips and driver.eco == old        # bus is standing, skill still old
    c.advance(DAY)
    assert driver.eco == old + 1 and driver.training is None and bus.trips > trips


def test_training_limits():
    c = company(buses=1)
    driver = next(iter(c.drivers.values()))
    driver.eco = busco.MAX_SKILL
    with pytest.raises(CompanyError):
        c.train(driver.id, "eco")
    with pytest.raises(CompanyError):
        c.train(driver.id, "gibtsnicht")
    c.cash = 10
    with pytest.raises(CompanyError):
        c.train(driver.id, "safety")


def test_skilled_driver_earns_more_than_novice():
    a, b = company(buses=1), company(buses=1)
    for d in b.drivers.values():
        d.eco = d.punctual = d.service = d.safety = 5
        d.wage_check = None
    a.advance(60 * DAY); b.advance(60 * DAY)
    profit = lambda c: sum(e["revenue"] - e["costs"] for e in c.ledger.values())
    assert profit(b) > profit(a)
    assert next(iter(b.drivers.values())).wage > next(iter(a.drivers.values())).wage


def test_fire_and_reassign_driver():
    c = company(buses=2)
    d1, d2 = sorted(c.drivers)
    b1 = c.drivers[d1].bus_id
    c.assign_driver(d2, b1)                    # d2 takes over the bus from d1
    assert c.buses[b1].driver == d2 and c.drivers[d1].bus_id is None
    c.fire(d2)
    assert c.buses[b1].driver is None and d2 not in c.drivers


def test_tourist_trip_to_sight():
    cat = catalog()
    cat.routes[("city.a", "viewpoints.deberlin")] = (150, 140)
    cat.routes[("viewpoints.deberlin", "city.a")] = (150, 140)
    c = BusCompany(cat, 5_000_000, seed=7)
    c.build_garage("city.a", "small")
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_route(bus.id, "viewpoints.deberlin")
    c.assign_driver(hire(c).id, bus.id)
    c.advance(14 * DAY)
    assert bus.trips > 10 and bus.revenue > 0
    assert cat.cities() == ["city.a", "city.b", "city.c", "city.d"] or "viewpoints.deberlin" not in cat.cities()
    assert cat.sights() == ["viewpoints.deberlin"]
    assert busco.city_name("viewpoints.deberlin") == "Aussicht: Berlin"
    # tourism needs more time per round trip (stay) than a line of the same length
    assert busco.estimate_daily_profit(MODEL_DD, 150, 140, tourist=True) != busco.estimate_daily_profit(MODEL_DD, 150, 140)


def test_bus_state_for_map_and_determinism():
    c = company(buses=1)
    bus = next(iter(c.buses.values()))
    assert c.bus_state(bus)[3] == "wartet"
    seen = set()
    for _ in range(200):
        c.advance(20)
        a, b, frac, status = c.bus_state(bus)
        assert 0.0 <= frac <= 1.0
        seen.add(status)
        if status == "unterwegs":
            assert {a, b} == {"city.a", "city.b"}
    assert {"unterwegs", "wartet"} <= seen
    x, y = company(buses=2), company(buses=2)
    x.advance(40 * DAY)
    for _ in range(40):
        y.advance(DAY)
    assert round(x.cash, 2) == round(y.cash, 2) and x.xp_pending == y.xp_pending


def test_old_state_without_drivers_gets_drivers():
    c = company(buses=2)
    data = json.loads(json.dumps(c.to_dict()))
    for key in ("drivers", "next_driver_id", "hired_keys"):
        data.pop(key)
    for b in data["buses"]:
        for key in ("driver", "trip_from", "trip_to", "trip_start", "trip_end"):
            b.pop(key, None)
    old = BusCompany.from_dict(data)
    assert len(old.drivers) == 2 and all(b.driver in old.drivers for b in old.buses.values())
    old.advance(3 * DAY)
    assert any(b.trips for b in old.buses.values())


def test_catalog_merge_adds_sights():
    base = catalog()
    other = BusCatalog({("city.a", "viewpoints.x"): (100, 90), ("viewpoints.x", "city.a"): (100, 90)}, ["neu_modell"])
    assert base.merge(other) == 2 and "neu_modell" in base.models and base.sights() == ["viewpoints.x"]
    assert base.merge(other) == 0


# ---- Own routes and contracts ---------------------------------------------------

def with_contracts():
    c = company(buses=0)
    c.catalog.contracts = [
        {"stops": ["city.a", "city.c", "city.b"], "legs": [[120, 110], [180, 170]], "dep": 8 * 60},
        {"stops": ["city.a", "city.d"], "legs": [[1100, 1000]], "dep": 6 * 60},          # too long (> 11 h)
        {"stops": ["city.b", "city.c"], "legs": [[180, 170]], "dep": 9 * 60},            # no garage in b
    ]
    return c


def test_estimate_leg_from_coordinates():
    cat = BusCatalog({("city.a", "city.b"): (300, 280)}, [])
    km, minutes = cat.estimate_leg("city.berlin", "city.dresden")
    assert 180 < km < 260 and minutes > 100
    assert cat.estimate_leg("city.a", "city.b") == (300, 280)
    with pytest.raises(CompanyError):
        cat.estimate_leg("city.a", "city.unbekannt")


def test_custom_route_visits_all_stops_back_and_forth():
    c = company(buses=0)
    route = c.create_route("Dreierlinie", ["city.a", "city.c", "city.b"], "line")
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    c.assign_custom_route(bus.id, route.id)
    seen = []
    last = 0
    for _ in range(3 * 24 * 6):
        c.advance(10)
        if bus.trips != last:
            seen.append((bus.trip_from, bus.trip_to))
            last = bus.trips
    assert seen[:6] == [("city.a", "city.c"), ("city.c", "city.b"), ("city.b", "city.c"),
                        ("city.c", "city.a"), ("city.a", "city.c"), ("city.c", "city.b")], seen[:8]
    assert c.line_label(bus) == "Dreierlinie" and c.bus_stops(bus) == ["city.a", "city.c", "city.b"]


def test_custom_route_with_new_legs_and_sights():
    c = company(buses=0)
    c.catalog.routes[("city.a", "viewpoints.deberlin")] = (150, 140)
    route = c.create_route("Ausflug Berlin", ["city.a", "viewpoints.deberlin", "city.c"], "excursion",
                           legs=[(150, 140), (90, 100)])
    assert c.catalog.routes[("city.c", "viewpoints.deberlin")] == (90, 100)       # return direction added
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    c.assign_custom_route(bus.id, route.id)
    c.advance(10 * DAY)
    assert bus.trips > 8 and bus.revenue > 0


def test_custom_route_validation():
    c = company(buses=0)
    with pytest.raises(CompanyError):
        c.create_route("", ["city.a", "city.b"])
    with pytest.raises(CompanyError):
        c.create_route("x", ["city.a"])
    with pytest.raises(CompanyError):
        c.create_route("x", ["city.a", "city.a"])
    with pytest.raises(CompanyError):
        c.create_route("x", ["viewpoints.deberlin", "city.a"])
    with pytest.raises(CompanyError):
        c.create_route("x", ["city.a", "city.b"], "quatsch")
    with pytest.raises(CompanyError):
        c.create_route("x", ["city.a", "city.b"], legs=[(0, 5)])
    with pytest.raises(CompanyError):
        c.create_route("x", ["city.a"] + ["city.b", "city.c"] * 4)
    r = c.create_route("Eigene", ["city.a", "city.b"])
    with pytest.raises(CompanyError):
        c.create_route("eigene", ["city.a", "city.c"])
    c.build_garage("city.b", "small")
    other = c.buy_bus("city.b", MODEL_A)
    with pytest.raises(CompanyError):
        c.assign_custom_route(other.id, r.id)                    # route starts in a, bus belongs to b
    bus = c.buy_bus("city.a", MODEL_A)
    c.assign_custom_route(bus.id, r.id)
    with pytest.raises(CompanyError):
        c.delete_route(r.id)                                      # still in use
    c.assign_route(bus.id, "city.c")
    c.delete_route(r.id)
    assert r.id not in c.routes


def test_contract_offers_filter_by_garage_and_length():
    c = with_contracts()
    offers = c.contract_offers()
    assert [o.stops for o in offers] == [["city.a", "city.c", "city.b"]]
    o = offers[0]
    assert o.total_km == 300 and o.pay_per_run == round(300 * busco.CONTRACT_RATE_PER_KM)
    assert o.period == 1 and o.runs == busco.CONTRACT_DAYS and o.dep == 480
    assert [x.key for x in offers] == [x.key for x in c.contract_offers()]            # stable


def test_contract_runs_and_pays_with_bonus():
    c = with_contracts()
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    offer = c.contract_offers()[0]
    cash = c.cash
    contract = c.accept_contract(offer.key, bus.id)
    assert bus.contract_id == contract.id and c.contract_offers() == []              # offer gone
    c.advance(busco.CONTRACT_DAYS * DAY + 3 * DAY)
    assert contract.status == "completed" and contract.done == offer.runs and contract.missed == 0
    assert bus.contract_id is None
    pay = offer.pay_per_run * offer.runs
    assert c.cash > cash + 0.5 * pay and contract.earned > 0
    assert any("abgeschlossen" in t for _, t in c.log)


def test_contract_bus_returns_to_old_route_afterwards():
    c = with_contracts()
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    c.assign_route(bus.id, "city.b")
    c.accept_contract(c.contract_offers()[0].key, bus.id)
    trips_before = bus.trips
    c.advance(busco.CONTRACT_DAYS * DAY + 5 * DAY)
    assert bus.contract_id is None and bus.trips > trips_before + busco.CONTRACT_DAYS


def test_contract_rules():
    c = with_contracts()
    key = c.contract_offers()[0].key
    c.build_garage("city.b", "small")
    far = c.buy_bus("city.b", MODEL_A)
    c.assign_driver(hire(c).id, far.id)
    with pytest.raises(CompanyError):
        c.accept_contract(key, far.id)                           # wrong garage
    nodriver = c.buy_bus("city.a", MODEL_A)
    with pytest.raises(CompanyError):
        c.accept_contract(key, nodriver.id)                      # no driver
    with pytest.raises(CompanyError):
        c.accept_contract("0:99", nodriver.id)                   # unknown offer
    c.assign_driver(hire(c).id, nodriver.id)
    c.accept_contract(key, nodriver.id)
    with pytest.raises(CompanyError):
        c.assign_route(nodriver.id, "city.b")                    # runs a contract


def test_contract_missed_when_driver_in_training_and_no_bonus():
    c = with_contracts()
    bus = c.buy_bus("city.a", MODEL_DD)
    driver = hire(c)
    c.assign_driver(driver.id, bus.id)
    offer = c.contract_offers()[0]
    contract = c.accept_contract(offer.key, bus.id)
    c.advance(2 * DAY)
    c.train(driver.id, "eco")                                    # 2 days of training -> misses trips
    c.advance(busco.CONTRACT_DAYS * DAY + 3 * DAY)
    assert contract.missed >= 1 and contract.done + contract.missed == offer.runs
    assert contract.status == "completed"
    assert not any("Bonus" in t for _, t in c.log if "Vertrag" in t and "abgeschlossen" in t)


def test_contract_without_driver_counts_missed():
    c = with_contracts()
    bus = c.buy_bus("city.a", MODEL_DD)
    driver = hire(c)
    c.assign_driver(driver.id, bus.id)
    contract = c.accept_contract(c.contract_offers()[0].key, bus.id)
    c.fire(driver.id)
    rep0 = c.reputation
    c.advance(5 * DAY)
    assert contract.missed >= 3 and contract.done == 0 and c.reputation < rep0


def test_cancel_contract_costs_fee_and_frees_bus():
    c = with_contracts()
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    offer = c.contract_offers()[0]
    contract = c.accept_contract(offer.key, bus.id)
    cash = c.cash
    fee = c.cancel_contract(contract.id)
    assert fee == round(busco.CONTRACT_CANCEL_FEE * offer.runs * offer.pay_per_run)
    assert c.cash == cash - fee and bus.contract_id is None and contract.status == "cancelled"
    with pytest.raises(CompanyError):
        c.cancel_contract(contract.id)


def test_contract_position_on_map_and_chunk_independence():
    def build():
        c = with_contracts()
        bus = c.buy_bus("city.a", MODEL_DD)
        c.assign_driver(hire(c).id, bus.id)
        c.accept_contract(c.contract_offers()[0].key, bus.id)
        return c, bus
    c, bus = build()
    states = set()
    for _ in range(3 * 24 * 4):
        c.advance(15)
        a, b, frac, status = c.bus_state(bus)
        states.add(status)
        if status == "unterwegs":
            assert 0 <= frac <= 1 and {a, b} <= {"city.a", "city.c", "city.b"}
    assert {"unterwegs", "wartet"} <= states
    x, _ = build(); y, _ = build()
    x.advance(10 * DAY)
    for _ in range(10):
        y.advance(DAY)
    assert round(x.cash, 2) == round(y.cash, 2)


def test_routes_and_contracts_roundtrip():
    c = with_contracts()
    route = c.create_route("Dreier", ["city.a", "city.c", "city.b"])
    bus = c.buy_bus("city.a", MODEL_DD)
    c.assign_driver(hire(c).id, bus.id)
    c.assign_custom_route(bus.id, route.id)
    bus2 = c.buy_bus("city.a", MODEL_A)
    c.assign_driver(hire(c).id, bus2.id)
    c.accept_contract(c.contract_offers()[0].key, bus2.id)
    c.advance(5 * DAY)
    again = BusCompany.from_dict(json.loads(json.dumps(c.to_dict())))
    assert again.routes.keys() == c.routes.keys() and again.contracts.keys() == c.contracts.keys()
    assert again.accepted_offers == c.accepted_offers and again.catalog.contracts == c.catalog.contracts
    c.advance(5 * DAY); again.advance(5 * DAY)
    assert round(c.cash, 2) == round(again.cash, 2)


def test_catalog_from_doc_builds_contract_pool():
    doc = sii.SiiDocument.from_bytes(make_save_text().encode())
    cat = BusCatalog.from_doc(doc)
    assert cat.contracts and all(x["stops"][0].startswith("city.") for x in cat.contracts)
    assert all(len(x["stops"]) == len(x["legs"]) + 1 for x in cat.contracts)


def test_trip_xp_is_small_and_capped():
    assert busco.trip_xp(100) == 10 and busco.trip_xp(300) == 20
    assert busco.trip_xp(5000) == busco.XP_PER_TRIP_MAX == 20
    assert busco.trip_xp(5000, 200) == 200 and busco.trip_xp(100, 0) == 0
    c = company(buses=1, dest="city.b")
    c.set_settings(xp_per_trip=200)
    c.advance(10 * DAY)
    trips = sum(b.trips for b in c.buses.values())
    assert 0 < c.xp_total <= 200 * trips
    with pytest.raises(CompanyError):
        c.set_settings(xp_per_trip=5000)


def test_finance_categories_add_up():
    c = company(buses=1, dest="city.b")
    c.advance(5 * DAY)
    inc = sum(c.fin_total.get(k, 0) for k in busco.INCOME_CATS)
    exp = sum(c.fin_total.get(k, 0) for k in busco.EXPENSE_CATS)
    assert inc > 0 and exp > 0
    run_cats = ["Treibstoff", "Fahrerlöhne", "Wartung & Maut", "Werkstatt & Pannen", "Versicherung", "Garagenunterhalt"]
    assert abs(sum(c.fin_total.get(k, 0) for k in run_cats) - c.totals["costs"]) < 1
    assert abs(inc - c.totals["revenue"]) < 1
    assert abs(sum(c.finance_period(0, 10).values()) - sum(c.fin_total.values())) < 0.01
    again = busco.BusCompany.from_dict(c.to_dict())
    assert again.fin_total == c.fin_total and again.fin == c.fin


def test_tuning_changes_rates_and_reprices_running_contracts():
    c = company(buses=1, dest="city.b")
    base_fuel = busco.FUEL_PRICE
    c.set_tuning({"rate_per_km": 26.0, "fuel_price": 3.1, "garage_price_pct": 200})
    assert busco.FUEL_PRICE == 3.1 and busco.CONTRACT_RATE_PER_KM == pytest.approx(52.0 * busco.SIM_INCOME_FACTOR)
    assert busco.GARAGE_SIZES["small"]["price"] == 500_000
    again = busco.BusCompany.from_dict(c.to_dict())
    assert again.settings.tuning == {"rate_per_km": 26.0, "fuel_price": 3.1, "garage_price_pct": 200.0}
    with pytest.raises(CompanyError):
        c.set_tuning({"rate_per_km": 0})
    c.set_tuning({})
    assert busco.FUEL_PRICE == base_fuel and busco.CONTRACT_RATE_PER_KM == pytest.approx(26.0 * busco.SIM_INCOME_FACTOR)
    assert c.settings.tuning == {}


def test_trip_profit_estimate_is_per_trip():
    one = busco.estimate_trip_profit("volvo_9700_23_143d6_500", 300, 280)
    day = busco.estimate_daily_profit("volvo_9700_23_143d6_500", 300, 280)
    assert one > 0 and day > one


def test_respect_hours_limits_daily_driving_and_income_factor():
    free, tight = company(buses=2), company(buses=2)
    free.set_settings(respect_hours=False)
    free.advance(10 * DAY)
    tight.advance(10 * DAY)
    assert sum(b.trips for b in tight.buses.values()) < sum(b.trips for b in free.buses.values())
    full = company(buses=1)
    low = company(buses=1)
    full.set_tuning({"sim_income_pct": 100})        # the values apply module-wide: set them directly before each run
    full.advance(5 * DAY)
    low.set_tuning({"sim_income_pct": 25})
    low.advance(5 * DAY)
    rev = lambda c: sum(e["revenue"] for e in c.ledger.values())      # noqa: E731
    assert rev(low) == pytest.approx(rev(full) * 0.25, rel=1e-9)
