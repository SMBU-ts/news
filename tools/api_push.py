#!/usr/bin/env python3
"""Push commits to GitHub using the Git Data API (fallback when HTTPS git is blocked).

Usage:
    python tools/api_push.py

Requires: gh CLI authenticated with repo scope.
"""
import subprocess
import json
import os
import sys
import base64
from pathlib import Path

GH = r"C:/Program Files/GitHub CLI/gh.exe"
REPO = "SMBU-ts/news"
BRANCH = "main"
ROOT = Path(__file__).resolve().parent.parent


def gh(*args, method="GET"):
    cmd = [GH, "api", "-X", method]
    cmd.extend([str(a) for a in args])
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        print(f"GH ERROR [{method}]: {r.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(r.stdout) if r.stdout.strip() else {}


def gh_raw(*args, method="GET", input_data=None):
    cmd = [GH, "api", "-X", method]
    if input_data:
        cmd.extend(["--input", "-"])
    cmd.extend([str(a) for a in args])
    r = subprocess.run(
        cmd,
        input=json.dumps(input_data) if input_data else None,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if r.returncode != 0:
        print(f"GH ERROR [{method}]: {r.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(r.stdout) if r.stdout.strip() else {}


def create_blob(filepath):
    with open(ROOT / filepath, "rb") as f:
        content = f.read()
    b64 = base64.b64encode(content).decode("ascii")
    result = gh_raw(f"repos/{REPO}/git/blobs", method="POST", input_data={
        "content": b64,
        "encoding": "base64",
    })
    return result["sha"] if result else None


def main():
    ref = gh(f"repos/{REPO}/git/refs/heads/{BRANCH}")
    if not ref:
        sys.exit(1)
    base_sha = ref["object"]["sha"]
    print(f"Remote HEAD: {base_sha[:8]}")

    base_commit = gh(f"repos/{REPO}/git/commits/{base_sha}")
    base_tree_sha = base_commit["tree"]["sha"]

    local_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()

    result = subprocess.run(
        ["git", "diff", "--name-status", base_sha, local_sha],
        capture_output=True, text=True, cwd=ROOT
    )
    changes = []
    for line in result.stdout.strip().split("\n"):
        if not line: continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            changes.append((parts[0], parts[1]))

    print(f"Files to update: {len(changes)}")

    tree_entries = []
    for status, filepath in changes:
        if status == "D":
            tree_entries.append({
                "path": filepath.replace("\\", "/"),
                "mode": "100644", "type": "blob", "sha": None,
            })
        else:
            sha = create_blob(filepath)
            if not sha:
                print(f"  FAILED {filepath}")
                continue
            mode = "100755" if filepath.endswith((".sh", ".py")) else "100644"
            tree_entries.append({
                "path": filepath.replace("\\", "/"),
                "mode": mode, "type": "blob", "sha": sha,
            })
            print(f"  OK {filepath}")

    if not tree_entries:
        print("No files to push"); return

    tree_result = gh_raw(f"repos/{REPO}/git/trees", method="POST", input_data={
        "base_tree": base_tree_sha, "tree": tree_entries,
    })
    if not tree_result:
        sys.exit(1)

    commit_result = gh_raw(f"repos/{REPO}/git/commits", method="POST", input_data={
        "message": subprocess.run(
            ["git", "log", "-1", "--format=%s", local_sha],
            capture_output=True, text=True, cwd=ROOT
        ).stdout.strip(),
        "tree": tree_result["sha"],
        "parents": [base_sha],
    })
    if not commit_result:
        sys.exit(1)

    ref_result = gh_raw(f"repos/{REPO}/git/refs/heads/{BRANCH}", method="PATCH", input_data={
        "sha": commit_result["sha"], "force": False,
    })
    if not ref_result:
        sys.exit(1)
    print(f"PUSHED! {commit_result['sha'][:8]}")


if __name__ == "__main__":
    main()
