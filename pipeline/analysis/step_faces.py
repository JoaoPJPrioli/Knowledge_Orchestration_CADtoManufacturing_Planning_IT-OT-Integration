"""Enumerate the faces of a STEP B-Rep with a geometric kernel (OCP / OpenCASCADE).
Usage: python step_faces.py <file.step>
Prints, per face: surface type, axis location/direction, radius/semi-angle, bbox, area, orientation.
"""
import sys, math
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BSplineSurface, GeomAbs_SurfaceOfRevolution, GeomAbs_SurfaceOfExtrusion, GeomAbs_BezierSurface, GeomAbs_OffsetSurface, GeomAbs_OtherSurface
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools

NAMES = {GeomAbs_Plane:'Plane', GeomAbs_Cylinder:'Cylinder', GeomAbs_Cone:'Cone', GeomAbs_Sphere:'Sphere', GeomAbs_Torus:'Torus', GeomAbs_BSplineSurface:'BSpline', GeomAbs_SurfaceOfRevolution:'Revolution', GeomAbs_SurfaceOfExtrusion:'Extrusion', GeomAbs_BezierSurface:'Bezier', GeomAbs_OffsetSurface:'Offset', GeomAbs_OtherSurface:'Other'}

def main(path):
    r = STEPControl_Reader()
    assert r.ReadFile(path) == IFSelect_RetDone, "read failed"
    r.TransferRoots()
    shape = r.OneShape()
    # overall bbox
    bb = Bnd_Box(); BRepBndLib.Add_s(shape, bb, True)
    xmin,ymin,zmin,xmax,ymax,zmax = bb.CornerMin().X(),bb.CornerMin().Y(),bb.CornerMin().Z(),bb.CornerMax().X(),bb.CornerMax().Y(),bb.CornerMax().Z()
    print(f"PART bbox: x[{xmin:.3f},{xmax:.3f}] y[{ymin:.3f},{ymax:.3f}] z[{zmin:.3f},{zmax:.3f}]  size L={xmax-xmin:.3f} W={ymax-ymin:.3f} H={zmax-zmin:.3f}")
    props = GProp_GProps(); BRepGProp.VolumeProperties_s(shape, props)
    c = props.CentreOfMass()
    print(f"PART volume={props.Mass():.2f} mm3, centroid=({c.X():.3f},{c.Y():.3f},{c.Z():.3f})")
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    i = 0
    rows = []
    while exp.More():
        face = TopoDS.Face(exp.Current())
        ad = BRepAdaptor_Surface(face)
        st = ad.GetType()
        fb = Bnd_Box(); BRepBndLib.Add_s(face, fb, True)
        fx0,fy0,fz0,fx1,fy1,fz1 = fb.CornerMin().X(),fb.CornerMin().Y(),fb.CornerMin().Z(),fb.CornerMax().X(),fb.CornerMax().Y(),fb.CornerMax().Z()
        gp = GProp_GProps(); BRepGProp.SurfaceProperties_s(face, gp)
        area = gp.Mass()
        rev = face.Orientation() == TopAbs_REVERSED
        info = ""
        if st == GeomAbs_Cylinder:
            cyl = ad.Cylinder(); ax = cyl.Axis(); loc = ax.Location(); d = ax.Direction()
            info = f"R={cyl.Radius():.3f} axis_loc=({loc.X():.3f},{loc.Y():.3f},{loc.Z():.3f}) dir=({d.X():.3f},{d.Y():.3f},{d.Z():.3f})"
        elif st == GeomAbs_Cone:
            cone = ad.Cone(); ax = cone.Axis(); loc = ax.Location(); d = ax.Direction()
            info = f"Rref={cone.RefRadius():.3f} semiangle={math.degrees(cone.SemiAngle()):.2f}deg axis_loc=({loc.X():.3f},{loc.Y():.3f},{loc.Z():.3f}) dir=({d.X():.3f},{d.Y():.3f},{d.Z():.3f})"
        elif st == GeomAbs_Plane:
            pl = ad.Plane(); n = pl.Axis().Direction(); loc = pl.Location()
            info = f"normal=({n.X():.3f},{n.Y():.3f},{n.Z():.3f}) loc=({loc.X():.3f},{loc.Y():.3f},{loc.Z():.3f})"
        elif st == GeomAbs_Torus:
            t = ad.Torus(); ax = t.Axis(); loc = ax.Location(); d = ax.Direction()
            info = f"Rmaj={t.MajorRadius():.3f} Rmin={t.MinorRadius():.3f} axis_loc=({loc.X():.3f},{loc.Y():.3f},{loc.Z():.3f}) dir=({d.X():.3f},{d.Y():.3f},{d.Z():.3f})"
        rows.append((i, NAMES.get(st,'?'), rev, area, (fx0,fy0,fz0,fx1,fy1,fz1), info))
        i += 1
        exp.Next()
    for (i, name, rev, area, (fx0,fy0,fz0,fx1,fy1,fz1), info) in rows:
        print(f"F{i:02d} {name:9s} rev={int(rev)} area={area:8.2f} bbox x[{fx0:7.3f},{fx1:7.3f}] y[{fy0:7.3f},{fy1:7.3f}] z[{fz0:7.3f},{fz1:7.3f}] {info}")

if __name__ == '__main__':
    main(sys.argv[1])
