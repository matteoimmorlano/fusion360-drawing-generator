import numpy as np
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
def _edges(comp, defl=0.05):
    out=[]
    if comp is None or comp.IsNull(): return out
    ex=TopExp_Explorer(comp, TopAbs_EDGE)
    while ex.More():
        e=TopoDS.Edge(ex.Current()); c=BRepAdaptor_Curve(e)
        d=GCPnts_QuasiUniformDeflection(c, defl)
        if d.IsDone() and d.NbPoints()>1:
            out.append(np.array([[d.Value(i).X(), d.Value(i).Y()] for i in range(1,d.NbPoints()+1)]))
        ex.Next()
    return out
_meshed=set()
def project_poly(shape, view_dir, x_dir):
    if id(shape) not in _meshed:
        BRepMesh_IncrementalMesh(shape, 0.05, False, 0.2, True); _meshed.add(id(shape))
    algo=HLRBRep_PolyAlgo(shape)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0,0,0), gp_Dir(*view_dir), gp_Dir(*x_dir))))
    algo.Update()
    h=HLRBRep_PolyHLRToShape(); h.Update(algo)
    return {"visible": _edges(h.VCompound())+_edges(h.OutLineVCompound()), "tangent": _edges(h.Rg1LineVCompound())}
