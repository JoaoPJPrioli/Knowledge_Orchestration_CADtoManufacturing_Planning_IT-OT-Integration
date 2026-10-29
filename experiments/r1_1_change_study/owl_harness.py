"""Run the reasoner path (CFRM + Pellet + KEFC) on an edited copy of the knowledge.

Knowledge edits are applied as text edits to a temporary copy of knowledge/
(the files a knowledge engineer would edit); the repository is never
modified. Code edits needed by a scenario (entries in the vocabulary
dictionaries of skl_repository.py) are applied in-process, restored
afterwards, and counted.
"""
import contextlib
import copy
import difflib
import os
import shutil
import sys
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import REPO, use_repo  # noqa: E402

use_repo()
import rdflib  # noqa: E402
import skl_repository as skl  # noqa: E402
from semantic_reconciler import SemanticReconciler  # noqa: E402
from kefc_controller import KEFCController  # noqa: E402
from expert_validation import ExpertValidationStore  # noqa: E402

KNOWLEDGE = os.path.join(REPO, "knowledge")
CODE_DICTS = ("FEATURE_TYPE_TO_CLASS", "MATERIAL_KEY_TO_INDIVIDUAL", "OWL_OPERATION_TO_LEGACY_ID",
              "OWL_TOOL_TO_LEGACY_ID")


# --- knowledge edit primitives (operate on a path inside the temp copy) -----

def insert_before_rdf_end(relpath: str, xml: str) -> Callable[[str], None]:
    def f(root):
        p = os.path.join(root, relpath)
        s = open(p, encoding="utf-8").read()
        i = s.rindex("</rdf:RDF>")
        open(p, "w", encoding="utf-8").write(s[:i] + xml.strip("\n") + "\n\n" + s[i:])
    return f


def replace_text(relpath: str, old: str, new: str) -> Callable[[str], None]:
    def f(root):
        p = os.path.join(root, relpath)
        s = open(p, encoding="utf-8").read()
        if s.count(old) != 1:
            raise AssertionError(f"{relpath}: expected one occurrence of {old[:60]!r}, found {s.count(old)}")
        open(p, "w", encoding="utf-8").write(s.replace(old, new))
    return f


def add_rules(lines: List[str]) -> Callable[[str], None]:
    def f(root):
        p = os.path.join(root, "rules", "machining_rules.swrl")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("\n" + "\n".join(lines) + "\n")
    return f


def remove_rules(rule_ids: List[str]) -> Callable[[str], None]:
    def f(root):
        p = os.path.join(root, "rules", "machining_rules.swrl")
        kept, removed = [], 0
        for line in open(p, encoding="utf-8"):
            if any(line.startswith(rid + ":") for rid in rule_ids):
                removed += 1
                continue
            kept.append(line)
        if removed != len(rule_ids):
            raise AssertionError(f"removed {removed} of {len(rule_ids)} rules")
        open(p, "w", encoding="utf-8").write("".join(kept))
    return f


# --- measurement ------------------------------------------------------------

def _owl_files(root):
    for sub in ("foundation", "specialized"):
        d = os.path.join(root, sub)
        for f in sorted(os.listdir(d)):
            if f.endswith(".owl"):
                yield os.path.join(sub, f)


def knowledge_delta(orig_root: str, new_root: str) -> Dict:
    """Asserted-triple delta of the ontologies (rdflib, blank nodes ignored),
    rule-line delta of the SWRL file, and edited text lines over all files."""
    added = removed = 0
    for rel in _owl_files(orig_root):
        g1, g2 = rdflib.Graph(), rdflib.Graph()
        g1.parse(os.path.join(orig_root, rel), format="xml")
        g2.parse(os.path.join(new_root, rel), format="xml")
        t1 = {t for t in g1 if not any(isinstance(x, rdflib.BNode) for x in t)}
        t2 = {t for t in g2 if not any(isinstance(x, rdflib.BNode) for x in t)}
        added += len(t2 - t1)
        removed += len(t1 - t2)
    rf = os.path.join("rules", "machining_rules.swrl")

    def rules(root):
        return [l.strip() for l in open(os.path.join(root, rf), encoding="utf-8")
                if l.strip() and not l.strip().startswith("#")]
    r1, r2 = rules(orig_root), rules(new_root)
    lines = 0
    for rel in list(_owl_files(orig_root)) + [rf]:
        a = open(os.path.join(orig_root, rel), encoding="utf-8").read().splitlines()
        b = open(os.path.join(new_root, rel), encoding="utf-8").read().splitlines()
        lines += sum(1 for d in difflib.ndiff(a, b) if d[:2] in ("+ ", "- ") and d[2:].strip())
    return {"triples_added": added, "triples_removed": removed,
            "rules_added": len(set(r2) - set(r1)), "rules_removed": len(set(r1) - set(r2)),
            "file_lines_changed": lines}


@contextlib.contextmanager
def edited_knowledge(edits: List[Callable[[str], None]], code: Optional[Dict[str, Dict]] = None):
    tmp = tempfile.mkdtemp(prefix="r1_1_kb_")
    root = os.path.join(tmp, "knowledge")
    shutil.copytree(KNOWLEDGE, root)
    for e in edits:
        e(root)
    saved = (skl.FOUNDATION_DIR, skl.SPECIALIZED_DIR, skl.RULES_FILE)
    dict_backup = {n: copy.deepcopy(getattr(skl, n)) for n in CODE_DICTS}
    skl.FOUNDATION_DIR = os.path.join(root, "foundation")
    skl.SPECIALIZED_DIR = os.path.join(root, "specialized")
    skl.RULES_FILE = os.path.join(root, "rules", "machining_rules.swrl")
    for name, entries in (code or {}).items():
        getattr(skl, name).update(entries)  # same dict objects are imported by KEFC
    try:
        yield root
    finally:
        skl.FOUNDATION_DIR, skl.SPECIALIZED_DIR, skl.RULES_FILE = saved
        for n in CODE_DICTS:
            d = getattr(skl, n)
            d.clear()
            d.update(dict_backup[n])
        shutil.rmtree(tmp, ignore_errors=True)


def run_owl(entities: List[Dict], material: str = "steel_1045", machine: str = "cnc_lathe",
            edits=(), code=None, inspect: Optional[Callable] = None) -> Dict:
    """Plan with the reasoner path on edited knowledge. Returns normalised steps
    and requests, or halted=True with the reasoner's error."""
    with edited_knowledge(list(edits), code) as root:
        delta = knowledge_delta(KNOWLEDGE, root)
        store_dir = tempfile.mkdtemp(prefix="r1_1_store_")
        try:
            rec = SemanticReconciler(material_key=material, machine_key=machine)
            try:
                reconciled = rec.reconcile(copy.deepcopy(entities))
            except skl.SKLReasonerError as e:
                # Keep the reasoner's own diagnosis; drop host-specific JVM option echoes.
                raw = str(e)
                head = raw.split(":", 1)[0]
                errs = [l.strip() for l in raw.splitlines() if "ERROR" in l]
                msg = head + ": " + (" ".join(errs) if errs else raw[-300:])
                return {"halted": True, "error": msg[:600], "steps": [], "requests": [], "delta": delta}
            store = ExpertValidationStore(os.path.join(store_dir, "s.json"))
            plan = KEFCController(rec.repo, store, machine_key=machine).build_manufacturing_plan(
                reconciled, material=material, machine=machine)
            extra = inspect(rec.repo, reconciled, plan) if inspect else None
        finally:
            shutil.rmtree(store_dir, ignore_errors=True)
    steps = []
    for s in plan["steps"]:
        p = s["parameters"] or {}
        steps.append({"step_number": s["step_number"], "feature_id": s["feature_id"],
                      "operation": s["ontology_operation"], "tool": s["ontology_tool"],
                      "parameters": {k: (p[k]["value"] if k in p else None)
                                     for k in ("feed_rate", "spindle_speed", "depth_of_cut", "coolant")} if p else {},
                      "status": s["validation_status"],
                      "provenance": {"operation": s["operation_selection_rule_id"],
                                     "tool": s["tool_selection_rule_id"],
                                     "parameters": (p.get("feed_rate") or {}).get("rule_id") if p else None}})
    reqs = [{"feature_id": r.feature_id, "operation": r.operation, "reason_code": r.reason_code}
            for r in store.all_requests()]
    return {"halted": False, "steps": steps, "requests": reqs, "delta": delta, "inspect": extra}
