"""Launch one verified Diablo package directly on a MiSTer target.

The launcher is copied into every release package and uses only Python's
standard library on the target. It verifies the package before loading its RBF,
creates a current-boot DDR admission, owns the transport lease for the child,
and keeps user game data outside the immutable package.
"""
from __future__ import annotations

import argparse
import errno
import datetime as dt
try:
    import fcntl
except ImportError:  # pragma: no cover - the production target is Linux.
    fcntl = None  # type: ignore[assignment]
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from typing import Any


PACKAGE_SCHEMA = "diablo-package-manifest-v2"
DEPLOYMENT_SCHEMA = "diablo-deployment-manifest-v2"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
BOOT_ID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
PRIVATE_MARKERS = (".mpq", ".sav", ".sve", "private", "secret", "password", "token")
SHARED_BYTES = 2 * 1024 * 1024
MISTER_INSTALL_STATE = Path("/media/fat/.diablo-install.json")
CAMPAIGN_FILES = {
    "diablo": ("diabdat.mpq",),
    "hellfire": ("diabdat.mpq", "hellfire.mpq", "hfmonk.mpq", "hfmusic.mpq", "hfvoice.mpq"),
}


class LaunchError(RuntimeError):
    """The package did not reach a safe runnable state."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_cached(path: Path, cache: dict[Path, tuple[int, int, int, int, str]]) -> str:
    """Hash each unchanged package file once during launch verification."""
    stat = path.stat()
    signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    cached = cache.get(path)
    if cached is not None and cached[:4] == signature:
        return cached[4]
    digest = sha256_file(path)
    cache[path] = (*signature, digest)
    return digest


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _relative(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LaunchError(f"{label} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise LaunchError(f"{label} must stay below the package root")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise LaunchError(f"{label} escapes the package root") from error
    return path


def _real_file(root: Path, value: object, label: str) -> Path:
    relative = _relative(root, value, label)
    path = root / relative
    if path.is_symlink() or not path.is_file() or path.resolve().is_symlink():
        raise LaunchError(f"{label} is missing or is a symlink: {relative}")
    return path.resolve()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LaunchError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise LaunchError(f"{label} must be a JSON object")
    return value


def _file_records(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise LaunchError(f"package contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = path
    return result


def verify_package(root: Path) -> dict[str, Any]:
    """Verify package metadata without importing any project code."""
    root = root.resolve()
    hash_cache: dict[Path, tuple[int, int, int, int, str]] = {}
    package = _read_json(_real_file(root, "package-manifest.json", "package manifest"), "package manifest")
    if package.get("schema") != PACKAGE_SCHEMA or package.get("status") != "pass":
        raise LaunchError("unsupported or non-passing package manifest")
    if package.get("private_data_excluded") is not True:
        raise LaunchError("package manifest does not exclude private data")
    for field in ("candidate_id", "source_id"):
        if not HEX64.fullmatch(str(package.get(field, ""))):
            raise LaunchError(f"package manifest {field} is invalid")
    deployment_record = package.get("deployment_manifest")
    if not isinstance(deployment_record, dict) or deployment_record.get("path") != "deployment.json":
        raise LaunchError("package manifest has no deployment manifest")
    deployment_path = _real_file(root, "deployment.json", "deployment manifest")
    if deployment_record.get("sha256") != _sha256_cached(deployment_path, hash_cache):
        raise LaunchError("deployment manifest hash does not match package manifest")
    deployment = _read_json(deployment_path, "deployment manifest")
    if deployment.get("schema") != DEPLOYMENT_SCHEMA or deployment.get("status") != "pass":
        raise LaunchError("unsupported or non-passing deployment manifest")
    if deployment.get("private_data_excluded") is not True:
        raise LaunchError("deployment manifest does not exclude private data")
    if deployment.get("candidate_id") != package.get("candidate_id") or deployment.get("source_id") != package.get("source_id"):
        raise LaunchError("package and deployment identities differ")
    roles = {record.get("role") for record in deployment.get("artifacts", []) if isinstance(record, dict)}
    if roles != {"engine", "rbf", "abi", "launcher"}:
        raise LaunchError("deployment manifest does not contain all runtime roles")
    expected_role_paths = {"engine": "devilutionx", "rbf": "Diablo.rbf",
                           "abi": "transport_abi.hex", "launcher": "diablo_launcher.py"}
    for record in deployment.get("artifacts", []):
        if isinstance(record, dict) and record.get("role") in expected_role_paths:
            if record.get("path") != expected_role_paths[record["role"]]:
                raise LaunchError(f"deployment artifact path for {record['role']} must be {expected_role_paths[record['role']]}")
    files = _file_records(root)
    listed: set[str] = set()
    records = package.get("files")
    if not isinstance(records, list):
        raise LaunchError("package manifest files are missing")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise LaunchError("package file record is malformed")
        relative = _relative(root, record["path"], "package file").as_posix()
        if relative in listed:
            raise LaunchError(f"package file is listed twice: {relative}")
        listed.add(relative)
        path = files.get(relative)
        if path is None or record.get("bytes") != path.stat().st_size or record.get("sha256") != _sha256_cached(path, hash_cache):
            raise LaunchError(f"package file hash/size mismatch: {relative}")
    expected = set(files) - {"package-manifest.json"}
    if listed != expected:
        raise LaunchError("package manifest does not cover exactly the installed package")
    for record in deployment.get("artifacts", []):
        if not isinstance(record, dict):
            continue
        path = _real_file(root, record.get("path"), "deployment artifact")
        if record.get("bytes") != path.stat().st_size or record.get("sha256") != _sha256_cached(path, hash_cache):
            raise LaunchError(f"deployment artifact hash/size mismatch: {record.get('role')}")
    assets = deployment.get("runtime_assets")
    if not isinstance(assets, dict) or assets.get("path") != "assets":
        raise LaunchError("deployment asset tree is missing")
    asset_records = assets.get("files")
    if not isinstance(asset_records, list):
        raise LaunchError("deployment asset records are missing")
    current_assets: list[dict[str, Any]] = []
    assets_root = _real_file(root, "assets", "assets directory") if (root / "assets").is_file() else root / "assets"
    if not assets_root.is_dir() or assets_root.is_symlink():
        raise LaunchError("assets directory is missing")
    for path in sorted(assets_root.rglob("*"), key=lambda item: item.relative_to(assets_root).as_posix()):
        if path.is_symlink():
            raise LaunchError(f"assets tree contains a symlink: {path}")
        if path.is_file():
            current_assets.append({"path": path.relative_to(assets_root).as_posix(),
                                   "bytes": path.stat().st_size, "sha256": _sha256_cached(path, hash_cache)})
    current_assets.sort(key=lambda item: str(item["path"]))
    listed_assets = sorted(asset_records, key=lambda item: str(item.get("path")) if isinstance(item, dict) else "")
    if listed_assets != current_assets or assets.get("bytes") != sum(item["bytes"] for item in current_assets):
        raise LaunchError("deployment asset tree hash/size mismatch")
    if assets.get("sha256") != hashlib.sha256(canonical_bytes(current_assets)).hexdigest():
        raise LaunchError("deployment asset tree digest mismatch")
    return {"candidate_id": package["candidate_id"], "source_id": package["source_id"],
            "board_profile": package.get("board_profile"), "deployment": deployment}


def _managed_package_identity(root: Path) -> dict[str, Any] | None:
    """Validate installed identity and entrypoints without scanning asset directories.

    Deployment already performs the complete content-hash verification before
    publishing a release.  On the target, re-hashing the 17 MiB package on
    every RBF selection delays the first video. Even a metadata-only recursive
    scan takes tens of seconds on a cold MiSTer SD filesystem. Trust the
    deployment receipt for assets; check manifest hashes and runtime entrypoints
    here. Full file/asset auditing remains available with
    DIABLO_MISTER_VERIFY_FULL=1. Direct Downloader installs at _Other/Diablo
    use their package manifest rather than an unrelated transactional receipt.
    """
    try:
        if os.environ.get("DIABLO_MISTER_VERIFY_FULL") == "1":
            return None
        root = root.resolve()
        legacy_root = (MISTER_INSTALL_STATE.parent / "_Other" / "Diablo").resolve()
        direct_install = root == legacy_root
        state = {} if direct_install else _read_json(MISTER_INSTALL_STATE, "MiSTer install state")
        release = state.get("active_release")
        expected_root = (MISTER_INSTALL_STATE.parent / release).resolve() if isinstance(release, str) else None
        legacy_root = (MISTER_INSTALL_STATE.parent / "_Other" / "Diablo").resolve()
        if not direct_install and (state.get("status") != "pass" or state.get("board_profile") != "de10-nano-mister"
                                   or root != expected_root):
            return None

        package_path = _real_file(root, "package-manifest.json", "package manifest")
        package = _read_json(package_path, "package manifest")
        if (package.get("schema") != PACKAGE_SCHEMA or package.get("status") != "pass"
                or package.get("board_profile") != "de10-nano-mister"
                or package.get("private_data_excluded") is not True):
            return None
        candidate_id = str(package.get("candidate_id", ""))
        source_id = str(package.get("source_id", ""))
        if (not HEX64.fullmatch(candidate_id) or not HEX64.fullmatch(source_id)
                or (not direct_install and (state.get("active_candidate_id") != candidate_id
                    or state.get("active_package_manifest_sha256") != sha256_file(package_path)))):
            return None

        deployment_record = package.get("deployment_manifest")
        deployment_path = _real_file(root, "deployment.json", "deployment manifest")
        if (not isinstance(deployment_record, dict)
                or deployment_record.get("path") != "deployment.json"
                or deployment_record.get("sha256") != sha256_file(deployment_path)):
            return None
        deployment = _read_json(deployment_path, "deployment manifest")
        if (deployment.get("schema") != DEPLOYMENT_SCHEMA or deployment.get("status") != "pass"
                or deployment.get("private_data_excluded") is not True
                or deployment.get("candidate_id") != candidate_id
                or deployment.get("source_id") != source_id):
            return None

        expected_roles = {"engine": "devilutionx", "rbf": "Diablo.rbf",
                          "abi": "transport_abi.hex", "launcher": "diablo_launcher.py"}
        artifacts = deployment.get("artifacts")
        if not isinstance(artifacts, list) or {item.get("role") for item in artifacts if isinstance(item, dict)} != set(expected_roles):
            return None
        for item in artifacts:
            if not isinstance(item, dict) or item.get("role") not in expected_roles:
                return None
            if item.get("path") != expected_roles[item["role"]]:
                return None
            artifact = _real_file(root, item["path"], "deployment artifact")
            if item.get("bytes") != artifact.stat().st_size:
                return None

        records = package.get("files")
        if not isinstance(records, list):
            return None
        listed: dict[str, dict[str, Any]] = {}
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                return None
            relative = item["path"]
            if (relative in listed or "\\" in relative
                    or any(part in {"", ".", ".."} for part in relative.split("/"))):
                return None
            listed[relative] = item
        for item in artifacts:
            record = listed.get(item["path"])
            if (record is None or record.get("bytes") != item.get("bytes")
                    or record.get("sha256") != item.get("sha256")):
                return None

        assets = deployment.get("runtime_assets")
        if not isinstance(assets, dict) or assets.get("path") != "assets" or not isinstance(assets.get("files"), list):
            return None
        assets_root = root / "assets"
        if not assets_root.is_dir() or assets_root.is_symlink():
            return None
        current_assets = [{"path": relative[len("assets/"):], "bytes": record.get("bytes"),
                           "sha256": record.get("sha256")}
                          for relative, record in sorted(listed.items())
                          if relative.startswith("assets/")]
        if (assets["files"] != current_assets
                or assets.get("bytes") != sum(item["bytes"] for item in current_assets)
                or assets.get("sha256") != hashlib.sha256(canonical_bytes(current_assets)).hexdigest()):
            return None
        return {"candidate_id": candidate_id, "source_id": source_id,
                "board_profile": package.get("board_profile"), "deployment": deployment}
    except (OSError, TypeError, ValueError, LaunchError):
        return None


def _writable(path: Path, label: str) -> Path:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise LaunchError(f"{label} must be a real directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise LaunchError(f"{label} must not be a symlink: {path}")
    probe = path / (".diablo-write-probe-" + secrets.token_hex(8))
    try:
        probe.write_bytes(b"probe\n")
    except OSError as error:
        raise LaunchError(f"{label} is not writable: {path}: {error}") from error
    finally:
        try:
            probe.unlink()
        except FileNotFoundError:
            pass
    return path.resolve()


def _stage_hellfire_mod(package: Path, save_root: Path) -> None:
    """Use a packed, identifiable mod and preserve old loose files outside saves."""
    source = package / "assets" / "mods" / "hf.mpq"
    if source.is_symlink() or not source.is_file():
        raise LaunchError("package is missing the packed Hellfire mod")
    mods = save_root / "mods"
    if mods.is_symlink() or (mods.exists() and not mods.is_dir()):
        raise LaunchError(f"Hellfire mod staging path is not a real directory: {mods}")
    mods.mkdir(parents=True, exist_ok=True)
    destination = mods / "hf.mpq"
    if destination.is_symlink() or (destination.exists() and
            (not destination.is_file() or sha256_file(destination) != sha256_file(source))):
        raise LaunchError(f"existing Hellfire mod differs from package: {destination}")
    legacy = mods / "hf"
    backup = save_root.parent / (save_root.name + ".legacy-hf")
    if legacy.is_symlink() or (legacy.exists() and not legacy.is_dir()):
        raise LaunchError(f"legacy Hellfire mod is not a real directory: {legacy}")
    if legacy.exists():
        if backup.exists() or backup.is_symlink():
            raise LaunchError(f"legacy Hellfire backup already exists: {backup}")
        bundled = package / "assets" / "mods" / "hf"
        for path in legacy.rglob("*"):
            expected = bundled / path.relative_to(legacy)
            if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                raise LaunchError(f"unsupported legacy Hellfire entry: {path}")
            if path.is_file() and (not expected.is_file() or
                    sha256_file(path) != sha256_file(expected)):
                raise LaunchError(f"existing Hellfire mod differs from package: {path}")
    if not destination.exists():
        temporary = mods / "hf.mpq.tmp"
        if temporary.exists() or temporary.is_symlink():
            raise LaunchError(f"Hellfire staging file already exists: {temporary}")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    if legacy.exists():
        legacy.rename(backup)

def _boot_id(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
    except OSError as error:
        raise LaunchError(f"cannot read boot ID: {path}: {error}") from error
    if not BOOT_ID.fullmatch(value):
        raise LaunchError("boot ID is not a kernel UUID")
    return value


def _unsigned(value: str, label: str) -> int:
    if not value or value.startswith(("+", "-")):
        raise LaunchError(f"{label} must be unsigned")
    try:
        result = int(value, 0)
    except ValueError as error:
        raise LaunchError(f"{label} must be unsigned") from error
    if result < 0:
        raise LaunchError(f"{label} must be unsigned")
    return result


def _data_file(data_root: Path, name: str) -> Path | None:
    wanted = name.casefold()
    for path in data_root.iterdir():
        if path.is_file() and not path.is_symlink() and path.name.casefold() == wanted:
            return path
    return None


def _require_campaign_data(data_root: Path, campaign: str) -> None:
    if data_root.is_symlink() or not data_root.is_dir():
        raise LaunchError(f"data root is not a real directory: {data_root}")
    missing = [name for name in CAMPAIGN_FILES[campaign] if _data_file(data_root, name) is None]
    if missing:
        raise LaunchError("missing campaign data: " + ", ".join(missing))


MISTER_CORE_PROCESS_NAMES = {"mister", "mister_build", "misterdos", "diablo"}


def _core_process_matches(rbf: Path) -> bool:
    expected = str(rbf)
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            values = entry.joinpath("cmdline").read_bytes().split(b"\0")
            argv = [value.decode("utf-8", "replace") for value in values if value]
        except OSError:
            continue
        if argv and Path(argv[0]).name.casefold() in MISTER_CORE_PROCESS_NAMES and expected in argv[1:]:
            return True
    return False


def _fpga_is_operating() -> bool:
    try:
        return Path("/sys/class/fpga_manager/fpga0/state").read_text(encoding="ascii").strip().lower() == "operating"
    except OSError:
        return False


MISTER_FRONTEND_PATH = Path("/media/fat/MiSTer")


def _frontend_process_present() -> bool:
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            values = entry.joinpath("cmdline").read_bytes().split(b"\0")
            argv = [value.decode("utf-8", "replace") for value in values if value]
        except OSError:
            continue
        if argv and Path(argv[0]).name.casefold() in MISTER_CORE_PROCESS_NAMES:
            return True
    return False


def _request_core_load(command_path: Path, rbf: Path) -> bool:
    """Request a load without blocking forever on an unread MiSTer FIFO."""
    flags = os.O_WRONLY | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(command_path, flags)
    except OSError as error:
        if error.errno in (errno.ENXIO, errno.ENODEV):
            return False
        raise
    try:
        os.write(descriptor, f"load_core {rbf}\n".encode("ascii"))
    finally:
        os.close(descriptor)
    return True


def _start_frontend(rbf: Path) -> subprocess.Popen:
    if MISTER_FRONTEND_PATH.is_symlink() or not MISTER_FRONTEND_PATH.is_file():
        raise LaunchError(f"MiSTer frontend is missing: {MISTER_FRONTEND_PATH}")
    if not os.access(MISTER_FRONTEND_PATH, os.X_OK):
        raise LaunchError(f"MiSTer frontend is not executable: {MISTER_FRONTEND_PATH}")
    return subprocess.Popen([str(MISTER_FRONTEND_PATH), str(rbf)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def _load_core(command_path: Path, rbf: Path, timeout: float, already_loaded: bool = False) -> None:
    if command_path.is_symlink() or not command_path.exists():
        raise LaunchError(f"MiSTer command FIFO is missing: {command_path}")
    frontend: subprocess.Popen | None = None
    if not already_loaded and not _core_process_matches(rbf):
        if _frontend_process_present():
            try:
                accepted = _request_core_load(command_path, rbf)
            except OSError as error:
                raise LaunchError(f"cannot request RBF load: {error}") from error
            if not accepted:
                raise LaunchError("MiSTer frontend is present but its command FIFO has no reader")
        else:
            frontend = _start_frontend(rbf)
    state = Path("/sys/class/fpga_manager/fpga0/state")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            operating = state.read_text(encoding="ascii").strip().lower() == "operating"
            if operating and (already_loaded or _core_process_matches(rbf)):
                return
        except OSError:
            pass
        if frontend is not None and frontend.poll() is not None:
            raise LaunchError("MiSTer frontend exited before the requested core reached operating state")
        time.sleep(0.25)
    raise LaunchError("FPGA/core loader did not reach operating state for the requested RBF")


def _admission(path: Path, boot_id: str, physical_base: int, candidate_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise LaunchError(f"refusing to replace admission file: {path}")
    text = ("schema=diablo-reserved-ddr-admission-v1\n" f"boot_id={boot_id}\n"
            f"physical_base=0x{physical_base:x}\n" f"bytes={SHARED_BYTES}\n" f"candidate_id={candidate_id}\n")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, text.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_linux_memory(physical_base: int, iomem: str) -> list[dict[str, int]]:
    """Reject Linux-owned RAM before permitting the DE10-Nano DDR transport.

    A boot ID authenticates the session, but cannot establish that an updated
    kernel still excludes our transport aperture from its page allocator.
    This check is independent of the kernel version and Linux fbdev support.
    """
    end = physical_base + SHARED_BYTES
    if physical_base < 0 or physical_base % 4096 or end > 0x40000000:
        raise LaunchError("transport aperture must fit the DE10-Nano 1 GiB DDR and be page aligned")
    ranges = []
    for line in iomem.splitlines():
        match = re.fullmatch(r"\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)\s*:\s*System RAM\s*", line)
        if match is None:
            if "System RAM" in line:
                raise LaunchError("cannot parse System RAM in /proc/iomem")
            continue
        start, last = (int(value, 16) for value in match.groups())
        if last <= start:
            raise LaunchError("/proc/iomem System RAM addresses are hidden or invalid")
        ranges.append({"start": start, "end_inclusive": last})
        if physical_base <= last and end > start:
            raise LaunchError("transport aperture overlaps Linux System RAM; restore the reserved-DDR boot configuration")
    if not ranges:
        raise LaunchError("cannot establish Linux System RAM ranges from /proc/iomem")
    return ranges


def _linux_runtime_evidence(physical_base: int) -> dict[str, Any]:
    iomem = Path("/proc/iomem").read_text(encoding="ascii")
    return {"kernel_release": os.uname().release,
            "video_backend": "fpga-shared-ddr", "sdl_video_driver": "dummy",
            "fbdev_mmap_required": False,
            "system_ram": _validate_linux_memory(physical_base, iomem),
            "iomem_sha256": hashlib.sha256(iomem.encode("ascii")).hexdigest(),
            "physical_base": physical_base, "mapped_bytes": SHARED_BYTES}


def _engine_args(args: argparse.Namespace, package: Path, save_root: Path, config_root: Path, log_path: Path) -> list[str]:
    command = [str(package / "devilutionx"), "--" + args.campaign,
               "--data-dir", str(args.data_root), "--save-dir", str(save_root),
               "--config-dir", str(config_root), "--lang", args.lang,
               "--verbose"]
    command.extend(args.engine_arg)
    return command


def _force_frame_pacing(engine_args: list[str]) -> bool:
    # The FPGA output is 60 Hz in normal gameplay as well as timedemos.
    return True


def _stop_engine(process: subprocess.Popen, owns_process_group: bool = True) -> int:
    """Stop our engine without ever signalling the replacement MiSTer core."""
    if process.poll() is not None:
        return process.wait()
    try:
        if owns_process_group:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return process.wait()
    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if owns_process_group:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        return process.wait(timeout=5)


def _wait_for_engine(process: subprocess.Popen, rbf: Path, duration: float,
                     already_loaded: bool = False) -> tuple[int, bool, bool]:
    """Invalidate this run if its core disappears, including unlimited sessions."""
    deadline = time.monotonic() + duration if duration > 0 else None
    while True:
        exit_code = process.poll()
        if exit_code is not None:
            return exit_code, False, False
        if already_loaded:
            core_changed = not _fpga_is_operating()
        else:
            # MiSTer’s one-shot RBF loader exits after programming the FPGA;
            # the loaded core is then represented by fpga_manager state.
            core_changed = not (_core_process_matches(rbf) or _fpga_is_operating())
        if core_changed:
            return _stop_engine(process, not already_loaded), False, True
        remaining = deadline - time.monotonic() if deadline is not None else None
        if remaining is not None and remaining <= 0:
            return _stop_engine(process, not already_loaded), True, False
        try:
            return process.wait(timeout=min(0.25, remaining) if remaining is not None else 0.25), False, False
        except subprocess.TimeoutExpired:
            pass


def _pin_engine_to_cpu0() -> None:
    """Run in the forked engine child, before exec and creation of audio threads.

    The launcher is single-threaded. Do not change the parent or MiSTer's
    affinity: its CPU-1 mask is otherwise inherited by the engine.
    """
    os.sched_setaffinity(0, {0})


def _start_engine(command: list[str], **kwargs: Any) -> subprocess.Popen:
    if not hasattr(os, "sched_setaffinity"):
        raise LaunchError("the MiSTer engine requires Linux CPU affinity support")
    return subprocess.Popen(command, preexec_fn=_pin_engine_to_cpu0, **kwargs)


def launch(args: argparse.Namespace) -> dict[str, Any]:
    package = args.package_root.resolve()
    identity = _managed_package_identity(package) or verify_package(package)
    candidate_id = str(identity["candidate_id"])
    data_root = args.data_root.resolve()
    _require_campaign_data(data_root, args.campaign)
    save_root = _writable(args.save_root.resolve(), "save root")
    _stage_hellfire_mod(package, save_root)
    config_root = _writable((args.config_root or (save_root / "config")).resolve(), "config root")
    runtime_root = _writable((args.runtime_root or (Path("/tmp") / ("diablo-" + candidate_id[:16]))).resolve(), "runtime root")
    boot_id = _boot_id(args.boot_id_file)
    physical_base = _unsigned(args.physical_base, "physical base")
    if physical_base % 4096 or physical_base + SHARED_BYTES > (1 << 32):
        raise LaunchError("physical base must be page aligned and fit the 32-bit target aperture")
    linux_runtime = _linux_runtime_evidence(physical_base)
    lock_path = runtime_root / "transport.lock"
    admission_path = runtime_root / "admission.txt"
    ready_path = runtime_root / "ready.json"
    log_path = runtime_root / "engine.log"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+b")
    if fcntl is None:
        lock_handle.close()
        raise LaunchError("the MiSTer launcher requires POSIX file locking")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        lock_handle.close()
        raise LaunchError(f"another transport owner holds the lease: {lock_path}") from error
    try:
        # We hold the lease: remnants of an interrupted prior run are no
        # longer authoritative. Never remove these before acquiring the lock.
        for stale in (admission_path, ready_path):
            stale.unlink(missing_ok=True)
        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write((json.dumps({"schema": "diablo-transport-lock-v1", "boot_id": boot_id,
                                       "candidate_id": candidate_id, "pid": os.getpid()}, sort_keys=True) + "\n").encode())
        lock_handle.flush()
        _load_core(args.command_path, package / "Diablo.rbf", args.loader_timeout, args.core_already_loaded)
        _admission(admission_path, boot_id, physical_base, candidate_id)
        ready_path.write_text(json.dumps({"schema": "diablo-mister-ready-v1", "candidate_id": candidate_id,
                                          "boot_id": boot_id, "physical_base": physical_base,
                                          "linux_runtime": linux_runtime}) + "\n", encoding="utf-8")
        command = []
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        with log_path.open("ab") as output:
            env = dict(os.environ)
            env.update({"DIABLO_MISTER_TRANSPORT": "1", "DIABLO_MISTER_SHARED_PHYS": f"0x{physical_base:x}",
                        "DIABLO_MISTER_CANDIDATE_ID": candidate_id, "DIABLO_MISTER_ADMISSION_FILE": str(admission_path),
                        "DIABLO_MISTER_TRANSPORT_LOCK": str(lock_path), "DIABLO_MISTER_TRANSPORT_LOCK_FD": str(lock_handle.fileno()),
                        "DIABLO_MISTER_SESSION_EPOCH": f"0x{secrets.randbits(32) or 1:08x}",
                        "DIABLO_DATA_DIR": str(data_root), "DIABLO_SAVE_DIR": str(save_root),
                        "DIABLO_CAMPAIGN": args.campaign, "SDL_VIDEODRIVER": "dummy",
                        "SDL_AUDIODRIVER": "dummy", "SDL_RENDER_DRIVER": "software",
                        "DIABLO_MISTER_FORCE_FRAME_PACING": "1" if _force_frame_pacing(args.engine_arg) else "0",
                        # Dirty-region copies are the measured lower-cost path for
                        # the shared-DDR indexed framebuffer. Preserve an explicit
                        # environment override for diagnostics and rollback.
                        "DIABLO_MISTER_DIRTY_COPY": os.environ.get("DIABLO_MISTER_DIRTY_COPY", "1")})
            command = _engine_args(args, package, save_root, config_root, log_path)
            process = _start_engine(command, cwd=package, env=env, stdout=output, stderr=subprocess.STDOUT,
                                    start_new_session=not args.core_already_loaded,
                                    pass_fds=(lock_handle.fileno(),))
            try:
                exit_code, timed_out, core_changed = _wait_for_engine(
                    process, package / "Diablo.rbf", args.duration, args.core_already_loaded)
            finally:
                _stop_engine(process, not args.core_already_loaded)
        return {"status": ("fail" if core_changed else
                           "pass" if timed_out and args.duration > 0 else ("pass" if exit_code == 0 else "fail")),
                 "timed_out": timed_out,
                 "core_changed": core_changed,
                 "stop_reason": "core_changed" if core_changed else "duration" if timed_out else "engine_exit",
                "candidate_id": candidate_id, "source_id": identity["source_id"], "campaign": args.campaign,
                "linux_runtime": linux_runtime,
                "command": command, "exit_code": exit_code, "started_utc": started,
                "log": str(log_path), "admission": str(admission_path), "ready": str(ready_path),
                "forced_frame_pacing": _force_frame_pacing(args.engine_arg)}
    finally:
        for path in (admission_path, ready_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--save-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--campaign", choices=tuple(CAMPAIGN_FILES), default="diablo")
    parser.add_argument("--physical-base", default="0x3fe00000")
    parser.add_argument("--boot-id-file", type=Path, default=Path("/proc/sys/kernel/random/boot_id"))
    parser.add_argument("--command-path", type=Path, default=Path("/dev/MiSTer_cmd"))
    parser.add_argument("--core-already-loaded", action="store_true",
                        help="run beneath the Diablo main= frontend without requesting another RBF load")
    parser.add_argument("--loader-timeout", type=float, default=45.0)
    parser.add_argument("--duration", type=float, default=0.0,
                        help="seconds to run before clean termination; zero waits for the game")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--engine-arg", action="append", default=[],
                        help="additional argument passed to devilutionx; repeat for multiple arguments")
    args = parser.parse_args(argv)
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        result = launch(args)
    except (LaunchError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
