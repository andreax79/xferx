from pathlib import Path

import errno
import shutil

import pytest

from xferx.altair.fdos2fs import (
    ATTR_DELETED,
    FDOS2Filesystem,
    MAX_ENTRIES,
)
from xferx.altair.disk import (
    AltairDisk,
    SECTOR_ORDER,
    SECTOR_SIZE,
    SECTORS_PER_TRACK,
    TOTAL_SECTORS,
)
from xferx.commons import READ_FILE_FULL
from xferx.native import NativeFile
from xferx.shell import Shell


def physical_offset(logical):
    track, sector = divmod(logical, SECTORS_PER_TRACK)
    return (track * SECTORS_PER_TRACK + SECTOR_ORDER[sector] - 1) * SECTOR_SIZE


def make_image(path, entries=None):
    image = bytearray(b"\xff" * (TOTAL_SECTORS * SECTOR_SIZE))
    entries = entries or [("FIRST", 0, 50, 5), ("GONE", ATTR_DELETED, 55, 1), ("LAST", 1, 56, 1)]
    for slot, (name, attributes, start, length) in enumerate(entries):
        track, sector = divmod(start, SECTORS_PER_TRACK)
        raw = name.encode("ascii").ljust(5, b" ")
        raw += bytes([attributes, track, sector + 1]) + (length + 1).to_bytes(2, "big") + b"\x42"
        directory_sector, index = divmod(slot, 11)
        offset = physical_offset(3 + directory_sector) + index * 11
        image[offset : offset + 11] = raw
    for logical in range(26, TOTAL_SECTORS):
        offset = physical_offset(logical)
        image[offset : offset + SECTOR_SIZE] = bytes([logical % 256]) * SECTOR_SIZE
    path.write_bytes(image)


@pytest.mark.parametrize("fill,use_device", [(0, False), (0xE5, True)])
def test_initialize_new_disk(tmp_path, fill, use_device):
    path = tmp_path / "new.dsk"
    original = bytes([fill]) * (TOTAL_SECTORS * SECTOR_SIZE)
    path.write_bytes(original)
    file = NativeFile(path)
    fs = FDOS2Filesystem.initialize(AltairDisk(file) if use_device else file)
    directory = fs.get_root()
    try:
        assert fs.get_size() == TOTAL_SECTORS * SECTOR_SIZE
        assert fs.dev.sector_size == SECTOR_SIZE
        assert list(fs.entries_list) == []
        assert directory.read_entry(0) == b"*****\xff\x01\x01\x00\x01\x00"
        assert fs.read_block(0, 3) == b"\xff" * (3 * SECTOR_SIZE)
        assert fs.read_block(3)[11:] == b"\xff" * (SECTOR_SIZE - 11)
        assert fs.read_block(4, 22) == b"\xff" * (22 * SECTOR_SIZE)
        assert path.read_bytes()[SECTORS_PER_TRACK * SECTOR_SIZE :] == original[SECTORS_PER_TRACK * SECTOR_SIZE :]
        fs.write_bytes("FIRST", b"new FDOS disk")
        assert fs.get_file_entry("FIRST").start_sector == SECTORS_PER_TRACK
    finally:
        fs.close()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        assert fs.read_bytes("FIRST").startswith(b"new FDOS disk")
    finally:
        fs.close()


@pytest.mark.parametrize("size", [0, 1024, TOTAL_SECTORS * SECTOR_SIZE - 1, TOTAL_SECTORS * SECTOR_SIZE + 1])
def test_initialize_rejects_wrong_size_without_writing(tmp_path, size):
    path = tmp_path / "bad.dsk"
    original = b"\xa5" * size
    path.write_bytes(original)
    file = NativeFile(path)
    try:
        with pytest.raises(OSError) as exc:
            FDOS2Filesystem.initialize(file)
        assert exc.value.errno == errno.EINVAL
    finally:
        file.close()
    assert path.read_bytes() == original


def test_initialize_clears_existing_directory(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    original = path.read_bytes()
    fs = FDOS2Filesystem.initialize(NativeFile(path))
    try:
        assert list(fs.filter_entries_list(None, include_all=True)) == []
        assert not fs.exists("FIRST")
        assert not fs.exists("LAST")
        assert path.read_bytes()[SECTORS_PER_TRACK * SECTOR_SIZE :] == original[SECTORS_PER_TRACK * SECTOR_SIZE :]
    finally:
        fs.close()


def test_shell_initialize_new_disk(tmp_path):
    path = tmp_path / "new.dsk"
    shell = Shell(verbose=True)
    shell.onecmd(f"create /allocate:256256B {path}", batch=True)
    assert path.stat().st_size == TOTAL_SECTORS * SECTOR_SIZE
    shell.onecmd(f"initialize /fdos-ii {path}", batch=True)
    shell.onecmd(f"mount t: /fdos-ii {path}", batch=True)
    try:
        fs = shell.volumes.get_volume("T")
        assert isinstance(fs, FDOS2Filesystem)
        assert list(fs.entries_list) == []
        fs.write_bytes("FIRST", b"initialized through the shell")
        assert fs.read_bytes("FIRST").startswith(b"initialized through the shell")
        shell.onecmd("initialize t:", batch=True)
        assert list(shell.volumes.get_volume("T").entries_list) == []
    finally:
        shell.onecmd("dismount t:", batch=True)


def test_reading_and_paths(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        assert [entry.name for entry in fs.entries_list] == ["FIRST", "LAST"]
        assert [entry.name for entry in fs.filter_entries_list("f*")] == ["FIRST"]
        assert [entry.name for entry in fs.filter_entries_list(None, include_all=True)] == ["FIRST", "GONE", "LAST"]
        assert fs.get_file_entry("/").is_dir()
        assert fs.get_file_entry("first").get_size() == 5 * SECTOR_SIZE
        expected = b"".join(bytes([sector]) * SECTOR_SIZE for sector in range(50, 55))
        assert fs.read_bytes("first") == expected
        with fs.open_file("FIRST") as file:
            assert file.read_block(0, READ_FILE_FULL) == expected
            assert file.read_block(4, 9) == expected[-SECTOR_SIZE:]
            assert file.read_block(5) == b""
            assert file.read_block(TOTAL_SECTORS * 2) == b""
            file.seek(127)
            assert file.read(130) == expected[127:257]
            with pytest.raises(OSError):
                file.read_block(-1)
        with pytest.raises(OSError):
            file.read_block(0)
        with pytest.raises(FileNotFoundError):
            fs.get_file_entry("GONE")
        with pytest.raises(IsADirectoryError):
            fs.get_root().open()
        with pytest.raises(NotADirectoryError):
            list(fs.get_file_entry("FIRST").iterdir())
    finally:
        fs.close()


@pytest.mark.parametrize("count", [12, MAX_ENTRIES])
def test_directory_sector_boundaries(tmp_path, count):
    path = tmp_path / "fdos.dsk"
    make_image(path, [(f"F{slot:04}", 0, 26 + slot, 1) for slot in range(count)])
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        assert len(list(fs.entries_list)) == count
        assert fs.read_bytes(f"F{count - 1:04}") == bytes([(25 + count) % 256]) * SECTOR_SIZE
    finally:
        fs.close()


@pytest.mark.parametrize("field,value", [(0, 0), (5, 2), (6, 77), (7, 0), (7, 27), (8, 255), (9, 0)])
def test_reject_invalid_directory(tmp_path, field, value):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    image = bytearray(path.read_bytes())
    image[physical_offset(3) + field] = value
    path.write_bytes(image)
    file = NativeFile(path)
    try:
        with pytest.raises(OSError):
            FDOS2Filesystem.mount(file)
    finally:
        file.close()


def test_reject_wrong_size(tmp_path):
    path = tmp_path / "bad.dsk"
    path.write_bytes(bytes(1024))
    file = NativeFile(path)
    try:
        with pytest.raises(OSError):
            FDOS2Filesystem.mount(file)
    finally:
        file.close()


def test_existing_file_write(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    original = path.read_bytes()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        entry = fs.get_file_entry("FIRST")
        with entry.open() as file:
            assert file.write(b"changed") == 7
            file.write_block(b"Z" * SECTOR_SIZE * 2, 1, 2)
            for block, count, buffer in (
                (-1, 1, bytes(SECTOR_SIZE)),
                (0, -1, bytes(SECTOR_SIZE)),
                (5, 1, bytes(SECTOR_SIZE)),
                (4, 2, bytes(SECTOR_SIZE * 2)),
                (0, 1, b"short"),
            ):
                with pytest.raises(OSError):
                    file.write_block(buffer, block, count)
        with pytest.raises(OSError):
            file.write_block(bytes(SECTOR_SIZE), 0)
        assert fs.read_bytes("FIRST") == (
            b"changed"
            + bytes([50]) * (SECTOR_SIZE - 7)
            + b"Z" * SECTOR_SIZE * 2
            + bytes([53]) * SECTOR_SIZE
            + bytes([54]) * SECTOR_SIZE
        )
    finally:
        fs.close()
    modified = bytearray(path.read_bytes())
    for logical in range(50, 53):
        offset = physical_offset(logical)
        modified[offset : offset + SECTOR_SIZE] = original[offset : offset + SECTOR_SIZE]
    assert bytes(modified) == original


@pytest.mark.parametrize("size", [0, 1, 127, 128, 129, 512, 4097])
def test_create_and_round_trip(tmp_path, size):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    original = path.read_bytes()
    content = (bytes(range(256)) * ((size + 255) // 256))[:size]
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        first = fs.read_bytes("FIRST")
        last = fs.read_bytes("LAST")
        fs.write_bytes("new", content)
        entry = fs.get_file_entry("NEW")
        assert entry.get_length() == max(1, (size + 127) // 128)
        assert entry.read_bytes() == content.ljust(entry.get_size(), b"\0")
        assert fs.read_bytes("FIRST") == first
        assert fs.read_bytes("LAST") == last
        assert entry.get_length() + 1 == int.from_bytes(entry.raw[8:10], "big")
    finally:
        fs.close()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        assert fs.read_bytes("NEW").startswith(content)
    finally:
        fs.close()
    after = path.read_bytes()
    for logical in range(3):
        offset = physical_offset(logical)
        assert after[offset : offset + SECTOR_SIZE] == original[offset : offset + SECTOR_SIZE]
    for logical in range(3, SECTORS_PER_TRACK):
        offset = physical_offset(logical)
        assert after[offset + 121 : offset + 128] == original[offset + 121 : offset + 128]


def test_delete_and_reuse(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        old = fs.get_file_entry("FIRST")
        assert old.delete()
        assert not fs.exists("FIRST")
        deleted = list(fs.filter_entries_list("FIRST", include_all=True))[0]
        assert deleted.raw[:5] == old.raw[:5]
        assert deleted.raw[6:] == old.raw[6:]
        replacement = fs.create_file("NEW", 256)
        assert replacement.slot == old.slot
        assert replacement.start_sector == old.start_sector
        assert fs.get_file_entry("LAST").raw[10] == 0x42
    finally:
        fs.close()


@pytest.mark.parametrize("size", [1, 5 * SECTOR_SIZE, 6 * SECTOR_SIZE])
def test_overwrite(tmp_path, size):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        last = fs.read_bytes("LAST")
        old = fs.get_file_entry("FIRST")
        fs.write_bytes("FIRST", b"X" * size)
        new = fs.get_file_entry("FIRST")
        assert new.raw[10:] == old.raw[10:]
        assert new.read_bytes() == (b"X" * size).ljust(new.get_size(), b"\0")
        assert fs.read_bytes("LAST") == last
        if size <= old.get_size():
            assert new.slot == old.slot and new.start_sector == old.start_sector
        else:
            assert new.start_sector >= 57
            assert list(fs.filter_entries_list("FIRST", include_all=True))[0].attributes & ATTR_DELETED
    finally:
        fs.close()


@pytest.mark.parametrize("name,size", [("TOOLONG", 1), ("", 1), ("A B", 1), ("A/B", 1), ("A*", 1), ("OK", -1)])
def test_invalid_creation_does_not_change_image(tmp_path, name, size):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    original = path.read_bytes()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        with pytest.raises(OSError):
            fs.create_file(name, size)
    finally:
        fs.close()
    assert path.read_bytes() == original


def test_full_disk_does_not_destroy_existing_file(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path, [("FIRST", 0, 26, TOTAL_SECTORS - 27), ("LAST", 0, TOTAL_SECTORS - 1, 1)])
    original = path.read_bytes()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        with pytest.raises(OSError) as exc:
            fs.write_bytes("NEW", b"new")
        assert exc.value.errno == errno.ENOSPC
        with pytest.raises(OSError) as exc:
            fs.write_bytes("FIRST", bytes((TOTAL_SECTORS - 26) * SECTOR_SIZE))
        assert exc.value.errno == errno.ENOSPC
    finally:
        fs.close()
    assert path.read_bytes() == original


def test_full_directory(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path, [(f"F{slot:04}", 0, 26 + slot, 1) for slot in range(MAX_ENTRIES - 1)])
    original = path.read_bytes()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        with pytest.raises(OSError) as exc:
            fs.create_file("NEW", 1)
        assert exc.value.errno == errno.ENOSPC
        assert path.read_bytes() == original
        fs.get_file_entry("F0000").delete()
        fs.write_bytes("NEW", b"reused slot")
        assert fs.get_file_entry("NEW").slot == 0
    finally:
        fs.close()


@pytest.mark.parametrize("attributes", [-1, 2, ATTR_DELETED, 255, "1"])
def test_invalid_attributes(tmp_path, attributes):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    original = path.read_bytes()
    fs = FDOS2Filesystem.mount(NativeFile(path))
    try:
        with pytest.raises(ValueError):
            fs.write_bytes("NEW", b"invalid", metadata={"attributes": attributes})
    finally:
        fs.close()
    assert path.read_bytes() == original


def test_shell(tmp_path, capsys):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    shell = Shell(verbose=True)
    shell.onecmd(f"mount t: /fdos-ii {path}", batch=True)
    try:
        assert isinstance(shell.volumes.get_volume("T"), FDOS2Filesystem)
        shell.onecmd("dir/brief t:", batch=True)
        output = capsys.readouterr().out
        assert "FIRST" in output and "LAST" in output and "GONE" not in output
        source = tmp_path / "input.txt"
        source.write_bytes(b"copied through the shell")
        shell.onecmd(f"copy {source} t:NEW", batch=True)
        assert shell.volumes.get_volume("T").read_bytes("NEW").startswith(source.read_bytes())
        shell.onecmd("delete t:NEW", batch=True)
        assert not shell.volumes.get_volume("T").exists("NEW")
    finally:
        shell.onecmd("dismount t:", batch=True)
