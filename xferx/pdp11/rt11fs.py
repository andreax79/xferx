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
import re
import sys
import typing as t
from datetime import date

from ..abstract import AbstractDirectoryEntry, AbstractFile
from ..commons import (
    ASCII,
    BLOCK_SIZE,
    READ_FILE_FULL,
    bytes_to_word,
    filename_match,
    word_to_bytes,
)
from ..device.abstract import AbstractDevice
from ..device.rx import (
    RX01_SECTOR_SIZE,
    RX01_SIZE,
    RX02_SECTOR_SIZE,
    RX02_SIZE,
    RX_SECTOR_TRACK,
)
from .abstract import AbstractRXBlockFilesystem
from .rad50 import asc2rad, rad2asc

__all__ = [
    "RT11File",
    "RT11DirectoryEntry",
    "RT11Filesystem",
]

HOMEBLK = 1
DEFAULT_DIR_SEGMENT = 6
DEFAULT_PACK_CLUSTER_SIZE = 1
DIR_ENTRY_SIZE = 14
DIRECTORY_SEGMENT_HEADER_SIZE = 10
DIRECTORY_SEGMENT_SIZE = BLOCK_SIZE * 2
PARTITION_FULLNAME_RE = re.compile(r"^\[(\d+)\](.*)$")
MAX_PARTITION_SIZE = (1 < 16) - 1

E_TENT = 0o000400  # Tentative file
E_MPTY = 0o001000  # Empty area
E_PERM = 0o002000  # Permanent file
E_EOS = 0o004000  # End-of-segment marker
E_READ = 0o040000  # Protected from write
E_PROT = 0o100000  # Protected permanent file
E_PRE = 0o000020  # Prefix block indicator


def date_to_rt11(val: t.Optional[date]) -> int:
    """
    Translate Python date to RT-11 date
    """
    if val is None:
        return 0
    age = (val.year - 1972) // 32
    if age < 0:
        age = 0
    elif age > 3:
        age = 3
    year = (val.year - 1972) % 32
    return year + (val.day << 5) + (val.month << 10) + (age << 14)


def rt11_to_date(val: int) -> t.Optional[date]:
    """
    Translate RT-11 date to Python date
    """
    if val == 0:
        return None
    year = val & int("0000000000011111", 2)
    day = (val & int("0000001111100000", 2)) >> 5
    month = (val & int("0011110000000000", 2)) >> 10
    age = (val & int("1100000000000000", 2)) >> 14
    year = year + 1972 + age * 32
    if day == 0:
        day = 1
    if month == 0:
        month = 1
    try:
        return date(year, month, day)
    except:
        return None


def rt11_canonical_filename(fullname: t.Optional[str], wildcard: bool = False) -> str:
    """
    Generate the canonical RT11 name
    """
    fullname = (fullname or "").upper()
    try:
        filename, extension = fullname.split(".", 1)
    except Exception:
        filename = fullname
        extension = "*" if wildcard else ""
    filename = rad2asc(asc2rad(filename[0:3])) + rad2asc(asc2rad(filename[3:6]))
    extension = rad2asc(asc2rad(extension))
    return f"{filename}.{extension}"


def rt11_split_fullname(
    partition: int, fullname: t.Optional[str], wildcard: bool = True
) -> t.Tuple[int, t.Optional[str]]:
    """
    Split the partition number from the fullname

    [1]filename.ext -> 1, filename.ext
    """
    if fullname:
        try:
            match = PARTITION_FULLNAME_RE.match(fullname)
            if match:
                partition_str, fullname = match.groups()
                partition = int(partition_str)
        except Exception:
            pass
        if fullname:
            fullname = rt11_canonical_filename(fullname, wildcard=wildcard)
    return partition, fullname


class RT11File(AbstractFile):
    entry: "RT11DirectoryEntry"
    closed: bool
    size: int

    def __init__(self, entry: "RT11DirectoryEntry"):
        self.entry = entry
        self.closed = False
        self.size = entry.length * BLOCK_SIZE

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.entry.length
        if self.closed or block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        if block_number + number_of_blocks > self.entry.length:
            number_of_blocks = self.entry.length - block_number
        return self.entry.partition.read_block(
            self.entry.file_position + block_number,
            number_of_blocks,
        )

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the file
        """
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.length
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        self.entry.partition.write_block(
            buffer,
            self.entry.file_position + block_number,
            number_of_blocks,
        )

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.entry.get_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return self.entry.get_block_size()

    def close(self) -> None:
        """
        Close the file
        """
        self.closed = True

    def __str__(self) -> str:
        return self.entry.fullname


class RT11DirectoryEntry(AbstractDirectoryEntry):

    partition: "RT11Partition"
    status: int = 0
    filename: str = ""
    extension: str = ""
    length: int = 0
    job: int = 0
    channel: int = 0
    raw_creation_date: int = 0
    extra_bytes: bytes = b''
    file_position: int = 0  # block number

    def __init__(self, partition: "RT11Partition"):
        self.partition = partition

    @classmethod
    def read(
        cls,
        partition: "RT11Partition",
        buffer: bytes,
        position: int,
        file_position: int,
        extra_bytes: int,
    ) -> "RT11DirectoryEntry":
        self = cls(partition)
        self.status = bytes_to_word(buffer, position)
        self.filename = rad2asc(buffer, position + 2) + rad2asc(buffer, position + 4)  # 6 RAD50 chars
        self.extension = rad2asc(buffer, position + 6)  # 3 RAD50 chars
        self.length = bytes_to_word(buffer, position + 8)  # length in blocks
        self.job = buffer[position + 10]
        self.channel = buffer[position + 11]
        self.raw_creation_date = bytes_to_word(buffer, position + 12)
        self.extra_bytes = buffer[position + 14 : position + 14 + extra_bytes]
        self.file_position = file_position
        return self

    @classmethod
    def copy(cls, entry: "RT11DirectoryEntry") -> "RT11DirectoryEntry":
        self = cls(entry.partition)
        self.status = entry.status
        self.filename = entry.filename
        self.extension = entry.extension
        self.length = entry.length
        self.job = entry.job
        self.channel = entry.channel
        self.raw_creation_date = entry.raw_creation_date
        self.extra_bytes = entry.extra_bytes
        self.file_position = entry.file_position
        return self

    def to_bytes(self) -> bytes:
        out = bytearray()
        assert self.length >= 0, "Length must be non-negative"
        out.extend(word_to_bytes(self.status))
        out.extend(asc2rad(self.filename[0:3]))
        out.extend(asc2rad(self.filename[3:6]))
        out.extend(asc2rad(self.extension))
        out.extend(word_to_bytes(self.length))
        out.append(self.job)
        out.append(self.channel)
        out.extend(word_to_bytes(self.raw_creation_date))
        out.extend(self.extra_bytes)
        return bytes(out)

    @property
    def is_empty(self) -> bool:
        """
        Empty area
        """
        return self.status & E_MPTY == E_MPTY

    @property
    def is_tentative(self) -> bool:
        """
        Tentative file
        """
        return self.status & E_TENT == E_TENT

    @property
    def is_permanent(self) -> bool:
        """
        Permanent file
        """
        return self.status & E_PERM == E_PERM

    @property
    def is_end_of_segment(self) -> bool:
        """
        End-of-segment marker
        """
        return self.status & E_EOS == E_EOS

    @property
    def is_read_only(self) -> bool:
        """
        Protected from write
        """
        return self.status & E_READ == E_READ

    @property
    def is_delete_protected(self) -> bool:
        """
        Protected from delete
        """
        return self.status & E_PROT == E_PROT

    @property
    def has_prefix_block(self) -> bool:
        """
        Indicates the presence of at least one prefix block in this file.
        """
        return self.status & E_PRE == E_PRE

    @property
    def fullname(self) -> str:
        return f"{self.filename}.{self.extension}"

    @property
    def basename(self) -> str:
        return self.fullname

    def get_length(self) -> int:
        """
        Get the length in blocks
        """
        return self.length

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.length * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return BLOCK_SIZE

    @property
    def creation_date(self) -> t.Optional[date]:
        return rt11_to_date(self.raw_creation_date)

    @property
    def description(self) -> str:
        desc = []
        if self.is_permanent:
            desc.append("Permanent")
        if self.is_tentative:
            desc.append("Tentative")
        if self.is_empty:
            desc.append("Empty area")
        if self.is_end_of_segment:
            desc.append("End-of-segment")
        if self.is_read_only:
            desc.append("Read-only")
        if self.is_delete_protected:
            desc.append("Protected")
        if self.status & E_PRE == E_PRE:
            desc.append("Prefix block")
        return ",".join(desc)

    def _get_entry_segment(self) -> t.Tuple["RT11Segment", "RT11DirectoryEntry"]:
        """
        Read the segment containing this entry
        """
        for segment in self.partition.read_dir_segments():
            for entry in segment.entries_list:
                if entry.file_position == self.file_position:
                    return segment, entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.fullname)

    def delete(self) -> bool:
        """
        Delete the file
        """
        try:
            segment, entry = self._get_entry_segment()
        except FileNotFoundError:
            return False
        # unset E_PROT,E_TENT,E_READ,E_PROT flasgs, set E_MPTY flag
        entry.status = entry.status & ~E_PERM & ~E_TENT & ~E_READ & ~E_PROT | E_MPTY
        self.status = entry.status
        segment.compact()
        segment.write()
        return True

    def write(self) -> bool:
        """
        Write the directory entry
        """
        try:
            segment, entry = self._get_entry_segment()
        except FileNotFoundError:
            return False
        entry.status = self.status
        entry.filename = self.filename
        entry.extension = self.extension
        entry.length = self.length
        entry.job = self.job
        entry.channel = self.channel
        entry.raw_creation_date = self.raw_creation_date
        entry.extra_bytes = self.extra_bytes
        segment.write()
        return True

    def open(self, file_mode: t.Optional[str] = None) -> RT11File:
        """
        Open a file
        """
        return RT11File(self)

    def read_bytes(self, file_mode: t.Optional[str] = None) -> bytes:
        """
        Get the content of the file
        """
        data = super().read_bytes()
        if file_mode == ASCII:
            data = data.rstrip(b"\0")
        return data

    def __str__(self) -> str:
        length = str(self.length) if not self.is_end_of_segment else "-"
        return (
            f"{self.fullname:<11} "
            f"{self.creation_date or '          '} "
            f"{length:>6}  {self.status:6o}  "
            f"{self.job:3d} {self.channel:3d} {self.file_position:6d}  {self.description}"
        )

    def __repr__(self) -> str:
        return str(self)


class RT11Segment(object):
    """
    Volume Directory Segment

    +--------------+
    |5-Word header |
    +--------------+
    |Entries       |
    |.             |
    |.             |
    +--------------+
    |End-of-segment|
    |Marker        |
    +--------------+
    """

    partition: "RT11Partition"
    # Block number of this directory segment
    block_number = 0
    # Total number of segments in this directory (1-31)
    num_of_segments = 0
    # Segment number of the next logical directory segment
    next_logical_dir_segment = 0
    # Number of the highest segment currently in use
    highest_segment = 0
    # Number of extra bytes per directory entry
    extra_bytes = 0
    # Block number where the stored data identified by this segment begins
    data_block_number = 0
    # Max directory entries
    max_entries = 0
    # Directory entries
    entries_list: t.List["RT11DirectoryEntry"]

    def __init__(self, partition: "RT11Partition"):
        self.partition = partition
        self.entries_list = []

    @classmethod
    def read(cls, partition: "RT11Partition", block_number: int) -> "RT11Segment":
        """
        Read a Volume Directory Segment from disk
        """
        self = cls(partition)
        self.block_number = block_number
        t = self.partition.read_block(self.block_number, 2)
        self.num_of_segments = bytes_to_word(t, 0)
        self.next_logical_dir_segment = bytes_to_word(t, 2)
        self.highest_segment = bytes_to_word(t, 4)
        self.extra_bytes = bytes_to_word(t, 6)
        self.data_block_number = bytes_to_word(t, 8)

        file_position = self.data_block_number
        dir_entry_size = DIR_ENTRY_SIZE + self.extra_bytes
        self.max_entries = (DIRECTORY_SEGMENT_SIZE - DIRECTORY_SEGMENT_HEADER_SIZE) // dir_entry_size
        for position in range(DIRECTORY_SEGMENT_HEADER_SIZE, DIRECTORY_SEGMENT_SIZE - dir_entry_size, dir_entry_size):
            dir_entry = RT11DirectoryEntry.read(self.partition, t, position, file_position, self.extra_bytes)
            file_position = file_position + dir_entry.length
            self.entries_list.append(dir_entry)
            if dir_entry.is_end_of_segment:
                break
        return self

    def to_bytes(self) -> bytes:
        out = bytearray()
        out.extend(word_to_bytes(self.num_of_segments))
        out.extend(word_to_bytes(self.next_logical_dir_segment))
        out.extend(word_to_bytes(self.highest_segment))
        out.extend(word_to_bytes(self.extra_bytes))
        out.extend(word_to_bytes(self.data_block_number))
        for entry in self.entries_list:
            out.extend(entry.to_bytes())
        out.extend(b"\0" * (BLOCK_SIZE * 2 - len(out)))
        return bytes(out)

    def write(self) -> None:
        self.partition.write_block(self.to_bytes(), self.block_number, 2)

    @property
    def next_block_number(self) -> int:
        """Block number of the next directory segment"""
        if self.next_logical_dir_segment == 0:
            return 0
        else:
            return (self.next_logical_dir_segment - 1) * 2 + self.partition.dir_segment

    def compact(self) -> None:
        """Compact multiple unused entries"""
        prev_empty_entry = None
        new_entries_list = []
        for entry in self.entries_list:
            if not entry.is_empty:
                prev_empty_entry = None
                new_entries_list.append(entry)
            elif prev_empty_entry is None:
                prev_empty_entry = entry
                new_entries_list.append(entry)
            else:
                prev_empty_entry.length = prev_empty_entry.length + entry.length
                if entry.is_end_of_segment:
                    prev_empty_entry.status = prev_empty_entry.status | E_EOS
        self.entries_list = new_entries_list

    def __str__(self) -> str:
        buf = io.StringIO()
        buf.write("\n*Segment\n")
        buf.write(f"Block number:               {self.block_number}\n")
        buf.write(f"Next dir segment:           {self.next_block_number}\n")
        buf.write(f"Number of segments:         {self.num_of_segments}\n")
        buf.write(f"Highest segment:            {self.highest_segment}\n")
        buf.write(f"Max entries:                {self.max_entries}\n")
        buf.write(f"Data block:                 {self.data_block_number}\n")
        buf.write("\nNum  File        Date       Length  Status  Job Chn  Block")
        buf.write("\n---  ----        ----       ------  ------  --- ---  -----\n")
        for i, x in enumerate(self.entries_list):
            buf.write(f"{i:02d}#  {x}\n")
        return buf.getvalue()


class RT11Partition:
    """
    RT–11 allows a block number up to 16 bits (65535) long.
    To utile largest disks, RT–11 uses disk partitioning and
    divides the disk into logical partitions of 65,535 blocks each.
    """

    fs: "RT11Filesystem"
    partition_number: int  # Partition number
    partition_size: int  # Partition size
    base_block_number: int  # Block number of the first block of this partition
    pack_cluster_size: int = DEFAULT_PACK_CLUSTER_SIZE  # Pack cluster size
    dir_segment: int = DEFAULT_DIR_SEGMENT  # First directory segment block
    ver: str = ""  # System version
    id: str = ""  # Volume Identification
    owner: str = ""  # Owner name
    sys_id: str = ""  # System Identification

    def __init__(self, fs: "RT11Filesystem", partition_number: int, partition_size: int):
        self.fs = fs
        self.partition_number = partition_number
        self.partition_size = partition_size
        self.base_block_number = partition_number * (1 << 16)

    @classmethod
    def read(cls, fs: "RT11Filesystem", partition_number: int, partition_size: int) -> "RT11Partition":
        self = cls(fs, partition_number, partition_size)
        self.read_home()
        return self

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        return self.fs.read_block(block_number + self.base_block_number, number_of_blocks)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        self.fs.write_block(buffer, block_number + self.base_block_number, number_of_blocks)

    def read_home(self) -> None:
        """Read home block"""
        tmp = self.read_block(HOMEBLK)
        self.pack_cluster_size = bytes_to_word(tmp[466:468]) or DEFAULT_PACK_CLUSTER_SIZE
        self.dir_segment = bytes_to_word(tmp[468:470]) or DEFAULT_DIR_SEGMENT
        self.ver = rad2asc(tmp[470:472])
        self.id = tmp[472:484].decode("ascii", "replace").replace("�", "?")
        self.owner = tmp[484:496].decode("ascii", "replace").replace("�", "?")
        self.sys_id = tmp[496:508].decode("ascii", "replace").replace("�", "?")
        self.checksum = bytes_to_word(tmp[510:512])

    def write_home(self) -> None:
        """Write home block"""
        # Convert data to bytes
        pack_cluster_size_bytes = word_to_bytes(self.pack_cluster_size)
        dir_segment_bytes = word_to_bytes(self.dir_segment)
        ver_bytes = asc2rad(self.ver)
        id_bytes = self.id.encode("ascii")
        owner_bytes = self.owner.encode("ascii")
        sys_id_bytes = self.sys_id.encode("ascii")
        checksum_bytes = word_to_bytes(0)
        # Create a byte array for the home block
        home_block = bytearray([0] * BLOCK_SIZE)
        # Fill the byte array with the data
        home_block[466:468] = pack_cluster_size_bytes
        home_block[468:470] = dir_segment_bytes
        home_block[470:472] = ver_bytes
        home_block[472:484] = id_bytes.ljust(12, b'\0')  # Pad with null bytes if needed
        home_block[484:496] = owner_bytes.ljust(12, b'\0')
        home_block[496:508] = sys_id_bytes.ljust(12, b'\0')
        home_block[510:512] = checksum_bytes
        # Write the block
        self.write_block(home_block, HOMEBLK)

    def read_dir_segments(self) -> t.Iterator["RT11Segment"]:
        """Read directory segments"""
        next_block_number = self.dir_segment
        while next_block_number != 0:
            segment = RT11Segment.read(self, next_block_number)
            next_block_number = segment.next_block_number
            yield segment

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator["RT11DirectoryEntry"]:
        if pattern:
            pattern = rt11_canonical_filename(pattern, wildcard=wildcard)
        for segment in self.read_dir_segments():
            for entry in segment.entries_list:
                if filename_match(entry.basename, pattern, wildcard):
                    if not include_all and (entry.is_empty or entry.is_tentative or entry.is_end_of_segment):
                        continue
                    yield entry

    @property
    def entries_list(self) -> t.Iterator["RT11DirectoryEntry"]:
        for segment in self.read_dir_segments():
            for entry in segment.entries_list:
                yield entry

    def get_file_entry(self, fullname: str) -> RT11DirectoryEntry:  # fullname=filename+ext
        fullname = rt11_canonical_filename(fullname)
        for entry in self.entries_list:
            if entry.fullname == fullname and entry.is_permanent:
                return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)

    def _split_segment(
        self,
        current_segment: "RT11Segment",
        entry: RT11DirectoryEntry,
        entry_number: int,
    ) -> t.Tuple["RT11Segment", "RT11DirectoryEntry", int]:
        # entry is the last entry of the current_segment,
        # new new segment will contain all the entries after that
        status_bak = entry.status  # save the status

        # find the new segment number
        segments = list(self.read_dir_segments())
        first_segment = segments[0]
        sn = [x.block_number for x in segments]
        p = 0
        segment_number_block_number = None
        for i in range(self.dir_segment, self.dir_segment + (first_segment.num_of_segments * 2), 2):
            p = p + 1
            if i not in sn:
                segment_number_block_number = i
                break
        if segment_number_block_number is None:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

        # set the next segment of the current segment
        current_segment.next_logical_dir_segment = (segment_number_block_number - self.dir_segment) // 2 + 1
        # mark the entry as end of segment
        entry.status = E_EOS
        # write the current segment
        current_segment.write()

        # update the total num of segments
        if first_segment.block_number == current_segment.block_number:
            current_segment.num_of_segments = len(segments)
            current_segment.write()
        else:
            first_segment.num_of_segments = len(segments)
            first_segment.write()

        # create the new segment
        segment = RT11Segment(self)
        segment.block_number = segment_number_block_number
        segment.num_of_segments = first_segment.num_of_segments
        segment.next_logical_dir_segment = 0
        segment.highest_segment = 1
        segment.extra_bytes = segments[0].extra_bytes
        segment.data_block_number = entry.file_position + entry.length
        segment.entries_list = []

        # create the new entry list
        for i, e in enumerate(current_segment.entries_list[entry_number:]):
            entry = RT11DirectoryEntry.copy(e)
            if i == 0:
                entry.status = status_bak
            segment.entries_list.append(entry)
        segment.write()

        return segment, segment.entries_list[0], 0

    def _search_empty_entry(self, length: int, fullname: str) -> t.Tuple["RT11Segment", "RT11DirectoryEntry", int]:
        """
        Searches for an empty area that is large enough to accommodate the new file
        """
        entry: t.Optional[RT11DirectoryEntry] = None
        entry_number: int = -1
        for segment in self.read_dir_segments():
            for i, e in enumerate(segment.entries_list):
                if e.is_empty and e.length >= length:
                    if entry is None or entry.length > e.length:
                        entry = e
                        entry_number = i
                        if entry.length == length:
                            return segment, entry, entry_number
        if entry is None:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), fullname)
        return segment, entry, entry_number

    def allocate_space(
        self,
        fullname: str,  # fullname=filename+ext, length in blocks
        length: int,  # length in blocks
        creation_date: t.Optional[date] = None,  # optional creation date
    ) -> RT11DirectoryEntry:
        """
        Allocate space for a new file
        """
        # Search for an empty entry
        segment, entry, entry_number = self._search_empty_entry(length, fullname)
        if entry.length != length:
            if len(segment.entries_list) >= segment.max_entries:
                segment, entry, entry_number = self._split_segment(segment, entry, entry_number)
            # If the entry length is not equal to the requested length,
            # create a new empty space entry after the entry
            empty_entry = RT11DirectoryEntry(self)
            empty_entry.filename = entry.filename
            empty_entry.extension = entry.extension
            empty_entry.length = entry.length - length
            empty_entry.file_position = entry.file_position + length
            empty_entry.status = E_MPTY
            segment.entries_list.insert(entry_number + 1, empty_entry)
        # Fill the entry
        tmp = os.path.splitext(fullname.upper())
        entry.filename = tmp[0]
        entry.extension = tmp[1] and tmp[1][1:] or ""
        entry.raw_creation_date = date_to_rt11(creation_date)
        entry.job = 0
        entry.channel = 0
        entry.status = E_PERM
        entry.length = length
        # Write the segment
        segment.write()
        return entry

    @classmethod
    def create(
        cls, fs: "RT11Filesystem", partition_number: int, partition_size: int, **kwargs: t.Union[bool, str]
    ) -> "RT11Partition":
        """
        Initialize the RT-11 partition
        """
        self = cls(fs, partition_number, partition_size)
        # Determinate the number of directory segments
        if partition_size >= 18000:  # 9Mb
            # DW (RD51) 10Mb
            # DL (RL02) 10.4M
            # DM (RK06) 13.8M
            num_of_segments = 31
        elif partition_size >= 4000:  # 2Mb
            # RK (RK05) 2.45M
            # DW (RD50) 5Mb
            # DL (RL01) 5.2M
            num_of_segments = 16
        elif partition_size >= 800:  # 400Kb
            # DZ (RX50) 400K
            # DY (RX02) 512K
            num_of_segments = 4
        else:
            # DX (RX01) 256K
            num_of_segments = 1
        # Write the home block
        self.pack_cluster_size = DEFAULT_PACK_CLUSTER_SIZE
        self.dir_segment = DEFAULT_DIR_SEGMENT
        self.ver = "V05"
        self.id = ""
        self.owner = ""
        self.sys_id = "DECRT11A"
        self.write_home()
        # Create the directory segment
        segment = RT11Segment(self)
        segment.block_number = self.dir_segment
        segment.num_of_segments = num_of_segments
        segment.next_logical_dir_segment = 0
        segment.highest_segment = 1
        segment.extra_bytes = 0
        segment.data_block_number = self.dir_segment + (num_of_segments * 2)
        # first entry (empty area)
        dir_entry = RT11DirectoryEntry(self)
        dir_entry.file_position = segment.data_block_number
        dir_entry.length = partition_size - dir_entry.file_position
        dir_entry.status = E_MPTY
        dir_entry.filename = "EMPTY"
        dir_entry.extension = "FIL"
        segment.entries_list.append(dir_entry)
        # second entry (end-of-segment)
        dir_entry = RT11DirectoryEntry(self)
        dir_entry.file_position = partition_size
        dir_entry.status = E_EOS
        segment.entries_list.append(dir_entry)
        segment.write()
        return self

    def free(self) -> int:
        """
        Get the number of free blocks
        """
        unused = 0
        for segment in self.read_dir_segments():
            for x in segment.entries_list:
                if x.is_empty or x.is_tentative:
                    unused = unused + x.length
        return unused

    def examine(self) -> str:
        buf = io.StringIO()
        buf.write("\n*Partition\n")
        buf.write(f"Partition number:           {self.partition_number}\n")
        buf.write(f"Partition size:             {self.partition_size}\n")
        buf.write(f"Partition starting block:   {self.base_block_number}\n")
        buf.write(f"Pack cluster size:          {self.pack_cluster_size}\n")
        buf.write(f"Directory segment:          {self.dir_segment}\n")
        buf.write(f"System version:             {self.ver}\n")
        buf.write(f"Volume identification:      {self.id}\n")
        buf.write(f"Owner name:                 {self.owner}\n")
        buf.write(f"System identification:      {self.sys_id}\n")
        buf.write(f"Checksum:                   {self.checksum:x}\n")
        return buf.getvalue()


class RT11Filesystem(AbstractRXBlockFilesystem):
    """
    RT-11 Filesystem
    """

    fs_name = "rt11"
    fs_description = "PDP-11 RT-11"
    fs_platforms = ["pdp11"]

    partitions: t.List[RT11Partition]  # Disk partitions
    current_partition: int  # Current partition
    number_of_blocks: int  # Number of blocks

    @classmethod
    def mount(
        cls,
        file_or_dev: t.Union["AbstractFile", "AbstractDevice"],
        strict: t.Union[bool, str] = True,
        **kwargs: t.Union[bool, str],
    ) -> "RT11Filesystem":
        self = cls(file_or_dev)
        self.current_partition = 0
        self.number_of_blocks = self.dev.get_size() // BLOCK_SIZE
        # Calculate the number of partitions and their sizes
        self.partitions = [
            RT11Partition.read(self, i, size) for (i, size) in enumerate(self.calculate_partition_sizes())
        ]
        if strict:
            self.check_rt11()
        return self

    def check_rt11(self) -> None:
        """
        Check if the filesystem is a valid RT-11 filesystem
        """
        for partition in self.partitions:
            if partition.pack_cluster_size != 1:
                raise OSError(errno.EIO, "Pack cluster size is not 1")
            if partition.dir_segment >= partition.partition_size:
                raise OSError(errno.EIO, "Invalid directory segment")

    def calculate_partition_sizes(self) -> t.List[int]:
        """
        Calculate the partition sizes based on the device size
        """
        partition_sizes = []
        tmp = self.number_of_blocks
        while tmp > 0:
            if tmp >= 1 << 16:
                partition_sizes.append(MAX_PARTITION_SIZE)
                tmp = tmp - (1 << 16)
            else:
                partition_sizes.append(tmp)
                tmp = 0
        return partition_sizes

    def get_partition(self, partition_number: int) -> RT11Partition:
        """
        Get a partition by number
        """
        try:
            return self.partitions[partition_number]
        except Exception:
            raise FileNotFoundError(errno.ENOENT, "Partition not found", partition_number)

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator["RT11DirectoryEntry"]:
        partition = self.current_partition
        if pattern:
            partition, pattern = rt11_split_fullname(partition, pattern, wildcard)
        for segment in self.get_partition(partition).read_dir_segments():
            for entry in segment.entries_list:
                if filename_match(entry.basename, pattern, wildcard):
                    if not include_all and (entry.is_empty or entry.is_tentative or entry.is_end_of_segment):
                        continue
                    yield entry

    @property
    def entries_list(self) -> t.Iterator["RT11DirectoryEntry"]:
        for segment in self.get_partition(self.current_partition).read_dir_segments():
            for entry in segment.entries_list:
                yield entry

    def get_file_entry(self, fullname: str) -> RT11DirectoryEntry:  # fullname=filename+ext
        partition = self.current_partition
        if fullname:
            partition, fullname = rt11_split_fullname(partition, fullname, wildcard=False)  # type: ignore
        for segment in self.get_partition(partition).read_dir_segments():
            for entry in segment.entries_list:
                if entry.fullname == fullname and entry.is_permanent:
                    return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)

    def write_bytes(
        self,
        fullname: str,
        content: t.Union[bytes, bytearray],
        creation_date: t.Optional[date] = None,
        file_type: t.Optional[str] = None,
        file_mode: t.Optional[str] = None,
    ) -> None:
        number_of_blocks = int(math.ceil(len(content) * 1.0 / BLOCK_SIZE))
        entry = self.create_file(fullname, number_of_blocks, creation_date, file_type)
        # TODO open file
        if not entry:
            return
        content = content + (b"\0" * BLOCK_SIZE)
        self.write_block(content, entry.file_position, entry.length)

    def create_file(
        self,
        fullname: str,
        number_of_blocks: int,  # length in blocks
        creation_date: t.Optional[date] = None,  # optional creation date
        file_type: t.Optional[str] = None,
    ) -> RT11DirectoryEntry:
        partition, fullname = rt11_split_fullname(self.current_partition, fullname, wildcard=False)  # type: ignore
        part = self.get_partition(partition)
        try:
            part.get_file_entry(fullname).delete()
        except FileNotFoundError:
            pass
        return part.allocate_space(fullname, number_of_blocks, creation_date)

    def chdir(self, fullname: str) -> bool:
        try:
            partition = int(fullname)
        except:
            return False
        if partition < 0 or partition >= len(self.partitions):
            return False
        self.current_partition = int(fullname)
        return True

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        i = 0
        files = 0
        blocks = 0
        unused = 0
        partition = self.current_partition
        if pattern:
            partition, pattern = rt11_split_fullname(partition, pattern, wildcard=True)
        part = self.get_partition(partition)
        for segment in part.read_dir_segments():
            for x in segment.entries_list:
                if x.is_empty or x.is_tentative:
                    unused = unused + x.length
                if not filename_match(x.basename, pattern, wildcard=True):
                    continue
                if (
                    not x.is_empty
                    and not x.is_tentative
                    and not x.is_permanent
                    and not x.is_delete_protected
                    and not x.is_read_only
                ):
                    continue
                i = i + 1
                if x.is_empty or x.is_tentative:
                    if options.get("brief"):
                        continue
                    fullname = "< UNUSED >"
                    dt = ""
                else:
                    fullname = x.is_empty and x.filename or "%-6s.%-3s" % (x.filename, x.extension)
                    if options.get("brief"):
                        # Lists only file names and file types
                        sys.stdout.write(f"{fullname}\n")
                        continue
                    dt = x.creation_date and x.creation_date.strftime("%d-%b-%y") or ""
                if x.is_permanent:
                    files = files + 1
                    blocks = blocks + x.length
                if x.is_delete_protected:
                    attr = "P"
                elif x.is_read_only:
                    attr = "A"
                else:
                    attr = " "
                sys.stdout.write(f"{fullname:10} {x.length:5}{attr:1} {dt:9}")
                if i % 2 == 1:
                    sys.stdout.write("    ")
                else:
                    sys.stdout.write("\n")
        if options.get("brief"):
            return
        if i % 2 == 1:
            sys.stdout.write("\n")
        sys.stdout.write(f" {files} Files, {blocks} Blocks\n")
        sys.stdout.write(f" {unused} Free blocks\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        if arg:
            self.dump(arg)
        else:
            is_rx = getattr(self.dev, 'is_rx', False)
            sys.stdout.write(f"Number of partitions:       {len(self.partitions)}\n")
            sys.stdout.write(f"Is RX01/RX02:               {'YES' if is_rx else 'NO'}\n")
            for partition in self.partitions:
                sys.stdout.write(partition.examine())
                for segment in partition.read_dir_segments():
                    sys.stdout.write(f"{segment}\n")

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.dev.get_size()

    @classmethod
    def initialize(
        cls, file_or_dev: t.Union["AbstractFile", "AbstractDevice"], **kwargs: t.Union[bool, str]
    ) -> "RT11Filesystem":
        """
        Write an RT–11 empty device directory
        """
        self = cls(file_or_dev)
        size = self.dev.get_size()
        if size == RX01_SIZE:
            # Adjust the size for RX01 (skip track 0)
            size = size - RX_SECTOR_TRACK * RX01_SECTOR_SIZE
            self.number_of_blocks = size // BLOCK_SIZE
            self.partitions = [RT11Partition.create(self, 0, self.number_of_blocks)]
        elif size == RX02_SIZE:
            # Adjust the size for RX02 (skip track 0)
            size = size - RX_SECTOR_TRACK * RX02_SECTOR_SIZE
            self.number_of_blocks = size // BLOCK_SIZE
            self.partitions = [RT11Partition.create(self, 0, self.number_of_blocks)]
        else:
            self.number_of_blocks = size // BLOCK_SIZE
            self.partitions = [
                RT11Partition.create(self, i, size) for (i, size) in enumerate(self.calculate_partition_sizes())
            ]
        self.current_partition = 0
        return self

    def get_pwd(self) -> str:
        if self.current_partition == 0:
            return ""
        else:
            return f"[{self.current_partition}]"
