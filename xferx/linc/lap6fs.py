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
BLOCK_SIZE_BYTES = 384  # Block size (in bytes)

MANUSCRIPT_FORK = "M"  # Text files
BINARY_FORK = "B"  # Binary files


# LAP6 Keyboard Code: 6-bit code -> character
#
# LAP6 HANDBOOK, Pag 34
# https://ftpmirror.your.org/pub/misc/bitsavers/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf

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
        result = bytearray()
        for i in range(0, len(words), 2):
            chr1 = words[i]
            try:
                chr2 = words[i + 1]
            except IndexError:
                chr2 = 0
            chr3 = ((chr2 >> 8) & 0o17) | ((chr1 >> 4) & 0o360)
            result.append(chr1 & 0xFF)
            result.append(chr2 & 0xFF)
            result.append(chr3 & 0xFF)
        return bytes(result)
    else:
        return b"".join([lap6_word_to_ascii(x) for x in words])


def from_bytes_to_12bit_words(byte_data: t.Union[bytes, bytearray], file_mode: str = "ASCII") -> t.List[int]:
    """
    Convert bytes to 12-bit words.
    """
    words = []
    if file_mode == IMAGE:
        for i in range(0, len(byte_data), 3):
            chr1 = byte_data[i] & 0xFF
            try:
                chr2 = byte_data[i + 1] & 0xFF
            except IndexError:
                chr2 = 0
            try:
                chr3 = byte_data[i + 2] & 0xFF
            except IndexError:
                chr3 = 0
            words.append(chr1 | ((chr3 & 0o360) << 4))
            words.append(chr2 | ((chr3 & 0o17) << 8))
    else:
        for i in range(0, len(byte_data), 2):
            chr1 = byte_data[i] & 0xFF
            try:
                chr2 = byte_data[i + 1] & 0xFF
            except IndexError:
                chr2 = 0
            words.append(ascii_to_lap6_word(bytes([chr1, chr2])))
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
    file_mode: str
    fork: str

    def __init__(self, entry: "LAP6Path", file_mode: t.Optional[str] = None, fork: t.Optional[str] = None):
        self.entry = entry
        self.fork = fork.upper() if fork else MANUSCRIPT_FORK
        if file_mode is not None:
            self.file_mode = file_mode
        else:
            self.file_mode = IMAGE if self.fork == BINARY_FORK else ASCII
        self.size = entry.get_length(self.fork) * BLOCK_SIZE_BYTES

    @property
    def name(self) -> str:
        """Final path component"""
        return self.entry.name

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.entry.get_length(self.fork)
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.get_length(self.fork)
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        data = bytearray()
        if self.fork == BINARY_FORK:
            first_block_number = self.entry.binary_block_number
        else:
            first_block_number = self.entry.manuscript_block_number
        for i in range(number_of_blocks):
            block_position = block_number + first_block_number + i
            words = self.entry.fs.read_words_block(block_position)
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
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.get_length(self.fork)
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        if self.fork == BINARY_FORK:
            first_block_number = self.entry.binary_block_number
        else:
            first_block_number = self.entry.manuscript_block_number
        for i in range(number_of_blocks):
            block_position = block_number + first_block_number + i
            data = buffer[i * BLOCK_SIZE_BYTES : (i + 1) * BLOCK_SIZE_BYTES]
            words = from_bytes_to_12bit_words(data, self.file_mode)
            self.entry.fs.write_words_block(block_position, words)

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

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """
        Get the length in blocks
        """
        if fork and fork.upper() == BINARY_FORK:
            return self.binary_length
        else:
            return self.manuscript_length

    def get_size(self, fork: t.Optional[str] = None) -> int:
        """
        Get file size in bytes
        """
        return self.get_length(fork) * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return BLOCK_SIZE_BYTES

    def open(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> LAP6File:
        """
        Open a file
        """
        return LAP6File(self, file_mode, fork)

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
        words = self.fs.read_words_block(self.fs.index_block_number) + self.fs.read_words_block(
            self.fs.index_block_number + 1
        )
        if words[0:DIR_ENTRY_SIZE] != UNUSED_ENTRY:
            raise OSError(errno.EIO, "Invalid LAP6 Index")
        for i in range(1, len(words) // DIR_ENTRY_SIZE):
            entry = LAP6Path.read(self.fs, words, i * DIR_ENTRY_SIZE)
            if include_all or not entry.is_empty:
                if pattern is None or filename_match(entry.name, pattern, wildcard=wildcard):
                    yield entry


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
            |                   |
            +-------------------+
    0o300   |                   | 50 blocks
            / LAP6 / Unused     /
            |                   |
            +-------------------+
    0o350   |                   | May be any length
            / Working Area      /
            |                   |
            +-------------------+
    0o426   | Index directory   | May be anywhere above the beginning of the working area
            |                   |
            +-------------------+
    0o430   |                   | May be any length
            / Upper File area   /
    0o777   |                   |
            +-------------------+

    LAP6 HANDBOOK, Pag 33, 41
    https://bitsavers.org/pdf/washingtonUniversity/linc/LINC_Reference_Manuals/LINC_Vol_16_Section_3_LAP6_Handbook_May67.pdf
    """

    fs_name = "lap6"
    fs_description = "LINC LAP6 Tape"
    fs_platforms = ["linc"]
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
        number_of_blocks = self.dev.get_size() // BLOCK_SIZE
        # Find the index block number
        self.index_block_number = -1
        for i in range(6, number_of_blocks, 8):
            words = self.dev.read_words_block(i)
            if words[0:8] == UNUSED_ENTRY:
                self.index_block_number = i
                break
        if self.index_block_number == -1:
            raise OSError(errno.EIO, "LAP6 Index not found")
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
                    f"{entry.name:<8}  M {entry.manuscript_block_number:>4} {entry.manuscript_length:>4}\n"
                )
                sys.stdout.write(f"{'':<8}  B {entry.binary_block_number:>4} {entry.binary_length:>4}\n")
            elif entry.manuscript_block_number != UNUSED:
                sys.stdout.write(
                    f"{entry.name:<8}  M {entry.manuscript_block_number:>4} {entry.manuscript_length:>4}\n"
                )
            elif entry.binary_block_number != UNUSED:
                sys.stdout.write(f"{entry.name:<8}  B {entry.binary_block_number:>4} {entry.binary_length:>4}\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        if arg:
            for entry in self.get_root().iterdir(pattern=arg):
                sys.stdout.write(f"{entry.examine()}\n")
        else:
            sys.stdout.write(f"Index block number: {self.index_block_number}\n\n")
            sys.stdout.write("Filename  Manuscript   Binary\n")
            sys.stdout.write("--------  ----------   ------\n")
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
            if end is None or end > entry.get_length() - 1:
                end = entry.get_length() - 1
            if fork == BINARY_FORK:
                first_block_number = entry.binary_block_number
            else:
                first_block_number = entry.manuscript_block_number
            for block_number in range(start, end + 1):
                words = self.read_words_block(first_block_number + block_number)
                sys.stdout.write(f"\nBLOCK NUMBER   {block_number:08}\n")
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
