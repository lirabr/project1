from __future__ import annotations

import ast
import hashlib
import re
import shlex
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "data", "build", "dist"}


def files():
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if path.is_file() and not any(p in SKIP or p.endswith(".egg-info") for p in relative.parts):
            yield path


def main() -> None:
    failures = []
    paths = list(files())
    cli = ast.parse((ROOT / "trading-desk/src/desk/cli.py").read_text())
    commands = {node.args[0].value for node in ast.walk(cli)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser" and node.args
                and isinstance(node.args[0], ast.Constant)}
    for path in paths:
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
        elif path.suffix == ".toml" or path.name == "uv.lock":
            tomllib.loads(path.read_text())
        elif path.suffix == ".md":
            text = path.read_text()
            if len(re.findall(r"^```", text, re.MULTILINE)) % 2:
                failures.append(f"Unbalanced code fence: {path}")
            if path.name == "conversation-transcript.md":
                continue
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                target = urlsplit(link)
                if not target.scheme and target.path and not (path.parent / unquote(target.path)).exists():
                    failures.append(f"Missing link: {path.name} -> {link}")
            for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
                for line in block.splitlines():
                    if "desk-research " not in line:
                        continue
                    tokens = shlex.split(line, comments=True)
                    if "desk-research" not in tokens:
                        continue
                    rest = tokens[tokens.index("desk-research") + 1:]
                    while rest and rest[0] in {"--universe", "--walkforward", "--costs", "--desk", "--risk"}:
                        rest = rest[2:]
                    if rest and rest[0] != "--help" and rest[0] not in commands:
                        failures.append(f"Unknown CLI command: {path.name}: {rest[0]}")
    archive = ROOT / "trading-desk-complete.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                failures.append("Corrupt starter archive")
            archived = set(zf.namelist())
            expected = {str(p.relative_to(ROOT)) for p in paths if p.is_relative_to(ROOT / "trading-desk")
                        and p.name != ".DS_Store" and (not p.name.startswith(".env") or p.name == ".env.example")}
            if archived != expected:
                failures.append(f"ZIP inventory mismatch: missing={expected - archived}, extra={archived - expected}")
            for name in archived:
                if not (ROOT / name).is_file():
                    failures.append(f"Archive-only file: {name}")
                elif hashlib.sha256(zf.read(name)).digest() != hashlib.sha256((ROOT / name).read_bytes()).digest():
                    failures.append(f"Archive differs: {name}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Pack validated: {len(paths)} files; Python/TOML syntax, Markdown links/fences, CLI names and archive checked")


if __name__ == "__main__":
    main()
