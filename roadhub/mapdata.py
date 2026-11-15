"""Kartendaten: Positionen der ETS2-Städte (echte Geokoordinaten, grob) und der Sehenswürdigkeiten.

Die Karte ist eine schematische Europakarte. Die Spielkarte von ETS2 selbst ist urheberrechtlich
geschützt und liegt nicht bei. Die Städte stehen dort, wo sie in der Wirklichkeit liegen.
"""

from __future__ import annotations

import json
import os

# 'city.xyz' -> (Breite, Länge)
CITY_COORDS: dict[str, tuple[float, float]] = {
    "city.a_coruna": (43.37, -8.40), "city.aalborg": (57.05, 9.92), "city.aarhus": (56.16, 10.20),
    "city.ajaccio": (41.92, 8.74), "city.akureyri": (65.68, -18.10), "city.albacete": (38.99, -1.86),
    "city.alesund": (62.47, 6.15), "city.algeciras": (36.13, -5.45), "city.almeria": (36.84, -2.46),
    "city.alta": (69.97, 23.27), "city.amsterdam": (52.37, 4.90), "city.ancona": (43.62, 13.52),
    "city.andenes": (69.31, 16.12), "city.antwerp": (51.22, 4.40), "city.badajoz": (38.88, -6.97),
    "city.barcelona": (41.39, 2.17), "city.bari": (41.12, 16.87), "city.bastia": (42.70, 9.45),
    "city.berlin": (52.52, 13.40), "city.bern": (46.95, 7.45), "city.bialystok": (53.13, 23.16),
    "city.birmingham": (52.49, -1.89), "city.blonduos": (65.66, -20.28), "city.bodo": (67.28, 14.40),
    "city.bologna": (44.49, 11.34), "city.bonifacio": (41.39, 9.16), "city.bordeaux": (44.84, -0.58),
    "city.borlange": (60.48, 15.44), "city.bourges": (47.08, 2.40), "city.bratislava": (48.15, 17.11),
    "city.bremen": (53.08, 8.80), "city.brest": (48.39, -4.49), "city.brno": (49.20, 16.61),
    "city.brussel": (50.85, 4.35), "city.bucuresti": (44.43, 26.10), "city.budapest": (47.50, 19.04),
    "city.burgas": (42.50, 27.47), "city.burgos": (42.34, -3.70), "city.bystrica": (48.74, 19.15),
    "city.cagliari": (39.22, 9.12), "city.calais": (50.95, 1.86), "city.cambridge": (52.21, 0.12),
    "city.carlisle": (54.89, -2.93), "city.cassino": (41.49, 13.83), "city.catanzaro": (38.91, 16.59),
    "city.ciudad_real": (38.99, -3.93), "city.clermont": (45.78, 3.08), "city.cluj_napoca": (46.77, 23.60),
    "city.daugavpils": (55.87, 26.54), "city.debrecen": (47.53, 21.63), "city.dijon": (47.32, 5.04),
    "city.dortmund": (51.51, 7.47), "city.dover": (51.13, 1.31), "city.dresden": (51.05, 13.74),
    "city.duisburg": (51.43, 6.76), "city.dusseldorf": (51.23, 6.78), "city.edinburgh": (55.95, -3.19),
    "city.edirne": (41.68, 26.56), "city.egilsstadir": (65.27, -14.40), "city.esbjerg": (55.48, 8.45),
    "city.faro": (37.02, -7.93), "city.firenze": (43.77, 11.26), "city.frankfurt": (50.11, 8.68),
    "city.gavle": (60.67, 17.14), "city.gdansk": (54.35, 18.65), "city.geneve": (46.20, 6.14),
    "city.genova": (44.41, 8.93), "city.gijon": (43.53, -5.66), "city.glasgow": (55.86, -4.25),
    "city.goteborg": (57.71, 11.97), "city.groningen": (53.22, 6.57), "city.hamburg": (53.55, 9.99),
    "city.helsinki": (60.17, 24.94), "city.hofn": (64.25, -15.21), "city.hunedoara": (45.75, 22.90),
    "city.husavik": (66.04, -17.34), "city.iasi": (47.16, 27.59), "city.innsbruck": (47.27, 11.39),
    "city.isafjordur": (66.07, -23.12), "city.istanbul": (41.01, 28.98), "city.ivalo": (68.66, 27.54),
    "city.joensuu": (62.60, 29.76), "city.jonkoping": (57.78, 14.16), "city.kaliningrad": (54.71, 20.51),
    "city.karlskrona": (56.16, 15.59), "city.karlstad": (59.38, 13.50), "city.kassel": (51.31, 9.48),
    "city.katowice": (50.26, 19.02), "city.kaunas": (54.90, 23.90), "city.keflavik": (63.99, -22.56),
    "city.kiel": (54.32, 10.14), "city.kiruna": (67.86, 20.23), "city.klagenfurt": (46.62, 14.31),
    "city.klaipeda": (55.71, 21.14), "city.kobenhavn": (55.68, 12.57), "city.koln": (50.94, 6.96),
    "city.kosice": (48.72, 21.26), "city.kotka": (60.47, 26.95), "city.krakow": (50.06, 19.94),
    "city.lahti": (60.98, 25.66), "city.larochelle": (46.16, -1.15), "city.lehavre": (49.49, 0.11),
    "city.leipzig": (51.34, 12.37), "city.lemans": (48.00, 0.20), "city.liepaja": (56.51, 21.01),
    "city.lille": (50.63, 3.06), "city.lillehammer": (61.12, 10.47), "city.limoges": (45.83, 1.26),
    "city.linkoping": (58.41, 15.62), "city.lisboa": (38.72, -9.14), "city.liverpool": (53.41, -2.99),
    "city.livorno": (43.55, 10.31), "city.lodz": (51.76, 19.46), "city.london": (51.51, -0.13),
    "city.lublin": (51.25, 22.57), "city.lulea": (65.58, 22.15), "city.luxembourg": (49.61, 6.13),
    "city.lyon": (45.76, 4.84), "city.madrid": (40.42, -3.70), "city.malaga": (36.72, -4.42),
    "city.malmo": (55.60, 13.00), "city.manchester": (53.48, -2.24), "city.marseille": (43.30, 5.37),
    "city.metz": (49.12, 6.18), "city.milano": (45.46, 9.19), "city.montpellier": (43.61, 3.88),
    "city.munchen": (48.14, 11.58), "city.nantes": (47.22, -1.55), "city.napoli": (40.85, 14.27),
    "city.narvik": (68.44, 17.43), "city.nice": (43.70, 7.27), "city.nurnberg": (49.45, 11.08),
    "city.odense": (55.40, 10.39), "city.olafsvik": (64.89, -23.71), "city.olhao": (37.03, -7.84),
    "city.olsztyn": (53.78, 20.49), "city.ornskoldsvik": (63.29, 18.72), "city.oslo": (59.91, 10.75),
    "city.osnabruck": (52.28, 8.05), "city.ostersund": (63.18, 14.64), "city.ostrava": (49.83, 18.28),
    "city.oulu": (65.01, 25.47), "city.palermo": (38.12, 13.36), "city.panevezys": (55.73, 24.36),
    "city.paris": (48.86, 2.35), "city.parnu": (58.38, 24.50), "city.patreksfjord": (65.60, -23.98),
    "city.pecs": (46.07, 18.23), "city.pleven": (43.42, 24.62), "city.plovdiv": (42.14, 24.75),
    "city.porto": (41.15, -8.61), "city.poznan": (52.41, 16.93), "city.prague": (50.08, 14.44),
    "city.reims": (49.26, 4.03), "city.rennes": (48.11, -1.68), "city.reykjavik": (64.15, -21.94),
    "city.rezekne": (56.51, 27.34), "city.riga": (56.95, 24.11), "city.roma": (41.90, 12.50),
    "city.roscoff": (48.72, -3.98), "city.rostock": (54.09, 12.14), "city.rotterdam": (51.92, 4.48),
    "city.rovaniemi": (66.50, 25.73), "city.salamanca": (40.97, -5.66), "city.salzburg": (47.81, 13.04),
    "city.sangiovanni": (38.22, 15.64), "city.sevilla": (37.39, -5.98), "city.sheffield": (53.38, -1.47),
    "city.sofia": (42.70, 23.32), "city.stavanger": (58.97, 5.73), "city.stockholm": (59.33, 18.07),
    "city.strasbourg": (48.57, 7.75), "city.stuttgart": (48.78, 9.18), "city.szczecin": (53.43, 14.55),
    "city.szeged": (46.25, 20.15), "city.tallinn": (59.44, 24.75), "city.tartu": (58.38, 26.72),
    "city.tekirdag": (40.98, 27.51), "city.thorshofn": (66.20, -15.33), "city.torino": (45.07, 7.69),
    "city.toulouse": (43.60, 1.44), "city.trelleborg": (55.38, 13.16), "city.tromso": (69.65, 18.96),
    "city.trondheim": (63.43, 10.40), "city.turku": (60.45, 22.27), "city.umea": (63.83, 20.26),
    "city.uppsala": (59.86, 17.64), "city.vaasa": (63.10, 21.62), "city.valmiera": (57.54, 25.43),
    "city.venezia": (45.44, 12.32), "city.verona": (45.44, 10.99), "city.vigo": (42.24, -8.72),
    "city.villarreal": (39.94, -0.10), "city.vilnius": (54.69, 25.28), "city.warszawa": (52.23, 21.01),
    "city.wien": (48.21, 16.37), "city.wroclaw": (51.11, 17.04), "city.zaragoza": (41.65, -0.89),
    "city.zurich": (47.38, 8.54),
}


# 'viewpoints.xyz' -> (Breite, Länge). Von Hand gesetzt, wo ich den Ort sicher kenne, sonst aus den
# Streckenlängen im Save geschätzt (tools/locate_sights.py). Alle Werte sind ungefähr.
SIGHT_COORDS: dict[str, tuple[float, float]] = {
    "viewpoints.atgrossglock": (47.07, 12.69), "viewpoints.atschonbrunn": (48.18, 16.31),
    "viewpoints.atworthersee": (46.62, 14.16), "viewpoints.baltcastles": (59.38, 26.88),
    "viewpoints.baltconvent": (59.11, 27.50), "viewpoints.baltdaugavpi": (55.88, 26.54),
    "viewpoints.baltklaipeda": (55.71, 21.14), "viewpoints.baltrigapp": (56.95, 24.11),
    "viewpoints.baltvalmiera": (57.54, 25.43), "viewpoints.beantwerp": (51.22, 4.40),
    "viewpoints.beardennes": (50.20, 5.50), "viewpoints.blkecernavod": (44.33, 28.03),
    "viewpoints.blkeistanbul": (41.02, 28.98), "viewpoints.blkeorsova": (44.72, 22.40),
    "viewpoints.blkepernik": (42.60, 23.04), "viewpoints.blkepoianav": (47.39, 26.53),
    "viewpoints.blker73": (45.58, 26.75), "viewpoints.blkwljubljan": (46.05, 14.51),
    "viewpoints.chfurka": (46.57, 8.41), "viewpoints.chgeneve": (46.20, 6.15),
    "viewpoints.chzurichw": (47.38, 8.52), "viewpoints.deberlin": (52.52, 13.40),
    "viewpoints.dedresden": (51.05, 13.74), "viewpoints.deduisburg": (51.43, 6.76),
    "viewpoints.deettal": (47.57, 11.09), "viewpoints.defrankfurt": (50.11, 8.68),
    "viewpoints.dekassel": (51.31, 9.39), "viewpoints.denurnberg": (49.45, 11.08),
    "viewpoints.derostock": (54.09, 12.14), "viewpoints.destuttgart": (48.78, 9.18),
    "viewpoints.frbrest": (48.39, -4.49), "viewpoints.frmarseille": (43.30, 5.37),
    "viewpoints.frpeyrat": (45.82, 1.77), "viewpoints.frrousse": (42.18, 9.44),
    "viewpoints.frserre": (44.52, 6.33), "viewpoints.frusse": (47.25, 0.30),
    "viewpoints.ibebarcelona": (41.39, 2.17), "viewpoints.ibeejido": (36.77, -2.81),
    "viewpoints.ibeguadiana": (37.20, -7.40), "viewpoints.ibelisboa": (38.72, -9.14),
    "viewpoints.ibeolhao": (37.03, -7.84), "viewpoints.ibereservoir": (42.84, -5.99),
    "viewpoints.ibesantander": (43.46, -3.80), "viewpoints.ibezaragoza": (41.65, -0.89),
    "viewpoints.isbarthastra": (65.50, -24.53), "viewpoints.iscanyon": (66.01, -16.51),
    "viewpoints.isgeyser": (64.31, -20.30), "viewpoints.isgothafoss": (65.68, -17.55),
    "viewpoints.isgullfoss": (64.33, -20.12), "viewpoints.isjoekul": (64.05, -16.18),
    "viewpoints.islagoon": (63.88, -22.45), "viewpoints.isselfoss": (63.93, -21.00),
    "viewpoints.isseljaland": (63.62, -19.99), "viewpoints.isthingvelli": (64.26, -21.12),
    "viewpoints.itbari": (41.12, 16.87), "viewpoints.itetna": (37.75, 14.99),
    "viewpoints.itneapol": (40.85, 14.27), "viewpoints.itsangiovann": (38.22, 15.64),
    "viewpoints.itsassari": (40.73, 8.56), "viewpoints.ittaranto": (40.47, 17.24),
    "viewpoints.nldevlieter": (52.79, 5.63), "viewpoints.nleindhoven": (51.44, 5.48),
    "viewpoints.nlgroningen": (53.22, 6.57), "viewpoints.pocalesund": (62.47, 6.15),
    "viewpoints.pocbjornfjel": (68.43, 18.12), "viewpoints.pocbodo": (67.28, 14.40),
    "viewpoints.pocgavle": (60.67, 17.14), "viewpoints.pocheia": (70.15, 20.48),
    "viewpoints.pockiruna": (67.86, 20.23), "viewpoints.poclalby": (62.27, 21.83),
    "viewpoints.poclulea": (65.58, 22.15), "viewpoints.pocmuotkatak": (69.65, 26.75),
    "viewpoints.pocnordkapp": (71.17, 25.78), "viewpoints.pocsanta": (66.54, 25.85),
    "viewpoints.pocsvolvaer": (68.23, 14.57), "viewpoints.poctrondheim": (63.43, 10.40),
    "viewpoints.pocviitasaar": (63.07, 25.87), "viewpoints.sccopenhagen": (55.68, 12.57),
    "viewpoints.sckalmar": (56.66, 16.36), "viewpoints.scmabodalen": (60.40, 7.02),
    "viewpoints.scstockholm": (59.33, 18.07),
}

SIGHT_NAMES: dict[str, str] = {
    "viewpoints.isgeyser": "Geysir", "viewpoints.isgullfoss": "Gullfoss", "viewpoints.isselfoss": "Selfoss",
    "viewpoints.isthingvelli": "Þingvellir", "viewpoints.isseljaland": "Seljalandsfoss",
    "viewpoints.isjoekul": "Gletscherlagune Jökulsárlón", "viewpoints.islagoon": "Blaue Lagune",
    "viewpoints.isgothafoss": "Goðafoss", "viewpoints.iscanyon": "Ásbyrgi-Canyon",
    "viewpoints.isbarthastra": "Barðaströnd", "viewpoints.pocnordkapp": "Nordkap",
    "viewpoints.pocsanta": "Weihnachtsmanndorf Rovaniemi", "viewpoints.atschonbrunn": "Schloss Schönbrunn",
    "viewpoints.atgrossglock": "Großglockner", "viewpoints.atworthersee": "Wörthersee",
    "viewpoints.chfurka": "Furkapass", "viewpoints.chgeneve": "Genfer See", "viewpoints.chzurichw": "Zürich West",
    "viewpoints.deberlin": "Berlin", "viewpoints.dedresden": "Dresden", "viewpoints.deduisburg": "Duisburger Hafen",
    "viewpoints.deettal": "Kloster Ettal", "viewpoints.defrankfurt": "Frankfurt", "viewpoints.dekassel": "Herkules Kassel",
    "viewpoints.denurnberg": "Nürnberg", "viewpoints.derostock": "Rostock", "viewpoints.destuttgart": "Stuttgart",
    "viewpoints.frbrest": "Brest", "viewpoints.frmarseille": "Marseille", "viewpoints.frserre": "Lac de Serre-Ponçon",
    "viewpoints.frusse": "Schloss Ussé", "viewpoints.ibebarcelona": "Barcelona", "viewpoints.ibelisboa": "Lissabon",
    "viewpoints.ibeolhao": "Olhão", "viewpoints.ibesantander": "Santander", "viewpoints.ibezaragoza": "Zaragoza",
    "viewpoints.ibeguadiana": "Guadiana", "viewpoints.ibeejido": "El Ejido",
    "viewpoints.itbari": "Bari", "viewpoints.itetna": "Ätna", "viewpoints.itneapol": "Neapel / Vesuv",
    "viewpoints.ittaranto": "Tarent", "viewpoints.itsassari": "Sassari", "viewpoints.nleindhoven": "Eindhoven",
    "viewpoints.nlgroningen": "Groningen", "viewpoints.pocalesund": "Ålesund", "viewpoints.pocbodo": "Bodø",
    "viewpoints.pocbjornfjel": "Björnfjell", "viewpoints.pocgavle": "Gävle", "viewpoints.pockiruna": "Kiruna",
    "viewpoints.poclulea": "Luleå", "viewpoints.pocsvolvaer": "Svolvær", "viewpoints.poctrondheim": "Trondheim",
    "viewpoints.pocviitasaar": "Viitasaari", "viewpoints.sccopenhagen": "Kopenhagen", "viewpoints.sckalmar": "Kalmar",
    "viewpoints.scmabodalen": "Måbødalen", "viewpoints.scstockholm": "Stockholm",
    "viewpoints.baltrigapp": "Riga", "viewpoints.baltklaipeda": "Klaipėda", "viewpoints.baltvalmiera": "Valmiera",
    "viewpoints.baltdaugavpi": "Festung Daugavpils", "viewpoints.baltconvent": "Kloster Kuremäe",
    "viewpoints.baltcastles": "Burgen im Baltikum", "viewpoints.beantwerp": "Antwerpen", "viewpoints.beardennes": "Ardennen",
    "viewpoints.blkeistanbul": "Istanbul", "viewpoints.blkecernavod": "Cernavodă", "viewpoints.blkeorsova": "Orșova",
    "viewpoints.blkepernik": "Pernik", "viewpoints.blkwljubljan": "Ljubljana",
}


def _register_labels() -> None:
    from . import buslines
    buslines.SIGHT_LABELS.update(SIGHT_NAMES)


_register_labels()


def is_sight(key: str | None) -> bool:
    return bool(key) and key.startswith("viewpoints.")


def coords(key: str) -> tuple[float, float] | None:
    return CITY_COORDS.get(key) or SIGHT_COORDS.get(key)


def sight_label(key: str) -> str:
    """Anzeigename einer Sehenswürdigkeit ('Geysir'); unbekannte bekommen den Roh-Namen."""
    if key in SIGHT_NAMES:
        return SIGHT_NAMES[key]
    return "Aussicht " + key.split(".", 1)[-1]


# ---------------------------------------------------------------- Küstenlinien / Grenzen
_SHAPES: list[list[list[float]]] | None = None


def shapes() -> list[list[list[float]]]:
    """Länderumrisse (Natural Earth 110m, gemeinfrei) als Liste von Ringen [[lon, lat], ...]."""
    global _SHAPES
    if _SHAPES is None:
        path = os.path.join(os.path.dirname(__file__), "europe_shapes.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _SHAPES = json.load(fh)
        except (OSError, ValueError):
            _SHAPES = []
    return _SHAPES
