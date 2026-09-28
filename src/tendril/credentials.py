"""CLI-only loading of a private local Jev credential into the environment."""

import os
import stat
from pathlib import Path

from .guidance import GuidanceError, require_credentials


def load_cli_credentials(key_file=None):
    """Prefer the process key; otherwise read an owner-only regular key file.

    Library callers still supply TYPESAFE_API_KEY themselves. Neither the key
    nor its local path belongs in experiment configuration or replay records.
    """
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        os.environ["TYPESAFE_API_KEY"] = key
        return
    path = (
        Path(key_file).expanduser()
        if key_file else Path.home() / ".config/tendril/typesafe.key"
    )
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if key_file is None:
            require_credentials()
        raise GuidanceError(
            "Jev key file is missing; set TYPESAFE_API_KEY or check --key-file"
        ) from None
    except OSError:
        raise GuidanceError(
            "Cannot open Jev key file; use a readable regular file without a symlink"
        ) from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise GuidanceError(
                "Jev key file must be a regular file owned by you "
                "with owner-only permissions (chmod 600)"
            )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(8193)
        key = raw.decode("utf-8").strip()
        if (
            len(raw) > 8192 or not key
            or any(c.isspace() for c in key) or "\x00" in key
        ):
            raise GuidanceError("Jev key file must contain one nonempty raw API key")
    except (OSError, UnicodeError):
        raise GuidanceError(
            "Cannot read Jev key file; use one UTF-8 line containing the raw API key"
        ) from None
    finally:
        os.close(fd)
    os.environ["TYPESAFE_API_KEY"] = key
