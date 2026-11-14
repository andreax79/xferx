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

USER_FILE_AREA_SECTORS = (TRACKS - 1) * SECTORS_PER_TRACK  # sectors available for user files
DIRECTORY_ENTRY_SIZE = 11  # bytes per directory entry
ENTRIES_PER_SECTOR = SECTOR_SIZE // DIRECTORY_ENTRY_SIZE  # directory entries per sector
DIRECTORY_SECTORS = 23
MAX_ENTRIES = DIRECTORY_SECTORS * ENTRIES_PER_SECTOR
FILENAME_LEN = 5  # max filename length

ATTR_USER = 0x00  # User file
ATTR_PERMANENT = 0x01  # Permanent file, cannot be deleted
ATTR_DELETED = 0x80  # Deleted file, can be reused
ATTR_END = 0xFF  # End of directory marker


class FDOSFile(AbstractFile):
    """
    A FDOS-II/III file is a contiguous sequence of sectors on the diskette.
    The file is described by a directory entry that contains the starting sector and
    the number of sectors allocated to the file.
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
        if not isinstance(current, FDOSPath) or current.slot != self.entry.slot or current.raw != self.entry.raw:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        self.entry.fs.write_block(buffer, self.entry.start_sector + block_number, number_of_blocks)


class FDOSPath(XFERXPath):
    """
    File Control Block (PCB)

    Byte
        +-----------------------+
     0  |                       |
        / File name             /  padded with spaces to 5 bytes
     4  |                       |
        +-----------------------+
     5  | Attributes            |
        +-----------------------+
     6  | First track           |
        +-----------------------+
     7  | First sector          |
        +-----------------------+
     8  | Sector count + 1      |
        |                       |
        +-----------------------+
    10  | Reserved              |
        +-----------------------+

    Pag 14
    https://www.bitsavers.org/pdf/icom/FDOS-II_Manual_197610.pdf
    """

    fs: "FDOS2Filesystem"

    def __init__(self, fs: "FDOS2Filesystem", slot: int, raw: bytes):
        """Initialize a directory entry or the root directory"""
        super().__init__(fs)
        self.slot = slot
        self.raw = raw
        if self.attributes != ATTR_END:
            if (
                self.attributes not in (0, ATTR_PERMANENT, ATTR_DELETED, ATTR_DELETED | ATTR_PERMANENT)
                or not self.name
                or any(value < 32 or value > 126 for value in raw[:FILENAME_LEN])
                or not 1 <= self.sector <= SECTORS_PER_TRACK
                or self.start_sector < SECTORS_PER_TRACK
                or self.get_length() < 1
                or self.start_sector + self.get_length() > TOTAL_SECTORS
            ):
                raise OSError(errno.EIO, "Invalid directory entry")

    @property
    def name(self) -> str:
        """Final path component"""
        return self.raw[:FILENAME_LEN].decode("ascii").rstrip()

    @property
    def fullname(self) -> str:
        """Name with path"""
        return self.name

    def is_deleted(self) -> bool:
        """Is a deleted file"""
        return bool(self.attributes & ATTR_DELETED)

    def is_readonly(self) -> bool:
        """Is a read-only file"""
        return bool(self.attributes & ATTR_PERMANENT)

    @property
    def parent(self) -> "Directory":
        """The logical parent of the path"""
        return self.fs.get_root()

    @property
    def attributes(self) -> int:
        """Get file attribute flags"""
        return self.raw[5]

    @property
    def track(self) -> int:
        """Get the zero-based logical track where the file starts"""
        return self.raw[6]

    @property
    def sector(self) -> int:
        """Get the one-based logical sector where the file starts"""
        return self.raw[7] & 0x3F

    @property
    def start_sector(self) -> int:
        """Get the zero-based logical sector where the file starts"""
        return self.track * SECTORS_PER_TRACK + self.sector - 1

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """Get the length in blocks"""
        return int.from_bytes(self.raw[8:10], "big") - 1

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
        current = self.fs.get_file_entry(self.name)
        if not isinstance(current, FDOSPath) or current.slot != self.slot or current.raw != self.raw:
            raise OSError(errno.EIO, "Directory entry has changed")
        raw = self.raw[:FILENAME_LEN] + bytes([self.attributes | ATTR_DELETED]) + self.raw[6:]
        directory = self.fs.get_root()
        directory.write_entry(self.slot, raw)
        return True


class Directory(XFERXPath):
    """
    Each diskette contains a directory located on sectors 4-26 of track 0 on the diskette.
    Each sector contains 11 File Control Blocks (FCBs) that describe the files.

        +-----------------------+
     0  | FBCS n                |  11 bytes
        +-----------------------+
    11  | FBCS n+1              |  11 bytes
        +-----------------------+
        /                       /
        +-----------------------+
    110 | FBCS n+10             |  11 bytes
        +-----------------------+
    """

    fs: "FDOS2Filesystem"

    @property
    def name(self) -> str:
        """Final path component"""
        return ""

    @property
    def fullname(self) -> str:
        """Name with path"""
        return self.name

    @property
    def parent(self) -> "Directory":
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
        for slot in range(MAX_ENTRIES):
            raw = self.read_entry(slot)
            entry = FDOSPath(self.fs, slot, raw)
            if entry.attributes == ATTR_END:
                return
            entry = FDOSPath(self.fs, slot, raw)
            if not include_all and entry.is_deleted():
                continue
            if pattern is None or filename_match(entry.name.upper(), pattern, wildcard):
                yield entry

    def get_free_sectors(self) -> int:
        """Get the number of free sectors on the disk"""
        occupied: t.Set[int] = set()
        for entry in self.iterdir(include_all=True):
            occupied.update(range(entry.start_sector, entry.start_sector + entry.get_length()))
        return USER_FILE_AREA_SECTORS - len(occupied)

    def read_entry(self, slot: int) -> bytes:
        """Read a raw directory entry from its slot"""
        if not 0 <= slot < MAX_ENTRIES:
            raise OSError(errno.EIO, "FDOS directory slot outside directory")
        sector, index = divmod(slot, ENTRIES_PER_SECTOR)
        offset = index * DIRECTORY_ENTRY_SIZE
        return self.fs.read_block(3 + sector)[offset : offset + DIRECTORY_ENTRY_SIZE]

    def write_entry(self, slot: int, raw: bytes) -> None:
        """Write a directory entry"""
        if not 0 <= slot < MAX_ENTRIES or len(raw) != DIRECTORY_ENTRY_SIZE:
            raise OSError(errno.EIO, "Invalid FDOS directory entry write")
        sector, index = divmod(slot, ENTRIES_PER_SECTOR)
        offset = index * DIRECTORY_ENTRY_SIZE
        data = bytearray(self.fs.read_block(3 + sector))
        data[offset : offset + DIRECTORY_ENTRY_SIZE] = raw
        self.fs.write_block(data, 3 + sector)


class FDOS2Filesystem(AbstractBlockFilesystem):
    """
    iCOM FDOS-II/III Filesystem

    Track 0

    Sector
        +-----------------------+
     1  | System I/O Data       |
        +-----------------------+
     2  | User Object Code      |
     3  |                       |
        +-----------------------+
     4  | FCB 1-11              |  ---
        +-----------------------+   |
     5  | FCB 12-22             |   |
        +-----------------------+   |  File Directory
        /                       /   |
        +-----------------------+   |
    26  | FCB 243-253           |  ---
        +-----------------------+

    FDOS-II Manual, Pag 14
    https://www.bitsavers.org/pdf/icom/FDOS-II_Manual_197610.pdf

    FDOS-III Manual, Pag 14
    https://deramp.com/downloads/altair/software/icom_floppy/FDOS/FDOS-III%20Manual.pdf
    """

    fs_name = "fdos"
    fs_description = "iCOM FDOS-II/III"
    fs_platforms = ["8080", "altair"]
    fs_entry_metadata = ["attributes"]

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
    ) -> "FDOS2Filesystem":
        """
        Mount the FDOS-II/III filesystem
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
        if size < 0:
            raise OSError(errno.EINVAL, "Invalid file size")
        directory = self.get_root()
        entries = list(directory.iterdir(include_all=True))
        old = next(
            (entry for entry in entries if not entry.is_deleted() and entry.name.upper() == fullname),
            None,
        )
        attributes = (metadata or {}).get("attributes", old.attributes if old else ATTR_USER)
        if not isinstance(attributes, int) or attributes not in (ATTR_USER, ATTR_PERMANENT):
            raise ValueError("FDOS file attributes must be 0 (user) or 1 (permanent)")
        length = max(1, (size + SECTOR_SIZE - 1) // SECTOR_SIZE)
        allocated = (
            old
            if old and length <= old.get_length()
            else next((entry for entry in entries if entry.is_deleted() and length <= entry.get_length()), None)
        )
        append = allocated is None
        if allocated:
            slot, start = allocated.slot, allocated.start_sector
        else:
            if len(entries) >= MAX_ENTRIES - 1:
                raise OSError(errno.ENOSPC, "Directory is full")
            slot = len(entries)
            marker = directory.read_entry(slot)
            marker_sector = marker[7] & 0x3F
            tail = marker[6] * SECTORS_PER_TRACK + marker_sector - 1
            start = max(
                [SECTORS_PER_TRACK]
                + [entry.start_sector + entry.get_length() for entry in entries]
                + ([tail] if 1 <= marker_sector <= SECTORS_PER_TRACK and tail <= TOTAL_SECTORS else [])
            )
        if start + length > TOTAL_SECTORS:
            raise OSError(errno.ENOSPC, "Disk is full")
        track, sector = divmod(start, SECTORS_PER_TRACK)
        unit = old.raw[7] & 0xC0 if old else 0
        raw = fullname.encode("ascii").ljust(FILENAME_LEN, b" ") + bytes([attributes, track, unit | (sector + 1)])
        raw += (length + 1).to_bytes(2, "big") + (old.raw[10:] if old else b"\0")
        self.write_block(bytes(length * SECTOR_SIZE), start, length)
        if append:
            end_track, end_sector = divmod(start + length, SECTORS_PER_TRACK)
            end = b"*****" + bytes([ATTR_END, end_track, end_sector + 1]) + marker[8:]
            directory.write_entry(slot + 1, end)
        directory.write_entry(slot, raw)
        if old and old.slot != slot:
            directory.write_entry(
                old.slot, old.raw[:FILENAME_LEN] + bytes([old.attributes | ATTR_DELETED]) + old.raw[6:]
            )
        return FDOSPath(self, slot, raw)

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

    def get_file_entry(self, fullname: str) -> t.Union[FDOSPath, Directory]:
        """Get the directory entry for a file"""
        if fullname in ("", "/"):
            return self.get_root()
        for entry in self.entries_list:
            if entry.name.upper() == fullname.upper():
                return entry
        raise FileNotFoundError(errno.ENOENT, "File not found", fullname)

    def get_root(self) -> Directory:
        """Get the root directory entry"""
        return Directory(self)

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        """List directory contents"""
        directory = self.get_root()
        entries = list(directory.iterdir(pattern, wildcard=True))
        sys.stdout.write("NAME   ATTR TRAK SCTR  SIZE\n\n")
        for entry in entries:
            sys.stdout.write(
                f"{entry.name:<7} {entry.attributes:02X}   "
                f"{entry.track:02X}   {entry.sector:02X}   {entry.get_length():05}\n"
            )
        free_sectors = directory.get_free_sectors()
        sys.stdout.write(f"\n{free_sectors:05} SECTORS FREE\n\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        """Examine the filesystem or a directory entry"""
        if arg:
            entry = self.get_file_entry(arg)
            if isinstance(entry, FDOSPath):
                sys.stdout.write(f"Filename:      {entry.name}\n")
                sys.stdout.write(f"Attributes:    {entry.attributes:02X}\n")
                sys.stdout.write(f"Read-only:     {'Yes' if entry.is_readonly() else 'No'}\n")
                sys.stdout.write(f"Deleted:       {'Yes' if entry.is_deleted() else 'No'}\n")
                sys.stdout.write(f"Track:         {entry.track}\n")
                sys.stdout.write(f"Sector:        {entry.sector}\n")
                sys.stdout.write(f"Length:        {entry.get_length()} sectors\n")
                return
        sys.stdout.write("  #  Filename Attr Track Sector    Size\n")
        sys.stdout.write(" --  -------- ---- ----- ------    ----\n")
        for entry in self.get_root().iterdir(include_all=True):
            sys.stdout.write(
                f"{entry.slot:>3}  {entry.name:<7}   {entry.attributes:02X}    "
                f"{entry.track:>2}     {entry.sector:>2}   {entry.get_size():>6}\n"
            )

    @classmethod
    def initialize(
        cls,
        file_or_dev: t.Union[AbstractFile, AbstractDevice],
        **kwargs: t.Union[bool, str],
    ) -> "FDOS2Filesystem":
        """
        Create an empty FDOS II/III filesystem
        """
        self = cls(file_or_dev)
        if self.dev.get_size() != TOTAL_SECTORS * SECTOR_SIZE:
            raise OSError(errno.EINVAL, "FDOS requires a 77-track, 26-sector, 128-byte disk image")
        self.dev.sector_size = SECTOR_SIZE
        self.write_block(b"\xff" * (SECTORS_PER_TRACK * SECTOR_SIZE), 0, SECTORS_PER_TRACK)
        directory = self.get_root()
        directory.write_entry(0, b"*****" + bytes([ATTR_END, 1, 1, 0, 1, 0]))
        return cls.mount(self.dev)
