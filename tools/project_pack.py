from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_source(source: Path) -> None:
    source = source.resolve()
    if source == ROOT or source in ROOT.parents or ROOT in source.parents:
        raise ValueError("Source and destination must be separate sibling packs")
    manifest = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        manifest[str(rel)] = digest(path)
        if path.name == ".DS_Store" or path.suffix == ".zip" or rel.parts[:3] == ("trading-desk", "data", "artifacts"):
            continue
        target = ROOT / rel
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    archive = source / "trading-desk-complete.zip"
    with zipfile.ZipFile(archive) as zf:
        differences = [name for name in zf.namelist() if not name.endswith("/") and
                       hashlib.sha256(zf.read(name)).hexdigest() != manifest.get(name)]
    if differences:
        raise ValueError(f"Source archive differs from expanded files: {differences}")
    (ROOT / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Imported source; inventoried {len(manifest)} files; source ZIP matches expanded starter")


def verify_source(source: Path) -> None:
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    actual = {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}
    if actual != manifest:
        raise ValueError("Source files changed since import")
    print(f"Original source unchanged: {len(manifest)} file hashes verified")


def bundle() -> None:
    starter = ROOT / "trading-desk"
    destination = ROOT / "trading-desk-complete.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(starter.rglob("*")):
            rel = path.relative_to(starter)
            if not path.is_file() or any(p in EXCLUDED or p.endswith(".egg-info") for p in rel.parts):
                continue
            if rel.parts[0] == "data" or path.name == ".DS_Store" or path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
                continue
            zf.write(path, Path("trading-desk") / rel)
    with zipfile.ZipFile(destination) as zf:
        assert zf.testzip() is None
        for name in zf.namelist():
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest(ROOT / name)
        print(f"Verified starter ZIP: {len(zf.namelist())} files")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("import-source", "verify-source"):
        sub = commands.add_parser(name)
        sub.add_argument("source", type=Path)
    commands.add_parser("bundle")
    args = parser.parse_args()
    if args.command == "import-source":
        import_source(args.source)
    elif args.command == "verify-source":
        verify_source(args.source)
    else:
        bundle()


if __name__ == "__main__":
    main()
