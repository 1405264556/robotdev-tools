"""Fast rosbag2 discovery and metadata inspection without message deserialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from rosbags.highlevel import AnyReader

StorageFormat = Literal["sqlite3", "mcap", "mixed", "unknown"]
InputKind = Literal["standard_directory", "storage_directory", "raw_file", "unknown"]

SQLITE_MAGIC = b"SQLite format 3\x00"
MCAP_MAGIC = b"\x89MCAP0\r\n"
STORAGE_SUFFIXES = {".db3", ".mcap"}
SKIP_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}


@dataclass(slots=True, frozen=True)
class TopicType:
    """One Topic/type pair advertised by the recording."""

    topic: str
    message_type: str


@dataclass(slots=True, frozen=True)
class BagCandidate:
    """A detected rosbag2 input with lightweight metadata."""

    path: Path
    input_kind: InputKind
    storage_format: StorageFormat
    storage_files: tuple[Path, ...]
    metadata_present: bool
    readable: bool
    size_bytes: int
    message_count: int | None
    topic_count: int | None
    duration_s: float | None
    topic_types: tuple[TopicType, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for CLI and integrations."""

        payload = asdict(self)
        payload["path"] = str(self.path)
        payload["storage_files"] = [str(path) for path in self.storage_files]
        return payload


def detect_storage_file(path: str | Path) -> StorageFormat:
    """Detect SQLite3 or MCAP from file magic, with suffix as a corruption fallback."""

    candidate = Path(path)
    try:
        with candidate.open("rb") as stream:
            header = stream.read(max(len(SQLITE_MAGIC), len(MCAP_MAGIC)))
    except OSError:
        header = b""
    if header.startswith(SQLITE_MAGIC):
        return "sqlite3"
    if header.startswith(MCAP_MAGIC):
        return "mcap"
    if candidate.suffix.lower() == ".db3":
        return "sqlite3"
    if candidate.suffix.lower() == ".mcap":
        return "mcap"
    return "unknown"


def _normalize_input(path: Path) -> Path:
    if path.is_file() and path.name.lower() == "metadata.yaml":
        return path.parent
    return path


def _storage_files(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,) if path.suffix.lower() in STORAGE_SUFFIXES else ()
    if not path.is_dir():
        return ()
    return tuple(
        sorted(
            child
            for child in path.iterdir()
            if child.is_file() and child.suffix.lower() in STORAGE_SUFFIXES
        )
    )


def _combined_storage_format(files: tuple[Path, ...]) -> StorageFormat:
    formats = {detect_storage_file(path) for path in files}
    formats.discard("unknown")
    if len(formats) > 1:
        return "mixed"
    if formats:
        return formats.pop()
    return "unknown"


def inspect_rosbag(path: str | Path) -> BagCandidate:
    """Inspect one file or directory and return type, size, topics, and basic metadata."""

    candidate = _normalize_input(Path(path).expanduser().resolve())
    metadata_present = candidate.is_dir() and (candidate / "metadata.yaml").is_file()
    if candidate.is_file():
        input_kind: InputKind = "raw_file"
    elif metadata_present:
        input_kind = "standard_directory"
    elif candidate.is_dir():
        input_kind = "storage_directory"
    else:
        input_kind = "unknown"

    try:
        files = _storage_files(candidate)
    except OSError as exc:
        return BagCandidate(
            candidate,
            input_kind,
            "unknown",
            (),
            metadata_present,
            False,
            0,
            None,
            None,
            None,
            (),
            f"Cannot list input: {exc}",
        )
    storage_format = _combined_storage_format(files)
    try:
        size_bytes = sum(item.stat().st_size for item in files)
    except OSError:
        size_bytes = 0

    error: str | None = None
    if not candidate.exists():
        error = "Path does not exist."
    elif not files:
        error = "No .db3 or .mcap storage file was found."
    elif storage_format == "mixed":
        error = "SQLite3 and MCAP files are mixed in one bag directory."
    elif storage_format == "unknown":
        error = "Storage format could not be identified."
    if error is not None:
        return BagCandidate(
            candidate,
            input_kind,
            storage_format,
            files,
            metadata_present,
            False,
            size_bytes,
            None,
            None,
            None,
            (),
            error,
        )

    try:
        with AnyReader(list(files)) as reader:
            topic_types = tuple(
                TopicType(topic, message_type)
                for topic, message_type in sorted(
                    {(connection.topic, connection.msgtype) for connection in reader.connections}
                )
            )
            message_count = int(reader.message_count)
            duration_s = max(0.0, float(reader.duration) / 1e9)
    except Exception as exc:
        return BagCandidate(
            candidate,
            input_kind,
            storage_format,
            files,
            metadata_present,
            False,
            size_bytes,
            None,
            None,
            None,
            (),
            f"Cannot open rosbag2: {exc}",
        )
    return BagCandidate(
        path=candidate,
        input_kind=input_kind,
        storage_format=storage_format,
        storage_files=files,
        metadata_present=metadata_present,
        readable=True,
        size_bytes=size_bytes,
        message_count=message_count,
        topic_count=len({item.topic for item in topic_types}),
        duration_s=round(duration_s, 6),
        topic_types=topic_types,
    )


def discover_rosbags(
    root: str | Path,
    *,
    max_depth: int = 4,
    max_candidates: int = 100,
) -> list[BagCandidate]:
    """Recursively discover rosbag2 directories below ``root``.

    A directory containing one or more storage files is returned as one logical
    bag, which keeps split recordings together. Selecting a raw storage file
    inspects that file alone.
    """

    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    start = _normalize_input(Path(root).expanduser().resolve())
    if start.is_file():
        inspection = inspect_rosbag(start)
        return [inspection] if inspection.storage_files else []
    if not start.is_dir():
        return []

    found: list[BagCandidate] = []
    pending: list[tuple[Path, int]] = [(start, 0)]
    while pending and len(found) < max_candidates:
        directory, depth = pending.pop()
        try:
            files = _storage_files(directory)
        except OSError:
            continue
        if files:
            found.append(inspect_rosbag(directory))
            continue
        if depth >= max_depth:
            continue
        try:
            children = sorted(directory.iterdir(), reverse=True)
        except OSError:
            continue
        for child in children:
            if child.is_dir() and not child.is_symlink() and child.name not in SKIP_DIRECTORIES:
                pending.append((child, depth + 1))
    return sorted(found, key=lambda item: str(item.path).casefold())
