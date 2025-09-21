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


import struct
import typing as t
from dataclasses import dataclass

from ..commons import dump_struct

__all__ = [
    "AppleSingle",
    "ProDOSFileInfo",
    "FinderInfo",
]

APPLE_SINGLE_MAGIC = 0x00051600
APPLE_SINGLE_HEADER_FORMAT = ">II16sH"
APPLE_SINGLE_HEADER_SIZE = struct.calcsize(APPLE_SINGLE_HEADER_FORMAT)
APPLE_SINGLE_ENTRY_FORMAT = ">III"
APPLE_SINGLE_ENTRY_SIZE = struct.calcsize(APPLE_SINGLE_ENTRY_FORMAT)
APPLE_SINGLE_PRODOS_INFO_FORMAT = ">HHI"
APPLE_SINGLE_PRODOS_INFO_SIZE = struct.calcsize(APPLE_SINGLE_PRODOS_INFO_FORMAT)
APPLE_SINGLE_FINDER_INFO_FORMAT = ">4s4sHLH H6sBBHI"
APPLE_SINGLE_FINDER_INFO_SIZE = struct.calcsize(APPLE_SINGLE_FINDER_INFO_FORMAT)
APPLE_SINGLE_DATA_FORK = 1
APPLE_SINGLE_RESOURCE_FORK = 2
APPLE_SINGLE_FINDER_INFO = 9
APPLE_SINGLE_PRODOS_INFO = 11
APPLE_SINGLE_VERSION_2 = 0x20000

assert APPLE_SINGLE_FINDER_INFO_SIZE == 32


@dataclass
class ProDOSFileInfo:
    access: int = 0  # ProDOS access
    file_type: int = 0  # ProDOS file type
    aux_type: int = 0  # ProDOS aux type

    @classmethod
    def read(cls, buffer: t.Union[bytes, bytearray], position: int) -> "ProDOSFileInfo":
        self = cls()
        (
            self.access,
            self.file_type,
            self.aux_type,
        ) = struct.unpack_from(APPLE_SINGLE_PRODOS_INFO_FORMAT, buffer, position)
        return self

    def write(self) -> bytes:
        return struct.pack(
            APPLE_SINGLE_PRODOS_INFO_FORMAT,
            self.access,
            self.file_type,
            self.aux_type,
        )

    def __str__(self) -> str:
        return f"Access: {self.access:04X} File type: {self.file_type:04X} Aux type: {self.aux_type:08X}"


@dataclass
class FinderInfo:
    """
    Finder info/extended info structure

    Inside Macintosh Volume IV, Pag 193
    https://vintageapple.org/inside_o/pdf/Inside_Macintosh_Volume_IV_1986.pdf
    """

    # Finder information
    raw_file_type: bytes = b"????"  # file type (4 characters)
    raw_file_creator: bytes = b"????"  # file creator (4 characters)
    finder_flags: int = 0  # finder flags (2 bytes)
    icon_position: int = 0  # icon position (4 bytes)
    folder_number: int = 0  # folder number (2 bytes)
    # Extended Finder information
    icon_id: int = 0  # icon ID (2 bytes)
    reserved: bytes = b"\0\0\0\0\0\0"  # reserved (6 bytes)
    script_code: int = 0  # script code (1 byte)
    extended_flags: int = 0  # extended flags (1 byte)
    comment_id: int = 0  # comment ID (2 bytes)
    put_away_folder_id: int = 0  # home directory ID (4 bytes)

    @classmethod
    def read(cls, buffer: t.Union[bytes, bytearray], position: int) -> "FinderInfo":
        self = cls()
        (
            self.raw_file_type,
            self.raw_file_creator,
            self.finder_flags,
            self.icon_position,
            self.folder_number,
            self.icon_id,
            self.reserved,
            self.script_code,
            self.extended_flags,
            self.comment_id,
            self.put_away_folder_id,
        ) = struct.unpack_from(APPLE_SINGLE_FINDER_INFO_FORMAT, buffer, position)
        return self

    def write(self) -> bytes:
        return struct.pack(
            APPLE_SINGLE_FINDER_INFO_FORMAT,
            self.raw_file_type,
            self.raw_file_creator,
            self.finder_flags,
            self.icon_position,
            self.folder_number,
            self.icon_id,
            self.reserved,
            self.script_code,
            self.extended_flags,
            self.comment_id,
            self.put_away_folder_id,
        )


@dataclass
class AppleSingle:
    """
    AppleSingle file format to store data fork, resource fork and metadata in a single file

    An AppleSingle file consists of a header followed by one or more data entries.
    The header consists of several fixed fields and a list of entry descriptors, each
    pointing to a data entry

    https://nulib.com/library/AppleSingle_AppleDouble.pdf
    """

    data: t.Optional[bytes] = None  # Data fork
    resource: t.Optional[bytes] = None  # Resource fork
    prodos_file_info: t.Optional[ProDOSFileInfo] = None  # ProDOS file info
    finder_info: t.Optional[FinderInfo] = None  # Finder info

    @classmethod
    def read(cls, content: t.Union[bytes, bytearray]) -> "AppleSingle":
        """
        Parse an AppleSingle file
        """
        self = cls()
        # Read the header
        (
            magic,
            _version,
            _filler,
            number_of_entries,
        ) = struct.unpack_from(APPLE_SINGLE_HEADER_FORMAT, content, 0)
        if magic != APPLE_SINGLE_MAGIC:
            raise ValueError("Invalid AppleSingle format")
        # Read the entries
        for i in range(0, number_of_entries):
            position = APPLE_SINGLE_HEADER_SIZE + i * APPLE_SINGLE_ENTRY_SIZE
            (
                entry_id,
                entry_offset,
                entry_length,
            ) = struct.unpack_from(APPLE_SINGLE_ENTRY_FORMAT, content, position)
            if entry_id == APPLE_SINGLE_DATA_FORK:
                data_fork_offset = entry_offset
                data_fork_length = entry_length
                self.data = bytes(content[data_fork_offset : data_fork_offset + data_fork_length])
            elif entry_id == APPLE_SINGLE_RESOURCE_FORK:
                resource_fork_offset = entry_offset
                resource_fork_length = entry_length
                self.resource = bytes(content[resource_fork_offset : resource_fork_offset + resource_fork_length])
            elif entry_id == APPLE_SINGLE_PRODOS_INFO:
                self.prodos_file_info = ProDOSFileInfo.read(content, entry_offset)
            elif entry_id == APPLE_SINGLE_FINDER_INFO:
                self.finder_info = FinderInfo.read(content, entry_offset)
        return self

    def write(self) -> bytes:
        """
        Encode an AppleSingle file
        """
        num_of_entries = 0
        if self.prodos_file_info is not None:
            num_of_entries += 1
        if self.finder_info is not None:
            num_of_entries += 1
        if self.data is not None:
            num_of_entries += 1
        if self.resource is not None:
            num_of_entries += 1

        # Write the header
        buffer = bytearray()
        buffer += struct.pack(
            APPLE_SINGLE_HEADER_FORMAT,
            APPLE_SINGLE_MAGIC,
            APPLE_SINGLE_VERSION_2,
            b"\0" * 16,  # filler
            num_of_entries,  # number of entries
        )
        offset = APPLE_SINGLE_HEADER_SIZE + num_of_entries * APPLE_SINGLE_ENTRY_SIZE

        # ProDOS file info entry
        if self.prodos_file_info is not None:
            buffer += struct.pack(
                APPLE_SINGLE_ENTRY_FORMAT,
                APPLE_SINGLE_PRODOS_INFO,  # entry_id
                offset,  # offset
                APPLE_SINGLE_PRODOS_INFO_SIZE,  # length
            )
            offset += APPLE_SINGLE_PRODOS_INFO_SIZE

        # Finder info entry
        if self.finder_info is not None:
            buffer += struct.pack(
                APPLE_SINGLE_ENTRY_FORMAT,
                APPLE_SINGLE_FINDER_INFO,  # entry_id
                offset,  # offset
                APPLE_SINGLE_FINDER_INFO_SIZE,  # length
            )
            offset += APPLE_SINGLE_FINDER_INFO_SIZE

        # Data fork entry
        if self.data is not None:
            buffer += struct.pack(
                APPLE_SINGLE_ENTRY_FORMAT,
                APPLE_SINGLE_DATA_FORK,  # entry_id
                offset,  # offset
                len(self.data),  # length
            )
            offset += len(self.data)

        # Resource fork entry
        if self.resource is not None:
            buffer += struct.pack(
                APPLE_SINGLE_ENTRY_FORMAT,
                APPLE_SINGLE_RESOURCE_FORK,  # entry_id
                offset,  # offset
                len(self.resource),  # length
            )
            offset += len(self.resource)

        # Write the entries
        if self.prodos_file_info is not None:
            buffer += self.prodos_file_info.write()
        if self.finder_info is not None:
            buffer += self.finder_info.write()
        if self.data is not None:
            buffer += self.data
        if self.resource is not None:
            buffer += self.resource
        return bytes(buffer)

    def __str__(self) -> str:
        data = {}
        if self.prodos_file_info is not None:
            data["ProDOS file info"] = str(self.prodos_file_info)
        if self.finder_info is not None:
            data["Finder info"] = str(self.finder_info)
        if self.data is not None:
            data["Data fork"] = f"{len(self.data)} bytes"
        if self.resource is not None:
            data["Resource fork"] = f"{len(self.resource)} bytes"
        return dump_struct(data, newline=True, format_label=False)
