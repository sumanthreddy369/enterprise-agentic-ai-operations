"""Narrow tracked-file exposure gate. Does not replace a dedicated secret scanner."""

import re
import subprocess
from pathlib import Path

names = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
problems = []
patterns = [rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
for name in filter(None, names):
    path = Path(name)
    if path.name.startswith(".env") and path.name != ".env.example":
        problems.append(f"{name}: environment file must not be tracked")
    if path.suffix in {".db", ".safetensors", ".pt"}:
        problems.append(f"{name}: generated/sensitive artifact must not be tracked")
    if (
        name.startswith(("data/raw/", "data/bronze/", "data/silver/", "data/gold/"))
        and path.name != ".gitkeep"
    ):
        problems.append(f"{name}: dataset content must not be tracked")
    if path.stat().st_size > 2_000_000:
        problems.append(f"{name}: file exceeds repository size policy")
    if any(re.search(pattern, path.read_bytes()) for pattern in patterns):
        problems.append(f"{name}: potential credential/private key")
if problems:
    raise SystemExit("\n".join(problems))
print("Tracked-file exposure checks passed (limited patterns; not a complete secret scan).")
