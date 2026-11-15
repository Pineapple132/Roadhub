import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from roadhub import editor, sii  # noqa: E402
from tests.fixtures import make_info_text, make_save_text  # noqa: E402


def make_doc(eol="\r\n"):
    return sii.SiiDocument.from_bytes(make_save_text(eol).encode("utf-8"))


# ---- Crypto ---------------------------------------------------------------

def test_roundtrip_encrypt_decrypt():
    plain = make_save_text().encode("utf-8")
    enc = sii.encrypt_text(plain)
    assert enc[:4] == b"ScsC"
    assert sii.decrypt_bytes(enc) == plain


def test_plaintext_passthrough():
    plain = make_save_text().encode("utf-8")
    assert sii.decrypt_bytes(plain) == plain


def test_binary_format_rejected_with_help():
    inner = b"BSII" + b"\x00" * 64
    with pytest.raises(sii.UnsupportedFormat) as exc:
        sii.decrypt_bytes(inner)
    assert "g_save_format" in str(exc.value)


def test_garbage_rejected():
    with pytest.raises(sii.SiiError):
        sii.decrypt_bytes(b"hello world, not a save")


def test_truncated_encrypted_rejected():
    with pytest.raises(sii.SiiError):
        sii.decrypt_bytes(b"ScsC" + b"\x00" * 10)


def test_wrong_size_detected():
    plain = make_save_text().encode("utf-8")
    enc = bytearray(sii.encrypt_text(plain))
    enc[52:56] = (len(plain) + 5).to_bytes(4, "little")
    with pytest.raises(sii.SiiError):
        sii.decrypt_bytes(bytes(enc))


# ---- Parser / writing ---------------------------------------------------

@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_unchanged_doc_is_byte_identical(eol):
    text = make_save_text(eol).encode("utf-8")
    doc = sii.SiiDocument.from_bytes(text)
    assert doc.to_bytes() == text


def test_utf8_preserved():
    doc = make_doc()
    assert "Zürich Hbf" in doc.to_bytes().decode("utf-8")


def test_invalid_utf8_bytes_preserved():
    text = make_save_text().encode("utf-8").replace(b"Z\xc3\xbcrich", b"Z\xfcrich")
    doc = sii.SiiDocument.from_bytes(text)
    assert doc.to_bytes() == text


def test_unclosed_unit_detected():
    broken = b"SiiNunit\r\n{\r\nbank : _nameless.1 {\r\n money_account: 5\r\n"
    with pytest.raises(sii.SiiError):
        sii.SiiDocument.from_bytes(broken)


def test_set_inserts_missing_key_and_reindexes():
    doc = make_doc()
    bank = doc.first("bank")
    doc.set(bank, "new_key", "7")
    assert doc.get(doc.first("bank"), "new_key") == "7"
    # following units must still be found correctly
    assert doc.get(doc.first("economy"), "game_time") == "50000"


def test_save_creates_backup_and_atomic_write(tmp_path):
    path = tmp_path / "game.sii"
    path.write_bytes(sii.encrypt_text(make_save_text().encode()))
    doc = sii.load(str(path))
    editor.write_profile(doc, {"money_account": 42})
    backup = sii.save(doc, str(path))
    assert backup and os.path.exists(backup)
    # backup = unchanged original (encrypted), result = readable plain text
    assert open(backup, "rb").read()[:4] == b"ScsC"
    assert open(path, "rb").read()[:4] == b"SiiN"
    assert editor.read_profile(sii.load(str(path)))["money_account"] == "42"
    assert not any(p.name.endswith(".tmp_write") for p in tmp_path.iterdir())


# ---- Profile ---------------------------------------------------------------

def test_read_profile():
    p = editor.read_profile(make_doc())
    assert p["money_account"] == "1234567"
    assert p["experience_points"] == "8000"
    assert p["mechanical"] == "3"


def test_write_profile_changes_only_requested():
    doc = make_doc()
    before = doc.to_bytes().decode().split("\r\n")
    changed = editor.write_profile(doc, {"money_account": 99_000_000, "adr": 63})
    assert set(changed) == {"money_account", "adr"}
    after = doc.to_bytes().decode().split("\r\n")
    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert diff == [
        (" money_account: 1234567", " money_account: 99000000"),
        (" adr: 1", " adr: 63"),
    ]
    assert len(before) == len(after)


def test_write_profile_no_change_when_same():
    doc = make_doc()
    assert editor.write_profile(doc, {"money_account": 1234567}) == []


@pytest.mark.parametrize(
    "values",
    [{"adr": 64}, {"long_dist": 7}, {"experience_points": -1}, {"nonsense": 1}],
)
def test_write_profile_validation_leaves_doc_untouched(values):
    doc = make_doc()
    before = doc.to_bytes()
    with pytest.raises(sii.SiiError):
        editor.write_profile(doc, {"money_account": 5, **values})
    assert doc.to_bytes() == before  # the valid field was not written either


def test_parse_int_accepts_separators_rejects_text():
    assert editor.parse_int("1.234.567", "x") == 1234567
    with pytest.raises(sii.SiiError):
        editor.parse_int("abc", "x")


def test_bus_info_readonly():
    info = editor.read_bus_info(make_doc())
    assert info["bus_stop-Einheiten im Save"] == "5"
    assert info["Eigene Busse (player.buses)"] == "1"
    assert info["Bus-Linienangebote (line_offer_data)"] == "4"
    assert info["Einträge im Bus-Auftragslog"] == "2"


# ---- Jobs -------------------------------------------------------------

def test_list_offers_and_helpers():
    doc = make_doc()
    offers = editor.list_offers(doc)
    assert len(offers) == 8
    assert not any(o.is_empty for o in offers)
    assert offers[0].source_key == "aria_food.berlin"
    assert "aria_food.hamburg" in editor.list_destinations(doc)
    templates = editor.list_templates(offers)
    assert {t.cargo for t in templates} == {"cargo.cheese", "cargo.cement"}
    routes = editor.known_routes(offers)
    assert (offers[0].source_key, offers[0].target_key) in routes


def _spec(doc, **over):
    offers = editor.list_offers(doc)
    tpl = editor.list_templates(offers)[0]
    base = dict(
        company_unit="company.volatile.aria_food.berlin",
        slot=1,
        target_key="sellplan.paris",
        template=tpl,
        distance_km=812,
        urgency=1,
        hours_valid=48,
    )
    base.update(over)
    return editor.JobSpec(**base)


def test_apply_job_sets_all_fields_consistently():
    doc = make_doc()
    spec = _spec(doc)
    exp = editor.apply_job(doc, spec)
    assert exp == 50000 + 48 * 60

    offer = [o for o in editor.list_offers(doc)
             if o.company_unit == spec.company_unit and o.slot == 1][0]
    v = offer.values
    assert v["target"] == '"sellplan.paris"'
    assert v["expiration_time"] == str(exp)
    assert v["urgency"] == "1"
    assert v["shortest_distance_km"] == "812"
    assert v["cargo"] == spec.template.cargo
    assert v["trailer_definition"] == spec.template.trailer_definition
    assert v["units_count"] == spec.template.units_count


def test_apply_job_updates_expiry_event_and_resorts_queue():
    doc = make_doc()
    spec = _spec(doc)
    exp = editor.apply_job(doc, spec)

    # event for (berlin, slot 1) carries the new time
    ev = [e for e in doc.by_type["economy_event"]
          if editor.strip_quotes(doc.get(e, "unit_link")) == spec.company_unit
          and doc.get(e, "param") == "1"][0]
    assert doc.get(ev, "time") == str(exp)

    # queue is sorted ascending by time and contains every event exactly once
    queue = doc.first("economy_event_queue")
    names = [v for _, v in editor._indexed_values(doc, queue, "data")]
    times = [int(doc.get(doc.by_name[n], "time")) for n in names]
    assert times == sorted(times)
    assert len(names) == len(set(names)) == 12
    assert doc.get(queue, "data") == "12"


@pytest.mark.parametrize(
    "over",
    [
        {"target_key": "nowhere.mars"},
        {"target_key": "aria_food.berlin"},   # same company as the start
        {"distance_km": 0},
        {"urgency": 3},
        {"hours_valid": 0},
        {"slot": 9},
        {"company_unit": "company.volatile.ghost.town"},
    ],
)
def test_apply_job_validation_leaves_doc_untouched(over):
    doc = make_doc()
    before = doc.to_bytes()
    with pytest.raises(sii.SiiError):
        editor.apply_job(doc, _spec(doc, **over))
    assert doc.to_bytes() == before


def test_apply_job_result_survives_save_and_reload(tmp_path):
    path = tmp_path / "game.sii"
    path.write_bytes(sii.encrypt_text(make_save_text().encode()))
    doc = sii.load(str(path))
    editor.apply_job(doc, _spec(doc))
    sii.save(doc, str(path))
    again = sii.load(str(path))
    offers = editor.list_offers(again)
    changed = [o for o in offers if o.target_key == "sellplan.paris"
               and o.company_unit == "company.volatile.aria_food.berlin" and o.slot == 1]
    assert len(changed) == 1


# ---- Extensions after testing with a real save ------------------------------

def test_templates_dedupe_ignores_company_truck_and_keeps_first():
    doc = make_doc()
    offers = editor.list_offers(doc)
    # same trailer/cargo, different tractor -> only one template
    for o in offers:
        if o.cargo_name == "cheese":
            o.values["company_truck"] = "some_other_truck_" + o.offer_unit
    cheese = [t for t in editor.list_templates(offers) if t.cargo == "cargo.cheese"]
    assert len(cheese) == 1
    assert cheese[0].company_truck.startswith("some_other_truck_")


def test_unquoted_and_slashed_truck_names_copied_verbatim():
    doc = make_doc()
    spec = _spec(doc)
    editor.apply_job(doc, spec)
    offer = [o for o in editor.list_offers(doc)
             if o.company_unit == spec.company_unit and o.slot == 1][0]
    assert offer.values["company_truck"] == spec.template.company_truck


def test_empty_slots_detected_and_fillable():
    doc = sii.SiiDocument.from_bytes(make_save_text(empty_first_slot=True).encode())
    offers = editor.list_offers(doc)
    empties = [o for o in offers if o.is_empty]
    assert len(empties) == 1
    e = empties[0]
    assert (e.company_unit, e.slot) == ("company.volatile.aria_food.berlin", 0)
    assert e.target_key == ""
    # empty slots yield no templates and no routes
    assert all(t.cargo != "null" for t in editor.list_templates(offers))

    tpl = editor.list_templates(offers)[0]
    spec = editor.JobSpec(e.company_unit, 0, "sellplan.paris", tpl, 600, 0, 24)
    exp = editor.apply_job(doc, spec)
    filled = [o for o in editor.list_offers(doc) if o.offer_unit == e.offer_unit][0]
    assert not filled.is_empty and filled.values["expiration_time"] == str(exp)
    # event of the empty slot was adjusted and the queue stays sorted
    queue = doc.first("economy_event_queue")
    names = [v for _, v in editor._indexed_values(doc, queue, "data")]
    times = [int(doc.get(doc.by_name[n], "time")) for n in names]
    assert times == sorted(times)


def _write_pair(tmp_path, money=1234567, xp_total=8250):
    game = tmp_path / "game.sii"
    game.write_bytes(sii.encrypt_text(make_save_text().encode()))
    info = tmp_path / "info.sii"
    info.write_bytes(sii.encrypt_text(make_info_text(money, xp_total).encode()))
    return game, info


def test_sync_info_updates_money_and_total_xp(tmp_path):
    game, info = _write_pair(tmp_path)
    doc = sii.load(str(game))
    editor.write_profile(doc, {"money_account": 777, "experience_points": 1000})
    assert editor.sync_info_file(str(game), doc) == str(info)
    again = sii.load(str(info))
    unit = again.first("save_container")
    assert again.get(unit, "info_money_account") == "777"
    assert again.get(unit, "info_players_experience") == "1250"   # 1000 + 250 bus XP
    assert again.get(unit, "info_explored_ratio") == "&3ccf5f50"  # rest untouched
    assert any(p.name.startswith("info.sii.backup_") for p in tmp_path.iterdir())


def test_sync_info_noop_when_unchanged_or_missing(tmp_path):
    game, info = _write_pair(tmp_path)           # values match the save
    doc = sii.load(str(game))
    assert editor.sync_info_file(str(game), doc) is None
    info.unlink()
    assert editor.sync_info_file(str(game), doc) is None


# ---- Optional test with a real save (only if present) ------------------------

REAL = os.environ.get("ETS2_REAL_SAVE")


@pytest.mark.skipif(not REAL or not os.path.exists(REAL or ""), reason="kein echter Save angegeben")
def test_real_save_roundtrip_and_job_edit():
    raw = open(REAL, "rb").read()
    plain = sii.decrypt_bytes(raw)
    doc = sii.SiiDocument.from_bytes(plain)
    assert doc.to_bytes() == plain
    offers = editor.list_offers(doc)
    target = next(o for o in offers if not o.is_empty)
    tpl = editor.list_templates(offers)[0]
    dest = next(d for d in editor.list_destinations(doc) if d != target.source_key)
    before = list(doc.lines)
    editor.apply_job(doc, editor.JobSpec(target.company_unit, target.slot, dest, tpl, 500, 0, 48))
    assert len(doc.lines) == len(before)
    queue = doc.first("economy_event_queue")
    names = [v for _, v in editor._indexed_values(doc, queue, "data")]
    times = [int(doc.get(doc.by_name[n], "time")) for n in names]
    assert times == sorted(times) and len(set(names)) == len(names)


# ---- Bus tab: editable bus values -------------------------------------

def test_read_bus_fields():
    v = editor.read_bus_fields(make_doc())
    assert v["bus_experience_points"] == "250"
    assert v["low_acceleration"] == "3" and v["long_duty"] == "1"


def test_write_bus_fields_only_touches_requested_lines():
    doc = make_doc()
    before = doc.to_bytes().decode().split("\r\n")
    changed = editor.write_profile(doc, {"bus_experience_points": 5000, "tight_schedule": 4})
    assert set(changed) == {"bus_experience_points", "tight_schedule"}
    after = doc.to_bytes().decode().split("\r\n")
    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert sorted(diff) == sorted([
        (" bus_experience_points: 250", " bus_experience_points: 5000"),
        (" tight_schedule: 0", " tight_schedule: 4"),
    ])
    assert len(before) == len(after)


@pytest.mark.parametrize("values", [{"bus_experience_points": -1}, {"ecodriving": 7},
                                    {"bus_experience_points": 100_000_000}])
def test_bus_validation(values):
    doc = make_doc()
    before = doc.to_bytes()
    with pytest.raises(sii.SiiError):
        editor.write_profile(doc, values)
    assert doc.to_bytes() == before


def test_sync_info_uses_new_bus_xp(tmp_path):
    game, info = _write_pair(tmp_path)
    doc = sii.load(str(game))
    editor.write_profile(doc, {"bus_experience_points": 4000})
    editor.sync_info_file(str(game), doc)
    again = sii.load(str(info))
    assert again.get(again.first("save_container"), "info_players_experience") == str(8000 + 4000)
