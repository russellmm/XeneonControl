"""Create releases from an explicit source allowlist, excluding all research binaries."""
import hashlib
from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parent
release = root / "release"
release.mkdir(exist_ok=True)
sources = ["xeneon_control.py", "background_refresh.py", "protocol.py", "transport.py", "settings.py", "tray.py", "tray.ico", "test_protocol.py", "test_refresh.py", "test_ui.py", "test_tray.py",
           "README.md", "PROTOCOL.md", "LICENSE", "THIRD-PARTY-NOTICES.md",
           "70-xeneon-control.rules", "install-ubuntu.sh", "launch-ubuntu.sh", "Build-Windows.ps1", "package_release.py"]
for name in sources:
    assert (root / name).is_file(), name

with tarfile.open(release / "XeneonControl-Ubuntu.tar.gz", "w:gz") as archive:
    for name in sources:
        info = archive.gettarinfo(str(root / name), arcname="XeneonControl/" + name)
        info.mode = 0o755 if name.endswith(".sh") else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        with (root / name).open("rb") as source:
            archive.addfile(info, source)

with zipfile.ZipFile(release / "XeneonControl-Source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for name in sources:
        archive.write(root / name, "XeneonControl/" + name)

with zipfile.ZipFile(release / "XeneonControl-Windows.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(release / "XeneonControl.exe", "XeneonControl/XeneonControl.exe")
    for name in ("README.md", "LICENSE", "THIRD-PARTY-NOTICES.md"):
        archive.write(root / name, "XeneonControl/" + name)
    for path in sorted((release / "third-party-licenses").iterdir()):
        archive.write(path, "XeneonControl/third-party-licenses/" + path.name)

for name in ("README.md", "LICENSE", "THIRD-PARTY-NOTICES.md"):
    (release / name).write_bytes((root / name).read_bytes())

deliverables = [release / n for n in ("XeneonControl.exe", "XeneonControl-Windows.zip", "XeneonControl-Ubuntu.tar.gz", "XeneonControl-Source.zip")]
(release / "SHA256SUMS.txt").write_text("\n".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in deliverables) + "\n")
for path in deliverables:
    print(path.name, path.stat().st_size)
