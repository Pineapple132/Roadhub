"""Erzeugt einen kleinen, synthetischen Save im Aufbau eines echten game.sii.

ACHTUNG: Das ist kein echter Spielstand, sondern ein nach dem bekannten Format
nachgebauter Testfall (Struktur laut TS-SE-Tool-Quellcode).
"""

from __future__ import annotations


def make_save_text(eol: str = "\r\n", empty_first_slot: bool = False) -> str:
    companies = [
        ("aria_food", "berlin"),
        ("aria_food", "hamburg"),
        ("fcp_lkw", "munich"),
        ("sellplan", "paris"),
    ]
    cargo_sets = [
        ("cargo.cheese", "volvo_fh16_4x2_420", "trailer.scs_fridge", "trailer_def.scs.refrigerated.20", 20),
        ("cargo.cement", '"heavy/mercedes_6x4"', "trailer.scs_silo", "trailer_def.scs.silo.25", 25),
    ]
    lines: list[str] = ["SiiNunit", "{"]
    lines += [
        "bank : _nameless.1.1 {",
        " money_account: 1234567",
        " loan_limit: 1000000",
        "}",
    ]

    # Jobs und Events
    offer_idx = 0
    job_units: list[str] = []
    company_units: list[str] = []
    events: list[tuple[str, int, str, int]] = []  # name, time, link, param
    ev_idx = 0
    for ci, (comp, city) in enumerate(companies):
        cname = f"company.volatile.{comp}.{city}"
        offers = []
        for slot in range(2):
            oname = f"_nameless.job.{offer_idx:04x}"
            offer_idx += 1
            offers.append(oname)
            tgt = companies[(ci + 1 + slot) % len(companies)]
            cs = cargo_sets[(ci + slot) % len(cargo_sets)]
            expiry = 1000 + 100 * offer_idx
            if empty_first_slot and ci == 0 and slot == 0:
                job_units += [
                    f"job_offer_data : {oname} {{",
                    ' target: ""',
                    " expiration_time: nil",
                    " urgency: nil",
                    " shortest_distance_km: 0",
                    " ferry_time: 0",
                    " ferry_price: 0",
                    " cargo: null",
                    " company_truck: daf_4x2_b",
                    " trailer_variant: null",
                    " trailer_definition: trailer_def.scs.flatbed.single_3.flatbed_w",
                    " units_count: 0",
                    " fill_ratio: 1",
                    " trailer_place: 0",
                    "}",
                ]
                events.append((f"_nameless.ev.{ev_idx:04x}", 60000, cname, slot))
                ev_idx += 1
                continue
            job_units += [
                f"job_offer_data : {oname} {{",
                f' target: "{tgt[0]}.{tgt[1]}"',
                f" expiration_time: {expiry}",
                " urgency: 0",
                f" shortest_distance_km: {300 + 25 * offer_idx}",
                " ferry_time: 0",
                " ferry_price: 0",
                f" cargo: {cs[0]}",
                f" company_truck: {cs[1]}",
                f" trailer_variant: {cs[2]}",
                f" trailer_definition: {cs[3]}",
                f" units_count: {cs[4]}",
                " fill_ratio: 1",
                " trailer_place: 0",
                "}",
            ]
            events.append((f"_nameless.ev.{ev_idx:04x}", expiry, cname, slot))
            ev_idx += 1
        company_units += [
            f"company : {cname} {{",
            " permanent_data: company.permanent." + comp,
            f" job_offer: {len(offers)}",
        ]
        company_units += [f" job_offer[{i}]: {o}" for i, o in enumerate(offers)]
        company_units += [" discovered: true", "}"]

    # --- Bus-Haltestellen, Linienangebote und deren Ablauf-Events -----------------
    bus_units: list[str] = []
    bus_offer_names = {
        ("zurich", 0): "_nameless.line.0001",
        ("zurich", 1): "_nameless.line.0002",
        ("bern", 0): "_nameless.line.0003",
        ("bern", 1): "_nameless.line.0004",
    }
    for stop, count in (("zurich", 2), ("bern", 2), ("basel", 0)):
        bus_units += [f"bus_stop : bus_stop.city.{stop} {{", " discovered: false", f" lines_offer: {count}"]
        bus_units += [f" lines_offer[{i}]: {bus_offer_names[(stop, i)]}" for i in range(count)]
        bus_units += ["}"]
    bus_units += ["bus_stop : bus_stop.viewpoints.chfurka {", " discovered: false", " lines_offer: 0", "}"]

    def regular(name, src, targets, dists, times, base, dep, bus, exp):
        out = [
            f"line_offer_data : {name} {{", " type: regular", f" source: bus_stop.city.{src}",
            f" saved_targets: {len(targets)}",
        ]
        out += [f' saved_targets[{i}]: "{t}"' for i, t in enumerate(targets)]
        for key, vals in (("targets_distances", dists), ("targets_times", times),
                          ("targets_ferry_times", [0] * len(targets)), ("targets_base_times", base)):
            out += [f" {key}: {len(vals)}"] + [f" {key}[{i}]: {v}" for i, v in enumerate(vals)]
        out += [f" departure_time_of_day: {dep}", f" bus_name: {bus}", f" expiration_time: {exp}",
                " tight_schedule_rank: 0", " satisfaction_decrease_rank: 0", " low_acceleration_rank: 0", "}"]
        return out

    def empty_line(name):
        return [
            f"line_offer_data : {name} {{", " type: tourist", " source: null", " saved_targets: 0",
            " targets_distances: 0", " targets_times: 0", " targets_ferry_times: 0",
            " targets_base_times: 0", " departure_time_of_day: 0", ' bus_name: ""',
            " expiration_time: 0", " tight_schedule_rank: 0", " satisfaction_decrease_rank: 0",
            " low_acceleration_rank: 0", "}",
        ]

    bus_units += regular("_nameless.line.0001", "zurich", ["city.bern", "city.basel"], [116, 90], [100, 80], [80, 65], 370, "man_lions_24_139h6_520", 51500)
    bus_units += empty_line("_nameless.line.0002")
    bus_units += regular("_nameless.line.0003", "bern", ["city.zurich"], [116], [100], [80], 430, "volvo_9700_23_143d6_460_2", 51800)
    bus_units += empty_line("_nameless.line.0004")
    events.append(("_nameless.ev.b001", 51500, "bus_stop.city.zurich", 0))
    events.append(("_nameless.ev.b002", 53000, "bus_stop.city.zurich", 1))
    events.append(("_nameless.ev.b003", 51800, "bus_stop.city.bern", 0))
    events.append(("_nameless.ev.b004", 54000, "bus_stop.city.bern", 1))

    queue_order = sorted(events, key=lambda e: e[1])
    lines += [
        "economy : _nameless.eco.0001 {",
        " bank: _nameless.1.1",
        " game_time: 50000",
        " total_distance: 12345",
        " experience_points: 8000",
        " adr: 1",
        " long_dist: 2",
        " heavy: 0",
        " fragile: 1",
        " urgent: 0",
        " mechanical: 3",
        " long_duty: 1",
        " tight_schedule: 0",
        " satisfaction_decrease: 0",
        " low_acceleration: 3",
        " satisfaction_increase: 1",
        " ecodriving: 0",
        " bus_stops: 0",
        " bus_job_log: _nameless.bus.log",
        " bus_experience_points: 250",
        " bus_total_distance: 0",
        " bus_finished_job_count: 0",
        "}",
    ]
    lines += company_units + job_units
    for name, t, link, param in events:
        lines += [
            f"economy_event : {name} {{",
            f" time: {t}",
            f" unit_link: {link}",
            f" param: {param}",
            "}",
        ]
    lines += ["player : _nameless.player.1 {", " buses: 1", " buses[0]: _nameless.v.1", "}"]
    lines += ["economy_event_queue : _nameless.q.0001 {", f" data: {len(queue_order)}"]
    lines += [f" data[{i}]: {e[0]}" for i, e in enumerate(queue_order)]
    lines += ["}"]
    lines += ["bus_stop : _nameless.bus.0001 {", ' name: "Zürich Hbf"', "}"]
    lines += bus_units
    lines += [
        "bus_job_log : _nameless.bus.log {", " version: 0", " entries: 2",
        " entries[0]: _nameless.e.1", " entries[1]: _nameless.e.2", "}",
    ]
    lines += ["}", ""]
    return eol.join(lines)


def make_info_text(money: int = 1234567, xp_total: int = 8250, eol: str = "\r\n") -> str:
    lines = [
        "SiiNunit", "{", "save_container : _nameless.info.0001 {",
        ' name: ""', " time: 50000", " version: 105",
        f" info_players_experience: {xp_total}",
        f" info_money_account: {money}",
        " info_explored_ratio: &3ccf5f50", "}", "}", "",
    ]
    return eol.join(lines)
