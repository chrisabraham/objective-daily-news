#!/usr/bin/env python3
"""
assemble_podcast_parts.py — rebuild the podcast binaries from their
chunked base64 parts.

The GitHub connector on the desk's seat caps a single command-line
argument at ~128 KB, so MP3s and the cover art cannot ride push_files
in one call. They travel instead as text parts under podcast-parts/,
listed in podcast-parts.json with byte counts and SHA-256 digests.
Run this on any seat holding the site tree; it verifies every digest
before writing, and writes nothing for a file whose parts fail.

    python3 assemble_podcast_parts.py [--check]
"""

import base64
import hashlib
import json
import os
import sys

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(SITE_DIR, "podcast-parts.json")
PARTS_DIR = os.path.join(SITE_DIR, "podcast-parts")


def main():
    check_only = "--check" in sys.argv
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    bad = 0
    for rel, meta in sorted(manifest["files"].items()):
        blob = b"".join(
            base64.b64decode(open(os.path.join(PARTS_DIR, p)).read())
            for p in meta["parts"]
        )
        ok = (len(blob) == meta["bytes"]
              and hashlib.sha256(blob).hexdigest() == meta["sha256"])
        if not ok:
            print(f"assemble: MISMATCH {rel}; not written")
            bad += 1
            continue
        if check_only:
            print(f"assemble: ok {rel} ({meta['bytes']} bytes, verified)")
            continue
        dest = os.path.join(SITE_DIR, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(blob)
        print(f"assemble: wrote {rel} ({meta['bytes']} bytes, sha256 verified)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
