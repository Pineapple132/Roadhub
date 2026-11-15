"""Schätzt die Position der Sehenswürdigkeiten aus den Strecken-Kilometern im Save (Trilateration)."""
import sys, math, json
sys.path.insert(0, ".")
from collections import defaultdict
from roadhub import sii, buslines, mapdata

C = mapdata.CITY_COORDS
RATIO = 1.38

def hav(a, b):
    R = 6371; p1, p2 = math.radians(a[0]), math.radians(b[0]); dl = math.radians(b[1] - a[1]); dp = p2 - p1
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(h))

def locate(path):
    doc = sii.load(path)
    legs = buslines.known_legs(buslines.list_line_offers(doc))
    obs = defaultdict(dict)
    for (a, b), l in legs.items():
        if a.startswith("city.") and b.startswith("viewpoints.") and l.km > 0 and l.ferry_minutes == 0:
            obs[b][a] = min(obs[b].get(a, 1e9), l.km)
        if b.startswith("city.") and a.startswith("viewpoints.") and l.km > 0 and l.ferry_minutes == 0:
            obs[a][b] = min(obs[a].get(b, 1e9), l.km)
    out = {}
    for vp, d in obs.items():
        pts = [(C[c], km / RATIO) for c, km in sorted(d.items(), key=lambda x: x[1])[:6] if c in C]
        if not pts:
            continue
        w = [1 / max(30.0, r) ** 2 for _, r in pts]
        lat = sum(p[0][0] * wi for p, wi in zip(pts, w)) / sum(w)
        lon = sum(p[0][1] * wi for p, wi in zip(pts, w)) / sum(w)
        def cost(la, lo):
            return sum(wi * (hav((la, lo), p) - r) ** 2 for (p, r), wi in zip(pts, w))
        step = 1.0
        best = cost(lat, lon)
        for _ in range(80):
            moved = False
            for dla, dlo in ((step,0),(-step,0),(0,step),(0,-step),(step,step),(-step,-step),(step,-step),(-step,step)):
                c2 = cost(lat + dla, lon + dlo)
                if c2 < best - 1e-9:
                    best, lat, lon, moved = c2, lat + dla, lon + dlo, True
            if not moved:
                step /= 2
                if step < 0.01:
                    break
        out[vp] = (round(lat, 2), round(lon, 2), len(pts))
    return out

if __name__ == "__main__":
    res = locate(sys.argv[1])
    for k in sorted(res):
        print(k, res[k])
    print(len(res))
