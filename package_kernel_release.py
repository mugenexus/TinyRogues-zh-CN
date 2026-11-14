"""Build and round-trip verify a delta-only release from the community 9.14 package."""

import argparse
import gc
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from build_kernel_preview import METADATA, RESOURCE, build, checked_path, digest


def package(vanilla, archive, decoded, installed, output):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        preview = root / "preview"
        build(vanilla, archive, decoded, preview)
        gc.collect()  # Release UnityPy's asset handles before replacing files on Windows.
        payload = root / "patch"
        payload.mkdir()
        manifest_name = "patch-manifest.json"
        with zipfile.ZipFile(archive) as source:
            name, = (n for n in source.namelist() if n.endswith("/" + manifest_name))
            prefix = name.rsplit("/", 1)[0] + "/"
            manifest = json.loads(source.read(name))
            for name in ("install.py", "xdelta3.exe", "xdelta3-LICENSE"):
                (payload / name).write_bytes(source.read(prefix + name))
            decoder = payload / "xdelta3.exe"
            if digest(decoder) != manifest["xdelta_sha256"]:
                raise ValueError("Unexpected decoder hash")
            for row in manifest["files"]:
                rel = checked_path(row["file"])
                target = preview / rel
                expected = digest(target)
                if digest(installed / rel) != expected:
                    raise ValueError(f"Build differs from Steam installation: {rel}")
                delta = payload / checked_path(row["delta"])
                delta.parent.mkdir(parents=True, exist_ok=True)
                if rel in {RESOURCE, METADATA}:
                    subprocess.run([str(decoder), "-e", "-s", str(vanilla / rel),
                                    str(target), str(delta)], check=True)
                    row["after"] = {"sha256": expected, "size": target.stat().st_size}
                    row["delta_sha256"] = digest(delta)
                else:
                    delta.write_bytes(source.read(prefix + row["delta"]))
                    if digest(delta) != row["delta_sha256"]:
                        raise ValueError(f"Unexpected delta hash: {rel}")
        manifest["playtest_verified"] = False
        (payload / manifest_name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        for name in manifest["baseline"]:
            rel = checked_path(name)
            shutil.copyfile(vanilla / rel, preview / rel)
        spec = importlib.util.spec_from_file_location("kernel_installer", payload / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.install(payload, preview)
        for row in manifest["files"]:
            if digest(preview / checked_path(row["file"])) != row["after"]["sha256"]:
                raise ValueError(f"Test install mismatch: {row['file']}")
        installer.install(payload, preview, rollback=True)
        for name, info in manifest["baseline"].items():
            if digest(preview / checked_path(name)) != info["sha256"]:
                raise ValueError(f"Test rollback mismatch: {name}")
        with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as release:
            for path in payload.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    release.write(path, path.relative_to(payload).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("vanilla", "archive", "decoded", "installed", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    package(*(path.resolve() for path in vars(args).values()))
