#!/usr/bin/env python3
"""Push all local files to GitHub via Git Data API (force update).

Usage:
    python tools/api_push_all.py

This script creates a new commit on top of the remote HEAD,
replacing the entire tree with the local working directory.
"""

import subprocess
import json
import base64
from pathlib import Path

GH = r"C:/Program Files/GitHub CLI/gh.exe"
REPO = "SMBU-ts/news"
BRANCH = "main"
ROOT = Path(__file__).resolve().parent.parent

# Files to exclude (same as .gitignore + binary patterns)
EXCLUDE_DIRS = {".workbuddy", "__pycache__", ".git", "output", ".backup_0721"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".log", ".DS_Store"}


def gh_api(path, method="GET", input_data=None):
    cmd = [GH, "api", "-X", method]
    if input_data:
        cmd.extend(["--input", "-"])
    cmd.append(path)
    r = subprocess.run(
        cmd,
        input=json.dumps(input_data) if input_data else None,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if r.returncode != 0:
        print(f"  GH ERROR [{method} {path}]: {r.stderr.strip()}")
        return None
    return json.loads(r.stdout) if r.stdout.strip() else {}


def collect_local_files():
    """Collect all files that should be tracked in git."""
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        parts = rel.parts
        # Exclude directories
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        # Exclude raw text files
        if "raw" in parts and str(rel).endswith(".txt"):
            continue
        # Exclude by extension
        if path.suffix in EXCLUDE_EXTS:
            continue
        # Exclude .gitignore patterns
        rel_str = str(rel).replace("\\", "/")
        files.append(rel_str)
    return sorted(files)


def create_blob(filepath):
    with open(ROOT / filepath, "rb") as f:
        content = f.read()
    b64 = base64.b64encode(content).decode("ascii")
    result = gh_api(f"repos/{REPO}/git/blobs", method="POST", input_data={
        "content": b64,
        "encoding": "base64",
    })
    return result.get("sha") if result else None


def main():
    # Get remote HEAD
    ref = gh_api(f"repos/{REPO}/git/refs/heads/{BRANCH}")
    if not ref:
        print("ERROR: Cannot get remote ref")
        return
    base_sha = ref["object"]["sha"]
    print(f"Remote HEAD: {base_sha[:8]}")

    # Collect local files
    local_files = collect_local_files()
    print(f"Local files to push: {len(local_files)}")

    # Create blobs for all files
    tree_entries = []
    for filepath in local_files:
        sha = create_blob(filepath)
        if not sha:
            print(f"  FAILED {filepath}")
            continue
        mode = "100755" if filepath.endswith((".sh", ".py")) else "100644"
        tree_entries.append({
            "path": filepath,
            "mode": mode,
            "type": "blob",
            "sha": sha,
        })
    print(f"Created {len(tree_entries)} blobs")

    # Create tree
    tree_result = gh_api(f"repos/{REPO}/git/trees", method="POST", input_data={
        "tree": tree_entries,
    })
    if not tree_result:
        print("ERROR: Cannot create tree")
        return
    print(f"Tree: {tree_result['sha'][:8]}")

    # Create commit
    commit_msg = (
        "hotsearch 2026-07-23\n\n"
        "- 每日热搜：五平台（微博/百度/今日头条/知乎/哔哩哔哩）各综合排名前10热点，共50条；"
        "agent 预生成 100-200 字中文摘要替代易失效的 Bing 抓取\n"
        "- 重建站点聚合页（index/archive/sitemap），热搜分类融入首页与归档\n"
        "- 同步当日 daily20 与每日新闻生成产物"
    )
    commit_result = gh_api(f"repos/{REPO}/git/commits", method="POST", input_data={
        "message": commit_msg,
        "tree": tree_result["sha"],
        "parents": [base_sha],
    })
    if not commit_result:
        print("ERROR: Cannot create commit")
        return
    print(f"Commit: {commit_result['sha'][:8]}")

    # Force update ref
    ref_result = gh_api(f"repos/{REPO}/git/refs/heads/{BRANCH}", method="PATCH", input_data={
        "sha": commit_result["sha"],
        "force": True,
    })
    if not ref_result:
        print("ERROR: Cannot update ref")
        return
    print(f"\nPUSHED! {commit_result['sha'][:8]}")
    print(f"GitHub Actions will deploy to https://smbu-ts.github.io/news/")


if __name__ == "__main__":
    main()
