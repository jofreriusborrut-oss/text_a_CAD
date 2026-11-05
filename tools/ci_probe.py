"""Temporary experiment (runs in CI): which way of engraving text gives a valid solid?"""
import subprocess
import sys
import traceback

import cadquery as cq

TEXT, SIZE, DEPTH, T = "EPSEVG RACING", 6, 1, 3


def plate():
    p = cq.Workplane("XY").box(80, 30, T, centered=(True, True, False))
    holes = cq.Workplane("XY").pushPoints([(-34, 0), (34, 0)]).circle(1.5).extrude(T)
    return p.cut(holes)


def report(name, build):
    try:
        result = build()
        shape = result.val() if isinstance(result, cq.Workplane) else result
        objs = result.vals() if isinstance(result, cq.Workplane) else [result]
        bb = shape.BoundingBox()
        print(f"{name:28s} valid={shape.isValid()} solids={len(shape.Solids())} stack={len(objs)} "
              f"bbox={bb.xlen:.2f}x{bb.ylen:.2f}x{bb.zlen:.2f} volume={shape.Volume():.1f} type={type(shape).__name__}")
    except Exception:  # noqa: BLE001
        print(f"{name:28s} ERROR {traceback.format_exc().strip().splitlines()[-1][:200]}")


def text_solid(**kw):
    return cq.Workplane("XY").workplane(offset=T - DEPTH).text(TEXT, SIZE, DEPTH + 0.5, combine=False, **kw)


print("fonts:", subprocess.run("fc-list | wc -l; fc-match Arial; fc-match sans", shell=True, capture_output=True, text=True).stdout.replace("\n", " | "))
print("full plate volume:", plate().val().Volume())
report("A face.text(-d, cut)", lambda: plate().faces(">Z").workplane().text(TEXT, SIZE, -DEPTH, combine="cut"))
report("A2 same, clean=False", lambda: plate().faces(">Z").workplane().text(TEXT, SIZE, -DEPTH, combine="cut", clean=False))
report("B cut(text workplane)", lambda: plate().cut(text_solid()))
report("B2 cut(text, clean=False)", lambda: plate().cut(text_solid(), clean=False))
report("B3 cut(text, tol=0.001)", lambda: plate().cut(text_solid(), tol=0.001))
report("text solid itself", lambda: text_solid())


def letter_by_letter(clean=True):
    body = plate()
    for solid in text_solid().val().Solids():
        body = body.cut(solid, clean=clean)
    return body


report("C letter by letter", letter_by_letter)
report("C2 letter by letter noclean", lambda: letter_by_letter(False))


def fused_text():
    solids = text_solid().val().Solids()
    fused = solids[0]
    for s in solids[1:]:
        fused = fused.fuse(s)
    return plate().cut(fused)


report("D fuse letters then cut", fused_text)
for font in ("DejaVu Sans", "Liberation Sans", "Arial"):
    report(f"E font {font}", lambda font=font: plate().cut(text_solid(font=font)))
report("F emboss union", lambda: plate().faces(">Z").workplane().text(TEXT, SIZE, DEPTH, combine=True))
report("G text kind=bold", lambda: plate().cut(text_solid(kind="bold")))
sys.exit(0)
