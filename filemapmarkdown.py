#!/usr/bin/env python3
"""
filemapmarkdown.py – Generate a Markdown tree of a folder and drop it in Downloads.

Usage
-----
export-markdown <directory_to_map>

Features
--------
• First run: bootstraps an isolated env with Astral's uv and re-executes itself.
• Output: <dirname>_filemap.md is written to your OS Downloads folder.
• When done: opens the Downloads folder in Explorer / Finder / xdg-open.
"""

from __future__ import annotations
import os, sys, subprocess, platform, argparse
from pathlib import Path


# ────────────────────────────────────────────────────────────────────────────────
# 0. Self-bootstrap with uv
# ────────────────────────────────────────────────────────────────────────────────
def _ensure_uv_env() -> None:
    """If we’re not already inside *any* venv, spin up one with uv and re-exec."""
    if sys.prefix == sys.base_prefix:                        # outside a venv
        env_dir = Path(__file__).with_suffix('').with_name(".filemap_env")
        if not env_dir.exists():
            print("[filemap] creating isolated env with uv …")
            subprocess.run(["uv", "venv", str(env_dir)], check=True)

        python_exe = env_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
        os.execv(python_exe, [str(python_exe)] + sys.argv)   # never returns


_ensure_uv_env()       # ← must run before any other imports


# ────────────────────────────────────────────────────────────────────────────────
# 1. Helpers
# ────────────────────────────────────────────────────────────────────────────────
def _downloads_dir() -> Path:
    if platform.system() == "Windows":  return Path(os.environ["USERPROFILE"]) / "Downloads"
    return Path.home() / "Downloads"


def _open_folder(path: Path) -> None:
    if platform.system() == "Windows":  os.startfile(path)                       # type: ignore
    elif platform.system() == "Darwin": subprocess.run(["open", str(path)])
    else:                                subprocess.run(["xdg-open", str(path)])


# ────────────────────────────────────────────────────────────────────────────────
# 2. Exclusion rules & directory walk
# ────────────────────────────────────────────────────────────────────────────────
_EXCLUDE_NAMES = {
    "__pycache__", ".git", ".DS_Store", ".idea", ".vscode", ".egg-info",
    "dist", "build", ".venv", "venv", ".pytest_cache", ".coverage", "htmlcov", ".tox",
}
_EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe"}


def _exclude(p: Path) -> bool:
    if p.name == "__init__.py": return False
    if p.is_file() and p.suffix in _EXCLUDE_EXTS: return True
    return any(part in _EXCLUDE_NAMES for part in p.parts)


def _sort_key(p: Path):       # dirs first, then case-insensitive alpha
    return (not p.is_dir(), p.name.lower())


def _tree_md(root: Path, prefix: str = "") -> str:
    items = sorted((p for p in root.iterdir() if not _exclude(p)), key=_sort_key)
    lines: list[str] = []
    for i, item in enumerate(items):
        last = i == len(items) - 1
        item_pref, child_pref = ("└── ", "    ") if last else ("├── ", "│   ")

        if item.is_dir():
            lines.append(f"{prefix}{item_pref}📁 **{item.name}/**")
            lines.append(_tree_md(item, prefix + child_pref))
        else:
            lines.append(f"{prefix}{item_pref}📄 {item.name}")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────────
# 3. Core
# ────────────────────────────────────────────────────────────────────────────────
def create_filemap(src: Path, dst_dir: Path) -> Path:
    if not src.exists() or not src.is_dir():
        raise ValueError(f"{src} is not a valid directory.")

    dst_dir.mkdir(parents=True, exist_ok=True)
    md_file = dst_dir / f"{src.name}_filemap.md"

    content  = f"# File Structure: {src}\n\n"
    content += f"📁 **{src.name}/**\n"
    content += _tree_md(src) + "\n"

    md_file.write_text(content, encoding="utf-8")
    return md_file


def _cli() -> None:
    p = argparse.ArgumentParser(
        prog="export-markdown",
        description="Create a Markdown tree of a directory and save it to Downloads."
    )
    p.add_argument("directory", type=Path, help="Directory to map")
    args = p.parse_args()

    downloads = _downloads_dir()
    try:
        target = create_filemap(args.directory.resolve(), downloads)
        print(f"✅  Markdown saved to {target}")
    except Exception as exc:
        print(f"❌  {exc}")
        sys.exit(1)

    _open_folder(downloads)


if __name__ == "__main__":
    _cli()
