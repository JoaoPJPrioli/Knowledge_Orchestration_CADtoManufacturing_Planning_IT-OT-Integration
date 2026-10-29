"""
Kernel-derived reference feature list for the motor-shaft STEP model.
======================================================================
Evaluation-only script. It uses a geometric kernel (OpenCASCADE through the
OCP bindings) to enumerate the B-Rep faces of ``eixo.step`` and to group them
into manufacturing features expressed in the pipeline's own vocabulary
(step, chamfer, groove, blind hole, counterbore, key, ...). The orchestration
pipeline itself remains kernel-free; this script exists only so that the
agent-extracted feature records can be scored against exact geometry.

Usage:
    python analysis/step_reference.py data/motor_data/eixo.step [out.json]

Grouping rules (all tolerances in mm):
  * The part axis is the direction shared by the largest number of
    cylindrical/conical faces (here +Z).
  * A cylindrical face is *external* when its topological orientation is
    FORWARD (material inside the surface) and *internal* when REVERSED.
  * Coaxial external cylindrical faces with equal radius and equal axial
    extent form one turned segment. A turned segment shorter than 5 mm whose
    radius is smaller than both axial neighbours is a *groove*; any other
    turned segment is a *step*.
  * An external conical face is a *chamfer* (the pipeline vocabulary has no
    separate taper class).
  * Internal cylindrical faces form *holes*. A hole closed by an internal
    cone of 118 deg included angle (59 deg semi-angle) is a *blind hole* with a
    drill point; a hole bounded on both ends by a larger coaxial hole or the
    outer face is reported with its own diameter. The internal segment that
    sits between a smaller hole and a larger entry cone is a *counterbore*;
    an internal cone at the entry is an inner *chamfer* (countersink).
  * Faces that are neither coaxial with the part axis nor planar end faces
    are grouped into one prismatic *key* feature described by its bounding
    box (width across X, height above the adjacent turned surface, length
    along Z).
The output is a JSON list; each entry carries the face indices it was
derived from so the grouping can be audited against ``step_faces.py``.
"""
import json
import math
import sys

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

TOL = 1e-3


def bbox(shape):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b, True)
    lo, hi = b.CornerMin(), b.CornerMax()
    return (lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z())


def load_faces(path):
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise SystemExit(f"cannot read {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while exp.More():
        face = TopoDS.Face(exp.Current())
        ad = BRepAdaptor_Surface(face)
        st = ad.GetType()
        rec = {"index": idx, "reversed": face.Orientation() == TopAbs_REVERSED,
               "bbox": bbox(face)}
        if st == GeomAbs_Cylinder:
            cyl = ad.Cylinder()
            d = cyl.Axis().Direction()
            loc = cyl.Axis().Location()
            rec.update(kind="cylinder", radius=cyl.Radius(),
                       axis=(d.X(), d.Y(), d.Z()), axis_loc=(loc.X(), loc.Y(), loc.Z()))
        elif st == GeomAbs_Cone:
            cone = ad.Cone()
            d = cone.Axis().Direction()
            loc = cone.Axis().Location()
            rec.update(kind="cone", semi_angle_deg=math.degrees(cone.SemiAngle()),
                       axis=(d.X(), d.Y(), d.Z()), axis_loc=(loc.X(), loc.Y(), loc.Z()))
        elif st == GeomAbs_Plane:
            n = ad.Plane().Axis().Direction()
            rec.update(kind="plane", normal=(n.X(), n.Y(), n.Z()))
        else:
            rec.update(kind="other")
        faces.append(rec)
        idx += 1
        exp.Next()
    return shape, faces


def parallel(a, b):
    return abs(abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) - 1.0) < 1e-6


def main(path, out=None):
    shape, faces = load_faces(path)
    part_bbox = bbox(shape)
    # --- part axis: most frequent axis among cylinders and cones ---------
    axes = {}
    for f in faces:
        if f["kind"] in ("cylinder", "cone"):
            key = tuple(round(abs(c), 6) for c in f["axis"])
            axes[key] = axes.get(key, 0) + 1
    part_axis = max(axes, key=axes.get)
    assert part_axis == (0.0, 0.0, 1.0), f"unexpected part axis {part_axis}"
    z0, z1 = part_bbox[2], part_bbox[5]

    coaxial = [f for f in faces if f["kind"] in ("cylinder", "cone") and parallel(f["axis"], part_axis)
               and abs(f["axis_loc"][0]) < TOL and abs(f["axis_loc"][1]) < TOL]
    offaxis = [f for f in faces if f not in coaxial and not (f["kind"] == "plane" and parallel(f["normal"], part_axis))]
    end_faces = [f for f in faces if f["kind"] == "plane" and parallel(f["normal"], part_axis)]

    # --- turned segments: group coaxial external cylinders by (R, z-range) -
    def zr(f):
        return (round(f["bbox"][2], 3), round(f["bbox"][5], 3))

    for f in faces:
        f["bbox"] = tuple(round(v, 3) for v in f["bbox"])

    ext_cyl, int_cyl, ext_cone, int_cone = {}, {}, {}, {}
    for f in coaxial:
        if f["kind"] == "cylinder":
            key = (round(f["radius"], 3),) + zr(f)
            (int_cyl if f["reversed"] else ext_cyl).setdefault(key, []).append(f["index"])
        else:
            key = (round(f["semi_angle_deg"], 2),) + zr(f)
            (int_cone if f["reversed"] else ext_cone).setdefault(key, []).append(f["index"])

    features = []

    # external turned profile ordered along z
    segments = sorted(ext_cyl.items(), key=lambda kv: kv[0][1])
    for i, ((r, za, zb), idxs) in enumerate(segments):
        length = zb - za
        prev_r = segments[i - 1][0][0] if i > 0 else None
        next_r = segments[i + 1][0][0] if i + 1 < len(segments) else None
        is_groove = (length < 5.0 and prev_r is not None and next_r is not None
                     and r < prev_r and r < next_r)
        features.append({
            "type": "Groove" if is_groove else "Step",
            "kind": "external cylinder",
            "diameter": 2 * r, "length": round(length, 3),
            "z_min": za, "z_max": zb, "centre": [0.0, 0.0, round((za + zb) / 2, 3)],
            "axis": "Z", "faces": idxs,
        })
    def cone_diameters(idxs, ang, za, zb):
        # large-end diameter from the face bounding box; small end from the taper
        fx = [faces[i]["bbox"] for i in idxs]
        r_large = max(max(abs(b[0]), abs(b[3]), abs(b[1]), abs(b[4])) for b in fx)
        r_small = r_large - (zb - za) * math.tan(math.radians(ang))
        return round(2 * r_large, 3), round(2 * r_small, 3)

    for (ang, za, zb), idxs in sorted(ext_cone.items(), key=lambda kv: kv[0][1]):
        length = zb - za
        d_large, d_small = cone_diameters(idxs, ang, za, zb)
        features.append({
            "type": "Chamfer", "kind": "external cone",
            "diameter": d_large, "diameter_small": d_small,
            "included_angle_deg": round(2 * ang, 2), "length": round(length, 3),
            "z_min": za, "z_max": zb, "centre": [0.0, 0.0, round((za + zb) / 2, 3)],
            "axis": "Z", "faces": idxs,
        })

    # internal profile: holes, counterbore, countersink, drill point
    holes = sorted(int_cyl.items(), key=lambda kv: kv[0][0])  # by radius ascending
    cones = sorted(int_cone.items(), key=lambda kv: kv[0][1])
    drill_points = [c for c in cones if abs(c[0][0] - 59.0) < 1.0]
    entry_cones = [c for c in cones if c not in drill_points]
    for j, ((r, za, zb), idxs) in enumerate(holes):
        has_point = any(abs(c[0][2] - za) < TOL for c in drill_points)
        touches_end = abs(zb - z1) < TOL or abs(za - z0) < TOL
        if j == 0:
            ftype = "Blind Hole" if has_point else ("Through Hole" if touches_end else "Hole")
        else:
            ftype = "Counterbore"
        rec = {
            "type": ftype, "kind": "internal cylinder",
            "diameter": 2 * r, "length": round(zb - za, 3),
            "z_min": za, "z_max": zb, "centre": [0.0, 0.0, round((za + zb) / 2, 3)],
            "entry_z": zb, "axis": "Z", "faces": idxs,
        }
        if has_point:
            tip = next(c for c in drill_points if abs(c[0][2] - za) < TOL)
            rec["drill_point_depth"] = round(tip[0][2] - tip[0][1], 3)
            rec["faces"] = idxs + tip[1]
        features.append(rec)
    for (ang, za, zb), idxs in entry_cones:
        d_large, d_small = cone_diameters(idxs, ang, za, zb)
        features.append({
            "type": "Chamfer", "kind": "internal cone (countersink)",
            "diameter": d_large, "diameter_small": d_small,
            "included_angle_deg": round(2 * ang, 2), "length": round(zb - za, 3),
            "z_min": za, "z_max": zb, "centre": [0.0, 0.0, round((za + zb) / 2, 3)],
            "entry_z": zb, "axis": "Z", "faces": idxs,
        })

    # prismatic (off-axis) feature: one key described by its bounding box
    if offaxis:
        xs = [f["bbox"][0] for f in offaxis] + [f["bbox"][3] for f in offaxis]
        ys = [f["bbox"][1] for f in offaxis] + [f["bbox"][4] for f in offaxis]
        zs = [f["bbox"][2] for f in offaxis] + [f["bbox"][5] for f in offaxis]
        xa, xb, ya, yb, za, zb = (round(v, 3) for v in (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
        # radius of the turned segment the key sits on
        seat = max((kv for kv in segments if kv[0][1] <= za and kv[0][2] >= zb),
                   key=lambda kv: kv[0][0], default=None)
        seat_r = seat[0][0] if seat else None
        features.append({
            "type": "Key", "kind": "prismatic boss with full-radius ends",
            "width": round(xb - xa, 3), "length": round(zb - za, 3),
            "height_above_seat": round(yb - seat_r, 3) if seat_r else None,
            "x_min": xa, "x_max": xb, "y_min": ya, "y_max": yb, "z_min": za, "z_max": zb,
            "centre": [round((xa + xb) / 2, 3), round((seat_r + yb) / 2, 3) if seat_r else None, round((za + zb) / 2, 3)],
            "axis": "normal +Y", "faces": sorted(f["index"] for f in offaxis),
        })

    features.sort(key=lambda f: f["z_min"])
    for i, f in enumerate(features, start=1):
        f["ref_id"] = f"R{i:02d}"
    result = {
        "source": path,
        "part_bbox": part_bbox,
        "part_axis": "Z",
        "face_count": len(faces),
        "end_faces": [f["index"] for f in end_faces],
        "features": features,
    }
    text = json.dumps(result, indent=2)
    if out:
        with open(out, "w") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
