# Copyright (C) 2014 Andrea Bonomi <andrea.bonomi@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import errno
import io
import math
import os
import sys
import threading
import typing as t
from datetime import date, datetime
from pathlib import Path, PureWindowsPath

from .abstract import AbstractDirectoryEntry, AbstractFile, AbstractFilesystem
from .commons import BLOCK_SIZE, READ_FILE_FULL
from .device.abstract import AbstractDevice

__all__ = [
    "NativeFile",
    "NativeDirectoryEntry",
    "NativeFilesystem",
]


def format_size(size: float) -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(size) < 1000 or unit == "T":
            break
        size = size / 1000
    return f"{size:3.1f}{unit}" if unit else str(int(size))


def path_to_str(path: Path) -> str:
    if isinstance(path, PureWindowsPath):
        # Windows path handling
        pwd = str(path)
        if len(pwd) >= 2 and pwd[1] == ":":
            pwd = pwd[2:]  # Remove drive letter
        pwd = pwd.replace("/", "\\")  # Ensure backslashes
        if not pwd.startswith("\\"):
            pwd = "\\" + pwd
        return pwd
    else:
        # POSIX path handling
        pwd = str(path)
        if not pwd.startswith("/"):
            pwd = "/" + pwd
        return pwd


class NativeFile(AbstractFile):

    f: t.Union[io.BufferedReader, io.BufferedRandom]

    def __init__(self, filename_or_path: t.Union[str, Path]):
        if isinstance(filename_or_path, Path):
            native_path = filename_or_path
        else:
            native_path = Path(filename_or_path)
        self.filename = path_to_str(native_path.resolve())
        try:
            self.f = native_path.open(mode="rb+")
            self.readonly = False
        except OSError:
            self.f = native_path.open(mode="rb")
            self.readonly = True
        self.size = native_path.stat().st_size
        self._lock = threading.Lock()

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            with self._lock:
                self.f.seek(0)
                return self.f.read()
        if block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        with self._lock:
            position = block_number * BLOCK_SIZE
            self.f.seek(position)
            return self.f.read(number_of_blocks * BLOCK_SIZE)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the file
        """
        if block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        if self.readonly:
            raise OSError(errno.EROFS, os.strerror(errno.EROFS))
        with self._lock:
            self.f.seek(block_number * BLOCK_SIZE)
            self.f.write(buffer[0 : number_of_blocks * BLOCK_SIZE])
            self.f.flush()

    def truncate(self, size: t.Optional[int] = None) -> None:
        """
        Resize the file to the given number of bytes.
        If the size is not specified, the current position will be used.
        """
        self.f.truncate(size)
        if size is not None and self.current_position > size:
            self.current_position = size

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.size

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return BLOCK_SIZE

    def close(self) -> None:
        """
        Close the file
        """
        self.f.close()

    def __str__(self) -> str:
        return self.filename


class NativeDirectoryEntry(AbstractDirectoryEntry):

    def __init__(self, native_path: Path) -> None:
        self.native_path = native_path
        self.native_fullname = path_to_str(self.native_path)
        self.filename = self.native_path.stem
        self.extension = self.native_path.suffix
        if self.extension.startswith("."):
            self.extension = self.extension[1:]
        self.stat = self.native_path.stat()
        self.length = self.stat.st_size  # length in bytes

    @property
    def creation_date(self) -> date:
        return datetime.fromtimestamp(self.stat.st_mtime)

    @property
    def fullname(self) -> str:
        return self.native_fullname

    @property
    def basename(self) -> str:
        return self.native_path.name

    @property
    def is_regular_file(self) -> bool:
        """
        Check if the entry is a regular file
        """
        return self.native_path.is_file()

    @property
    def is_directory(self) -> bool:
        """
        Check if the entry is a directory
        """
        return self.native_path.is_dir()

    @property
    def is_link(self) -> bool:
        """
        Check if the entry is a symbolic link
        """
        return self.native_path.is_symlink()

    @property
    def entry_type(self) -> t.Optional[str]:
        """
        Entry type
        """
        if self.native_path.is_file():
            return "FILE"
        elif self.native_path.is_dir():
            return "DIRECTORY"
        elif self.native_path.is_symlink():
            return "LINK"
        elif self.native_path.is_fifo():
            return "FIFO"
        elif self.native_path.is_socket():
            return "SOCKET"
        elif self.native_path.is_char_device():
            return "CHAR DEV"
        elif self.native_path.is_block_device():
            return "BLOCK DEV"
        else:
            return None

    def get_length(self) -> int:
        """
        Get the length in blocks
        """
        return int(math.ceil(self.get_size() / self.get_block_size()))

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.stat.st_size

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return BLOCK_SIZE

    def delete(self) -> bool:
        """
        Delete the directory entry
        """
        try:
            if self.is_directory:
                self.native_path.rmdir()
            else:
                self.native_path.unlink()
            return True
        except:
            return False

    def write(self) -> bool:
        """
        Write the directory entry
        """
        raise OSError(errno.EINVAL, "Invalid operation on native filesystem")

    def open(self, file_mode: t.Optional[str] = None) -> NativeFile:
        """
        Open a file
        """
        return NativeFile(self.fullname)

    def __str__(self) -> str:
        return f"{self.fullname:<11} {self.creation_date or '':<6} length: {self.length:>6}"


class NativeFilesystem(AbstractFilesystem):

    fs_name = "native"  # Filesystem name
    fs_description = "Native Filesystem"  # Filesystem description

    @classmethod
    def mount(
        cls, file_or_dev: t.Union["AbstractFile", "AbstractDevice"], **kwargs: t.Union[bool, str]
    ) -> "NativeFilesystem":
        if not isinstance(file_or_dev, NativeFile):
            raise OSError(errno.EIO, "Not a native file")
        return cls(base_path=Path(file_or_dev.filename))

    def __init__(self, base_path: t.Optional[Path] = None):
        if base_path:
            self.base_path = base_path.resolve()
            self.pwd = path_to_str(self.base_path)
        else:
            cwd = Path.cwd()
            self.base_path = Path(cwd.anchor)
            self.pwd = path_to_str(cwd)

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
    ) -> t.Iterator["NativeDirectoryEntry"]:
        if not pattern:
            # List all entries in the current directory
            current_path = self.base_path / self.pwd
            for path in current_path.iterdir():
                try:
                    yield NativeDirectoryEntry(path)
                except:
                    pass

        else:
            pattern_path = self.base_path / self.pwd / pattern

            # Check if the pattern is a directory
            if pattern_path.is_dir():
                if not expand:  # don't expand directories
                    yield NativeDirectoryEntry(pattern_path)
                    return
                pattern_path = pattern_path / "*"

            # glob the pattern
            parent = pattern_path.parent
            glob_pattern = pattern_path.name
            for path in parent.glob(glob_pattern):
                try:
                    yield NativeDirectoryEntry(path)
                except:
                    pass

    @property
    def entries_list(self) -> t.Iterator["NativeDirectoryEntry"]:
        dir_path = Path(self.pwd)
        for path in dir_path.iterdir():
            yield NativeDirectoryEntry(path)

    def get_file_entry(self, fullname: str) -> "NativeDirectoryEntry":
        """
        Get the file entry for a given path
        """
        path = self.base_path / self.pwd / fullname
        return NativeDirectoryEntry(path)

    def write_bytes(
        self,
        fullname: str,
        content: t.Union[bytes, bytearray],
        creation_date: t.Optional[date] = None,
        file_type: t.Optional[str] = None,
        file_mode: t.Optional[str] = None,
    ) -> None:
        """
        Write content to a file
        """
        path = self.base_path / self.pwd / fullname
        path.write_bytes(content)

        if creation_date:
            # Set the creation and modification date of the file
            ts = datetime.combine(creation_date, datetime.min.time()).timestamp()
            os.utime(str(path), (ts, ts))

    def create_file(
        self,
        fullname: str,
        number_of_blocks: int,  # length in blocks
        creation_date: t.Optional[date] = None,  # optional creation date
        file_type: t.Optional[str] = None,
        length_bytes: t.Optional[int] = None,  # optional length in bytes
    ) -> NativeDirectoryEntry:
        """
        Create a new file with a given length
        """
        path = self.base_path / self.pwd / fullname

        if length_bytes is None:
            length_bytes = number_of_blocks * BLOCK_SIZE
        # print(f"Creating file {path} with length {length_bytes} bytes {number_of_blocks} blocks")

        with path.open("wb") as f:
            f.truncate(length_bytes)

        if creation_date:
            # Set the creation and modification date of the file
            ts = datetime.combine(creation_date, datetime.min.time()).timestamp()
            os.utime(str(path), (ts, ts))
        return NativeDirectoryEntry(path)

    def create_directory(
        self,
        fullname: str,
        options: t.Dict[str, t.Union[bool, str]],
    ) -> t.Optional["NativeDirectoryEntry"]:
        """
        Create a directory
        """
        path = (self.base_path / self.pwd / fullname).resolve()
        path.mkdir(parents=True, exist_ok=False)  # May raise OSError in case of errors
        return NativeDirectoryEntry(path)

    def chdir(self, fullname: str) -> bool:
        """
        Change the current working directory
        """
        path = (self.base_path / self.pwd / fullname).resolve()
        if not path.is_dir():
            return False
        self.pwd = path_to_str(path)
        os.chdir(str(path))
        return True

    def isdir(self, fullname: str) -> bool:
        """
        Check if the path is a directory
        """
        path = self.base_path / self.pwd / fullname
        return path.is_dir()

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        if options.get("brief"):
            # Lists only file names and file types
            for x in self.filter_entries_list(pattern):
                sys.stdout.write(f"{x.basename}\n")
        else:
            for x in self.filter_entries_list(pattern):
                et = f"{format_size(x.get_size()):>15s}" if x.is_regular_file else x.entry_type
                dt = x.creation_date.strftime("%d-%b-%Y %H:%M ") if x.creation_date else ""
                sys.stdout.write(f"{et:>15s} {dt:>19s} {x.basename}\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        pass

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.base_path.stat().st_size

    def get_pwd(self) -> str:
        """
        Get the current working directory
        """
        return self.pwd

    def __str__(self) -> str:
        return str(self.base_path)
