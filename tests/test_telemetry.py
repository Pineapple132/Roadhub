import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from roadhub import busco, gamewatch, telemetry as T  # noqa: E402
from roadhub import editor, sii  # noqa: E402
from roadhub.busco import DAY  # noqa: E402
from tests.fixtures import make_save_text  # noqa: E402
from tests.test_busco import company  # noqa: E402


def snap(income=0, dest="", left=0.0, connected=True, paused=False, speed=70.0):
    return T.Snapshot(connected=connected, paused=paused, speed_kmh=speed, income=income,
                      source="A" if income else "", dest=dest, cargo="Kisten", left_m=left)


def test_parse_funbit_and_missing_fields():
    data = {"game": {"connected": True, "paused": False, "time": "x"}, "truck": {"speed": -61.5},
            "trailer": {"name": "Maschinen"},
            "job": {"income": 4200, "sourceCity": "Berlin", "destinationCity": "Prag"},
            "navigation": {"estimatedDistance": 281000}}
    s = T.parse_funbit(data)
    assert s.connected and s.has_job and s.income == 4200 and s.dest == "Prag"
    assert s.speed_kmh == 61.5 and s.left_m == 281000 and s.cargo == "Maschinen"
    empty = T.parse_funbit({})
    assert not empty.connected and not empty.has_job


def test_tracker_delivered_needs_two_empty_snapshots_near_goal():
    t = T.TripTracker()
    assert [e.kind for e in t.update(snap(5000, "B", 300_000))] == ["started"]
    t.update(snap(5000, "B", 150_000))
    assert 0.45 < t.progress < 0.55
    t.update(snap(5000, "B", 900))
    assert t.update(snap()) == []                       # an empty snapshot (menu) is not enough
    ev = t.update(snap())
    assert [e.kind for e in ev] == ["delivered"] and ev[0].income == 5000
    assert abs(ev[0].km - 300) < 1 and not t.active


def test_tracker_cancel_far_from_goal_pause_and_disconnect():
    t = T.TripTracker()
    t.update(snap(5000, "B", 300_000))
    t.update(snap(5000, "B", 250_000))
    assert t.update(snap(connected=False)) == []        # connection lost: infer nothing
    assert t.update(snap(paused=True)) == []
    t.update(snap())
    assert [e.kind for e in t.update(snap())] == ["cancelled"]


def test_tracker_new_job_replaces_old_one():
    t = T.TripTracker()
    t.update(snap(5000, "B", 300_000))
    kinds = [e.kind for e in t.update(snap(7000, "C", 100_000))]
    assert kinds == ["cancelled", "started"]


def test_demo_drive_ends_as_delivered():
    d = T.DemoDrive(seconds=1.0)
    t = T.TripTracker()
    kinds = []
    import time
    end = time.time() + 8
    while time.time() < end and "delivered" not in kinds:
        kinds += [e.kind for e in t.update(d.snapshot())]
        time.sleep(0.05)
    assert kinds[0] == "started" and kinds[-1] == "delivered"


def test_complete_trip_credits_income_to_shared_account():
    c = company(buses=2, dest="city.b")
    c.begin_trip()
    c.advance(2 * DAY)
    profit_before = c.firm_delta()
    cash0 = c.cash
    rep = c.complete_trip(6000, "Hamburg", "Kopenhagen", "Kisten", 463.4)
    assert rep["income"] == 6000 and c.cash == cash0 + 6000 and c.game_earned == 6000
    assert abs(c.firm_delta() - profit_before) < 0.01          # trip income is already in the game
    assert abs(rep["profit"] - profit_before) <= 1 or rep["trips"] > 0
    assert rep["cash_after"] - rep["cash_before"] == 6000
    assert c.trip_mark is None and c.trip_log[-1] is rep


def test_roundtrip_and_old_state_migration(tmp_path):
    c = company(buses=1, dest="city.b")
    c.begin_trip()
    c.complete_trip(1000, "A", "B", "x", 5)
    c.begin_trip()
    p = tmp_path / "f.json"
    c.save(str(p))
    d = busco.BusCompany.load(str(p))
    assert d.game_earned == 1000 and d.sync_base == c.sync_base and d.cash == c.cash
    assert d.trip_log == c.trip_log and d.trip_mark == c.trip_mark and d.totals == c.totals
    import json as _j
    old = c.to_dict()
    for k in ("sync_base", "game_earned"):
        old.pop(k)
    old["cash"] = old["start_cash"] + 70_000
    e = busco.BusCompany.from_dict(old)
    assert e.firm_delta() == 70_000                              # unpaid profit is kept


def test_payout_writes_only_the_firm_part(tmp_path):
    save = tmp_path / "game.sii"
    save.write_bytes(make_save_text().encode())
    c = company(buses=1, dest="city.b")
    m0 = int(editor.read_values(sii.load(str(save)), editor.ALL_FIELDS)["money_account"])
    c.sync_to_game(m0)
    c.advance(5 * DAY)
    c.complete_trip(8000, "A", "B", "", 100)           # already in the game, must not be paid twice
    delta = c.firm_delta()
    res = gamewatch.payout_into_save(c, str(save))
    after = int(editor.read_values(sii.load(str(save)), editor.ALL_FIELDS)["money_account"])
    assert res.euros == round(delta) and after == m0 + round(delta)


def test_purchases_cut_the_game_money_and_clamp_at_zero(tmp_path):
    save = tmp_path / "game.sii"
    save.write_bytes(make_save_text().encode())
    c = company(cash=5_000_000, buses=0, dest="city.b")
    c.cash, c.sync_base = 400_000.0, 400_000.0
    c.build_garage("city.b", "small")                   # -250,000 €
    res = gamewatch.payout_into_save(c, str(save))
    after = int(editor.read_values(sii.load(str(save)), editor.ALL_FIELDS)["money_account"])
    assert res.euros < 0 and after == res.new_money >= 0


BUS_JSON = {"game": {"connected": True, "paused": True, "gameName": "ETS2", "timeScale": 3.0},
            "truck": {"make": "Volvo", "model": "9700", "speed": 46.5},
            "trailer": {"attached": False, "name": ""},
            "job": {"income": 3617, "sourceCity": "", "destinationCity": ""},
            "navigation": {"estimatedDistance": 188086}}


def test_bus_job_without_cities_is_recognised():
    s = T.parse_funbit(BUS_JSON)
    assert s.has_job and s.income == 3617 and s.vehicle == "Volvo 9700" and s.left_m == 188086
    t = T.TripTracker()
    assert [e.kind for e in t.update(s)] == ["started"]
    t.update(T.parse_funbit({**BUS_JSON, "navigation": {"estimatedDistance": 800}, "game": {"connected": True}}))
    empty = T.parse_funbit({"game": {"connected": True}, "job": {"income": 0}})
    t.update(empty)
    ev = t.update(empty)
    assert [e.kind for e in ev] == ["delivered"] and ev[0].vehicle == "Volvo 9700"
    c = company(buses=1, dest="city.b")
    rep = c.complete_trip(ev[0].income, ev[0].source, ev[0].dest, ev[0].cargo, 188, ev[0].vehicle)
    assert busco.route_label(rep["source"], rep["dest"], rep["vehicle"]) == "Bus-Linie (Volvo 9700)"
    assert busco.route_label("A", "B") == "A nach B"


def test_stale_income_after_arrival_ends_trip_once_and_blocks_restart():
    t = T.TripTracker()
    arrived = T.parse_funbit({**BUS_JSON, "game": {"connected": True, "paused": False},
                              "navigation": {"estimatedDistance": 0}})
    assert arrived.income == 3617 and not arrived.has_job
    t.update(T.parse_funbit(BUS_JSON))
    t.update(T.parse_funbit({**BUS_JSON, "navigation": {"estimatedDistance": 900}}))
    assert t.update(arrived) == []
    ev = t.update(arrived)
    assert [e.kind for e in ev] == ["delivered"] and ev[0].income == 3617
    assert t.update(arrived) == [] and t.update(arrived) == []          # no second end
    # set navigation to something else, income unchanged: no new trip
    assert t.update(T.parse_funbit(BUS_JSON)) == []
    # new job with a different income starts
    new = T.parse_funbit({**BUS_JSON, "job": {"income": 2100}})
    assert [e.kind for e in t.update(new)] == ["started"]


def test_menu_stops_far_from_goal_is_cancelled():
    t = T.TripTracker()
    t.update(T.parse_funbit(BUS_JSON))
    gone = T.parse_funbit({**BUS_JSON, "game": {"connected": True, "paused": False},
                           "navigation": {"estimatedDistance": 0}})
    t.update(gone)
    assert [e.kind for e in t.update(gone)] == ["cancelled"]


def test_eta_parsing_and_manual_end():
    assert T.parse_duration("0001-01-01T02:23:55Z") == 2 * 3600 + 23 * 60 + 55
    assert T.parse_duration("0001-01-01T00:00:00Z") == 0 and T.parse_duration("") == 0
    s = T.parse_funbit({**BUS_JSON, "navigation": {"estimatedDistance": 5000, "estimatedTime": "0001-01-01T00:30:00Z"}})
    assert s.eta_s == 1800
    t = T.TripTracker()
    assert t.force_end("delivered") is None
    t.update(s)
    assert t.eta_s == 1800
    ev = t.force_end("delivered")
    assert ev.kind == "delivered" and ev.income == 3617 and not t.active
    assert t.update(s) == []                      # old income after a manual end: no new trip
    from roadhub.overlay import fmt_eta
    assert fmt_eta(8635) == "2:23 h" and fmt_eta(-5) == "0:00 h"


def test_read_money_and_sync_company(tmp_path, monkeypatch):
    save = tmp_path / "game.sii"
    save.write_bytes(make_save_text().encode())
    money = gamewatch.read_money(str(save))
    assert money == int(editor.read_values(sii.load(str(save)), editor.ALL_FIELDS)["money_account"])
    c = company(buses=1, dest="city.b")
    c.advance(DAY)
    delta = c.firm_delta()
    entry = type("E", (), {"path": str(save)})()
    monkeypatch.setattr(gamewatch, "newest_save", lambda: entry)
    assert gamewatch.sync_company(c) == money
    assert abs(c.cash - (money + delta)) < 0.01 and abs(c.firm_delta() - delta) < 0.01   # company stays reserved
    assert c.sync_base == money


def test_real_arrival_is_stable_like_a_navigation_app():
    from datetime import datetime
    from roadhub.overlay import fmt_arrival
    t = T.TripTracker()

    def snap(eta, game, paused=False):
        return T.Snapshot(connected=True, paused=paused, income=900, left_m=50_000, eta_s=eta, game_s=game)

    base = 2_000_000_000.0
    t.update(snap(19 * 600, base), now=100.0)               # 600 s real at 19:1
    assert abs(t.real_eta_s - 600) < 0.1
    # slight fluctuation of the navigation time (±2 %) does not change the arrival
    for k in range(1, 30):
        wobble = 1.02 if k % 2 else 0.98
        t.update(snap(19 * (600 - k) * wobble, base + 19 * k), now=100.0 + k)
    assert abs(t.real_eta_s - (600 - 29)) < 0.5            # simply counts down
    # a pause shifts the arrival by the pause duration
    before = t.real_eta_s
    t.update(snap(19 * 570, base, paused=True), now=130.0)
    t.update(snap(19 * 570, base, paused=True), now=160.0)
    assert abs(t.real_eta_s - before) < 1.5
    # a large lasting deviation is tracked slowly
    for k in range(1, 200):
        t.update(snap(19 * 2000, base + 1000 + 19 * k), now=160.0 + k)
    assert 800 < t.real_eta_s < 2000
    # measurement of the real speed after >= 30 s
    t2 = T.TripTracker()
    for i in range(0, 41, 2):
        t2.update(T.Snapshot(connected=True, income=900, left_m=50_000, eta_s=6000, game_s=base + i * 10), now=100.0 + i)
    assert abs(t2.rate - 10) < 0.01
    assert fmt_arrival(2880, datetime(2026, 11, 15, 14, 0)) == "14:48 Uhr (in 48 Min)"
    assert fmt_arrival(None) == ""
    s = T.parse_funbit(BUS_JSON)
    assert s.time_scale == 3.0 and s.game_s == 0.0
    assert T.parse_game_seconds("0067-06-04T07:52:00Z") - T.parse_game_seconds("0067-06-04T05:13:00Z") == 159 * 60
