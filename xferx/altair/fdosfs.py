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
import os
import sys
import typing as t

from ..abstract import AbstractBlockFilesystem, AbstractFile, XFERXPath
from ..commons import READ_FILE_FULL, filename_match
from ..device.abstract import AbstractDevice
from .disk import AltairDisk, SECTOR_SIZE, SECTORS_PER_TRACK, TOTAL_SECTORS, TRACKS

MAX_ENTRIES = 7  # maximum number of files in the catalog
FILENAME_LEN = 10  # max filename length
MAX_FILE_TRACK = 9  # max file size in tracks
MAX_FILE_SIZE = MAX_FILE_TRACK * SECTORS_PER_TRACK  # max file size in sectors
USER_FILE_AREA_TRACK = 14  # starting track of user file area


class FDOSFile(AbstractFile):
    """
    A FDOS file is a contiguous sequence of sectors on the diskette.
    Each file begins at a fixed position and may occupy up to the 9 tracks.
    """

    def __init__(self, entry: "FDOSPath"):
        """Initialize an open file from a directory entry"""
        self.entry = entry
        self.current_position = 0
        self.closed = False

    @property
    def name(self) -> str:
        """Final path component"""
        return self.entry.name

    def get_size(self) -> int:
        """Get file size in bytes"""
        return self.entry.get_size()

    def get_block_size(self) -> int:
        """Get file block size in bytes"""
        return SECTOR_SIZE

    def read_block(self, block_number: int, number_of_blocks: int = 1) -> bytes:
        """Read block(s) of data from the file"""
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = max(0, self.entry.get_length() - block_number)
        if self.closed or block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        count = min(number_of_blocks, max(0, self.entry.get_length() - block_number))
        if not count:
            return b""
        return self.entry.fs.read_block(self.entry.start_sector + block_number, count)

    def write_block(self, buffer: t.Union[bytes, bytearray], block_number: int, number_of_blocks: int = 1) -> None:
        """Write block(s) of data within the file's allocated sectors"""
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.get_length()
            or len(buffer) < number_of_blocks * SECTOR_SIZE
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        current = self.entry.fs.get_file_entry(self.entry.name)
        if not isinstance(current, FDOSPath) or current.file_number != self.entry.file_number:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        self.entry.fs.write_block(buffer, self.entry.start_sector + block_number, number_of_blocks)


class FDOSPath(XFERXPath):
    """ """

    fs: "FDOSFilesystem"
    file_number: int  # 1-based file number in the catalog
    filename: str  # filename
    length: int  # length in sectors

    @classmethod
    def read(cls, fs: "FDOSFilesystem", file_number: int) -> "FDOSPath":
        self = cls(fs)
        if not 1 <= file_number <= MAX_ENTRIES:
            raise OSError(errno.EIO, "Invalid file number")
        self.file_number = file_number
        buffer = self.fs.read_block(7 + file_number - 1)
        self.filename = buffer[: FILENAME_LEN + 1].strip(b"\0 ").decode("ascii")
        self.length = self.fs.read_block(14 + file_number - 1)[0] - 1
        return self

    @property
    def name(self) -> str:
        """Final path component"""
        return self.filename

    @property
    def fullname(self) -> str:
        """Name with path"""
        return self.name

    def is_deleted(self) -> bool:
        """Is a deleted file"""
        return self.length == 0

    @property
    def parent(self) -> "Catalog":
        """The logical parent of the path"""
        return self.fs.get_root()

    @property
    def track(self) -> int:
        """Get the zero-based logical track where the file starts"""
        return USER_FILE_AREA_TRACK + (self.file_number - 1) * MAX_FILE_TRACK

    @property
    def start_sector(self) -> int:
        """Get the zero-based logical sector where the file starts"""
        return self.track * SECTORS_PER_TRACK

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """Get the length in blocks"""
        return self.length

    def get_size(self, fork: t.Optional[str] = None) -> int:
        """Get file size in bytes"""
        return self.get_length() * SECTOR_SIZE

    def get_block_size(self) -> int:
        """Get file block size in bytes"""
        return SECTOR_SIZE

    def open(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> FDOSFile:
        """Open the file"""
        return FDOSFile(self)

    def delete(self) -> bool:
        """Mark the file as deleted"""
        self.filename = ""
        self.length = 0
        self.write()
        return True

    def write(self) -> None:
        """Write the directory entry to disk"""
        if not 1 <= self.file_number <= MAX_ENTRIES:
            raise OSError(errno.EIO, "Invalid file number")
        buffer = bytearray(SECTOR_SIZE)
        buffer[:FILENAME_LEN] = self.filename[:FILENAME_LEN].upper().encode("ascii").ljust(FILENAME_LEN, b" ")
        self.fs.write_block(buffer, 7 + self.file_number - 1)
        buffer = bytearray(SECTOR_SIZE)
        buffer[0] = self.length + 1
        self.fs.write_block(buffer, 14 + self.file_number - 1)


class Catalog(XFERXPath):
    """
    The catalog is stored on track 0.
    There are always exactly 7 files and starting locations on disk are fixed.

    The first 10 bytes of sectors 8-14 contain the name for files.
    The first bytes of sectors 15-21 contain the length of the files in sectors.
    """

    fs: "FDOSFilesystem"

    @property
    def name(self) -> str:
        """Final path component"""
        return ""

    @property
    def fullname(self) -> str:
        """Name with path"""
        return self.name

    @property
    def parent(self) -> "Catalog":
        """The logical parent of the path"""
        return self.fs.get_root()

    @property
    def attributes(self) -> int:
        """Get file attribute flags"""
        return 0

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """Get the length in blocks, excluding the extra EOF counter step"""
        return 0

    def get_size(self, fork: t.Optional[str] = None) -> int:
        """Get file size in bytes, including final-sector padding"""
        return 0

    def get_block_size(self) -> int:
        """Get file block size in bytes"""
        return SECTOR_SIZE

    def is_dir(self) -> bool:
        """Is a directory"""
        return True

    def is_mount(self) -> bool:
        """Is root directory"""
        return True

    def open(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> FDOSFile:
        """Open the file"""
        raise IsADirectoryError(self.name)

    def delete(self) -> bool:
        raise OSError(errno.EPERM, "Cannot delete the directory")

    def iterdir(
        self,
        pattern: t.Optional[str] = None,
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator["FDOSPath"]:
        """Iterate over directory entries"""
        pattern = pattern.upper() if pattern else None
        for file_number in range(1, MAX_ENTRIES + 1):
            entry = FDOSPath.read(self.fs, file_number)
            if not include_all and entry.is_deleted():
                continue
            if pattern is None or filename_match(entry.name.upper(), pattern, wildcard):
                yield entry


class FDOSFilesystem(AbstractBlockFilesystem):
    """
    iCOM FDOS Filesystem

    Track
         +-----------------------+
      0  | Catalog               |
         +-----------------------+
      1  |                       |
         / FDOS                  /
     13  |                       |
         +-----------------------+
     14  |                       |
         / File #1               /
     22  |                       |
         +-----------------------+
     23  |                       |
         / File #2               /
     31  |                       |
         +-----------------------+
     32  |                       |
         / File #3               /
     40  |                       |
         +-----------------------+
     41  |                       |
         / File #4               /
     49  |                       |
         +-----------------------+
     50  |                       |
         / File #5               /
     58  |                       |
         +-----------------------+
     59  |                       |
         / File #6               /
     67  |                       |
         +-----------------------+
     68  |                       |
         / File #7               /
     76  |                       |
         +-----------------------+

    Sphere Floppy Disk Operating System (FDOS)
    https://sphere.computer/articles/sphere-fdos.html

    EXORdisk MOTOROLA FLOPPY DISK SYSTEM USER'S GUIDE
    https://deramp.com/downloads/altair/software/icom_floppy/FDOS/EDOS-I%20Manual.pdf
    """

    fs_name = "fdos"
    fs_description = "iCOM FDOS"
    fs_platforms = ["8080", "altair", "sphere"]
    fs_entry_metadata = []

    dev: AltairDisk

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"]):
        if isinstance(file_or_device, AbstractFile):
            self.dev = AltairDisk(file_or_device)
        elif isinstance(file_or_device, AltairDisk):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, f"Invalid device type for {self.fs_description} filesystem")

    @classmethod
    def mount(
        cls,
        file_or_dev: t.Union["AbstractFile", "AbstractDevice"],
        strict: t.Union[bool, str] = True,
        **kwargs: t.Union[bool, str],
    ) -> "FDOSFilesystem":
        """
        Mount the FDOS filesystem
        """
        self = cls(file_or_dev)
        if self.dev.get_size() != TOTAL_SECTORS * SECTOR_SIZE:
            raise OSError(errno.EIO, "FDOS requires a 77-track, 26-sector, 128-byte disk image")
        self.dev.sector_size = SECTOR_SIZE
        if strict:
            try:
                list(self.get_root().iterdir(include_all=True))
            except OSError as error:
                raise OSError(errno.EIO, "Invalid FDOS directory", error) from error
        return self

    def create_file(
        self,
        fullname: str,
        size: int,
        metadata: t.Optional[t.Dict[str, t.Any]] = None,
    ) -> FDOSPath:
        """Create a new file"""
        fullname = fullname.upper()
        if not 1 <= len(fullname) <= FILENAME_LEN or any(
            ord(character) < 33 or ord(character) > 126 or character in "/\\:*?," for character in fullname
        ):
            raise OSError(errno.EINVAL, "Invalid filename")
        if size < 0 or size > MAX_FILE_SIZE * SECTOR_SIZE:
            raise OSError(errno.EINVAL, "Invalid file size")
        try:
            # If the file already exists, delete it first
            entry: FDOSPath = self.get_file_entry(fullname)  # type: ignore
            if not isinstance(entry, FDOSPath):
                raise OSError(errno.EIO, "Cannot overwrite the catalog")
            entry.delete()
        except FileNotFoundError:
            # If the file does not exist, find a deleted entry to use
            for x in self.get_root().iterdir(include_all=True):
                if x.is_deleted():
                    entry = x
                    break
            if entry is None:
                raise OSError(errno.ENOSPC, "Directory is full")
        # Write the new file entry
        entry.filename = fullname
        entry.length = (size + SECTOR_SIZE - 1) // SECTOR_SIZE
        entry.write()
        return entry

    @property
    def entries_list(self) -> t.Iterator[FDOSPath]:
        """Get an iterator of directory entries, excluding deleted files"""
        yield from self.get_root().iterdir(include_all=False)

    def filter_entries_list(
        self, pattern: t.Optional[str], include_all: bool = False, expand: bool = True
    ) -> t.Iterator[FDOSPath]:
        """Filter directory entries based on a pattern"""
        for entry in self.get_root().iterdir(include_all=include_all, pattern=pattern, wildcard=True):
            yield entry

    def get_file_entry(self, fullname: str) -> t.Union[FDOSPath, Catalog]:
        """Get the directory entry for a file"""
        if fullname in ("", "/"):
            return self.get_root()
        for entry in self.entries_list:
            if entry.name.upper() == fullname.upper():
                return entry
        raise FileNotFoundError(errno.ENOENT, "File not found", fullname)

    def get_root(self) -> Catalog:
        """Get the root directory entry"""
        return Catalog(self)

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        """List directory contents"""
        catalog = self.get_root()
        for entry in catalog.iterdir(pattern, wildcard=True, include_all=True):
            sys.stdout.write(f"{entry.file_number:02X}  {entry.filename:<10}  {entry.length:02X}\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        """Examine the filesystem or a directory entry"""
        if arg:
            entry = self.get_file_entry(arg)
            if isinstance(entry, FDOSPath):
                sys.stdout.write(f"File number:   {entry.file_number}\n")
                sys.stdout.write(f"Filename:      {entry.name}\n")
                sys.stdout.write(f"Deleted:       {'Yes' if entry.is_deleted() else 'No'}\n")
                sys.stdout.write(f"Track:         {entry.track}\n")
                sys.stdout.write(f"Length:        {entry.get_length()} sectors\n")
        sys.stdout.write("  #  Filename   Track      Size\n")
        sys.stdout.write(" --  --------   -----      ----\n")
        for entry in self.get_root().iterdir(include_all=True):
            sys.stdout.write(f"{entry.file_number:>3}  {entry.name:<10}    {entry.track:>2}    {entry.get_size():>6}\n")

    @classmethod
    def initialize(
        cls,
        file_or_dev: t.Union[AbstractFile, AbstractDevice],
        **kwargs: t.Union[bool, str],
    ) -> "FDOSFilesystem":
        """
        Create an empty FDOS filesystem
        """
        self = cls(file_or_dev)
        if self.dev.get_size() != TOTAL_SECTORS * SECTOR_SIZE:
            raise OSError(errno.EINVAL, "FDOS requires a 77-track, 26-sector, 128-byte disk image")
        self.dev.sector_size = SECTOR_SIZE
        self.write_block(b"\xff" * (SECTORS_PER_TRACK * SECTOR_SIZE), 0, SECTORS_PER_TRACK)
        catalog = self.get_root()
        for file_number in range(1, MAX_ENTRIES + 1):
            entry = FDOSPath(self)
            entry.file_number = file_number
            entry.filename = ""
            entry.length = 0
            entry.write()
        return self
