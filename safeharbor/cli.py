"""safeharbor — command-line interface.

    safeharbor status
    safeharbor doctor
    safeharbor backup
    safeharbor restore <backup> [--dry-run]
    safeharbor validate
    safeharbor a2a-test
    safeharbor generation record|show|validate
    safeharbor version

The CLI is stdlib-only and runs on a bare, air-gapped machine. All paths
default to the Gen1 layout and can be redirected with SH_* environment
variables or the ``--root`` flag (used by the local test suite).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .context import Context, HttpClient, ServiceControl
from .paths import Layout, default_layout


def _build_layout(args: argparse.Namespace) -> Layout:
    if getattr(args, "root", None):
        root = Path(args.root).resolve()
        return Layout(
            software_dir=root / "software",
            config_dir=root / "etc",
            state_dir=root / "var" / "lib",
            log_dir=root / "var" / "log",
            backup_dir=root / "var" / "lib" / "backups",
        )
    return default_layout()


def _context(args: argparse.Namespace) -> Context:
    layout = _build_layout(args)
    return Context(
        layout=layout,
        simulate=bool(getattr(args, "simulate", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )


def cmd_status(args: argparse.Namespace) -> int:
    from . import status

    return status.run(_context(args), machine_readable=args.json)


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import doctor

    return doctor.run(_context(args), machine_readable=args.json)


def cmd_backup(args: argparse.Namespace) -> int:
    from . import backup

    return backup.run_backup(_context(args), note=args.note or "")


def cmd_restore(args: argparse.Namespace) -> int:
    from . import restore

    ctx = _context(args)
    if args.list:
        from .backup import list_backups

        backups = list_backups(ctx)
        if not backups:
            print("No backups found.")
            return 1
        for b in backups:
            manifest = b / "backup-manifest.json"
            stamp = manifest.stat().st_mtime if manifest.is_file() else 0
            print(f"{b.name}  {b}")
        return 0
    if not args.backup:
        print("restore requires a backup path (or --list to list backups)")
        return 2
    backup_root = Path(args.backup).resolve()
    if not backup_root.is_dir():
        print(f"Backup not found: {backup_root}")
        return 2
    return restore.run(
        backup_root,
        ctx,
        dry=args.dry_run,
        force=args.force,
        yes=args.yes,
    )


def cmd_validate(args: argparse.Namespace) -> int:
    from . import validate

    backup = Path(args.backup).resolve() if args.backup else None
    return validate.run(_context(args), backup=backup, machine_readable=args.json)


def cmd_a2a(args: argparse.Namespace) -> int:
    from . import a2a

    return a2a.run_test(
        _context(args),
        peer_name=args.peer,
        levels=args.levels,
        reverse=args.reverse,
    )


def cmd_generation(args: argparse.Namespace) -> int:
    from . import generation

    ctx = _context(args)
    if args.generation_command == "record":
        return generation.record(ctx)
    if args.generation_command == "show":
        return generation.show(ctx, machine_readable=args.json)
    if args.generation_command == "validate":
        return generation.validate(ctx)
    print("generation requires record|show|validate")
    return 2


def cmd_version(args: argparse.Namespace) -> int:
    print(f"safeharbor {__version__}")
    return 0


def _common_parser() -> argparse.ArgumentParser:
    """Options accepted both before and after the subcommand.

    ``default=argparse.SUPPRESS`` is required: a subparser builds a fresh
    namespace and copies it over the main one, so an ordinary default here
    would clobber a value the main parser already consumed (argparse gotcha
    with subparsers + repeated option definitions).
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="Run against a self-contained layout under DIR (safe/test mode).",
    )
    common.add_argument(
        "--simulate",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Never touch services or the network (safe/test mode).",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safeharbor",
        description="Safe Harbor — reproducible deployment, recovery, validation "
        "and migration of persistent local AI agent environments.",
        parents=[_common_parser()],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    parents = [_common_parser()]

    p = sub.add_parser("status", help="Fast operational summary", parents=parents)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor", help="Deep validation", parents=parents)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("backup", help="Consistent backup of persistent state", parents=parents)
    p.add_argument("--note", help="operator note recorded in the backup manifest")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="Validated, deliberate restore", parents=parents)
    p.add_argument("backup", nargs="?", help="backup directory to restore")
    p.add_argument("--dry-run", action="store_true", help="inspect + validate, change nothing")
    p.add_argument("--force", action="store_true", help="allow overwriting newer state")
    p.add_argument("--yes", action="store_true", help="confirm non-interactively")
    p.add_argument("--list", action="store_true", help="list available backups")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("validate", help="Validate environment, state and backups", parents=parents)
    p.add_argument("--backup", help="validate a specific backup directory")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("a2a-test", help="A2A acceptance test (levels 1-6)", parents=parents)
    p.add_argument("--peer", help="test only this peer name")
    p.add_argument("--levels", type=int, default=6, help="run up to this level (default 6)")
    p.add_argument("--reverse", action="store_true", help="run L4 in reverse (Specialist side)")
    p.set_defaults(func=cmd_a2a)

    p = sub.add_parser("generation", help="Environment/generation metadata", parents=parents)
    gen = p.add_subparsers(dest="generation_command", required=True)
    gen.add_parser("record", help="Record a generation manifest from installed versions", parents=parents)
    g = gen.add_parser("show", help="Show the current generation manifest", parents=parents)
    g.add_argument("--json", action="store_true", help="machine-readable output")
    gen.add_parser("validate", help="Validate the current generation manifest", parents=parents)
    p.set_defaults(func=cmd_generation)

    p = sub.add_parser("version", help="Print version", parents=parents)
    p.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — top-level safety net
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())