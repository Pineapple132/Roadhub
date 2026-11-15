import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from roadhub import buslines as bl  # noqa: E402
from roadhub import editor, sii  # noqa: E402
from tests.fixtures import make_save_text  # noqa: E402


def make_doc():
    return sii.SiiDocument.from_bytes(make_save_text().encode("utf-8"))


def _spec(doc, **over):
    legs = {("city.zurich", "city.bern"): bl.Leg(116, 100, 80, 0)}
    base = dict(
        stop_unit="bus_stop.city.zurich", slot=1, line_type="regular",
        targets=["city.bern", "city.basel"],
        legs=[bl.Leg(116, 100, 80), bl.Leg(90, 80, 65)],
        bus_name="man_lions_24_139h6_520", departure=480, hours_valid=48,
    )
    base.update(over)
    return bl.LineSpec(**base)


def test_array_replace_keeps_position_and_changes_count():
    doc = make_doc()
    unit = doc.by_name["_nameless.line.0001"]
    doc.replace_array(unit, "saved_targets", ['"city.bern"'])
    unit = doc.by_name["_nameless.line.0001"]
    assert doc.get(unit, "saved_targets") == "1"
    assert doc.get_array(unit, "saved_targets") == ['"city.bern"']
    keys = [k for _, k, _ in doc.attrs(unit)]
    assert keys.index("saved_targets") < keys.index("targets_distances")  # same place
    # other units untouched
    assert doc.get(doc.first("bank"), "money_account") == "1234567"


def test_array_replace_inserts_missing_array():
    doc = make_doc()
    unit = doc.first("bank")
    doc.replace_array(unit, "loans", ["a", "b"])
    unit = doc.first("bank")
    assert doc.get(unit, "loans") == "2" and doc.get_array(unit, "loans") == ["a", "b"]


def test_list_line_offers_and_empty_detection():
    offers = bl.list_line_offers(make_doc())
    assert len(offers) == 4
    full = [o for o in offers if not o.is_empty]
    assert {o.start_name for o in full} == {"city.zurich", "city.bern"}
    z = [o for o in full if o.start_name == "city.zurich"][0]
    assert z.targets == ["city.bern", "city.basel"] and z.total_km == 206 and z.total_minutes == 180
    assert z.bus_name == "man_lions_24_139h6_520" and z.departure == 370
    assert len([o for o in offers if o.is_empty]) == 2


def test_known_legs_and_estimate():
    offers = bl.list_line_offers(make_doc())
    legs = bl.known_legs(offers)
    assert legs[("city.zurich", "city.bern")].km == 116
    assert legs[("city.bern", "city.basel")].km == 90          # second leg: from destination 0 to destination 1
    assert ("city.bern", "city.zurich") in legs
    est = bl.estimate_leg(100, legs)
    assert est.km == 100 and est.minutes > 0 and 0 < est.base_minutes <= est.minutes


def test_targets_models_helpers():
    doc = make_doc()
    assert "city.zurich" in bl.list_stop_targets(doc)
    assert "viewpoints.chfurka" in bl.list_stop_targets(doc)
    assert bl.list_bus_models(bl.list_line_offers(doc)) == [
        "man_lions_24_139h6_520", "volvo_9700_23_143d6_460_2"]
    assert bl.pretty_stop("city.a_coruna") == "A Coruna"


def test_apply_line_fills_empty_slot_completely():
    doc = make_doc()
    exp = bl.apply_line(doc, _spec(doc))
    assert exp == 50000 + 48 * 60
    o = [x for x in bl.list_line_offers(doc) if x.stop_unit == "bus_stop.city.zurich" and x.slot == 1][0]
    assert not o.is_empty and o.line_type == "regular" and o.source == "bus_stop.city.zurich"
    assert o.targets == ["city.bern", "city.basel"]
    assert [l.km for l in o.legs] == [116, 90] and [l.base_minutes for l in o.legs] == [80, 65]
    assert o.bus_name == "man_lions_24_139h6_520" and o.departure == 480 and o.expiration == str(exp)


def test_apply_line_shrinks_existing_line():
    doc = make_doc()
    spec = _spec(doc, slot=0, targets=["city.basel"], legs=[bl.Leg(70, 70, 55)])
    bl.apply_line(doc, spec)
    o = [x for x in bl.list_line_offers(doc) if x.stop_unit == "bus_stop.city.zurich" and x.slot == 0][0]
    assert o.targets == ["city.basel"] and len(o.legs) == 1 and o.total_km == 70


def test_apply_line_updates_event_and_queue():
    doc = make_doc()
    exp = bl.apply_line(doc, _spec(doc))
    ev = [e for e in doc.by_type["economy_event"]
          if editor.strip_quotes(doc.get(e, "unit_link")) == "bus_stop.city.zurich"
          and doc.get(e, "param") == "1"][0]
    assert doc.get(ev, "time") == str(exp)
    queue = doc.first("economy_event_queue")
    names = [v for _, v in editor._indexed_values(doc, queue, "data")]
    times = [int(doc.get(doc.by_name[n], "time")) for n in names]
    assert times == sorted(times) and len(set(names)) == len(names) == 12


def test_apply_line_changes_only_expected_lines():
    import collections
    doc = make_doc()
    before = collections.Counter(doc.to_bytes().decode().split("\r\n"))
    bl.apply_line(doc, _spec(doc))
    after = collections.Counter(doc.to_bytes().decode().split("\r\n"))
    changed = list((before - after).elements()) + list((after - before).elements())
    allowed = (" type:", " source:", " saved_targets", " targets_", " departure_time_of_day:",
               " bus_name:", " expiration_time:", " time:", " data[")
    unexpected = [ln for ln in changed if not ln.startswith(allowed)]
    assert unexpected == []


@pytest.mark.parametrize(
    "over",
    [
        {"stop_unit": "bus_stop.city.ghost"},
        {"slot": 7},
        {"line_type": "express"},
        {"targets": [], "legs": []},
        {"targets": ["city.bern"] * 2, "legs": [bl.Leg(1, 1, 1)] * 2},     # same stop twice in a row
        {"targets": ["city.nowhere"], "legs": [bl.Leg(10, 10, 8)]},
        {"targets": ["city.zurich"], "legs": [bl.Leg(10, 10, 8)]},         # start == destination
        {"legs": [bl.Leg(0, 10, 8), bl.Leg(90, 80, 65)]},
        {"legs": [bl.Leg(116, 100, 80)]},                                  # count does not match
        {"bus_name": ""},
        {"departure": 1440},
        {"hours_valid": 0},
    ],
)
def test_apply_line_validation_leaves_doc_untouched(over):
    doc = make_doc()
    before = doc.to_bytes()
    with pytest.raises(sii.SiiError):
        bl.apply_line(doc, _spec(doc, **over))
    assert doc.to_bytes() == before


def test_six_targets_rejected():
    doc = make_doc()
    targets = ["city.bern", "city.basel"] * 3
    legs = [bl.Leg(10, 10, 8)] * 6
    with pytest.raises(sii.SiiError):
        bl.apply_line(doc, _spec(doc, targets=targets, legs=legs))


REAL = os.environ.get("ETS2_REAL_SAVE")


@pytest.mark.skipif(not REAL or not os.path.exists(REAL or ""), reason="kein echter Save angegeben")
def test_real_save_line_edit():
    doc = sii.SiiDocument.from_bytes(sii.decrypt_bytes(open(REAL, "rb").read()))
    offers = bl.list_line_offers(doc)
    legs = bl.known_legs(offers)
    full = next(o for o in offers if not o.is_empty and o.line_type == "regular" and len(o.targets) >= 3)
    empty = next(o for o in offers if o.is_empty)
    models = bl.list_bus_models(offers)
    spec = bl.LineSpec(empty.stop_unit, empty.slot, "regular", full.targets[:3], full.legs[:3],
                       models[0], 600, 24)
    bl.apply_line(doc, spec)
    again = [o for o in bl.list_line_offers(doc) if (o.stop_unit, o.slot) == (empty.stop_unit, empty.slot)][0]
    assert again.targets == full.targets[:3] and again.legs == full.legs[:3] and not again.is_empty
    queue = doc.first("economy_event_queue")
    names = [v for _, v in editor._indexed_values(doc, queue, "data")]
    times = [int(doc.get(doc.by_name[n], "time")) for n in names]
    assert times == sorted(times) and len(set(names)) == len(names)
    assert bl.estimate_leg(150, legs).minutes > 0
