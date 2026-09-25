"""Maintainer research helper; output goes to ignored local files."""

import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(".local/research")
ROOT.mkdir(parents=True, exist_ok=True)


def get(url: str) -> bytes:
    with urlopen(url, timeout=60) as response:
        return response.read()


commit = json.loads(get("https://api.github.com/repos/logpai/loghub/commits/master"))["sha"]
print("LOGHUB COMMIT", commit)
for name in ["Apache", "OpenStack", "BGL", "HDFS", "Zookeeper"]:
    base = f"https://raw.githubusercontent.com/logpai/loghub/{commit}/{name}/{name}_2k.log"
    raw = get(base)
    structured = get(base + "_structured.csv")
    rows = list(csv.DictReader(io.StringIO(structured.decode())))
    (ROOT / f"{name}.log").write_bytes(raw)
    (ROOT / f"{name}.csv").write_bytes(structured)
    print(
        name,
        "bytes",
        len(raw),
        "lines",
        len(raw.splitlines()),
        "sha256",
        hashlib.sha256(raw).hexdigest(),
    )
    print("schema", list(rows[0]), "sample", rows[0])
for article in [12693914, 12692378]:
    try:
        meta = json.loads(get(f"https://api.figshare.com/v2/articles/{article}"))
        (ROOT / f"{article}.json").write_text(json.dumps(meta, indent=2))
        print("BPI", meta.get("title"), meta.get("license"), meta.get("files"))
        for item in meta.get("files", []):
            raw = get(item["download_url"])
            (ROOT / item["name"]).write_bytes(raw)
            print("downloaded", item["name"], len(raw), hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        print("BPI unavailable", article, str(exc))
