"""
Kernel reference v2 for eixo.step (evaluation only; the pipeline stays kernel-free).
Runs the R1 grouping of step_reference.py unchanged (R01 to R10) and adds to the
key (R06) explicit sub-feature anchors read from the B-Rep: the two full-radius
end cylinders (radius, axis direction, axis location, face indices), the two
flank planes and the top plane, with face areas from BRepGProp.

Usage:  python step_reference_v2.py <eixo.step> <step_reference.py dir> <out.json>
"""
import json, math, sys, os
sys.path.insert(0, sys.argv[2])
import step_reference as sr
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
import io, contextlib

def main(step, srdir, out):
    tmp = out + ".r1grouping.json"
    with contextlib.redirect_stdout(io.StringIO()):
        sr.main(step, tmp)
    ref = json.load(open(tmp)); os.remove(tmp)
    shape, faces = sr.load_faces(step)
    exp = TopExp_Explorer(shape, TopAbs_FACE); areas = []
    while exp.More():
        g = GProp_GProps(); BRepGProp.SurfaceProperties_s(TopoDS.Face(exp.Current()), g)
        areas.append(g.Mass()); exp.Next()
    key = next(f for f in ref["features"] if f["type"] == "Key")
    kf = [faces[i] for i in key["faces"]]
    ends = {}
    for f in kf:
        if f["kind"] == "cylinder":
            z = round(f["axis_loc"][2], 3)
            e = ends.setdefault(z, {"radius": round(f["radius"], 4),
                                    "axis_direction": [round(c, 6) + 0.0 for c in f["axis"]],
                                    "axis_location": [round(c, 4) + 0.0 for c in f["axis_loc"]],
                                    "faces": [], "area_mm2": 0.0,
                                    "orientation": "FORWARD (material inside: convex, raised)" if not f["reversed"] else "REVERSED (material outside: concave, recessed)"})
            e["faces"].append(f["index"]); e["area_mm2"] += areas[f["index"]]
    end_list = []
    for z in sorted(ends):
        e = ends[z]; e["area_mm2"] = round(e["area_mm2"], 3); e["z"] = z
        e["anchor_top"] = [0.0, key["y_max"], z]       # axis point on the key top plane
        e["anchor_seat"] = [0.0, key["y_min"], z]      # axis point at the chord of the seat
        end_list.append(e)
    flanks = [{"faces": [f["index"]], "normal": [round(c, 6) + 0.0 for c in f["normal"]],
               "x": round(f["bbox"][0], 3), "area_mm2": round(areas[f["index"]], 3)}
              for f in kf if f["kind"] == "plane" and abs(f["normal"][0]) > 0.99]
    top = [{"faces": [f["index"]], "normal": [round(c, 6) + 0.0 for c in f["normal"]],
            "y": round(f["bbox"][1], 3), "area_mm2": round(areas[f["index"]], 3)}
           for f in kf if f["kind"] == "plane" and abs(f["normal"][1]) > 0.99]
    seat_r = 12.0
    key.update({
        "end_radius": end_list[0]["radius"],
        "end_centre_distance": round(end_list[-1]["z"] - end_list[0]["z"], 3),
        "end_cylinders": end_list, "flank_planes": flanks, "top_plane": top,
        "height_above_chord": round(key["y_max"] - key["y_min"], 3),
        "chord_half_width_check": round(math.sqrt(seat_r**2 - (key["width"]/2)**2), 4),
        "anchors": [key["centre"], [key["centre"][0], key["y_max"], key["centre"][2]]]
                   + [e["anchor_top"] for e in end_list],
        "note": ("Raised (FORWARD-oriented) prismatic body with full-radius ends fused to the R05 seat. "
                 "Dimensions coincide with an IEC 60072-1 frame-90 shaft-end feather key, 8 x 7 (F = 8, GA - G = 7, "
                 "of which 3 mm stand above the 24 mm seat; the seat itself carries no keyway in the CAD)."),
    })
    for f in ref["features"]:
        f["face_areas_mm2"] = [round(areas[i], 3) for i in f["faces"]]
    ref["source"] = os.path.basename(step)
    ref["generator"] = "step_reference_v2.py (R1 grouping unchanged plus key sub-feature anchors)"
    json.dump(ref, open(out, "w"), indent=2)
    print(json.dumps({k: key[k] for k in ("end_radius", "end_centre_distance", "height_above_chord", "chord_half_width_check")}))

if __name__ == "__main__":
    main(*sys.argv[1:4])
