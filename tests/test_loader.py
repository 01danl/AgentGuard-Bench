import json
import stat
import zipfile
from dataclasses import replace

import pytest
from conftest import make_trace

from agentguard.loader import load_sessions
from agentguard.models import InputError, Limits
from agentguard.normalize import normalize_session


def test_utf8_jsonl(trace_file):
    (loaded,) = load_sessions(trace_file(make_trace([("read", '{"path":"данные.txt"}')])))
    assert loaded.session_id == "synthetic-test"
    assert any("данные" in str(row) for row in loaded.rows)


@pytest.mark.parametrize(
    "content",
    [
        b'{"type":',
        b"[]\n",
        b"\xff",
        b"NaN\n",
        b'{"a":1,"a":2}\n',
        b"",
    ],
)
def test_invalid_jsonl(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(content)
    with pytest.raises(InputError):
        load_sessions(path)


def test_diagnostic_has_line_not_source_payload(tmp_path):
    path = tmp_path / "bad.jsonl"
    header = json.dumps(make_trace([])[0])
    path.write_text(header + '\n{"SECRET_KEY":"raw secret", broken}\n')
    with pytest.raises(InputError, match="line 2") as error:
        load_sessions(path)
    assert "SECRET_KEY" not in str(error.value)
    assert "raw secret" not in str(error.value)


def test_zip_multiple_sessions_and_jsonl_attachment(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, session_id in [
            ("session.v4.jsonl", "parent"),
            ("subagents/child/session.v4.jsonl", "child"),
        ]:
            rows = make_trace([("read", "{}")], session_id=session_id)
            archive.writestr(name, "\n".join(json.dumps(row) for row in rows))
        archive.writestr("files/aa/digest/upload.jsonl", "not a session")
        archive.writestr("media/image.png", b"synthetic attachment")
    loaded = load_sessions(path)
    assert {item.session_id for item in loaded} == {"parent", "child"}
    assert len({item.source for item in loaded}) == 2


@pytest.mark.parametrize(
    "name",
    [
        "../session.jsonl",
        "/session.jsonl",
        "C:/session.jsonl",
        "x\\session.jsonl",
        "a/../../session.jsonl",
    ],
)
def test_zip_unsafe_paths(tmp_path, name):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, "{}")
    with pytest.raises(InputError, match="unsafe"):
        load_sessions(path)


def test_zip_symlink(tmp_path):
    path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("session.jsonl")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(InputError, match="symbolic link"):
        load_sessions(path)


@pytest.mark.parametrize(
    "limit",
    [
        {"max_input_bytes": 10},
        {"max_total_bytes": 10},
        {"max_line_bytes": 10},
        {"max_archive_entries": 1},
        {"max_sessions": 1},
        {"max_events": 1},
        {"max_compression_ratio": 1},
    ],
)
def test_limits(tmp_path, limit):
    path = tmp_path / "export.zip"
    content = "\n".join(json.dumps(row) for row in make_trace([("read", "{}")]))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("session.v4.jsonl", content)
        archive.writestr("subagents/child/session.v4.jsonl", content)
    with pytest.raises(InputError, match="limit"):
        load_sessions(path, replace(Limits(), **limit))


def test_corrupt_zip(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(InputError, match="corrupt"):
        load_sessions(path)


def test_duplicate_session_ids(tmp_path):
    path = tmp_path / "duplicate.zip"
    content = "\n".join(json.dumps(row) for row in make_trace([]))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.jsonl", content)
        archive.writestr("b.jsonl", content)
    with pytest.raises(InputError, match="Duplicate session IDs"):
        load_sessions(path)


@pytest.mark.parametrize("version", [0, 1, 2, 3, 5, True, None])
def test_refuses_unverified_versions(trace_file, version):
    rows = make_trace([])
    rows[0]["version"] = version
    with pytest.raises(InputError, match="unsupported session format"):
        load_sessions(trace_file(rows))


def test_concatenated_sessions_refused(trace_file):
    with pytest.raises(InputError, match="multiple headers"):
        load_sessions(trace_file(make_trace([]) + make_trace([])))


def test_sequence_gap_refused(trace_file):
    rows = make_trace([("read", "{}")])
    rows[-1]["seq"] += 1
    with pytest.raises(InputError, match="contiguous"):
        normalize_session(load_sessions(trace_file(rows))[0])


def test_single_jsonl_total_budget(trace_file):
    path = trace_file(make_trace([("read", "{}")]))
    with pytest.raises(InputError, match="limit"):
        load_sessions(path, replace(Limits(), max_total_bytes=10))


def test_uploaded_zstd_attachment_not_treated_as_log(tmp_path):
    path = tmp_path / "export.zip"
    content = "\n".join(json.dumps(row) for row in make_trace([]))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("session.v4.jsonl", content)
        archive.writestr("files/aa/digest/upload.jsonl.zstd", b"synthetic attachment")
    assert len(load_sessions(path)) == 1


def test_duplicate_zip_member_refused(tmp_path):
    path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.jsonl", "{}")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("a.jsonl", "{}")
    with pytest.raises(InputError, match="duplicate member"):
        load_sessions(path)


def test_consumed_log_crc_failure(tmp_path):
    path = tmp_path / "crc.zip"
    content = "\n".join(json.dumps(row) for row in make_trace([]))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("session.v4.jsonl", content)
    data = bytearray(path.read_bytes())
    start = data.index(content.encode())
    data[start + content.index("synthetic-test")] = ord("X")
    path.write_bytes(data)
    with pytest.raises(InputError, match="corrupt"):
        load_sessions(path)


@pytest.mark.parametrize("field", ["createdAt", "delegationDepth", "isSeeded", "id"])
def test_missing_required_header_fields(trace_file, field):
    rows = make_trace([])
    rows[0].pop(field)
    with pytest.raises(InputError):
        load_sessions(trace_file(rows))


def test_zip_dot_member_refused(tmp_path):
    path = tmp_path / "dot.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("./", b"")
    with pytest.raises(InputError, match="unsafe"):
        load_sessions(path)
