# -*- coding: utf-8 -*-
"""Rebuild a remote commit object locally from GitHub API metadata.

Needed after an API-side push (tools/api_push_incremental.py): the new commit
object exists on the server but not in the local object database, so
`git update-ref refs/heads/main <sha>` would fail. Reconstructing the raw
commit object byte-for-byte yields the identical SHA, so the local branch can
be moved onto it without diverging.

Usage: python tools/gh_materialize_commit.py <sha> [repo]
"""
import json
import os
import subprocess
import sys
import tempfile
import time

GH = r"C:/Program Files/GitHub CLI/gh.exe"


def gh_json(args):
    p = subprocess.run([GH, "api"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace"))
    return json.loads(p.stdout.decode("utf-8"))


def epoch(datestr):
    """ISO8601 -> unix seconds. Handles trailing Z / offsets via datetime."""
    from datetime import datetime, timezone
    d = datestr.replace("Z", "+00:00")
    return int(datetime.fromisoformat(d).timestamp())


def main():
    sha = sys.argv[1]
    repo = sys.argv[2] if len(sys.argv) > 2 else "SMBU-ts/news"

    meta = gh_json(["repos/%s/git/commits/%s" % (repo, sha)])

    # GitHub's API-created commits carry the pusher's local UTC offset and the
    # message with no trailing newline; the API reports the date normalized to
    # UTC ("Z"), so undo that shift to recover the stored offset.
    a, c = meta["author"], meta["committer"]
    ts = epoch(c["date"])
    offset = -time.timezone if not time.daylight else -time.altzone
    tz = "%+03d00" % (offset // 3600)
    lines = ["tree %s" % meta["tree"]["sha"]]
    for p in meta.get("parents", []):
        lines.append("parent %s" % p["sha"])
    lines.append("author %s <%s> %d %s" % (a["name"], a["email"], ts, tz))
    lines.append("committer %s <%s> %d %s" % (c["name"], c["email"], ts, tz))
    body = ("\n".join(lines) + "\n\n" + meta["message"]).encode("utf-8")

    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    with open(tmp, "wb") as f:
        f.write(body)
    try:
        p = subprocess.run(["git", "hash-object", "-t", "commit", "-w", tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        os.remove(tmp)
    got = p.stdout.decode().strip()
    print("reconstructed: %s" % got)
    print("expected     : %s" % sha)
    if got != sha:
        print("MISMATCH - object written but not identical; do not update ref")
        return 1
    print("MATCH ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
