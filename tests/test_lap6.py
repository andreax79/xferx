import struct
from pathlib import Path

from xferx.commons import BLOCK_SIZE, IMAGE
from xferx.linc.lap6fs import MAX_BLOCKS, STANDARD_INDEX_BLOCK, STANDARD_UPPER_FILE_AREA, UNUSED, LAP6Filesystem
from xferx.native import NativeFile
from xferx.shell import Shell

DSK = "tests/dsk/lap6.linc"


def test_initialize_empty_image(tmp_path: Path):
    path = tmp_path / "lap6.linc"
    path.write_bytes(bytes(MAX_BLOCKS * BLOCK_SIZE))

    filesystem = LAP6Filesystem.initialize(NativeFile(path))
    assert filesystem.index_block_number == STANDARD_INDEX_BLOCK
    assert list(filesystem.entries_list) == []
    filesystem.close()

    filesystem = LAP6Filesystem.mount(NativeFile(path))
    assert list(filesystem.entries_list) == []
    filesystem.close()


def test_create_file_allocates_nearest_space_to_index(tmp_path: Path):
    path = tmp_path / "lap6.linc"
    path.write_bytes(bytes(MAX_BLOCKS * BLOCK_SIZE))
    filesystem = LAP6Filesystem.initialize(NativeFile(path))

    first = filesystem.create_file("FIRST", 5 * BLOCK_SIZE)
    second = filesystem.create_file("SECOND", 5 * BLOCK_SIZE)
    assert first.manuscript_block_number == STANDARD_UPPER_FILE_AREA
    assert second.manuscript_block_number == first.manuscript_block_number + 5

    for index in range(2, 19):
        filesystem.create_file(f"F{index:02}", 5 * BLOCK_SIZE)
    lower = filesystem.create_file("F19", 5 * BLOCK_SIZE)
    assert lower.manuscript_block_number == 0o263
    filesystem.close()


def test_delete_releases_file_space(tmp_path: Path):
    path = tmp_path / "lap6.linc"
    path.write_bytes(bytes(MAX_BLOCKS * BLOCK_SIZE))
    filesystem = LAP6Filesystem.initialize(NativeFile(path))

    first = filesystem.create_file("FIRST", 5 * BLOCK_SIZE)
    filesystem.create_file("SECOND", 5 * BLOCK_SIZE)
    assert first.delete()

    replacement = filesystem.create_file("REPLACED", 5 * BLOCK_SIZE)
    assert replacement.manuscript_block_number == STANDARD_UPPER_FILE_AREA
    assert not filesystem.exists("FIRST")
    filesystem.close()


def test_write_manuscript_and_binary_forks(tmp_path: Path):
    path = tmp_path / "lap6.linc"
    path.write_bytes(bytes(MAX_BLOCKS * BLOCK_SIZE))
    filesystem = LAP6Filesystem.initialize(NativeFile(path))

    filesystem.write_bytes("BOTH", b"HELLO")
    filesystem.write_bytes("BOTH", bytes(range(16)) * 32, fork="B")

    assert filesystem.read_bytes("BOTH") == b"HELLO"
    assert filesystem.read_bytes("BOTH", file_mode=IMAGE, fork="B") == bytes(range(16)) * 32
    entry = filesystem.get_file_entry("BOTH")
    assert entry.manuscript_block_number != UNUSED
    assert entry.binary_block_number != UNUSED
    filesystem.close()


def test_lap6():
    shell = Shell(verbose=True)
    shell.onecmd(f"mount t: /lap6 {DSK}", batch=True)
    fs = shell.volumes.get_volume('T')
    assert fs.is_dir("")
    assert not fs.is_dir("F1")
    assert not fs.is_dir("notfound")
    assert isinstance(fs, LAP6Filesystem)

    shell.onecmd("dir t:", batch=True)
    shell.onecmd("type t:F1", batch=True)

    x = fs.read_bytes("F50", fork="M")
    x = x.rstrip(b"\0")
    assert len(x) == 2200
    for i in range(0, 50):
        assert f"{i:5d} ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890".encode("ascii") in x

    x1 = fs.read_bytes("F1000", fork="B")
    x1 = x1.rstrip(b"\0")
    assert len(x1) == 1000 * 2

    words = list(range(0, 1000))
    data = struct.pack(f"<{len(words)}H", *words)
    assert x1 == data
