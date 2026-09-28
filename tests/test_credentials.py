import os
from pathlib import Path

import pytest

from tendril import credentials
from tendril.cli import main
from tendril.guidance import GuidanceError, require_credentials


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    yield
    os.environ.pop("TYPESAFE_API_KEY", None)


def write_key(path, content="private-test-key\n", mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)
    return path


def test_environment_precedes_file_and_is_trimmed(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "  explicit-test-key  ")
    monkeypatch.setattr(os, "open", lambda *args: pytest.fail("opened key file"))
    credentials.load_cli_credentials(tmp_path / "missing")
    assert os.environ["TYPESAFE_API_KEY"] == "explicit-test-key"


def test_blank_environment_loads_default_private_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", " \n ")
    write_key(tmp_path / ".config/tendril/typesafe.key", mode=0o400)
    credentials.load_cli_credentials()
    assert os.environ["TYPESAFE_API_KEY"] == "private-test-key"


def test_explicit_file_overrides_default_location(tmp_path):
    write_key(tmp_path / ".config/tendril/typesafe.key", "default-test-key")
    path = write_key(tmp_path / "other.key")
    credentials.load_cli_credentials(path)
    assert os.environ["TYPESAFE_API_KEY"] == "private-test-key"


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o601, 0o620])
def test_insecure_permissions_rejected_before_read(tmp_path, monkeypatch, mode):
    path = write_key(tmp_path / "key", mode=mode)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: pytest.fail("read insecure file"))
    with pytest.raises(GuidanceError, match="owner-only"):
        credentials.load_cli_credentials(path)
    assert "TYPESAFE_API_KEY" not in os.environ


def test_wrong_owner_rejected_before_read(tmp_path, monkeypatch):
    path = write_key(tmp_path / "key")
    monkeypatch.setattr(os, "getuid", lambda: path.stat().st_uid + 1)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: pytest.fail("read wrong-owner file"))
    with pytest.raises(GuidanceError, match="owned by you"):
        credentials.load_cli_credentials(path)


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_nonregular_files_rejected_without_read(tmp_path, monkeypatch, kind):
    path = tmp_path / "key"
    if kind == "symlink":
        path.symlink_to(write_key(tmp_path / "target"))
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.mkdir(mode=0o700)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: pytest.fail("read nonregular file"))
    with pytest.raises(GuidanceError, match="regular file"):
        credentials.load_cli_credentials(path)


@pytest.mark.parametrize("content", ["", " \n", "first\nsecond", "first second", "x" * 8193, "key\x00"])
def test_invalid_contents_never_enter_errors_or_environment(tmp_path, content):
    path = write_key(tmp_path / "key", content)
    with pytest.raises(GuidanceError, match="one nonempty raw API key") as error:
        credentials.load_cli_credentials(path)
    assert str(error.value) == "Jev key file must contain one nonempty raw API key"
    assert "TYPESAFE_API_KEY" not in os.environ


def test_invalid_utf8_is_reported_without_contents(tmp_path):
    path = write_key(tmp_path / "key")
    path.write_bytes(b"secret\xff")
    with pytest.raises(GuidanceError, match="UTF-8") as error:
        credentials.load_cli_credentials(path)
    assert "secret" not in str(error.value)


def test_missing_default_keeps_guidance_error(tmp_path):
    with pytest.raises(GuidanceError, match="TYPESAFE_API_KEY"):
        credentials.load_cli_credentials()
    with pytest.raises(GuidanceError, match="key file is missing"):
        credentials.load_cli_credentials(tmp_path / "absent")


def test_library_never_loads_local_file(tmp_path):
    write_key(tmp_path / ".config/tendril/typesafe.key")
    with pytest.raises(GuidanceError, match="TYPESAFE_API_KEY"):
        require_credentials()


@pytest.mark.parametrize("command", ["evolve", "replicate"])
def test_cli_loads_key_without_recording_key_or_path(tmp_path, monkeypatch, capsys, command):
    from tendril import experiments, search

    key_file = write_key(tmp_path / "private.key")
    config = tmp_path / "config.json"
    config.write_text('{"seed": 3}')
    calls = []

    def run(config, out, *args):
        assert os.environ["TYPESAFE_API_KEY"] == "private-test-key"
        calls.append(config)
        return {"completed": True}

    monkeypatch.setattr(search, "run_search", run)
    monkeypatch.setattr(experiments, "replicate_jev", run)
    main([command, "--config", str(config), "--out", str(tmp_path / "run"), "--key-file", str(key_file)])
    assert calls == [{"seed": 3}]
    output = capsys.readouterr()
    assert "private-test-key" not in output.out + output.err
    assert str(key_file) not in output.out + output.err


def test_cli_rejects_insecure_file_cleanly_before_run(tmp_path, monkeypatch, capsys):
    from tendril import search

    path = write_key(tmp_path / "key", mode=0o644)
    monkeypatch.setattr(search, "run_search", lambda *args: pytest.fail("started search"))
    with pytest.raises(SystemExit) as error:
        main(["evolve", "--config", "unused.json", "--out", str(tmp_path / "run"), "--key-file", str(path)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "owner-only" in output.err and "Traceback" not in output.err
    assert "private-test-key" not in output.out + output.err
    assert not (tmp_path / "run").exists()


def test_seed_command_does_not_load_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(credentials, "load_cli_credentials", lambda *args: pytest.fail("loaded credentials"))
    main(["seed", "--out", str(tmp_path / "seed.json")])
    assert (tmp_path / "seed.json").exists()
    capsys.readouterr()
