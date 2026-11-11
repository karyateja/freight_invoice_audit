"""Command-line interface.

    python -m freight_audit run   --scale starter|full [--seed N] [--out DIR] [--carriers N --shipments N --invoices N]
    python -m freight_audit repro --scale starter|full [--seed N]
    python -m freight_audit docs
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import tempfile
from pathlib import Path

from . import config as C
from .export import write_json_doc, write_text
from .pipeline import reproducibility, run
from .schema import data_dictionary_md, ddl

ROOT = Path(__file__).resolve().parent.parent


def _cfg(args) -> C.ScaleConfig:
    cfg = C.SCALES[args.scale]
    overrides = {k: getattr(args, k) for k in ("carriers", "shipments", "invoices") if getattr(args, k)}
    if overrides:
        cfg = dataclasses.replace(cfg, name=f"{cfg.name}-custom", **overrides)
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m freight_audit", description="Freight invoice audit: synthetic data "
                                 "generator, audit engine, validation and evaluation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("run", "generate data, audit, validate, evaluate and export"),
                        ("repro", "run twice with the same seed and compare checksums")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--scale", choices=sorted(C.SCALES), default="starter")
        p.add_argument("--seed", type=int, default=C.DEFAULT_SEED)
        p.add_argument("--carriers", type=int)
        p.add_argument("--shipments", type=int)
        p.add_argument("--invoices", type=int)
        if name == "run":
            p.add_argument("--out", help="output directory (default: output/<scale>)")
            p.add_argument("--formats", default="csv,json,sql", help="comma list of csv,json,sql")
    sub.add_parser("docs", help="regenerate docs/DATA_DICTIONARY.md and docs/schema.sql from schema.py")
    args = ap.parse_args(argv)

    if args.cmd == "docs":
        write_text(ROOT / "docs" / "DATA_DICTIONARY.md", data_dictionary_md())
        write_text(ROOT / "docs" / "schema.sql", ddl())
        print("wrote docs/DATA_DICTIONARY.md and docs/schema.sql")
        return 0

    cfg = _cfg(args)
    if args.cmd == "run":
        out = Path(args.out) if args.out else ROOT / "output" / cfg.name
        res = run(cfg, args.seed, out, tuple(args.formats.split(",")))
        return 0 if res["validation"]["overall"] == "PASS" else 1

    reference = ROOT / "output" / cfg.name
    with tempfile.TemporaryDirectory(prefix="freight_repro_") as tmp:
        print(f"running {cfg.name} twice with seed {args.seed} ...", flush=True)
        res = reproducibility(cfg, args.seed, Path(tmp), reference if args.seed == C.DEFAULT_SEED else None)
    if "reference_output" in res:   # repo-relative: no local user path in a committed file
        res["reference_output"] = reference.relative_to(ROOT).as_posix()
    target = ROOT / "output" / f"reproducibility_{cfg.name}.json"
    write_json_doc(target, res)
    print(f"files compared: {res['files_compared']}  identical across runs: {res['identical']}"
          + (f"  matches committed output/{cfg.name}: {res['matches_reference']}" if "matches_reference" in res else ""))
    if res["differing_files"]:
        print("differing:", *res["differing_files"], sep="\n  ")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0 if res["identical"] and res.get("matches_reference", True) else 1


if __name__ == "__main__":
    sys.exit(main())
