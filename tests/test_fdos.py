from pathlib import Path

import errno
import shutil

import pytest

from xferx.altair.fdosfs import (
    # ATTR_DELETED,
    FDOSFilesystem,
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


def make_image(path, entries=None):
    image = bytearray(b"\xff" * (TOTAL_SECTORS * SECTOR_SIZE))
    entries = entries or [("FIRST", 5), ("LAST", 1)]
    path.write_bytes(image)
    file = NativeFile(path)
    fs = FDOSFilesystem.initialize(file)
    for name, length in entries:
        fs.write_bytes(name, b"X" * (length * SECTOR_SIZE))


@pytest.mark.parametrize("fill,use_device", [(0, False), (0xE5, True)])
def test_initialize_new_disk(tmp_path, fill, use_device):
    path = tmp_path / "new.dsk"
    original = bytes([fill]) * (TOTAL_SECTORS * SECTOR_SIZE)
    path.write_bytes(original)
    file = NativeFile(path)
    fs = FDOSFilesystem.initialize(AltairDisk(file) if use_device else file)
    directory = fs.get_root()
    try:
        assert fs.get_size() == TOTAL_SECTORS * SECTOR_SIZE
        assert fs.dev.sector_size == SECTOR_SIZE
        assert list(fs.entries_list) == []
        assert path.read_bytes()[SECTORS_PER_TRACK * SECTOR_SIZE :] == original[SECTORS_PER_TRACK * SECTOR_SIZE :]
        fs.write_bytes("FIRST", b"new FDOS disk")
        assert fs.get_file_entry("FIRST").start_sector == 14 * SECTORS_PER_TRACK
    finally:
        fs.close()
    fs = FDOSFilesystem.mount(NativeFile(path))
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
            FDOSFilesystem.initialize(file)
        assert exc.value.errno == errno.EINVAL
    finally:
        file.close()
    assert path.read_bytes() == original


def test_shell_initialize_new_disk(tmp_path):
    path = tmp_path / "new.dsk"
    shell = Shell(verbose=True)
    shell.onecmd(f"create /allocate:256256B {path}", batch=True)
    assert path.stat().st_size == TOTAL_SECTORS * SECTOR_SIZE
    shell.onecmd(f"initialize /fdos {path}", batch=True)
    shell.onecmd(f"mount t: /fdos {path}", batch=True)
    try:
        fs = shell.volumes.get_volume("T")
        assert isinstance(fs, FDOSFilesystem)
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
    fs = FDOSFilesystem.mount(NativeFile(path))
    try:
        assert [entry.name for entry in fs.entries_list] == ["FIRST", "LAST"]
        assert [entry.name for entry in fs.filter_entries_list("f*")] == ["FIRST"]
        assert fs.get_file_entry("/").is_dir()
        assert fs.get_file_entry("first").get_size() == 5 * SECTOR_SIZE
        with fs.open_file("FIRST") as file:
            assert file.read_block(5) == b""
            assert file.read_block(TOTAL_SECTORS * 2) == b""
            file.seek(127)
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


def test_delete(tmp_path):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    fs = FDOSFilesystem.mount(NativeFile(path))
    try:
        old = fs.get_file_entry("FIRST")
        assert old.delete()
        assert not fs.exists("FIRST")
        assert not list(fs.filter_entries_list("FIRST", include_all=False))
    finally:
        fs.close()


@pytest.mark.parametrize("size", [SECTOR_SIZE, 5 * SECTOR_SIZE, 6 * SECTOR_SIZE])
def test_overwrite(tmp_path, size):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    fs = FDOSFilesystem.mount(NativeFile(path))
    try:
        last = fs.read_bytes("LAST")
        old = fs.get_file_entry("FIRST")
        fs.write_bytes("FIRST", b"a" * size)
        new = fs.get_file_entry("FIRST")
        assert new.read_bytes() == (b"a" * size).ljust(new.get_size(), b"\0")
        assert fs.read_bytes("LAST") == last
        if size <= old.get_size():
            assert new.file_number == old.file_number
        else:
            assert list(fs.filter_entries_list("FIRST", include_all=False))
    finally:
        fs.close()


def test_shell(tmp_path, capsys):
    path = tmp_path / "fdos.dsk"
    make_image(path)
    shell = Shell(verbose=True)
    shell.onecmd(f"mount t: /fdos {path}", batch=True)
    try:
        assert isinstance(shell.volumes.get_volume("T"), FDOSFilesystem)
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
