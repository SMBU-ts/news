# -*- coding: utf-8 -*-
"""Incremental push via GitHub Git Data API.

Pushes ONLY the currently-staged/committed-vs-remote diff, using 3 API calls:
  create tree (with inline content) -> create commit -> update ref.

Much faster and far more resilient on flaky networks than tools/api_push_all.py
(which uploads one blob per file in the whole tree, ~460 calls).

Usage:
  python tools/api_push_incremental.py [commit_message]

Requires: gh CLI logged in, HEAD is the commit to publish, remote main == HEAD~1.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile

GH = r"C:/Program Files/GitHub CLI/gh.exe"
REPO = "SMBU-ts/news"
BRANCH = "main"


def run(cmd, stdin=None, check=True):
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, shell=isinstance(cmd, str))
    if check and p.returncode != 0:
        raise RuntimeError("cmd failed: %s\n%s" % (cmd, p.stderr.decode("utf-8", "replace")))
    return p


def gh(args, body=None):
    """Call gh api with an optional JSON body supplied via --input file."""
    if body is None:
        p = run([GH, "api"] + args)
    else:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        try:
            p = run([GH, "api"] + args + ["--input", tmp])
        finally:
            os.remove(tmp)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace"))
    return json.loads(p.stdout.decode("utf-8"))


def git(*args):
    p = run(["git"] + list(args))
    return p.stdout.decode("utf-8", "replace").strip()


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "update"

    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD~1")
    local_tree = git("rev-parse", "HEAD^{tree}")

    remote = gh(["repos/%s/commits/%s" % (REPO, BRANCH)])["sha"]
    if remote != parent:
        print("ABORT: remote %s != local HEAD~1 %s; rebase needed" % (remote[:9], parent[:9]))
        return 2
    print("remote==parent==%s  ok" % parent[:9])

    # paths changed in HEAD vs parent
    paths = git("diff", "--name-only", "HEAD~1", "HEAD").splitlines()
    paths = [p for p in paths if p]
    print("changed paths: %d" % len(paths))
    if not paths:
        print("nothing to push")
        return 0

    entries = []
    for path in paths:
        # stored (LF-normalized) blob content, exactly what git would upload
        blob = git("rev-parse", "HEAD:%s" % path)
        raw = run(["git", "cat-file", "blob", blob]).stdout
        text = raw.decode("utf-8")
        entries.append({"path": path, "mode": "100644", "type": "blob",
                        "content": text})

    base_tree = gh(["repos/%s/git/commits/%s" % (REPO, parent)])["tree"]["sha"]
    new_tree = gh(["repos/%s/git/trees" % REPO], {"base_tree": base_tree, "tree": entries})
    print("new tree: %s" % new_tree["sha"])
    if new_tree["sha"] == local_tree:
        print("tree matches local commit tree  (content identical)")
    else:
        print("NOTE: tree differs from local (%s)" % local_tree[:9])

    commit = gh(["repos/%s/git/commits" % REPO],
                {"message": msg, "tree": new_tree["sha"], "parents": [parent]})
    print("new commit: %s" % commit["sha"])

    gh(["repos/%s/git/refs/heads/%s" % (REPO, BRANCH)],
       {"sha": commit["sha"], "force": False})
    print("ref %s updated" % BRANCH)

    # keep the local branch pointing at the same commit (same tree, no divergence)
    git("update-ref", "refs/heads/%s" % BRANCH, commit["sha"])
    print("local ref synced -> %s" % commit["sha"][:9])
    print("STATUS:", git("status", "--short") or "(clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
