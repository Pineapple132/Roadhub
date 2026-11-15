"""Erzeugt roadhub/europe_shapes.json aus Natural Earth 110m (gemeinfrei).
Aufruf: build_shapes.py <naturalearth_lowres.shp>   (liegt z. B. im geopandas-0.14-Paket)"""
import json, sys
import shapefile

BOX = (-26.0, 33.0, 46.0, 73.0)   # lon0, lat0, lon1, lat1

def clip(ring):
    def clip_edge(pts, inside, inter):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out
    x0, y0, x1, y1 = BOX
    def ix(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    def iy(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = [tuple(p) for p in ring]
    for inside, inter in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)),
                          (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        if not pts:
            break
        pts = clip_edge(pts, inside, inter)
    return pts

out = []
sf = shapefile.Reader(sys.argv[1])
for shp in sf.shapes():
    parts = list(shp.parts) + [len(shp.points)]
    for a, b in zip(parts, parts[1:]):
        ring = clip(shp.points[a:b])
        if len(ring) >= 3:
            out.append([[round(x, 2), round(y, 2)] for x, y in ring])
json.dump(out, open("roadhub/europe_shapes.json", "w"), separators=(",", ":"))
print(len(out), "Ringe")
