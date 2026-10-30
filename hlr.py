"""Hidden-line-removed 2D projections of a STEP solid (OpenCascade)."""
import numpy as np
from OCP.STEPControl import STEPControl_Reader
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

def load_step(path):
    r = STEPControl_Reader(); r.ReadFile(path); r.TransferRoots(); return r.OneShape()

def bbox(shape):
    b = Bnd_Box(); BRepBndLib.Add_s(shape, b)
    p, q = b.CornerMin(), b.CornerMax(); return (p.X(), p.Y(), p.Z(), q.X(), q.Y(), q.Z())

def _edges(comp, defl=0.02):
    out = []
    if comp is None or comp.IsNull(): return out
    ex = TopExp_Explorer(comp, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge(ex.Current()); c = BRepAdaptor_Curve(e)
        d = GCPnts_QuasiUniformDeflection(c, defl)
        if d.IsDone() and d.NbPoints() > 1:
            out.append(np.array([[d.Value(i).X(), d.Value(i).Y()] for i in range(1, d.NbPoints()+1)]))
        ex.Next()
    return out

def project(shape, view_dir, x_dir, hidden=False):
    """view_dir: direction from the part toward the viewer. Returns dict of polylines (2D, mm)."""
    algo = HLRBRep_Algo(); algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0,0,0), gp_Dir(*view_dir), gp_Dir(*x_dir))))
    algo.Update(); algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    res = {"visible": _edges(h.VCompound()) + _edges(h.OutLineVCompound()),
           "tangent": _edges(h.Rg1LineVCompound())}
    if hidden:
        res["hidden"] = _edges(h.HCompound()) + _edges(h.OutLineHCompound())
    return res
