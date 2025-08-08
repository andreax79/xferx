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
from dataclasses import dataclass
from datetime import date

from ..abstract import AbstractDirectoryEntry, AbstractFile, AbstractFilesystem
from ..commons import (
    ASCII,
    IMAGE,
    READ_FILE_FULL,
    BlockDirection,
    Direction,
    filename_match,
    pairwise,
)
from ..device.abstract import AbstractDevice
from ..device.block_18bit import (
    BlockDevice18Bit,
    from_18bit_words_to_bytes,
    from_bytes_to_18bit_words,
)

__all__ = [
    "ADSSFilesystem",
    "ADSSFile",
    "ADSSDirectoryEntry",
    "ascii_to_five_seven",
    "five_seven_to_ascii",
    "decode_block_format",
    "encode_block_format",
]

# PDP-9 ADVANCED SOFTWARE SYSTEM MONITORS, Pag 95
# https://bitsavers.org/pdf/dec/pdp9/DEC-9A-MAD0-D.pdf

# PDP-15 Advanced Monitor Software System for PDP-1S/20/30/40
# PROGRAMMER'S REFERENCE MANUAL  Pag 80
# https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf

WORDS_PER_BLOCK = 256  # Number of words per block
DIRECTORY_BLOCK = 0o100  # Directory block number on a DECtape
DIRECTORY_WORDS = 0o400  # Non-system tape
DIRECTORY_SYSTEM_WORD = 0o203  # If this word is set to 0o777777, the tape is a system tape
SYSTEM_TAPE_DIRECTORY_WORDS = 0o200  # System tape
BITMAP_WORDS = 0o40  # Bitmap length in words
DIRECTORY_ENTRY_WORDS = 4  # Directory entry length in words
DIRECTORY_ENTRIES = (WORDS_PER_BLOCK - BITMAP_WORDS) // DIRECTORY_ENTRY_WORDS  # Number of directory entries per block
SYSTEM_TAPE_DIRECTORY_ENTRIES = 24  # Number of directory entries on a system tape
FILE_BITMAP_BLOCK = 0o71  # File bitmap block number
FILE_BITMAP_BLOCKS = 7  # Number of blocks for file bitmaps
BITMAPS_PER_BLOCK = WORDS_PER_BLOCK // BITMAP_WORDS  # Number of bitmaps per block
DECTAPE_BLOCKS = 384  # Number of blocks on a DECtape
COMMAND_TABLE_ENTRY_WORDS = 7  # Command table entry length in words
SYSBLK_SYS = "SYSBLK;SYS"

# Data Modes
# Pag 28, pag 134
# https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf
# Mode 0 - IOPS Binary
# Mode 1 - Image Binary
# Mode 2 - IOPS ASCII
# Mode 3 - Image Alphanumeric
# Mode 4 - Dump
# Mode 5 - 9-Channe1 Dump

BLOCK_ID_IOPS_BINARY = 0  # IOPS Binary
BLOCK_ID_IOPS_ASCII = 2  # IOPS ASCII
BLOCK_ID_EOF = 5  # End of File

assert DIRECTORY_ENTRIES == 56


@dataclass
class BlockContent:
    block: BlockDirection
    words: t.List[int]


def sixbit_to_ascii(word: int) -> str:
    """
    Convert a 18-bit word to an ASCII string
    """
    tmp = [(word >> x) & 0o77 for x in (12, 6, 0)]
    return ("".join(chr(ch if ch >= 32 else 64 + ch) for ch in tmp)).replace("@", "")


def ascii_to_sixbit(val: str) -> int:
    """
    Convert an ASCII string to a 18-bit word
    """
    if len(val) > 3:
        raise ValueError("String must be 3 characters or less")
    val = val.ljust(3, "@")  # Pad
    word = 0
    pow = (12, 6, 0)
    for i, ch in enumerate(val):
        word += ((ord(ch) - 32 if ord(ch) >= 96 else ord(ch)) & 0o77) << pow[i]
    return word


def get_file_mode(fullname: str) -> str:
    """
    Get the file mode based on the filename extension.
    If the extension is not recognized, return IMAGE.
    """
    _, extension = adss_split_ext(fullname)
    if extension == "SRC" or extension[0:1].isnumeric():
        return ASCII
    else:
        return IMAGE


def five_seven_to_ascii(words: t.List[int]) -> bytes:
    """
    Convert a list of 18-bit words using 5/7 ASCII encoding to a string.
    5/7 ASCII refers to the following encoding scheme:
    Five 7-bit ASCII characters are packed in two contiguous locations.

            0                 6   7               13   14           17
           +--------------------+--------------------+-----------------+
    Word 1 |   1st character    |   2nd character    | 3rd chr bit 1-4 |
           +--------------------+--------------------+-----------------+

            0              2   3                8   10           16  17
           +-----------------+--------------------+-----------------+--+
    Word 2 | 3rd chr bit 5-7 |   4 th character   | 5 th character  |  |
           +-----------------+--------------------+-----------------+--+

    Pag 30
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf
    """
    result = bytearray()
    for word1, word2 in pairwise(words):
        chars = [
            ((word1 >> 11) & 0o177),  # First character
            ((word1 >> 4) & 0o177),  # Second character
            (((word1 & 0o017) << 3) | ((word2 >> 15) & 0o07)),  # Third character
            ((word2 >> 8) & 0o177),  # Fourth character
            ((word2 >> 1) & 0o177),  # Fifth character
        ]
        result.extend(chars)
    return bytes(result)


def ascii_to_five_seven(data: bytes) -> t.List[int]:
    """
    Convert a string to a list of 18-bit words using 5/7 ASCII encoding.
    """
    words = []
    for i in range(0, len(data), 5):
        chars = data[i : i + 5]
        if len(chars) < 5:
            chars += b"\0" * (5 - len(chars))  # Pad with null bytes
        assert len(chars) == 5
        words.append((chars[0] << 11) | (chars[1] << 4) | (chars[2] >> 3))
        words.append(((chars[2] & 0o07) << 15) | (chars[3] << 8) | (chars[4] << 1))
    return words


def decode_block_format(words: t.List[int]) -> bytes:
    """
    Every block recorded includes a two-word Block Control Pair followed by the data.
    The Block Control Pair specifies:
    - the block type (ASCII, binary, EOF, etc.),
    - the length of the block in words (including the Block Control Pair)
    - the checksum of the block

    Pag 86
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf
    """
    result = bytearray()
    position = 0
    while position <= len(words) - 2:
        # Read the Block Control Pair
        block_id = (words[position]) & 0o7  # Block ID
        block_word_counter = words[position] >> 8  # Block Word Count (12 bit)
        # print(f"Block ID: {block_id}, Word Count: {block_word_counter} at position {position}")
        if block_id & BLOCK_ID_EOF or block_word_counter == 0:  # End of File or end of block
            break  # End of the block
        # print(f"Block ID: {block_id}, Word Count: {block_word_counter} at position {position}")
        checksum = words[position + 1]  # Checksum word
        tmp = 0o1000000 - (words[position] + sum(words[position + 2 : position + block_word_counter])) & 0o777777
        if tmp != checksum:
            print(f"Checksum error: expected {tmp}, got {checksum} at position {position}")
        if block_id == BLOCK_ID_IOPS_ASCII:
            # IOPS ASCII format
            data = five_seven_to_ascii(words[position + 2 : position + block_word_counter])
            # Convert carriage return to newline, strip null bytes
            result += data.replace(b"\r", b"\n").rstrip(b"\0")
        elif block_id == BLOCK_ID_IOPS_BINARY:
            # IOPS Binary format
            result += from_18bit_words_to_bytes(words[position + 2 : position + block_word_counter], IMAGE)
        else:
            print(f"Unknown block ID: {block_id} at position {position}")
        position += block_word_counter
    return bytes(result)


def split_data(data: bytes, max_length: int) -> t.List[bytes]:
    """
    Split a byte string into chunks of a maximum length
    """
    return [data[i : i + max_length] for i in range(0, len(data), max_length)]


def encode_block_control_pair(block_id: int, words: t.List[int]) -> t.Tuple[int, int]:
    """
    Create a block control pair for the given block ID and words.
    Returns a tuple of (block_word_counter, checksum).
    """
    block_word_counter = len(words) + 2  # +2 for the block control pair
    word1 = (block_word_counter << 8) | block_id
    checksum = 0o1000000 - (word1 + sum(words)) & 0o777777
    return word1, checksum


def encode_block_format(data: bytes, file_mode: str, words_per_block: int) -> t.Iterator[t.List[int]]:
    """
    Encode data into blocks of 18-bit words according to the specified file mode.
    """
    if file_mode == ASCII:
        words: t.List[int] = []
        split = data.split(b"\n")  # Split lines
        if not split[-1]:
            split = split[:-1]
        for line in split:  # Split lines
            line += b"\r"  # Add carriage return to each line
            for part in split_data(line, 256 - 6):  # TODO check with long lines
                block_id = BLOCK_ID_IOPS_ASCII
                part_words = ascii_to_five_seven(part)
                block_word_counter = len(part_words) + 2
                block_control_pair = encode_block_control_pair(block_id, part_words)
                # Check if the block is full
                if len(words) + block_word_counter + 2 > words_per_block:
                    words += [0, 0]  # End of the block
                    if len(words) < words_per_block:
                        words += [0] * (words_per_block - len(words))  # Pad to the block size
                    yield words
                    words = []
                words += block_control_pair
                words += part_words
        # End of the block
        words += encode_block_control_pair(BLOCK_ID_EOF, [])
        if len(words) < words_per_block:
            words += [0] * (words_per_block - len(words))  # Pad to the block size
        assert len(words) == words_per_block, "Block size mismatch"
        yield words
    else:
        words = []
        for part in split_data(data, 26 * 3):
            block_id = BLOCK_ID_IOPS_BINARY
            part_words = from_bytes_to_18bit_words(part, file_type=IMAGE)
            block_word_counter = len(part_words) + 2
            block_control_pair = encode_block_control_pair(block_id, part_words)
            # Check if the block is full
            if len(words) + block_word_counter + 2 > words_per_block:
                words += [0, 0]  # End of the block
                if len(words) < words_per_block:
                    words += [0] * (words_per_block - len(words))  # Pad to the block size
                yield words
                words = []
            words += block_control_pair
            words += part_words
        # End of the block
        words += encode_block_control_pair(BLOCK_ID_EOF, [])
        if len(words) < words_per_block:
            words += [0] * (words_per_block - len(words))  # Pad to the block size
        assert len(words) == words_per_block, "Block size mismatch"
        yield words


def adss_split_ext(fullname: str) -> t.Tuple[str, str]:
    """
    Split a fullname into the filename and extension.

    Filename and extension are separated by a ";"
    Example: "FILENAM;EXT"
    """
    fullname = fullname.upper()
    try:
        filename, extension = fullname.replace(" ", ";").split(";", 1)
        return filename.strip(), extension.strip()
    except Exception:
        return fullname, ""


def adss_canonical_filename(fullname: str, wildcard: bool = False) -> str:
    """
    Generate the canonical ADSS/DOS-15 filename

    A filename is a string of up to six alphanumeric characters.
    The extension can be up to three characters long.
    Any printing character in the ASCII set can be used
    with the exception of a space, ":", ";", ",", "(" and ")".
    Filename and extension are separated by a ";"
    """
    filename, extension = adss_split_ext(fullname)
    filename = sixbit_to_ascii(ascii_to_sixbit(filename[0:3])) + sixbit_to_ascii(ascii_to_sixbit(filename[3:6]))
    extension = sixbit_to_ascii(ascii_to_sixbit(extension))
    return f"{filename};{extension}"


def oct_dump(words: t.List[int], words_per_line: int = 8) -> None:
    """
    Display contents in octal and sixbit ASCII
    """
    for i in range(0, len(words), words_per_line):
        line = words[i : i + words_per_line]
        ascii = five_seven_to_ascii(line).decode("ascii", errors="ignore")
        printable = "".join(x if x.isprintable() else " " for x in ascii)
        oct_str = " ".join([f"{x:06o}" for x in line])
        sys.stdout.write(f"{i:08o}   {oct_str.ljust(5 * words_per_line)}  {printable}\n")


class ADSSFile(AbstractFile):
    entry: "ADSSDirectoryEntry"
    file_mode: str  # ASCII of IMAGE
    closed: bool

    def __init__(self, entry: "ADSSDirectoryEntry", file_mode: t.Optional[str] = None):
        self.entry = entry
        self.file_mode = file_mode or get_file_mode(entry.basename)
        self.closed = False

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.entry.get_length()
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.get_length()
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        data = bytearray()
        for i, block in enumerate(self.entry.get_block_contents()):
            if i >= block_number:
                data.extend(from_18bit_words_to_bytes(block.words, self.file_mode))
                number_of_blocks -= 1
                if number_of_blocks == 0:
                    break
        return bytes(data)

    def read_words_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> t.List[int]:
        """
        Read block(s) of words from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.entry.get_length()
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.get_length()
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        words: t.List[int] = []
        for i, block in enumerate(self.entry.get_block_contents()):
            if i >= block_number:
                words.extend(block.words)
                number_of_blocks -= 1
                if number_of_blocks == 0:
                    break
        return words

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the file
        """
        words = from_bytes_to_18bit_words(buffer, self.file_mode)
        self.write_words_block(words, block_number, number_of_blocks)

    def write_words_block(
        self,
        words: t.List[int],
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
            or block_number + number_of_blocks > self.entry.get_length()
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        words = list(words)
        for i, block in enumerate(self.entry.get_block_contents()):
            if i >= block_number:
                block.words[: WORDS_PER_BLOCK - 1] = words[: WORDS_PER_BLOCK - 1]  # Update the block words
                self.entry.fs.write_words_block(block.block, block.words)
                words = words[WORDS_PER_BLOCK - 1 :]  # Remove the written words
                number_of_blocks -= 1
                if number_of_blocks == 0:
                    break

    def get_length(self) -> int:
        """
        Get the length in blocks
        """
        return self.entry.get_length()

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.get_length() * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return (WORDS_PER_BLOCK - 1) * 3

    def close(self) -> None:
        """
        Close the file
        """
        self.closed = True

    def __str__(self) -> str:
        return self.entry.fullname


class ADSSDirectoryEntry(AbstractDirectoryEntry):
    """
    Directory Entry

    Word

        +-----------------------------------+
      0 | File name                         |
      1 |                                   |
        +-----------------------------------+
      2 | Extension                         |
        +-----------------------------------+
      3 | Active bit | Block number         |
        +-----------------------------------+

    """

    directory: "ADSSDirectory"
    file_number: int = 0  # File number in the directory
    filename: str  # Filename
    extension: str = ""  # File extension
    raw_data_link: int = 0  # Raw data link (active bit, block number)

    def __init__(self, directory: "ADSSDirectory"):
        self.directory = directory

    @classmethod
    def new(cls, directory: "ADSSDirectory", file_number: int) -> "ADSSDirectoryEntry":
        """
        Create a new empty Directory Entry
        """
        self = cls(directory)
        self.file_number = file_number
        self.filename = ""
        self.extension = ""
        self.raw_data_link = 0
        return self

    @classmethod
    def read(
        cls, directory: "ADSSDirectory", words: t.List[int], file_number: int, position: int
    ) -> "ADSSDirectoryEntry":
        self = cls(directory)
        self.file_number = file_number
        self.filename = sixbit_to_ascii(words[position]) + sixbit_to_ascii(words[position + 1])
        self.extension = sixbit_to_ascii(words[position + 2])
        self.raw_data_link = words[position + 3]
        return self

    def to_words(self) -> t.List[int]:
        """
        Dump the directory entry to words
        """
        return [
            ascii_to_sixbit(self.filename[0:3]),
            ascii_to_sixbit(self.filename[3:6]),
            ascii_to_sixbit(self.extension),
            self.raw_data_link,
        ]

    @property
    def block_number(self) -> int:
        """
        Get the first block number of the file
        """
        return self.raw_data_link & ~0o400000

    @block_number.setter
    def block_number(self, value: int) -> None:
        """
        Set the first block number of the file
        """
        if not (0 <= value <= 0o777777):
            raise ValueError("Block number must be between 0 and 0777777")
        self.raw_data_link = (self.raw_data_link & 0o400000) | value

    @property
    def is_empty(self) -> bool:
        """
        Is the file active?
        """
        return self.raw_data_link == 0o777777 or self.raw_data_link & (1 << 17) == 0

    @is_empty.setter
    def is_empty(self, value: bool) -> None:
        """
        Set the file as empty or active
        """
        if value:
            self.raw_data_link = self.raw_data_link & ~0o400000  # Clear the active bit
        else:
            self.raw_data_link = self.raw_data_link | 0o400000  # Set the active bit

    @property
    def is_sys(self) -> bool:
        """
        Is the file a system file?
        """
        return self.directory.fs.is_system_tape and self.file_number >= SYSTEM_TAPE_DIRECTORY_ENTRIES

    @property
    def fullname(self) -> str:
        return self.basename

    @property
    def basename(self) -> str:
        return f"{self.filename};{self.extension}"

    def get_file_bitmap(self) -> "ADSSBitmap":
        """
        The File Bitmap specifies the blocks occupied by the file
        """
        return ADSSBitmap.read(self.directory.fs, self.file_number)

    def get_block_contents(self) -> t.Iterator[BlockContent]:
        """
        Get the blocks used by the file

        Normal files are stored as linked blocks.
        The last word of each data block contains the number of next block in the file.
        System programs are stored in contiguous blocks.
        """
        if self.is_sys:
            # System programs
            command_entry = self.get_command_entry()
            if command_entry:
                yield from command_entry.get_block_contents()
            else:
                block = BlockDirection(self.block_number, Direction.FORWARD)
                words = self.directory.fs.read_words_block(block)
                yield from [BlockContent(block, words)]
        else:
            direction = Direction.FORWARD
            if not self.is_empty and not self.is_sys:
                block = BlockDirection(self.block_number, direction)
                while block.block_number not in (0, 0o777777):  # 0o777777 is the end of the file
                    words = self.directory.fs.read_words_block(block)
                    yield BlockContent(block, words)
                    next_block_number = words[-1]  # Last word is the next block number
                    if direction == Direction.FORWARD and (next_block_number < block.block_number):
                        direction = Direction.BACKWARD
                    elif direction == Direction.BACKWARD and (next_block_number > block.block_number):
                        direction = Direction.FORWARD
                    block = BlockDirection(next_block_number, direction)

    def get_blocks(self) -> t.Iterator[BlockDirection]:
        """
        Get the blocks used by the file
        """
        if self.is_empty:
            pass
        elif self.is_sys:
            command_entry = self.get_command_entry()
            if command_entry:
                yield from command_entry.get_blocks()
            else:
                yield BlockDirection(self.block_number, Direction.FORWARD)
        else:
            for block_content in self.get_block_contents():
                yield block_content.block

    def get_length(self) -> int:
        """
        Get the length in blocks
        """
        if self.is_empty:
            return 0
        elif self.is_sys:
            command_entry = self.get_command_entry()
            return command_entry.length if command_entry else 1
        else:
            return self.get_file_bitmap().used()

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.get_length() * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        if self.is_sys:
            return (WORDS_PER_BLOCK) * 3  # System programs are stored in contiguous blocks
        else:
            return (WORDS_PER_BLOCK - 1) * 3  # Stored as linked blocks

    def get_command_entry(self) -> t.Optional["CommandTableEntry"]:
        """
        Get the command entry associated with this directory entry
        """
        if self.is_empty or not self.is_sys:
            return None
        try:
            return self.directory.command_table.get_command_entry(self.fullname)
        except Exception:
            return None

    def delete(self) -> bool:
        """
        Delete the directory entry
        """
        # Update the directory bitmap
        bitmap = ADSSBitmap.read(self.fs)
        for block in self.get_blocks():
            bitmap.set_free(block.block_number)
        bitmap.write()
        # Update the file bitmap
        file_bitmap = ADSSBitmap.new(self.fs, self.file_number)
        file_bitmap.write()
        # Update the directory entry
        self.block_number = 0
        self.is_empty = True
        self.write()
        return True

    def write(self) -> bool:
        """
        Write the directory entry
        """
        self.directory.write()
        return True

    def allocate(self, number_of_blocks: int) -> t.List[BlockDirection]:
        """
        Allocate blocks for the file and update the directory entry
        """
        # Allocate blocks in the directory bitmap
        if number_of_blocks == 0:
            number_of_blocks = 1  # Allocate at least one block
        bitmap = ADSSBitmap.read(self.fs)
        blocks = bitmap.allocate(number_of_blocks)
        bitmap.write()
        # Update the file bitmap
        file_bitmap = ADSSBitmap.new(self.fs, self.file_number)
        for block in blocks:
            file_bitmap.set_used(block.block_number)
        file_bitmap.write()
        for i, block in enumerate(blocks):
            words = [0] * WORDS_PER_BLOCK
            next_block_number = blocks[i + 1].block_number if i + 1 < len(blocks) else 0o777777
            words[-1] = next_block_number  # Last word is the next block number
            self.fs.write_words_block(block, words)
        # Update the directory entry
        self.block_number = blocks[0].block_number
        self.is_empty = False
        self.write()
        return blocks

    def open(self, file_type: t.Optional[str] = None) -> ADSSFile:
        """
        Open a file
        """
        return ADSSFile(self, file_type)

    def read_bytes(self, file_mode: t.Optional[str] = None) -> bytes:
        """Get the content of the file"""
        file_mode = file_mode or get_file_mode(self.basename)
        result = bytearray()
        for block in self.get_block_contents():
            if self.is_sys:
                result.extend(from_18bit_words_to_bytes(block.words, IMAGE))
            else:
                result.extend(decode_block_format(block.words))
        return bytes(result)

    @property
    def fs(self) -> "ADSSFilesystem":
        return self.directory.fs

    def __str__(self) -> str:
        return f"{self.file_number:>2}  {self.filename:<6} {self.extension:<3}  {self.raw_data_link:06o} {'N' if self.is_empty else 'Y'}  {self.block_number:4}"


class ADSSDirectory:
    """
    Directory

    Word

        +-----------------------------------+
      0 | Directory Bitmap                  |  32 Words
        /                                   /
     31 |                                   |
        +-----------------------------------+
     32 | Directory Entry 1                 |   4 Words
     35 |                                   |
        +-----------------------------------+
        |                                   |
        /                                   /
        |                                   |
        +-----------------------------------+
    252 | Directory Entry 55                |   4 Words
    255 |                                   |
        +-----------------------------------+

    Pag 81
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf
    """

    fs: "ADSSFilesystem"
    entries: t.List["ADSSDirectoryEntry"]
    command_table: "CommandTable"  # Command table for system tapes

    def __init__(self, fs: "ADSSFilesystem"):
        self.fs = fs

    @classmethod
    def new(cls, fs: "ADSSFilesystem") -> "ADSSDirectory":
        """
        Create a new empty Directory
        """
        self = cls(fs)
        self.command_table = CommandTable.new(fs)
        self.entries = [ADSSDirectoryEntry.new(self, i) for i in range(DIRECTORY_ENTRIES)]
        return self

    @classmethod
    def read(cls, fs: "ADSSFilesystem") -> "ADSSDirectory":
        """
        Read Directory entries
        """
        self = cls(fs)
        # Read the directory entries
        self.entries = []
        words = self.fs.read_words_block(DIRECTORY_BLOCK)
        for i, position in enumerate(range(BITMAP_WORDS, len(words), DIRECTORY_ENTRY_WORDS)):
            entry = ADSSDirectoryEntry.read(self, words, i, position)
            self.entries.append(entry)
        # On a system tape, read the command table
        if self.fs.is_system_tape:
            try:
                sysblk = self.get_file_entry(SYSBLK_SYS)
                self.command_table = CommandTable.read(self.fs, sysblk.block_number)
            except FileNotFoundError:
                self.command_table = CommandTable.new(fs)
        return self

    def write(self) -> None:
        """
        Write the Directory to the disk
        """
        words = self.fs.read_words_block(DIRECTORY_BLOCK)[:BITMAP_WORDS]
        for entry in self.entries:
            words += entry.to_words()
        assert len(words) == 256
        self.fs.write_words_block(DIRECTORY_BLOCK, words)

    def get_file_entry(self, fullname: str) -> "ADSSDirectoryEntry":
        """
        Get a file entry by its fullname
        """
        fullname = adss_canonical_filename(fullname, wildcard=False)
        for entry in self.entries:
            if entry.fullname == fullname and not entry.is_empty:
                return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)

    def get_free_entry(self) -> t.Optional[ADSSDirectoryEntry]:
        """
        Get the first free entry in the directory
        """
        for entry in self.entries:
            if entry.is_empty:
                return entry
        return None


class CommandTableEntry:
    """
    Command table entry

    Word

        +-----------------------------------+
      0 | File name                         |
      1 |                                   |
        +-----------------------------------+
      2 | Block number                      |
        +-----------------------------------+
      3 | Size                              |
        +-----------------------------------+
      4 | Load address                      |
        +-----------------------------------+
      5 | Program size                      |
        +-----------------------------------+
      6 | Start address                     |
        +-----------------------------------+

    """

    command_table: "CommandTable"
    file_number: int  # File number in the directory
    is_empty: bool
    filename: str  # Filename
    block_number: int  # First file block number
    length: int  # Length in blocks
    load_address: int
    program_size: int
    start_address: int

    def __init__(self, command_table: "CommandTable"):
        self.command_table = command_table

    @classmethod
    def read(
        cls, command_table: "CommandTable", words: t.List[int], file_number: int, position: int
    ) -> "CommandTableEntry":
        self = cls(command_table)
        self.file_number = file_number
        self.is_empty = not bool(words[position])
        self.filename = sixbit_to_ascii(words[position]) + sixbit_to_ascii(words[position + 1])
        self.block_number = words[position + 2]
        self.length = words[position + 3]
        self.load_address = words[position + 4]
        self.program_size = words[position + 5]
        self.start_address = words[position + 6]
        return self

    @property
    def fullname(self) -> str:
        return self.basename

    @property
    def basename(self) -> str:
        return f"{self.filename};SYS"

    def get_block_contents(self) -> t.Iterator[BlockContent]:
        """
        Get the blocks used by the system program
        System programs are stored in contiguous blocks.
        """
        for block in self.get_blocks():
            words = self.fs.read_words_block(block)
            yield BlockContent(block, words)

    def get_blocks(self) -> t.Iterator[BlockDirection]:
        """
        Get the blocks used by the file

        The last word of each data block contains the number of next block in the file.
        """
        yield from [
            BlockDirection(x, Direction.FORWARD) for x in range(self.block_number, self.block_number + self.length)
        ]

    def get_length(self) -> int:
        """
        Get the length in blocks
        """
        return self.length

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.get_length() * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes
        """
        return (WORDS_PER_BLOCK) * 3

    def delete(self) -> bool:
        """
        Delete the command entry
        """
        return False

    def write(self) -> bool:
        """
        Write the command entry
        """
        return False

    @property
    def fs(self) -> "ADSSFilesystem":
        return self.command_table.fs

    def __str__(self) -> str:
        return (
            f"{self.file_number:>2}  {self.filename:<6}  {self.block_number:<3}  {self.length:>5}  "
            f"{'N' if self.is_empty else 'Y'} {self.load_address:06o}  {self.program_size:06o}  {self.start_address:06o}"
        )


class CommandTable:
    """
    Command Table

    The Command Table is used to store additional information about system programs.

    Word

        +-----------------------------------+
      0 | Command table size                |   1 Word
        +-----------------------------------+
      2 | Command Entry 1                   |   7 Words
      6 |                                   |
        +-----------------------------------+
        |                                   |
        /                                   /
        |                                   |
        +-----------------------------------+

    """

    fs: "ADSSFilesystem"
    entries: t.List["CommandTableEntry"]

    def __init__(self, fs: "ADSSFilesystem"):
        self.fs = fs

    @classmethod
    def new(cls, fs: "ADSSFilesystem") -> "CommandTable":
        """
        Create a new empty Command Table
        """
        self = cls(fs)
        self.entries = []
        return self

    @classmethod
    def read(cls, fs: "ADSSFilesystem", block_number: t.Optional[int] = None) -> "CommandTable":
        """
        Read Command Table entries
        """
        self = cls(fs)
        self.entries = []
        if block_number is None:
            # Get the command table block number from SYSBLK;SYS
            sysblk = self.fs.get_file_entry(SYSBLK_SYS)
            block_number = sysblk.block_number
        words = self.fs.read_words_block(block_number)
        command_table_size = words[0]
        for i, position in enumerate(range(1, command_table_size, COMMAND_TABLE_ENTRY_WORDS)):
            entry = CommandTableEntry.read(self, words, i, position)
            self.entries.append(entry)
        return self

    def get_command_entry(self, fullname: str) -> "CommandTableEntry":
        """
        Get the command by name
        """
        fullname = adss_canonical_filename(fullname, wildcard=False)
        for entry in self.entries:
            if entry.fullname == fullname and not entry.is_empty:
                return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)


class ADSSBitmap:
    """
    Directory/File Bitmap

    The Directory Bitmap defines block availability.
    It occupies the first 32 words of the Directory Block (block 64).
    One bit is allocated for each DECtape block.
    When set to 1, the bit indicates that the DECtape block is occupied.

    For each file in the directory, there is an additional bitmap,
    the File Bitmap, that defines the blocks occupied by that file.
    The File Bitmap occupies blocks 57 through 63.
    Each block is divided into eight File Bitmap Blocks.

    Pag 80
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-MR2B-D_AdvMonPgmRef.pdf
    """

    fs: "ADSSFilesystem"
    bitmaps: t.List[int]
    bitmap_block: int
    bitmap_position: int

    def __init__(self, fs: "ADSSFilesystem", file_number: t.Optional[int] = None):
        self.fs = fs
        if file_number is None:
            self.bitmap_block = DIRECTORY_BLOCK
            self.bitmap_position = 0
        else:
            # File bitmaps are stored in blocks 57-63
            self.bitmap_block = FILE_BITMAP_BLOCK + (file_number // BITMAPS_PER_BLOCK)
            self.bitmap_position = (file_number % BITMAPS_PER_BLOCK) * BITMAP_WORDS

    @classmethod
    def new(cls, fs: "ADSSFilesystem", file_number: t.Optional[int] = None) -> "ADSSBitmap":
        """
        Create a new empty bitmap
        """
        self = cls(fs, file_number)
        self.bitmaps = [0] * BITMAP_WORDS
        return self

    @classmethod
    def read(cls, fs: "ADSSFilesystem", file_number: t.Optional[int] = None) -> "ADSSBitmap":
        """
        Read the bitmap blocks
        """
        self = cls(fs, file_number)
        words = self.fs.read_words_block(self.bitmap_block)
        self.bitmaps = words[self.bitmap_position : self.bitmap_position + BITMAP_WORDS]
        return self

    def write(self) -> None:
        """
        Write the bitmap blocks
        """
        words = self.fs.read_words_block(self.bitmap_block)
        words[self.bitmap_position : self.bitmap_position + BITMAP_WORDS] = self.bitmaps  # Update the bitmap
        self.fs.write_words_block(self.bitmap_block, words)

    @property
    def total_bits(self) -> int:
        """
        Return the bitmap length in bit
        """
        return len(self.bitmaps) * 18

    def is_free(self, bit_index: int) -> bool:
        """
        Check if a block is free
        """
        int_index = bit_index // 18
        bit_position = bit_index % 18
        bit_value = self.bitmaps[int_index]
        return (bit_value & (1 << (17 - bit_position))) == 0

    def set_used(self, bit_index: int) -> None:
        """
        Mark a block as used
        """
        int_index = bit_index // 18
        bit_position = bit_index % 18
        self.bitmaps[int_index] |= 1 << (17 - bit_position)

    def set_free(self, bit_index: int) -> None:
        """
        Mark a block as free
        """
        int_index = bit_index // 18
        bit_position = bit_index % 18
        self.bitmaps[int_index] &= ~(1 << (17 - bit_position))

    def find_contiguous_blocks(self, size: int) -> int:
        """
        Find contiguous blocks, return the first block number
        """
        current_run = 0
        start_index = -1
        for i in range(self.total_bits - 1, -1, -1):
            if self.is_free(i):
                if current_run == 0:
                    start_index = i
                current_run += 1
                if current_run == size:
                    return start_index - size + 1
            else:
                current_run = 0
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    def allocate_one(self, from_block: int, direction: Direction) -> BlockDirection:
        """
        Allocate one block
        """
        if direction == Direction.FORWARD:
            r = range(max(from_block, 1), self.total_bits)
        else:  # Direction.BACKWARD
            r = range(min(from_block, self.total_bits - 1), 1, -1)
        for block in r:
            if self.is_free(block):
                self.set_used(block)
                return BlockDirection(block, direction)
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    def allocate(self, size: int) -> t.List[BlockDirection]:
        """
        Allocate blocks in a staggered manner.

        The first block is always recorded in the forward direction.
        Free blocks are chosen which are at least 5 beyond the last one.
        """
        blocks: t.List[BlockDirection] = []
        direction = Direction.FORWARD
        found = False
        while len(blocks) < size:
            try:
                if blocks:
                    pos = blocks[-1].block_number + (5 if direction == Direction.FORWARD else -5)
                else:
                    pos = 1
                block = self.allocate_one(pos, direction)
                blocks.append(block)
                found = True
            except OSError:
                if not found:  # If no block was found
                    raise
                direction = direction.reverse()
                found = False
        assert len(blocks) == size
        return blocks

    def used(self) -> int:
        """
        Count the number of used blocks
        """
        used = 0
        for block in self.bitmaps:
            used += block.bit_count()
        return used

    def get_allocated_blocks(self) -> t.List[int]:
        """
        Get the list of allocated blocks
        """
        allocated_blocks = []
        for i in range(self.total_bits):
            if not self.is_free(i):
                allocated_blocks.append(i)
        return allocated_blocks

    def free(self) -> int:
        """
        Count the number of free blocks
        """
        return self.total_bits - self.used()

    def __str__(self) -> str:
        free = self.free()
        used = self.used()
        return f"Free blocks: {free:<6} Used blocks: {used:<6}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ADSSBitmap) and self.bitmaps == other.bitmaps  # type: ignore


class ADSSFilesystem(AbstractFilesystem):
    """
    Advanced Monitor Software System (ADSS) filesystem for PDP-9/PDP-15
    This filesystem is also used by DOS-15 on DECtapes.

    Block 64 is the Directory Block, which contains the Directory Bitmap and Directory Entries.
    The first 32 words of the Directory Block are used for the Directory Bitmap.
    Each Directory Entry occupies 4 words.
    The Directory contains 56 entries.
    If the tape is a system tape, the first 32 entries are used for user files,
    and the last 24 entries are reserved for system programs.
    User files are stored as linked blocks, while system files are stored in contiguous blocks.
    Each file as an additional File Bitmap, which occupies blocks 57-63.
    The File Bitmap defines the blocks occupied by the file.
    For the system programs, there is a Command Table that contains additional information, such as the size.
    """

    fs_name = "adss"
    fs_description = "PDP-15 Advanced Monitor Software System"
    fs_platforms = ["pdp-9", "pdp-15"]
    is_system_tape: bool = False  # System tape
    dev: BlockDevice18Bit

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"]):
        if isinstance(file_or_device, AbstractFile):
            self.dev = BlockDevice18Bit(file_or_device, words_per_block=WORDS_PER_BLOCK)
        elif isinstance(file_or_device, BlockDevice18Bit):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, f"Invalid device type for {self.fs_description} filesystem")

    @classmethod
    def mount(
        cls,
        file_or_dev: t.Union["AbstractFile", "AbstractDevice"],
        strict: t.Union[bool, str] = True,
        **kwargs: t.Union[bool, str],
    ) -> "ADSSFilesystem":
        """
        Mount the filesystem from a file or device
        """
        self = cls(file_or_dev)
        words = self.dev.read_words_block(DIRECTORY_BLOCK)
        # Check if the tape is a system tape
        self.is_system_tape = words[DIRECTORY_SYSTEM_WORD] == 0o777777
        if strict:
            # Check the tape size
            blocks = self.get_size() // 3 // 512
            if abs(blocks - DECTAPE_BLOCKS) >= 4:
                raise OSError(errno.EINVAL, "Invalid ADSS tape size")
            # Check the bitmap
            bitmap = ADSSBitmap.read(self)
            # Mark the File Bitmap Blocks as used
            for block_number in [DIRECTORY_BLOCK, FILE_BITMAP_BLOCK]:
                if bitmap.is_free(block_number):
                    raise OSError(errno.EINVAL, "Invalid ADSS filesystem")
        return self

    def read_words_block(
        self,
        block: t.Union[int, BlockDirection],
    ) -> t.List[int]:
        """
        Read a 256 bytes block as 18bit words

        It is possible to read data from a DECtape in backward direction.
        However, a re-ordering of both the entire block and individual words is required.

        Pag 75
        https://bitsavers.org/pdf/dec/pdp15/DEC-15-H2DC-D_usersVol2.pdf
        """
        return self.dev.read_words_block(block)

    def write_words_block(
        self,
        block: t.Union[int, BlockDirection],
        words: t.List[int],
    ) -> None:
        """
        Write 256 18bit words as a block
        """
        self.dev.write_words_block(block, words)

    def read_dir_entries(self) -> t.Iterator["ADSSDirectoryEntry"]:
        """
        Read directory entries
        """
        yield from ADSSDirectory.read(self).entries

    @property
    def entries_list(self) -> t.Iterator["ADSSDirectoryEntry"]:
        for entry in self.read_dir_entries():
            if not entry.is_empty:
                yield entry

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
    ) -> t.Iterator["ADSSDirectoryEntry"]:
        pattern = adss_canonical_filename(pattern, wildcard=True) if pattern else ""
        for entry in self.read_dir_entries():
            if not entry.is_empty and filename_match(entry.basename, pattern, wildcard):
                yield entry

    def get_file_entry(self, fullname: str) -> "ADSSDirectoryEntry":
        """
        Get the directory entry for a file
        """
        for entry in self.filter_entries_list(fullname, wildcard=False):
            return entry
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)

    def create_file(
        self,
        fullname: str,
        number_of_blocks: int,  # length in blocks
        creation_date: t.Optional[date] = None,  # optional creation date
        file_type: t.Optional[str] = None,
    ) -> "ADSSDirectoryEntry":
        """
        Create a new file with a given length in number of blocks
        """
        fullname = adss_canonical_filename(fullname)
        # If the file already exists, delete it
        try:
            entry = self.get_file_entry(fullname)
            entry.delete()
        except FileNotFoundError:
            # Seach for a free entry in the directory
            directory = ADSSDirectory.read(self)
            entry = directory.get_free_entry()  # type: ignore
            if entry is None:
                raise OSError(errno.ENOSPC, "Directory full")
            filename, extension = adss_split_ext(fullname)
            entry.filename = filename
            entry.extension = extension
        # Allocate space and write the entry
        entry.allocate(number_of_blocks)
        return entry

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
        fullname = adss_canonical_filename(fullname)
        file_mode = file_mode or get_file_mode(fullname)
        blocks_content = list(encode_block_format(bytes(content), file_mode, words_per_block=WORDS_PER_BLOCK - 1))
        number_of_blocks = len(blocks_content)
        # Create the file entry
        entry = self.create_file(fullname, number_of_blocks, creation_date, file_type)
        # Write the file content
        for block, block_content in zip(entry.get_block_contents(), blocks_content):
            assert len(block_content) == WORDS_PER_BLOCK - 1
            block.words[: WORDS_PER_BLOCK - 1] = block_content
            self.write_words_block(block.block, block.words)

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        entries = self.filter_entries_list(pattern, wildcard=True)
        if not entries:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), pattern)
        if not options.get("brief"):
            sys.stdout.write("DIRECTORY LISTING\n")
        for x in entries:
            if not x.is_empty:
                if options.get("brief"):
                    sys.stdout.write(f"{x.filename:<6};{x.extension:<3}\n")
                else:
                    sys.stdout.write(f"{x.filename:<6} {x.extension:<3}  {x.block_number:>4o}\n")
        if not options.get("brief"):
            bitmap = ADSSBitmap.read(self)
            sys.stdout.write(f"{bitmap.free():<4o} FREE BLOCKS\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        if options.get("bitmap"):
            # Display the bitmap
            file_number = int(arg) if arg and arg.isdigit() else None
            bitmap = ADSSBitmap.read(self, file_number)
            for i in range(0, bitmap.total_bits):
                sys.stdout.write(f"{i:>4d} {'[ ]' if bitmap.is_free(i) else '[X]'}  ")
                if i % 16 == 15:
                    sys.stdout.write("\n")
            sys.stdout.write(f"\nUsed blocks: {bitmap.used()}\n")
        elif arg:
            # Display the file entry
            entries = self.filter_entries_list(arg, wildcard=True)
            for entry in entries:
                sys.stdout.write(f"File number:              {entry.file_number}\n")
                sys.stdout.write(f"Filename:                 {entry.filename}\n")
                sys.stdout.write(f"Extension:                {entry.extension}\n")
                sys.stdout.write(f"Raw data link:            {entry.raw_data_link:06o}\n")
                sys.stdout.write(f"Empty:                    {'Y' if entry.is_empty else 'N'}\n")
                sys.stdout.write(f"System file:              {'Y' if entry.is_sys else 'N'}\n")
                sys.stdout.write(f"First block number:       {entry.block_number}\n")
                sys.stdout.write(f"Size:                     {entry.get_length()}\n")
                command_entry = entry.get_command_entry()
                if command_entry:
                    sys.stdout.write(f"Command entry number:     {command_entry.file_number}\n")
                    sys.stdout.write(f"Command block number:     {command_entry.block_number}\n")
                    sys.stdout.write(f"Load address:             {command_entry.load_address:06o}\n")
                    sys.stdout.write(f"Program size:             {command_entry.program_size:06o}\n")
                    sys.stdout.write(f"Start address:            {command_entry.start_address:06o}\n")
                bitmap = ADSSBitmap.read(self, entry.file_number)
                blocks = str(list(entry.get_blocks()))
                sys.stdout.write(f"Blocks:                   {blocks}\n")
                sys.stdout.write("\n")
                if entry.basename == SYSBLK_SYS:
                    # Display the command table
                    sys.stdout.write("Command Table:\n\n")
                    sys.stdout.write("Num  Filename  Block  Length  Load Addr  Prog Size  Start Addr\n")
                    sys.stdout.write("---  --------  -----  ------  ---------  ---------  ----------\n")
                    for command_entry in entry.directory.command_table.entries:
                        sys.stdout.write(
                            f"{command_entry.file_number:>2}   {command_entry.filename:<6}   "
                            f"{command_entry.block_number:>6}  {command_entry.length:>6}     "
                            f"{command_entry.load_address:06o}     {command_entry.program_size:06o}      "
                            f"{command_entry.start_address:06o}\n"
                        )
                        # f"{'N' if command_entry.is_empty else 'Y'} "
        else:
            entries = self.read_dir_entries()
            directory = ADSSDirectory.read(self)
            bitmap = ADSSBitmap.read(self)
            user_files = len([x for x in directory.entries if not x.is_empty and not x.is_sys])
            user_blocks = sum([x.get_length() for x in directory.entries if not x.is_empty and not x.is_sys])
            system_blocks = bitmap.used() - user_blocks
            sys.stdout.write(f"Free blocks:           {bitmap.free():>4}\n")
            sys.stdout.write(f"User files:            {user_files:>4}\n")
            sys.stdout.write(f"System blocks:         {system_blocks:>4}\n")
            sys.stdout.write(f"Is system tape:           {'Y' if self.is_system_tape else 'N'}\n")
            sys.stdout.write("\n")
            # Display the directory entries
            sys.stdout.write("Num   Filename  Data link Block  Size  Type\n")
            sys.stdout.write("---   --------  --------- -----  ----  ----\n")
            full = bool(options.get("full", False))
            for entry in directory.entries:
                if full or not entry.is_empty:
                    if entry.is_empty:
                        ftype = '  -'
                    elif entry.is_sys:
                        ftype = 'System'
                    elif get_file_mode(entry.basename) == IMAGE:
                        ftype = 'Binary'
                    else:
                        ftype = 'ASCII'
                    block_number = f"{entry.block_number:4d}" if not entry.is_empty else "-"
                    length = f"{entry.get_length():4d}" if not entry.is_empty else "-"
                    sys.stdout.write(
                        f"{entry.file_number:>2}  {entry.filename:>6};{entry.extension:<3}  "
                        f"{entry.raw_data_link:06o} {block_number:>8}  {length:>4}  {ftype}\n"
                    )

    def dump(self, fullname: t.Optional[str], start: t.Optional[int] = None, end: t.Optional[int] = None) -> None:
        """
        Dump the content of a file or a range of blocks
        """
        if fullname:
            entry = self.get_file_entry(fullname)
            for i, block_content in enumerate(entry.get_block_contents()):
                if (start is None or start <= i) and (end is None or i <= end):
                    sys.stdout.write(f"\nBLOCK NUMBER   {str(block_content.block):>8} ({i:08})\n")
                    oct_dump(block_content.words)
        else:
            if start is None:
                start = 0
                if end is None:  # full disk
                    end = (self.get_size() // WORDS_PER_BLOCK // 4) - 1
            elif end is None:  # one single block
                end = start
            for block_number in range(start, end + 1):
                words = self.read_words_block(block_number)
                sys.stdout.write(f"\nBLOCK NUMBER   {block_number:>8}\n")
                oct_dump(words)

    @classmethod
    def initialize(
        cls, file_or_dev: t.Union["AbstractFile", "AbstractDevice"], **kwargs: t.Union[bool, str]
    ) -> "ADSSFilesystem":
        """
        Create an empty filesystem
        """
        self = cls(file_or_dev)
        self.is_system_tape = False
        bitmap = ADSSBitmap.new(self)
        # Mark the File Bitmap Blocks as used
        for block_number in range(FILE_BITMAP_BLOCK, FILE_BITMAP_BLOCK + BITMAPS_PER_BLOCK):
            bitmap.set_used(block_number)
        # Mark the Directory Block as used
        bitmap.set_used(DIRECTORY_BLOCK)
        bitmap.write()
        # Create an empty directory
        ADSSDirectory.new(self).write()
        return self

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.dev.get_size()
