#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "cadquery-ocp==8.0.1.1.0", "reportlab"]
# ///
"""Demo without Fusion 360: builds a simple bracket with OpenCascade and draws its A3 sheet
with the same engine the add-in uses.

    ./examples/demo.py [output.pdf]
"""
import os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

from tavola_fusion import genera

L, W, T = 140, 90, 12          # base plate
H, WT = 60, 12                 # upright wall height and thickness
BASE_HOLE, WALL_HOLE, CENTER_HOLE = 9, 12, 20


def box(x0, y0, z0, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def cyl(p, d, axis, length):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*axis)), d / 2, length).Shape()


def bracket():
    s = BRepAlgoAPI_Fuse(box(-L / 2, -W / 2, 0, L, W, T), box(-L / 2, W / 2 - WT, T, L, WT, H)).Shape()
    holes = []
    for x in (-55, 55):
        for y in (-32, 22):
            s = BRepAlgoAPI_Cut(s, cyl((x, y, -1), BASE_HOLE, (0, 0, 1), T + 2)).Shape()
            holes.append({"d": BASE_HOLE, "ax": [0, 0, 1], "c": [x, y, T / 2], "sweep": 360})
    s = BRepAlgoAPI_Cut(s, cyl((0, -5, -1), CENTER_HOLE, (0, 0, 1), T + 2)).Shape()
    holes.append({"d": CENTER_HOLE, "ax": [0, 0, 1], "c": [0, -5, T / 2], "sweep": 360})
    for x in (-40, 40):
        s = BRepAlgoAPI_Cut(s, cyl((x, W / 2 - WT - 1, T + 38), WALL_HOLE, (0, 1, 0), WT + 2)).Shape()
        holes.append({"d": WALL_HOLE, "ax": [0, 1, 0], "c": [x, W / 2 - WT / 2, T + 38], "sweep": 360})
    return s, holes


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "demo_drawing.pdf")
    shape, holes = bracket()
    props = GProp_GProps(); BRepGProp.VolumeProperties_s(shape, props)
    step = os.path.join(tempfile.mkdtemp(), "bracket.step")
    w = STEPControl_Writer(); w.Transfer(shape, STEPControl_AsIs); w.Write(step)

    data = {"P": {"plate_thickness": T, "wall_height": H, "base_hole_d": BASE_HOLE},
            "G": {"bbox": [-L / 2, -W / 2, 0, L / 2, W / 2, T + H], "volume_cm3": props.Mass() / 1000,
                  "fori": holes}}
    cfg = {"documento": "Bracket", "intestazione": "Your Company", "autore": "J. Doe",
           "titolo": "Mounting bracket", "numero": "DEMO-001", "materiale": "PETG", "densita": 1.27,
           "fabbricazione": "FDM", "nota": ""}
    genera(cfg, data, step, "A", "First issue", out)


if __name__ == "__main__":
    main()
