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
import os
import re
import sys
import struct
import typing as t
from datetime import date

from ..abstract import XFERXPath, AbstractFile, AbstractFilesystem
from ..commons import ASCII, BLOCK_SIZE, IMAGE, READ_FILE_FULL, filename_match
from ..device.abstract import AbstractDevice
from ..device.block_12bit import BlockDevice12Bit

__all__ = [
    "LAP6File",
    "LAP6Path",
    "LAP6Filesystem",
]

DIR_ENTRY_SIZE = 8  # Directory entry size (words)
UNUSED = 0o5757
UNUSED_ENTRY = [UNUSED] * DIR_ENTRY_SIZE  # An unused entry segment has 0o5757 in all 8 words
FILENAME_LENGTH = 8  # Filename length (characters)
MAX_BLOCKS = 512  # Maximum number of blocks (in blocks)
INDEX_BLOCKS = 2  # Index blocks (in blocks)

STANDARD_LOWER_FILE_AREA = 0o000  # Lower file area start (block number)
STANDARD_LOWER_FILE_AREA_END = 0o267  # Lower file area end (block number)
STANDARD_UNUSED_BLOCK = 0o270  # Unused block start (block number)
STANDARD_LAP6_BLOCK = 0o300  # LAP6 block start (block number)
STANDARD_WORKING_AREA = 0o350  # Working area start (block number)
STANDARD_INDEX_BLOCK = 0o426  # Index block number (in blocks)
STANDARD_UPPER_FILE_AREA = 0o430  # Upper file area start (block number)
STANDARD_UPPER_FILE_AREA_END = 0o777  # Upper file area end (block number)

MANUSCRIPT_FORK = "M"  # Text files
BINARY_FORK = "B"  # Binary files


# LAP6 Keyboard Code: 6-bit code -> character
#
# LAP6 HANDBOOK, Pag 34
# https://bitsavers.org/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf

LAP6_CHARSET: dict[int, bytes] = {
    0o00: b"0",
    0o01: b"1",
    0o02: b"2",
    0o03: b"3",
    0o04: b"4",
    0o05: b"5",
    0o06: b"6",
    0o07: b"7",
    0o10: b"8",
    0o11: b"9",
    0o12: b"\n",  # EOL (newline)
    0o13: b"\x7f",  # DEL
    0o14: b" ",  # SPACE
    0o15: b"i",  # i ???
    0o16: b"p",  # p ???
    0o17: b"-",
    0o20: b"+",
    0o21: b"\\",  # a vertical bar ???
    0o22: b"#",
    0o23: b"",  # CASE control
    0o24: b"A",
    0o25: b"B",
    0o26: b"C",
    0o27: b"D",
    0o30: b"E",
    0o31: b"F",
    0o32: b"G",
    0o33: b"H",
    0o34: b"I",
    0o35: b"J",
    0o36: b"K",
    0o37: b"L",
    0o40: b"M",
    0o41: b"N",
    0o42: b"O",
    0o43: b"P",
    0o44: b"Q",
    0o45: b"R",
    0o46: b"S",
    0o47: b"T",
    0o50: b"U",
    0o51: b"V",
    0o52: b"W",
    0o53: b"X",
    0o54: b"Y",
    0o55: b"Z",
    0o56: b"~",  # META control
    0o60: b"?",
    0o61: b"=",
    0o62: b"u",
    0o63: b",",
    0o64: b".",
    0o65: b"&",
    0o66: b"[",
    0o70: b'"',  # CASE A
    0o71: b'"',  # CASE B
    0o72: b"<",  # CASE C
    0o73: b">",  # CASE D
    0o74: b"]",  # CASE E
    0o75: b"*",  # CASE F
    0o76: b":",  # CASE G
    0o77: b"\0",
}


def lap6_word_to_ascii(word: int) -> bytes:
    """Decode a 12-bit LINC word into two LAP6 characters."""
    if not 0 <= word <= 0xFFF:
        raise ValueError("word must be a 12-bit unsigned value")
    high = (word >> 6) & 0x3F
    low = word & 0x3F
    return LAP6_CHARSET.get(high, b"?") + LAP6_CHARSET.get(low, b"?")


def ascii_to_lap6_word(data: bytes) -> int:
    """Encode two LAP6 characters into a 12-bit LINC word."""
    if len(data) != 2:
        data = data + b"\0"
    high = next((k for k, v in LAP6_CHARSET.items() if v == data[0:1]), 0)
    low = next((k for k, v in LAP6_CHARSET.items() if v == data[1:2]), 0)
    return (high << 6) | low


def lap6_canonical_filename(name: t.Optional[str], wildcard: bool = False) -> str:
    """
    Generate the canonical LAP6 name
    """
    name = (name or "").upper()[:FILENAME_LENGTH]
    return (
        from_12bit_words_to_bytes(from_bytes_to_12bit_words(name.encode("ascii")))
        .decode("ascii", errors="ignore")
        .strip("\0")
    )


def from_12bit_words_to_bytes(words: list[int], file_mode: str = ASCII) -> bytes:
    """
    Convert 12bit words to bytes
    """
    if file_mode == IMAGE:
        return struct.pack(f"<{len(words)}H", *words)
    else:
        return b"".join([lap6_word_to_ascii(x) for x in words])


def from_bytes_to_12bit_words(byte_data: t.Union[bytes, bytearray], file_mode: str = "ASCII") -> t.List[int]:
    """
    Convert bytes to 12-bit words.
    """
    words = []
    if file_mode == IMAGE:
        len_words = len(byte_data) // 2
        return [x & 0o7777 for x in struct.unpack(f"<{len_words}H", byte_data)]
    else:
        for i in range(0, len(byte_data), 2):
            chr1 = byte_data[i] & 0xFF
            try:
                chr2 = byte_data[i + 1] & 0xFF
            except IndexError:
                chr2 = 0
            words.append(ascii_to_lap6_word(bytes([chr1, chr2])))
    return words


def encode_lap6_file(content: t.Union[bytes, bytearray], fork: str) -> t.List[int]:
    """
    Encode the file content into 12-bit words for the specified fork type.
    """
    if fork == BINARY_FORK:
        data = bytes(content)
        if len(data) % 2:
            data += b"\0"
        return from_bytes_to_12bit_words(data, IMAGE)

    words = [0o2065, 0o5712]
    for offset in range(0, len(content), 2):
        words.append(ascii_to_lap6_word(bytes(content[offset : offset + 2])))
    if len(content) % 2 == 0:
        words.append(0o7777)
    return words


def oct_dump(words: t.List[int], words_per_line: int = 8) -> None:
    """
    Display contents in octal
    """
    for i in range(0, len(words), words_per_line):
        line = words[i : i + words_per_line]
        ascii_str = "".join([chr(x) if 32 <= x <= 126 else "." for x in from_12bit_words_to_bytes(line)])
        oct_str = " ".join([f"{x:04o}" for x in line])
        sys.stdout.write(f"{i:08o}   {oct_str.ljust(5 * words_per_line)}  {ascii_str}\n")


class LAP6File(AbstractFile):
    entry: "LAP6Path"
    file_mode: str  # file mode: "ASCII" or "IMAGE"
    fork: str  # fork type: "M" for manuscript, "B" for binary
    length: int  # fork's length in blocks
    first_block_number: int  # fork's first block number

    def __init__(self, entry: "LAP6Path", file_mode: t.Optional[str] = None, fork: t.Optional[str] = None):
        self.entry = entry
        self.fork = fork.upper() if fork else MANUSCRIPT_FORK
        if file_mode is not None:
            self.file_mode = file_mode
        else:
            self.file_mode = IMAGE if self.fork == BINARY_FORK else ASCII
        self.length = entry.get_length(self.fork)
        self.first_block_number = self.entry.get_first_block_number(self.fork)

    @property
    def name(self) -> str:
        """Final path component"""
        return self.entry.name

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as 256 12bit words
        """
        return self.entry.fs.read_words_block(block_number + self.first_block_number)

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write 256 12bit words as a block
        """
        self.entry.fs.write_words_block(block_number + self.first_block_number, words)

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.length
        if self.closed or block_number < 0 or number_of_blocks < 0 or block_number + number_of_blocks > self.length:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        data = bytearray()
        for i in range(number_of_blocks):
            words = self.read_words_block(i)
            t = from_12bit_words_to_bytes(words, self.file_mode)
            data.extend(t)
        return bytes(data)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the file
        """
        if self.closed or block_number < 0 or number_of_blocks < 0 or block_number + number_of_blocks > self.length:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        for i in range(number_of_blocks):
            block_position = block_number + self.first_block_number + i
            data = buffer[i * BLOCK_SIZE : (i + 1) * BLOCK_SIZE]
            words = from_bytes_to_12bit_words(data, self.file_mode)
            self.entry.fs.write_words_block(block_position, words)

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.length * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return self.entry.get_block_size()

    def __str__(self) -> str:
        return self.entry.fullname


class LAP6Path(XFERXPath):
    """
    An entry in the Index describes a manuscript or a binary program, or both.
    A manuscript and a binary program of the same name must be described in the same entry.
    A name does not appear without at least one of these entries.
    An empty entry segment has 0o5757 in all 8 words.

    An entry name can be any combination of displayable characters, except the comma.
    The name can be up to 8 characters long, and can contain spaces.

    Word
          +-----------------------------------+
        0 | File name char 1-2                |
        1 | File name char 3-4                |
        2 | File name char 5-6                |
        3 | File name char 7-8                |
          +-----------------------------------+
        4 | Manuscript first block number     | \
          +-----------------------------------+ | (0o5757 = no manuscript entry)
        5 | Manuscript length in blocks       | /
          +-----------------------------------+
        6 | Binary first block number         | \
          +-----------------------------------+ | (0o5757 = no binary entry)
        7 | Binary length in blocks           | /
          +-----------------------------------+
    """

    fs: "LAP6Filesystem"

    filename: str = ""
    manuscript_block_number: int = 0  # manuscript fork first block number
    manuscript_length: int = 0  # in blocks
    binary_block_number: int = 0  # binary fork first block number
    binary_length: int = 0  # in blocks

    def __init__(self, fs: "LAP6Filesystem"):
        self.fs = fs

    @classmethod
    def read(cls, fs: "LAP6Filesystem", words: t.List[int], position: int) -> "LAP6Path":
        self = cls(fs)
        words = words[position : position + DIR_ENTRY_SIZE]
        if words == UNUSED_ENTRY:
            # An unused entry segment has 0o5757 in all 8 words
            self.filename = ""
            return self
        self.filename = from_12bit_words_to_bytes(words[0:4]).decode("ascii", errors="ignore").strip("\0")
        self.manuscript_block_number = words[4]
        self.manuscript_length = words[5]
        self.binary_block_number = words[6]
        self.binary_length = words[7]
        return self

    def to_words(self) -> t.List[int]:
        """
        Convert the entry to a list of 8 words
        """
        if self.is_empty:
            return UNUSED_ENTRY
        words = []
        words.append(ascii_to_lap6_word(self.filename[0:2].encode("ascii")))
        words.append(ascii_to_lap6_word(self.filename[2:4].encode("ascii")))
        words.append(ascii_to_lap6_word(self.filename[4:6].encode("ascii")))
        words.append(ascii_to_lap6_word(self.filename[6:8].encode("ascii")))
        words.append(self.manuscript_block_number)
        words.append(self.manuscript_length)
        words.append(self.binary_block_number)
        words.append(self.binary_length)
        return words

    @property
    def is_empty(self) -> bool:
        return not self.filename

    @property
    def fullname(self) -> str:
        """Name with path"""
        return self.name

    @property
    def name(self) -> str:
        """Final path component"""
        return self.filename

    @property
    def parent(self) -> "LAP6Index":
        """The logical parent"""
        return self.fs.get_root()

    def get_first_block_number(self, fork: t.Optional[str] = None) -> int:
        """
        Get the first block number
        """
        if fork and fork.upper() == BINARY_FORK:
            return self.binary_block_number if self.binary_block_number != UNUSED else 0
        else:
            return self.manuscript_block_number if self.manuscript_block_number != UNUSED else 0

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """
        Get the length in blocks
        """
        if fork and fork.upper() == BINARY_FORK:
            return self.binary_length if self.binary_block_number != UNUSED else 0
        else:
            return self.manuscript_length if self.manuscript_block_number != UNUSED else 0

    def get_size(self, fork: t.Optional[str] = None) -> int:
        """
        Get file size in bytes
        """
        return self.get_length(fork) * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return BLOCK_SIZE

    def open(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> LAP6File:
        """
        Open a file
        """
        return LAP6File(self, file_mode, fork)

    def delete(self) -> bool:
        """Delete this file and release both of its forks."""
        index = self.fs.get_root()
        words = index.read_words()
        name = lap6_canonical_filename(self.name, wildcard=False)
        for position in range(DIR_ENTRY_SIZE, len(words), DIR_ENTRY_SIZE):
            entry = LAP6Path.read(self.fs, words, position)
            if entry.name == name:
                words[position : position + DIR_ENTRY_SIZE] = UNUSED_ENTRY
                index.write_words(words)
                return True
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.name)

    def read_bytes(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> bytes:
        """Get the content of the file"""
        if file_mode is None:
            if fork and fork.upper() == BINARY_FORK:
                file_mode = IMAGE
                fork = BINARY_FORK
            else:
                file_mode = ASCII
                fork = MANUSCRIPT_FORK
        if fork is None:
            if file_mode == IMAGE:
                fork = BINARY_FORK
            else:
                fork = MANUSCRIPT_FORK
        # Read the file content as 12-bit words
        with self.open(fork=fork) as f:
            words = []
            for i in range(f.length):
                words.extend(f.read_words_block(i))
        if file_mode == IMAGE:
            return from_12bit_words_to_bytes(words, IMAGE)
        # LAP6 Manuscript structure
        # - The first word contains the number 0o2065
        # - The second word contains 0o5712
        # - The last half-word of the manuscript contains 77
        # LAP6 HANDBOOK, Pag 39
        # https://bitsavers.org/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf
        if words[0] != 0o2065:
            raise OSError(errno.EIO, f"Invalid LAP6 manuscript: first word is {words[0]:06o} instead of 02065")
        if words[1] != 0o5712:
            raise OSError(errno.EIO, f"Invalid LAP6 manuscript: second word is {words[1]:06o} instead of 05712")
        data = from_12bit_words_to_bytes(words[2:], ASCII)
        # Cut the data at the "\0" (0o77 converted to ASCII)
        end_index = data.rfind(b"\0")
        if end_index != -1:
            data = data[:end_index]
        return data

    def examine(self) -> str:
        """
        Examine the directory entry
        """
        buf = io.StringIO()
        buf.write(f"Name:             {self.name}\n")
        if self.manuscript_block_number != UNUSED:
            buf.write(f"Manuscript:\n")
            buf.write(f"  First block:    {self.manuscript_block_number} \n")
            buf.write(f"  Length:         {self.manuscript_length} blocks\n")
        if self.binary_block_number != UNUSED:
            buf.write(f"Binary:\n")
            buf.write(f"  First block:    {self.binary_block_number} \n")
            buf.write(f"  Length:         {self.binary_length} blocks\n")
        return buf.getvalue()

    def __str__(self) -> str:
        if self.manuscript_block_number != UNUSED:
            manuscript = f"M {self.manuscript_block_number:>4} {self.manuscript_length:>4}"
        else:
            manuscript = "- ---- ----"
        if self.binary_block_number != UNUSED:
            binary = f"B {self.binary_block_number:>4} {self.binary_length:>4}"
        else:
            binary = "- ---- ----"
        return f"{self.name:<8}  {manuscript:>10}  {binary:>10}"

    def __repr__(self) -> str:
        return str(self)


class LAP6Index(XFERXPath):
    """
    LAP6 Index is always two blocks long.
    It is always in tape blocks whose block numbers end in 0o6 and 0o7.
    The blocks are divided into 64 entries of 8 words each.
    The first entry is the Index identifier (0o5757 in all 8 words).

    LAP6 HANDBOOK, Pag 41
    https://bitsavers.org/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf
    """

    fs: "LAP6Filesystem"

    @property
    def fullname(self) -> str:
        """Name with path"""
        return ""

    @property
    def name(self) -> str:
        """Final path component"""
        return ""

    def is_dir(self) -> bool:
        """Is a directory"""
        return True

    def is_mount(self) -> bool:
        """Is root directory"""
        return True

    @property
    def parent(self) -> "XFERXPath":
        """The logical parent"""
        return self

    def get_child(self, name: str) -> "LAP6Path":
        """
        Get a child entry by name
        """
        name = lap6_canonical_filename(name, wildcard=False)
        for entry in self.iterdir():
            if entry.name == name:
                return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), name)

    def iterdir(
        self,
        pattern: t.Optional[str] = None,
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator[LAP6Path]:
        """
        Iterate over the entries in the index
        """
        pattern = lap6_canonical_filename(pattern, wildcard=wildcard) if pattern else None
        words = self.read_words()
        for i in range(1, len(words) // DIR_ENTRY_SIZE):
            entry = LAP6Path.read(self.fs, words, i * DIR_ENTRY_SIZE)
            if include_all or not entry.is_empty:
                if pattern is None or filename_match(entry.name, pattern, wildcard=wildcard):
                    yield entry

    def read_words(self) -> t.List[int]:
        """
        Read the index blocks as a list of 12-bit words
        """
        index_block_number = self.fs.index_block_number
        words = self.fs.read_words_block(index_block_number) + self.fs.read_words_block(index_block_number + 1)
        if words[:DIR_ENTRY_SIZE] != UNUSED_ENTRY:
            raise OSError(errno.EIO, "Invalid LAP6 Index")
        return words

    def write_words(self, words: t.List[int]) -> None:
        """
        Write the index blocks as a list of 12-bit words
        """
        index_block_number = self.fs.index_block_number
        words_per_block = self.fs.dev.block_size_words
        for offset in range(0, len(words), words_per_block):
            self.fs.write_words_block(
                index_block_number + offset // words_per_block,
                words[offset : offset + words_per_block],
            )


class LAP6Filesystem(AbstractFilesystem):
    """
    LAP6 Tape

    The Standard LAP6 Tape layout is the following:

    Standard
    Block
    (may vary)

            +-------------------+
        0   |                   | May be any length
            / Lower File area   /
    0o267   |                   |
            +-------------------+
    0o270   |                   | 8 blocks
            / Unused            /
            |                   |
            +-------------------+
    0o300   |                   | 50 blocks
            / LAP6              /
            |                   |
            +-------------------+
    0o350   |                   | May be any length
            / Working Area      /
            |                   |
            +-------------------+
    0o426   | Index directory   | May be anywhere above the beginning of the working area
    0o427   |                   |
            +-------------------+
    0o430   |                   | May be any length
            / Upper File area   /
    0o777   |                   |
            +-------------------+

    LAP6 HANDBOOK, Pag 33, 41
    https://bitsavers.org/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf

    Note on the SIMH tape format:
    A plain image is 512 blocks of 256 words each (262144 bytes).
    Extended images have 6 extra bytes at the end of the file, which are used to store
    the block size, first forward block number, and first reverse block number.
    """

    fs_name = "lap6"
    fs_description = "LINC LAP6 Tape"
    fs_platforms = ["linc"]
    fs_forks = [MANUSCRIPT_FORK, BINARY_FORK]
    fs_entry_metadata = []

    dev: BlockDevice12Bit
    index_block_number: int = -1

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"], device_type: t.Union[bool, str] = ""):
        if isinstance(file_or_device, AbstractFile):
            self.dev = BlockDevice12Bit(file_or_device)
        elif isinstance(file_or_device, BlockDevice12Bit):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, f"Invalid device type for {self.fs_description} filesystem")

    @classmethod
    def mount(
        cls,
        file_or_dev: t.Union["AbstractFile", "AbstractDevice"],
        strict: t.Union[bool, str] = True,
        device_type: t.Union[bool, str] = "",
        **kwargs: t.Union[bool, str],
    ) -> "LAP6Filesystem":
        """
        Mount the LAP6 filesystem from a file
        """
        self = cls(file_or_dev, device_type)
        dev_size = self.dev.get_size()
        if dev_size == MAX_BLOCKS * BLOCK_SIZE:
            number_of_blocks = MAX_BLOCKS
        elif dev_size % BLOCK_SIZE == 6:
            data = self.dev.read_block(dev_size // BLOCK_SIZE)
            metadata_words = [x for x in struct.unpack_from("<hhh", data, 0)]
            block_size = metadata_words[0]
            forward_offset = -metadata_words[1]
            reverse_offset = -metadata_words[2]
            if block_size != BLOCK_SIZE // 2:
                raise OSError(errno.EIO, f"Invalid block size: {block_size} (expected {BLOCK_SIZE // 2})")
            if forward_offset < 0 or reverse_offset < 0:
                raise OSError(errno.EIO, f"Invalid offset: {forward_offset}/{reverse_offset} (expected positive)")
            if forward_offset != reverse_offset:
                raise OSError(errno.EIO, f"Invalid offset: {forward_offset}/{reverse_offset} (expected equal)")
            self.dev.offset = forward_offset * BLOCK_SIZE
            number_of_blocks = (dev_size - 6) / BLOCK_SIZE - forward_offset - forward_offset
            if number_of_blocks > MAX_BLOCKS:
                number_of_blocks = MAX_BLOCKS
        words = self.dev.read_words_block(STANDARD_INDEX_BLOCK)
        if words[0:8] == UNUSED_ENTRY:
            self.index_block_number = STANDARD_INDEX_BLOCK
        else:
            self.index_block_number = -1
            for i in range(6, number_of_blocks, 8):
                words = self.dev.read_words_block(i)
                if words[0:8] == UNUSED_ENTRY:
                    self.index_block_number = i
                    break
            if self.index_block_number == -1:
                raise OSError(errno.EIO, "LAP6 Index not found")
        return self

    def get_file_areas(self) -> t.List[t.Tuple[int, int]]:
        """
        Get the file areas (start, end) in block numbers
        """
        if self.index_block_number == STANDARD_INDEX_BLOCK:
            # Standard LAP6 layout
            return [
                (STANDARD_LOWER_FILE_AREA, STANDARD_LOWER_FILE_AREA_END),
                (STANDARD_UPPER_FILE_AREA, STANDARD_UPPER_FILE_AREA_END),
            ]
        else:
            # Non-standard LAP6 layout, the upper file area starts after the index blocks
            return [
                (self.index_block_number + INDEX_BLOCKS, STANDARD_UPPER_FILE_AREA_END),
            ]

    def allocate(
        self,
        number_of_blocks: int,
        index_words: t.List[int],
        ignored_name: t.Optional[str] = None,
        ignored_fork: t.Optional[str] = None,
    ) -> int:
        """
        Allocate a contiguous range of blocks for a new file, avoiding used blocks and the ignored entry.
        Return the first block number of the allocated range.
        """
        # Read the index and collect all used blocks, except for the ignored entry
        used: t.List[t.Tuple[int, int]] = []
        for position in range(DIR_ENTRY_SIZE, len(index_words), DIR_ENTRY_SIZE):
            entry = LAP6Path.read(self, index_words, position)
            for fork in (MANUSCRIPT_FORK, BINARY_FORK):
                if entry.name == ignored_name and fork == ignored_fork:
                    continue
                first_block = entry.manuscript_block_number if fork == MANUSCRIPT_FORK else entry.binary_block_number
                length = entry.get_length(fork)
                if first_block != UNUSED and length > 0:
                    used.append((first_block, first_block + length - 1))
        # Collect all gaps in the used blocks and find the best candidate for allocation
        candidates: t.List[t.Tuple[int, bool, int, int]] = []
        for area_start, area_end in self.get_file_areas():
            is_upper: bool = area_start >= self.index_block_number
            cursor = area_start
            for used_start, used_end in sorted(used):
                used_start = max(used_start, area_start)
                used_end = min(used_end, area_end)
                if used_end < cursor or used_start > area_end:
                    continue
                if used_start > cursor:
                    gap_end = used_start - 1
                    if gap_end - cursor + 1 >= number_of_blocks:
                        if is_upper:
                            distance = cursor - (self.index_block_number + INDEX_BLOCKS - 1)
                        else:
                            distance = self.index_block_number - gap_end
                        candidates.append((distance, is_upper, cursor, gap_end))
                cursor = max(cursor, used_end + 1)
                if cursor > area_end:
                    break
            if cursor <= area_end and area_end - cursor + 1 >= number_of_blocks:
                if is_upper:
                    distance = cursor - (self.index_block_number + INDEX_BLOCKS - 1)
                else:
                    distance = self.index_block_number - area_end
                candidates.append((distance, is_upper, cursor, area_end))
        # Select the best candidate based on distance
        if not candidates:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        _, is_upper, gap_start, gap_end = min(candidates)
        if is_upper:
            return gap_start
        else:
            return gap_end - number_of_blocks + 1

    def create_file(
        self,
        fullname: str,
        size: int,
        metadata: t.Optional[t.Dict[str, t.Any]] = None,
    ) -> LAP6Path:
        """
        Create or replace one fork of a LAP6 file
        """
        try:
            name = lap6_canonical_filename(fullname, wildcard=False)
        except Exception:
            raise OSError(errno.EINVAL, "Invalid LAP6 filename", fullname)
        if not name:
            raise OSError(errno.EINVAL, "Invalid LAP6 filename", fullname)

        metadata = metadata or {}
        fork = str(metadata.get("fork", MANUSCRIPT_FORK)).upper()
        if fork not in (MANUSCRIPT_FORK, BINARY_FORK):
            raise OSError(errno.EINVAL, f"Invalid LAP6 fork: {fork}", fullname)
        requested_blocks = metadata.get("number_of_blocks", 0)
        if not isinstance(requested_blocks, int) or requested_blocks < 0:
            raise OSError(errno.EINVAL, "Invalid LAP6 allocation size", fullname)
        number_of_blocks = max(1, requested_blocks, (size + BLOCK_SIZE - 1) // BLOCK_SIZE)

        # Find the entry in the index or create a new one
        index = self.get_root()
        words = index.read_words()
        entry: t.Optional[LAP6Path] = None
        entry_position: t.Optional[int] = None
        empty_position: t.Optional[int] = None
        for position in range(DIR_ENTRY_SIZE, len(words), DIR_ENTRY_SIZE):
            candidate = LAP6Path.read(self, words, position)
            if candidate.name == name:
                entry = candidate
                entry_position = position
                break
            if candidate.is_empty and empty_position is None:
                empty_position = position

        # If the entry does not exist, create a new one in the first empty position
        if entry is None:
            if empty_position is None:
                raise OSError(errno.ENOSPC, "LAP6 directory is full", fullname)
            # Create a new entry
            entry = LAP6Path(self)
            entry.filename = name
            entry.manuscript_block_number = UNUSED
            entry.manuscript_length = 0
            entry.binary_block_number = UNUSED
            entry.binary_length = 0
            entry_position = empty_position

        # Allocate blocks for the specified fork and update the entry
        old_block = entry.manuscript_block_number if fork == MANUSCRIPT_FORK else entry.binary_block_number
        ignored_name = name if old_block != UNUSED else None
        first_block = self.allocate(number_of_blocks, words, ignored_name, fork)
        if fork == MANUSCRIPT_FORK:
            entry.manuscript_block_number = first_block
            entry.manuscript_length = number_of_blocks
        else:
            entry.binary_block_number = first_block
            entry.binary_length = number_of_blocks

        assert entry_position is not None
        words[entry_position : entry_position + DIR_ENTRY_SIZE] = entry.to_words()
        index.write_words(words)

        initial_words = [0] * self.dev.block_size_words
        if fork == MANUSCRIPT_FORK:
            initial_words[:3] = [0o2065, 0o5712, 0o7777]
        for block_offset in range(number_of_blocks):
            self.write_words_block(first_block + block_offset, initial_words)
        return entry

    def delete_file(self, fullname: str) -> bool:
        """
        Remove a directory entry
        """
        return self.get_file_entry(fullname).delete()

    def write_bytes(
        self,
        fullname: str,
        content: t.Union[bytes, bytearray],
        fork: t.Optional[str] = None,
        metadata: t.Optional[t.Dict[str, t.Any]] = None,
        file_mode: t.Optional[str] = None,
    ) -> None:
        """
        Create a LAP6 fork and write its encoded contents
        """
        metadata = dict(metadata or {})
        if fork is None:
            fork = metadata.get("fork")
        if fork is None:
            fork = BINARY_FORK if file_mode == IMAGE else MANUSCRIPT_FORK
        fork = fork.upper()
        if fork not in (MANUSCRIPT_FORK, BINARY_FORK):
            raise OSError(errno.EINVAL, f"Invalid LAP6 fork: {fork}", fullname)

        words = encode_lap6_file(content, fork)
        words_per_block = self.dev.block_size_words
        number_of_blocks = max(1, (len(words) + words_per_block - 1) // words_per_block)
        metadata["fork"] = fork
        requested_blocks = metadata.get("number_of_blocks", 0)
        if isinstance(requested_blocks, int):
            metadata["number_of_blocks"] = max(number_of_blocks, requested_blocks)
        else:
            metadata["number_of_blocks"] = requested_blocks
        entry = self.create_file(fullname, number_of_blocks * BLOCK_SIZE, metadata)
        first_block = entry.get_first_block_number(fork)
        words.extend([0] * (number_of_blocks * words_per_block - len(words)))
        for block_offset in range(number_of_blocks):
            start = block_offset * words_per_block
            self.write_words_block(first_block + block_offset, words[start : start + words_per_block])

    @classmethod
    def initialize(
        cls, file_or_dev: t.Union["AbstractFile", "AbstractDevice"], **kwargs: t.Union[bool, str]
    ) -> "LAP6Filesystem":
        """
        Initialize a new LAP6 filesystem
        """
        self = cls(file_or_dev, kwargs.get("device_type", ""))
        self.index_block_number = STANDARD_INDEX_BLOCK
        empty_block = UNUSED_ENTRY * (self.dev.block_size_words // DIR_ENTRY_SIZE)
        for block_number in range(INDEX_BLOCKS):
            self.write_words_block(self.index_block_number + block_number, empty_block)
        return self

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as 256 12bit words
        """
        return self.dev.read_words_block(block_number)

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write 256 12bit words as a block
        """
        self.dev.write_words_block(block_number, words)

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator[LAP6Path]:
        """
        Filter directory entries based on a pattern
        """
        yield from self.get_root().iterdir(
            pattern,
            include_all=include_all,
            expand=expand,
            wildcard=wildcard,
        )

    @property
    def entries_list(self) -> t.Iterator[LAP6Path]:
        """
        Property to get an iterator of directory entries
        """
        yield from self.filter_entries_list("*")

    def get_file_entry(self, fullname: str) -> t.Union[LAP6Path, LAP6Index]:
        """
        Get the directory entry for a file
        """
        if not fullname:
            return self.get_root()
        else:
            return self.get_root().get_child(fullname)

    def get_root(self) -> LAP6Index:
        """
        Get the root directory
        """
        return LAP6Index(self)

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        """
        Index display

          NAME      BN  #BLKS

        GEORGE    M 430   12
                  B 262    2
        12345678  B 442    3
        DP-MAR20  M 445   27
                  B 474    6
        DP2 APR2  M 264    4
        DISPLAY   B 502    3
        MNEMONIC  M 505   11

        The first column is the name of the file, up to 8 characters long.
        The second column is the type, M for manuscript, B for binary.
        The third column is the first block number of the file (in octal).
        The fourth column is the length of the file in blocks (in octal).
        A manuscript and a binary program with the same name (e.g. GEORGE)
        always appear together.
        """
        sys.stdout.write("\n  NAME       BN  #BLKS\n\n")
        for entry in self.get_root().iterdir(pattern=pattern):
            if entry.manuscript_block_number != UNUSED and entry.binary_block_number != UNUSED:
                sys.stdout.write(
                    f"{entry.name:<8}  M {entry.manuscript_block_number:>4o} {entry.manuscript_length:>4o}\n"
                )
                sys.stdout.write(f"{'':<8}  B {entry.binary_block_number:>4o} {entry.binary_length:>4o}\n")
            elif entry.manuscript_block_number != UNUSED:
                sys.stdout.write(
                    f"{entry.name:<8}  M {entry.manuscript_block_number:>4o} {entry.manuscript_length:>4o}\n"
                )
            elif entry.binary_block_number != UNUSED:
                sys.stdout.write(f"{entry.name:<8}  B {entry.binary_block_number:>4o} {entry.binary_length:>4o}\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        if arg:
            for entry in self.get_root().iterdir(pattern=arg):
                sys.stdout.write(f"{entry.examine()}\n")
        else:
            sys.stdout.write(
                f"Tape offset:     {self.dev.offset // BLOCK_SIZE}\n"
                f"Index blocks:    {self.index_block_number:>3}-{self.index_block_number + 1:<3} "
                f"(0o{self.index_block_number:o}-0o{self.index_block_number + 1:o})\n\n"
                "File Areas\n"
                "----------\n"
            )
            for area_start, area_end in self.get_file_areas():
                label = "Upper" if area_start >= self.index_block_number else "Lower"
                sys.stdout.write(f"{label:<7} {area_start:>3}-{area_end:<3} (0o{area_start:>03o}-0o{area_end:>03o})\n")
            sys.stdout.write(
                "\n"
                "Filename  Manuscript   Binary\n"
                "--------  ----------   ------\n"
            )
            for entry in self.get_root().iterdir():
                sys.stdout.write(f"{entry}\n")

    def dump(
        self,
        fullname: t.Optional[str],
        start: t.Optional[int] = None,
        end: t.Optional[int] = None,
        fork: t.Optional[str] = None,
    ) -> None:
        """Dump the content of a file or a range of blocks"""
        if fullname:
            entry = self.get_file_entry(fullname)
            if not isinstance(entry, LAP6Path):
                return
            if start is None:
                start = 0
            if end is None or end > entry.get_length(fork) - 1:
                end = entry.get_length(fork) - 1
            first_block_number = entry.get_first_block_number(fork)
            for block_number in range(start, end + 1):
                dev_block_numbeer = first_block_number + block_number
                words = self.read_words_block(dev_block_numbeer)
                sys.stdout.write(f"\nBLOCK NUMBER   {block_number:08}  ({dev_block_numbeer:08})\n")
                oct_dump(words)
        else:
            if start is None:
                start = 0
                if end is None:  # full disk
                    end = self.get_size() // BLOCK_SIZE - 1
            elif end is None:  # one single block
                end = start
            for block_number in range(start, end + 1):
                words = self.read_words_block(block_number)
                sys.stdout.write(f"\nBLOCK NUMBER   {block_number:08}\n")
                oct_dump(words)
