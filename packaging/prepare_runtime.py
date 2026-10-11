"""Prepare a pinned, SHA-256 verified Windows runtime for a source build."""
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "runtime"
CACHE.mkdir(parents=True, exist_ok=True)

def fetch(url, digest):
    file = CACHE / url.rsplit("/", 1)[-1]
    if file.exists() and hashlib.sha256(file.read_bytes()).hexdigest() == digest:
        return file
    temporary = file.with_suffix(file.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=90) as source, temporary.open("wb") as out:
            shutil.copyfileobj(source, out, 1024 * 1024)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            raise ValueError("Runtime SHA-256 mismatch: " + file.name)
        temporary.replace(file)
        return file
    finally:
        temporary.unlink(missing_ok=True)

def extract(archive, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            if not (folder / name).resolve().is_relative_to(folder.resolve()):
                raise ValueError("Unsafe archive member")
        zipped.extractall(folder)

meta = json.loads((ROOT / "packaging/provenance.json").read_text())
runtime = ROOT / "runtime/quant-python"
extract(fetch(meta["url"], meta["sha256"]), runtime)
for wheel in meta["wheels"]:
    extract(fetch(wheel["url"], wheel["sha256"]), runtime / "Lib/site-packages")
(runtime / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n../app\n../app/workers\nimport site\n")
print("Verified Windows numerical runtime:", runtime)
