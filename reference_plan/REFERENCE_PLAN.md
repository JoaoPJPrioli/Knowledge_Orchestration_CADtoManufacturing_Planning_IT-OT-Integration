# Reference process plan for the replacement shaft

Status: drafted by the authors; every judgement listed (J01 to J17) for independent review. Part: motor shaft eixo, replacement part (remanufacturing). Material: AISI 1045 bar. Stock: d 30 cold-drawn bar (J01).
Geometry: pipeline/analysis/results/step_reference.json R01-R10 + IEC 60072-1 frame-90 interpretation (J02).

The plan is scored against the generated plan in comparison.json (manuscript Section 5.4 and Table 7; Supplementary Table S8). Scored: counted as a required reference operation (conditional operations are not counted). Every judgement behind the plan is listed below and can be reviewed in Reference_Plan_SignOff.xlsx.

| Op | Set-up | Feature | Operation family | Machine | Tool | Scored | Judgements |
|---|---|---|---|---|---|---|---|
| 10.01 | S10 | Drive-end (DE) face, z = 168.5 | facing | CNC lathe (CNCLatheFanuc0iTD) | CNMG 120408 rough + CNMG 120404 finish pass (TurningInsertRough / TurningInsertFinish) | yes | J05 |
| 10.02 | S10 | Spot/centre on axis before tap drill | centre_drilling | CNC lathe | Spot drill 90 deg or DIN 332-2 form-DS stepped centre drill | conditional | J07 |
| 10.03 | S10 | Tap-drill hole d 6.8, full-diameter depth 25.0 from DE face (R07) | drilling | CNC lathe | HSS twist drill 6.8, 118 deg (DrillBit); axial peck cycle at X0 | yes | J07 |
| 10.04 | S10 | Counterbore d 8.4, flat floor at z = 162.5 (R08) | counterboring | CNC lathe | Flat-bottom counterbore (CounterboreCutter) or step of DIN 332-2 drill | yes | J07, J10 |
| 10.05 | S10 | 60 deg countersink to d 12.2 (R09), DIN 332-2 centre seat | chamfering | CNC lathe | 60 deg countersink / DIN 332-2 stepped drill; NOT in tools.owl (only 90 deg chamfer tools) | yes | J07, J12 |
| 10.06 | S10 | Engage tailstock live 60 deg centre in R09 | setup_element | CNC lathe | Live centre; tailstock not modelled in machines.owl | setup | J05 |
| 10.07a | S10 | Rough turn d 24.0 seat (R05), leave 0.2-0.3 on diameter | rough_turning | CNC lathe | CNMG 120408 (TurningInsertRough) | yes | J01 |
| 10.07b | S10 | Rough turn d 24.95 body (R01) back past NDE face + parting width | rough_turning | CNC lathe | CNMG 120408 (TurningInsertRough) | yes | J01, J17 |
| 10.08a | S10 | Undercut d 23.6 x 1.754 at shaft-end root (R03) | grooving | CNC lathe | Grooving/profiling insert of width <= 1.5 mm with corner radius, or undercut form insert; tools.owl GroovingTool is 2 mm wide | yes | J04, J08 |
| 10.08b | S10 | 15 deg run-out cone d 23.6 -> 24.0 (R04) | grooving/chamfering/finish_turning | CNC lathe | Profiled with the undercut tool or in the finishing contour | yes | J09 |
| 10.09a | S10 | Finish turn d 24 j6 seat (R05): +0.009/-0.004 | finish_turning | CNC lathe | CNMG 120404 (TurningInsertFinish) or 35 deg profiling insert; G42 nose-radius compensation, in-process gauging | yes | J04 |
| 10.09b | S10 | Finish turn d 24.95 body (R01) | finish_turning | CNC lathe | CNMG 120404 (TurningInsertFinish) | yes | J17 |
| 10.09c | S10 | 1 x 45 deg end chamfer d 24 -> 22 (R10), turned in contour | chamfering | CNC lathe | Turning insert (contour); not a chamfer mill | yes | J12 |
| 10.09d | S10 | 0.5 x 45 deg chamfer d 24.95 -> 23.95 (R02), turned in contour | chamfering | CNC lathe | Turning insert (contour); not a chamfer mill | yes | J12 |
| 10.10 | S10 | Tap M8 x 1.25-6H in R07 (thread depth per DIN 332-2) | tapping | CNC lathe | HSS-E spiral-flute machine tap, rigid tapping (G84, stationary tap on centreline) or floating holder; NOT in ontology | yes | J06 |
| 10.11 | S10 | Part off at z ~ 80.0 (0.5 mm facing allowance) | parting | CNC lathe | Parting blade/insert; NOT in ontology | yes | J14 |
| 20.01 | S20 | Non-drive-end (NDE) face to overall length 88.0, z = 80.5 | facing | CNC lathe (reversed, soft jaws on d 24.95, stop on R02 shoulder) | CNMG 120404 (TurningInsertFinish) | yes | J05, J17 |
| 20.02 | S20 | Edge break NDE outer edge (not modelled in CAD) | chamfering | CNC lathe | Turning insert | no | J16 |
| 30.01 | S30 | Keyway 8 N9 (7.964-8.000) x t1 4.0 +0.2 x 40, form A (R4 ends), z 123.5-163.5, symmetric to axis | milling | Vertical milling machine / VMC (NOT in machines.owl) | 2-flute carbide keyway end mill d 8 (keyway tolerance) or undersize rough + side finish; tools.owl EndMill is a generic 4-flute | yes | J02, J03, J13 |
| 30.02 | S30 | Deburr keyway edges | deburring | Vertical milling machine / VMC | Hand/brush | no | J16 |
| 40.01 | S40 (optional) | Grind d 24 j6 seat (R05) if turning cannot hold IT6 | grinding | Cylindrical grinder (NOT in machines.owl) | Plain wheel; undercut R03/R04 gives run-out | no | J04 |
| 50.01 | S50 | j6 seat, run-out (IEC 60072-1 class), keyway width/depth (G = 20.0)/symmetry, M8-6H plug gauge, E = 50, GA = 27 after key fitted | inspection | Inspection | Air gauge/micrometer, slot gauge, thread plug gauge | no | J03, J16 |

## Judgements

- **J01.** Stock d 30 cold-drawn AISI 1045, about 170 to 210 HB; resolve the HRC 25 versus UTS 570 MPa inconsistency in `materials.owl`.
- **J02.** The catalogue CAD shows the key fitted; the replacement shaft has keyway 8 x 4 x 40 form A and an M8 threaded centre hole (IEC 60072-1 frame 90).
- **J03.** Keyway width N9 (normal fit) rather than P9; t1 = 4.0 +0.2; position and symmetry tolerance to be taken from the customer drawing.
- **J04.** j6 seat by finish turning with in-process gauging; optional cylindrical grinding (S40) because the R03/R04 undercut looks like a grinding relief.
- **J05.** Workholding: chuck plus tailstock live centre in the DS countersink in S10; reversal on soft jaws on d 24.95 in S20; sequence as in Section 2.
- **J06.** Thread M8 x 1.25-6H, depth per DIN 332-2; tapping on the lathe at the spindle centreline (not off-machine).
- **J07.** Centre-hole tooling: separate spot drill, 6.8 drill, 8.4 counterbore and 60 deg countersink, or one DIN 332-2 form-DS stepped centre drill (then 10.02 is not needed).
- **J08.** The R03 recess needs a grooving or profiling tool; longitudinal turning with an 80 deg CNMG insert is judged unable to form a recess that lies below both neighbouring diameters and is entered over a 15 deg ramp. The 2 mm `GroovingTool` is wider than the 1.754 mm land.
- **J09.** R04 (15 deg cone) may be produced by grooving/profiling, as a chamfer, or in the finishing contour; all three families accepted.
- **J10.** R08 is flat-bottomed (B-Rep PLANE at z 162.5), so it is counterbored; pre-drilling it with a 118 deg 8.4 drill is not the reference practice.
- **J11.** Key-region entities: Boss (entities 10, 18) = the fitted key, not a machined feature of the shaft; Through Hole (11, 12) = misread keyway end radii (real location, wrong family); Slot (13, 14, 22) = keyway (milling, correct family).
- **J12.** External chamfers are turned with the turning insert in the contour; a rotating chamfer mill cannot be driven on a lathe without driven tooling, and a 90 deg chamfer tool cannot form the 60 deg countersink R09.
- **J13.** Keyway on a vertical milling machine or VMC with a 2-flute keyway cutter (a keyseater or a lathe with driven tooling and C-axis would be alternatives).
- **J14.** Parting from bar in S10 (if sawn blanks are used, 10.11 disappears but both facing operations remain).
- **J15.** Handbook-type cutting-speed bands and the uncoated/coated reading of the `tools.owl` material strings (`parameter_audit.json`).
- **J16.** Edge break on the NDE edge, deburring and the inspection plan; run-out class per IEC 60072-1.
- **J17.** The modelled 88 mm solid is the complete replacement part (the pipeline makes the same assumption). If z = 80.5 is a truncation of a longer rotor shaft, S20 and 10.11 change and the d 24.95 body may carry a bearing-seat tolerance.
