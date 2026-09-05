"""Command-line interface for Gaitkit."""

from __future__ import annotations

import argparse
import json
from importlib.resources import files
from pathlib import Path

from .settings import load_settings, write_default_config
from .workflow import GaitkitWorkflow, check_environment, height_lookup_from_csv


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaitkit", description="Extract 28 gait parameters from RGB videos")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create an editable gaitkit.toml")
    init.add_argument("--config", default="gaitkit.toml")
    init.add_argument("--force", action="store_true")

    check = subparsers.add_parser("check", help="check model repositories, weights and Python environments")
    check.add_argument("--config", default="gaitkit.toml")

    run = subparsers.add_parser("run", help="run the complete RGB-to-gait-parameter workflow")
    run.add_argument("input", help="one video or a directory of videos")
    height = run.add_mutually_exclusive_group(required=True)
    height.add_argument("--height-mm", type=float, help="one measured height for all input videos")
    height.add_argument("--height-csv", help="CSV with video,height_mm columns")
    run.add_argument("--config", default="gaitkit.toml")
    run.add_argument("--output", help="override runtime.output_dir")

    describe = subparsers.add_parser("describe", help="print the five stage contracts")
    describe.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        path = write_default_config(args.config, overwrite=args.force)
        print(f"Created {path.name}")
        return 0
    if args.command == "describe":
        resource = files("gaitkit").joinpath("stage_contracts.json")
        payload = json.loads(resource.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for index, stage in enumerate(payload["stages"], 1):
                print(f"{index}. {stage['stage']}: {stage['input']}")
        return 0

    settings = load_settings(args.config)
    if args.command == "check":
        report = check_environment(settings)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "ok" else 2
    if args.command == "run":
        height = height_lookup_from_csv(args.height_csv) if args.height_csv else float(args.height_mm)
        workflow = GaitkitWorkflow(settings, output_dir=args.output)
        report = workflow.run(args.input, height_mm=height)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["failed_segments"] == 0 else 2
    return 2
