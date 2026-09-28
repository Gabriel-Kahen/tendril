import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from tendril.gallery import load_specimen, make_server, specimens


def record(root: Path):
    specimen = root / "generation-0" / "seed-7"
    specimen.mkdir(parents=True)
    (specimen / "result.json").write_text(json.dumps({"valid": True, "seed": 7}))
    (specimen / "frames.jsonl").write_text('{"time":0,"segments":[]}\n{"time":')
    (specimen / "events.jsonl").write_text('{"time":0,"type":"growth"}\n')
    return specimen


def test_recorded_data_and_partial_write(tmp_path):
    record(tmp_path)
    assert specimens(tmp_path)[0]["id"] == "generation-0/seed-7"
    data = load_specimen(tmp_path, "generation-0/seed-7")
    assert data["frames"] == [{"time": 0, "segments": []}]
    assert data["events"][0]["type"] == "growth"
    assert data["genome"] == {}


def test_path_traversal_and_external_symlink(tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    outside = record(tmp_path / "outside")
    (root / "escaped").symlink_to(outside, target_is_directory=True)
    for identifier in ("../outside/generation-0/seed-7", str(outside), "escaped"):
        with pytest.raises(ValueError):
            load_specimen(root, identifier)
    assert specimens(root) == []


def test_http_gallery(tmp_path):
    record(tmp_path)
    with make_server(tmp_path, port=0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base) as response:
                assert b"Interactive three dimensional" in response.read()
            for asset in ("scene.js", "vendor/three.module.js", "vendor/three.core.js"):
                with urlopen(base + "/" + asset) as response:
                    assert response.headers.get_content_type() == "text/javascript"
                    assert response.read()
            with urlopen(base + "/api/specimens") as response:
                assert json.load(response)[0]["result"]["seed"] == 7
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/api/specimen?id=../escape")
            assert error.value.code == 400
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/genome.json")
            assert error.value.code == 404
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/vendor/../../gallery.py")
            assert error.value.code == 404
        finally:
            server.shutdown()
            thread.join()


def test_external_record_file_symlink(tmp_path):
    root = tmp_path / "gallery"
    specimen = record(root)
    outside = tmp_path / "private.json"
    outside.write_text('{"private":true}')
    (specimen / "genome.json").symlink_to(outside)
    with pytest.raises(ValueError):
        load_specimen(root, "generation-0/seed-7")


def test_only_playable_ordinary_records_are_listed(tmp_path):
    record(tmp_path)
    for name, result, frame in [
        ("soft-probe", {"finite": True}, {"flex_vertices": []}),
        ("no-frames", {"valid": False}, None),
        ("wrong-frames", {"valid": True}, {"flex_vertices": []}),
        ("bad-validity", {"valid": "yes"}, {"segments": []}),
    ]:
        path = tmp_path / name
        path.mkdir()
        (path / "result.json").write_text(json.dumps(result))
        if frame is not None:
            (path / "frames.jsonl").write_text(json.dumps(frame) + "\n")
    assert [item["id"] for item in specimens(tmp_path)] == ["generation-0/seed-7"]
