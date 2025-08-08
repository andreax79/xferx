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
from datetime import date

from ..abstract import AbstractDirectoryEntry, AbstractFile, AbstractFilesystem
from ..commons import ASCII, IMAGE, READ_FILE_FULL, filename_match
from ..device.abstract import AbstractDevice
from ..device.block_18bit import BlockDevice18Bit, from_18bit_words_to_bytes
from .adssfs import (
    DECTAPE_BLOCKS,
    WORDS_PER_BLOCK,
    ADSSFilesystem,
    adss_canonical_filename,
    ascii_to_sixbit,
    decode_block_format,
    oct_dump,
    sixbit_to_ascii,
)

__all__ = [
    "DOS15DirectoryEntry",
    "DOS15File",
    "DOS15Filesystem",
]

# Pag 87
# https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODFFA-B-D_DOS-15_System_Manual_197408.pdf

RF_MFD_BLOCK = 0o1777  # MFD block number on RF disk
RP_MFD_BLOCK = 0o47040  # MFD block number on RP disk


def dos15_to_date(val: int) -> t.Optional[date]:
    """
    Translate DOS-15 date to Python date

    Month (bits 0-5), Day (bits 6-11), Year (bits 12-17 module 1970)
    """
    if val == 0:
        return None
    month = val >> 12
    day = (val >> 6) & 0o37
    year = (val & 0o37) + 1970
    try:
        return date(year, month, day)
    except ValueError:
        return None


def dos15_split_fullname(uic: str, fullname: t.Optional[str], wildcard: bool = True) -> t.Tuple[str, t.Optional[str]]:
    """
    Split a fullname into UIC and filename

    UIC and filename are separated by a ":"
    Example: "TMP:FILENAM;EXT"
    """
    if fullname:
        if ":" in fullname:
            try:
                uic, fullname = fullname.split(":", 1)
            except Exception:
                return uic.upper(), fullname
        if fullname:
            fullname = adss_canonical_filename(fullname, wildcard=wildcard)
    return uic.upper(), fullname


class DOS15File(AbstractFile):
    entry: "DOS15DirectoryEntry"
    file_mode: str  # ASCII of IMAGE
    closed: bool

    def __init__(self, entry: "DOS15DirectoryEntry", file_mode: t.Optional[str] = None):
        self.entry = entry
        self.file_mode = file_mode or IMAGE
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
        for i, next_block_number in enumerate(self.entry.get_blocks()):
            if i >= block_number:
                words = self.entry.fs.read_words_block(next_block_number)
                t = from_18bit_words_to_bytes(words, self.file_mode)
                data.extend(t)
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
        for i, next_block_number in enumerate(self.entry.get_blocks()):
            if i >= block_number:
                data = self.entry.fs.read_words_block(next_block_number)
                words.extend(data)
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
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

    def write_words_block(
        self,
        words: t.List[int],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the file
        """
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

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
        return (WORDS_PER_BLOCK - 2) * 3  # Exclude the last two words (previous/next block number)

    def close(self) -> None:
        """
        Close the file
        """
        self.closed = True

    def __str__(self) -> str:
        return self.entry.fullname


class DOS15DirectoryEntry(AbstractDirectoryEntry):
    """
    Directory Entry

    Word

        +-----------------------------------+
      0 | File name                         |
      1 |                                   |
        +-----------------------------------+
      2 | Extension                         |
        +-----------------------------------+
      3 | Truncated bit | First block       |
        +-----------------------------------+
      4 | Number of blocks                  |
        +-----------------------------------+
      5 | First Retrieval Information Block |
        +-----------------------------------+
      6 | Prot. | RIB first word            |
        +-----------------------------------+
      7 | Creation date                     |
        +-----------------------------------+

    Pag 87
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODFFA-B-D_DOS-15_System_Manual_197408.pdf
    """

    directory: "UserFileDirectoryBlock"
    file_number: int = 0  # File number in the directory
    filename: str  # Filename
    extension: str = ""  # File extension
    block_number: int = 0  # First file block number
    raw_data_link: int = 0  # Raw data link (truncated bit, block number)
    length: int  # Number of blocks in the file
    protection_code: int = 0  # Protection code
    retrieval_information_block: int  # RIB first block number
    rib_position: int = 0  # Position in RIB block
    raw_creation_date: int

    def __init__(self, directory: "UserFileDirectoryBlock"):
        self.directory = directory

    @classmethod
    def read(
        cls, directory: "UserFileDirectoryBlock", words: t.List[int], file_number: int, position: int
    ) -> "DOS15DirectoryEntry":
        self = cls(directory)
        self.file_number = file_number
        self.filename = sixbit_to_ascii(words[position]) + sixbit_to_ascii(words[position + 1])
        self.extension = sixbit_to_ascii(words[position + 2])
        self.raw_data_link = words[position + 3]
        self.block_number = self.raw_data_link & 0o377777  # First block number
        self.length = words[position + 4]  # Number of blocks in the file
        self.retrieval_information_block = words[position + 5]
        self.protection_code = words[position + 6] >> 16  # Protection code
        self.rib_position = words[position + 6] & ~0o600000  # RIB first word position
        self.raw_creation_date = words[position + 7]
        return self

    @property
    def is_active(self) -> bool:
        """
        Is the file active?
        """
        return self.block_number != 0 and self.raw_data_link & (1 << 17) == 0

    @property
    def fullname(self) -> str:
        return self.basename

    @property
    def basename(self) -> str:
        return f"{self.filename};{self.extension}"

    def get_blocks(self) -> t.List[int]:
        """
        Get the blocks used by the file
        """
        next_block_number = self.retrieval_information_block
        length = self.length  # Length in blocks
        position = self.rib_position
        blocks = []
        while next_block_number != 0o777777 and length > 0:
            print(next_block_number)
            rib = RetrievalInformationBlock.read(self, next_block_number)
            blocks = rib.data_blocks[position : position + length]
            length -= len(blocks)
            next_block_number = rib.next_block_number
            position = 0
        return blocks

    # def get_file_bitmap(self) -> "ADSSBitmap":
    #     """
    #     The File Bitmap specifies the blocks occupied by the file
    #     """
    #     return ADSSBitmap.read(self.directory.fs, self.file_number)

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
        return (WORDS_PER_BLOCK - 1) * 3

    @property
    def creation_date(self) -> t.Optional[date]:
        return dos15_to_date(self.raw_creation_date)

    def delete(self) -> bool:
        """
        Delete the directory entry
        """
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

    def write(self) -> bool:
        """
        Write the directory entry
        """
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

    def open(self, file_type: t.Optional[str] = None) -> DOS15File:
        """
        Open a file
        """
        return DOS15File(self, file_type)

    def read_bytes(self, file_mode: t.Optional[str] = None) -> bytes:
        """Get the content of the file"""
        if file_mode is None:
            file_mode = IMAGE
        # Always read the file as IMAGE
        with self.open(IMAGE) as f:
            length = self.get_length()  # Number of blocks in the file
            result = bytearray()
            if file_mode == ASCII:
                for i in range(length):
                    # Read the block, exclude the last two words (previous/next block number)
                    words = f.read_words_block(i)[:-2]
                    result += decode_block_format(words)
            else:
                for i in range(length):
                    # Read the block, exclude the last two words (previous/next block number)
                    words = f.read_words_block(i)[:-2]
                    result += from_18bit_words_to_bytes(words, IMAGE)
            return bytes(result)

    @property
    def fs(self) -> "DOS15Filesystem":
        return self.directory.fs

    def __str__(self) -> str:
        return f"{self.file_number:>2}  {self.filename:<6} {self.extension:<3}  {'Y' if self.is_active else 'N'}  {self.block_number:4}  {self.length:4}"


class RetrievalInformationBlock:
    """
    Retrieval Information Block (RIB)

    Word

        +-----------------------------------+
      0 | Number of blocks                  |
        +-----------------------------------+
      1 | Data block 1                      |
        //                                  /
      n | Data block n                      |
        +-----------------------------------+
    254 | Previous RIB block number         |
        +-----------------------------------+
    255 | Next RIB block number             |
        +-----------------------------------+

    Pag 83
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODFFA-A_DOS15_SysMan.pdf
    """

    entry: "DOS15DirectoryEntry"
    # Total number of blocks described by this RIB
    number_of_blocks: int = 0
    # List of entries in the UFD block
    data_blocks: t.List[int]
    # Block number of this Master File Directory block
    block_number: int = 0
    # Block number of the next Master File Directory block
    next_block_number: int = 0
    # Block number of the previous Master File Directory block
    previous_block_number: int = 0

    def __init__(self, entry: "DOS15DirectoryEntry"):
        self.entry = entry

    @classmethod
    def read(cls, entry: "DOS15DirectoryEntry", block_number: int) -> "RetrievalInformationBlock":
        self = cls(entry)
        self.block_number = block_number
        # Read the block
        words = self.fs.read_words_block(block_number)
        self.number_of_blocks = words[0]  # Number of blocks in the RIB
        self.data_blocks = words[1 : self.number_of_blocks + 1]  # Data blocks
        self.previous_block_number = words[-2]  # Pointer to previous MFD block
        self.next_block_number = words[-1]  # Pointer to next MFD block
        return self

    @property
    def fs(self) -> "DOS15Filesystem":
        return self.entry.directory.fs


class UserFileDirectoryBlock(object):
    """
    User File Directory Block
    """

    ufd: "MasterFileDirectoryEntry"
    # List of entries in the UFD block
    entries_list: t.List[DOS15DirectoryEntry]
    # Block number of this Master File Directory block
    block_number: int = 0
    # Block number of the next Master File Directory block
    next_block_number: int = 0
    # Block number of the previous Master File Directory block
    previous_block_number: int = 0

    def __init__(self, ufd: "MasterFileDirectoryEntry"):
        self.ufd = ufd

    @classmethod
    def read(cls, ufd: "MasterFileDirectoryEntry", block_number: int) -> "UserFileDirectoryBlock":
        self = cls(ufd)
        self.block_number = block_number
        # Read the UFD block
        self.entries_list = []
        words = self.fs.read_words_block(block_number)
        for i, position in enumerate(range(0, len(words) - 8, 8)):
            entry = DOS15DirectoryEntry.read(self, words, i, position)
            if entry.is_active:
                self.entries_list.append(entry)
        self.previous_block_number = words[-2]  # Pointer to previous MFD block
        self.next_block_number = words[-1]  # Pointer to next MFD block
        return self

    @property
    def fs(self) -> "DOS15Filesystem":
        return self.ufd.fs


class MasterFileDirectoryEntry:
    """
    Master File Directory Entry in the MFD block

    Word

        +-----------------------------------+
      0 | UIC                               |
        +-----------------------------------+
      1 | UFD First Block                   |
        +-----------------------------------+
      2 | Prot. bit | UFD Entry Size        |
        +-----------------------------------+
      3 | Unused                            |
        +-----------------------------------+
    """

    mfd_block: "MasterFileDirectoryBlock"
    uic: str  # User Identification Code
    ufd_block_number: int  # Block number of the file
    protected: bool  # Protected bit
    ufd_entry_size: int  # UFD entry size in bits

    def __init__(self, mfd_block: "MasterFileDirectoryBlock"):
        self.mfd_block = mfd_block

    @classmethod
    def read(
        cls, mfd_block: "MasterFileDirectoryBlock", words: t.List[int], position: int
    ) -> "MasterFileDirectoryEntry":
        """
        Read a Master File Directory entry from the MFD block
        """
        self = cls(mfd_block)
        self.uic = sixbit_to_ascii(words[position])
        self.ufd_block_number = words[position + 1]
        self.protected = bool(words[position + 2] >> 17)
        self.ufd_entry_size = words[position + 2] & ~0o400000
        return self

    def is_active(self) -> bool:
        """
        Check if the entry is active
        """
        return self.ufd_block_number != 0o777777 and self.ufd_entry_size != 0

    def read_ufd_blocks(self) -> t.Iterator["UserFileDirectoryBlock"]:
        """Read User File Directory blocks"""
        next_block_number = self.ufd_block_number
        while next_block_number != 0o777777:
            ufd_block = UserFileDirectoryBlock.read(self, next_block_number)
            next_block_number = ufd_block.next_block_number
            yield ufd_block

    @property
    def entries_list(self) -> t.Iterator[DOS15DirectoryEntry]:
        """
        Iterate over all entries in the User File Directory
        """
        for ufd_block in self.read_ufd_blocks():
            yield from ufd_block.entries_list

    @property
    def fs(self) -> "DOS15Filesystem":
        return self.mfd_block.fs

    def __str__(self) -> str:
        """
        String representation of the Master File Directory entry
        """
        return f"UIC: {self.uic:>3}  Block: {self.ufd_block_number:6d}  Protected: {'Y' if self.protected else 'N'}  Entry Size: {self.ufd_entry_size}"


class MasterFileDirectoryBlock:
    """
    Master File Directory Block


    Word

        +-----------------------------------+
      0 | -1                                |
        +-----------------------------------+
      1 | Bad Allocation Table Block        |
        +-----------------------------------+
      2 | SYS Block                         |
        +-----------------------------------+
      3 | Entry Size | SAT Table Block      |
        +-----------------------------------+
      4 | MFD Entries (4 words each)        |
        /                                   /
        |                                   |
        +-----------------------------------+
    """

    fs: "DOS15Filesystem"
    # List of entries in the MFD block
    entries_list: t.List[MasterFileDirectoryEntry]
    # Bad allocation table first block number
    bad_allocation_table: int
    # SYSBLK first block number
    sysblk: int
    # Storage Allocation Table first block number
    storage_allocation_table: int
    # Block number of this Master File Directory block
    block_number: int = 0
    # Block number of the next Master File Directory block
    next_block_number: int = 0
    # Block number of the previous Master File Directory block
    previous_block_number: int = 0

    def __init__(self, fs: "DOS15Filesystem"):
        self.fs = fs

    @classmethod
    def read(cls, fs: "DOS15Filesystem", block_number: int) -> "MasterFileDirectoryBlock":
        self = cls(fs)
        self.block_number = block_number
        # Read the MFD block
        words = self.fs.read_words_block(RF_MFD_BLOCK)
        if words[0] != 0o777777:
            words = self.fs.read_words_block(RP_MFD_BLOCK)
            assert words[0] == 0o777777
        self.bad_allocation_table = words[1]
        self.sysblk = words[2]
        # MFD entry size in bits, plus the block number of the first submap
        tmp = words[3]
        # entry_size = tmp >> 15
        self.storage_allocation_table = tmp & 0o377777
        self.entries_list = []
        for i in range(4, len(words) - 4, 4):
            entry = MasterFileDirectoryEntry.read(self, words, i)
            if entry.is_active():
                self.entries_list.append(entry)
        self.previous_block_number = words[-2]  # Pointer to previous MFD block
        self.next_block_number = words[-1]  # Pointer to next MFD block
        return self


class MasterFileDirectory:
    """
    Master File Directory

    Pag 81
    https://bitsavers.org/pdf/dec/pdp15/DEC-15-ODFFA-A_DOS15_SysMan.pdf
    """

    fs: "DOS15Filesystem"
    mfd_blocks: t.List[MasterFileDirectoryBlock]  # List of MFD blocks

    def __init__(self, fs: "DOS15Filesystem"):
        self.fs = fs

    @classmethod
    def read(cls, fs: "DOS15Filesystem") -> "MasterFileDirectory":
        """
        Read the Master File Directory (MFD)
        """
        self = cls(fs)
        self.mfd_blocks = []
        mfd_block_number = RF_MFD_BLOCK
        while mfd_block_number != 0o777777:  # 0o777777 is the end of the MFD
            mfd_block = MasterFileDirectoryBlock.read(self.fs, mfd_block_number)
            mfd_block_number = mfd_block.next_block_number
            self.mfd_blocks.append(mfd_block)
        return self

    @property
    def entries_list(self) -> t.Iterator[MasterFileDirectoryEntry]:
        """
        Iterate over all entries in the Master File Directory
        """
        for mfd_block in self.mfd_blocks:
            yield from mfd_block.entries_list

    def get_entry(self, uic: str) -> t.Optional[MasterFileDirectoryEntry]:
        for entry in self.entries_list:
            if entry.uic == uic:
                return entry
        return None


class DOS15Filesystem(AbstractFilesystem):
    """
    DOS-15 Filesystem

    +------------+          +--------+
    |    MFD     +--------> |  SAT   |
    |   Master   |          | Master |
    |    File    |          | Bitmap |
    |  Directory |          +--------+
    +-----+------+         +-----------+    +-----------+
          |                |   UFD     |    |    RIB    |    +---------+
          +--------------> +   User    +--> | Retrieval +--> | Block 1 |
                           |   File    |    |   Block   |    |         |
                           | Directory |    +-----------+    +--^----+-+
                           +-----------+                        |    |
                                                                |    |
                                                             +--+----.-+
                                                             | Block 2 |
                                                             +-^-----+-+

    Pag 129
    https://bitsavers.org/pdf/dec/pdp15/PDP-15_System_Software_Handouts_1975.pdf
    """

    fs_name = "dos15"
    fs_description = "PDP-15 DOS-15"
    fs_platforms = ["pdp-9", "pdp-15"]
    uic: str = ""  # current User Identification Code (only for disk, not DECtape)
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
    ) -> t.Union["DOS15Filesystem", "ADSSFilesystem"]:
        """
        Mount the filesystem from a file or device
        """
        self = cls(file_or_dev)
        blocks = self.get_size() // 3 // 512
        is_dectape = abs(blocks - DECTAPE_BLOCKS) < 4
        if is_dectape:
            return ADSSFilesystem.mount(self.dev, strict=strict, **kwargs)

        self.uic = ""
        if strict:
            mfd = MasterFileDirectory.read(self)
            for ufd in mfd.entries_list:
                if not self.uic:
                    self.uic = ufd.uic
                    break
        return self

    def read_words_block(
        self,
        block_number: int,
    ) -> t.List[int]:
        """
        Read a 256 bytes block as 18bit words
        """
        return self.dev.read_words_block(block_number)

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write 256 18bit words as a block
        """
        self.dev.write_words_block(block_number, words)

    def read_dir_entries(self, uic: t.Optional[str] = None) -> t.Iterator["DOS15DirectoryEntry"]:
        """
        Read directory entries
        """
        mfd = MasterFileDirectory.read(self)
        ufd = mfd.get_entry(uic or self.uic)
        if ufd:
            yield from ufd.entries_list

    @property
    def entries_list(self) -> t.Iterator["DOS15DirectoryEntry"]:
        yield from self.read_dir_entries()

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
        uic: t.Optional[str] = None,
    ) -> t.Iterator["DOS15DirectoryEntry"]:
        uic, pattern = dos15_split_fullname(fullname=pattern, wildcard=wildcard, uic=uic or self.uic)
        for entry in self.read_dir_entries(uic):
            if entry.is_active and filename_match(entry.basename, pattern, wildcard):
                yield entry

    def get_file_entry(self, fullname: str) -> DOS15DirectoryEntry:
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
    ) -> DOS15DirectoryEntry:
        """
        Create a new file with a given length in number of blocks
        """
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

    # def read_bitmap(self) -> ADSSBitmap:
    #     """
    #     Read the Directory Bitmap
    #     """

    def write_bytes(
        self,
        fullname: str,
        content: t.Union[bytes, bytearray],
        creation_date: t.Optional[date] = None,
        file_type: t.Optional[str] = None,
        file_mode: t.Optional[str] = None,
    ) -> None:
        raise OSError(errno.EROFS, os.strerror(errno.EROFS))

    def isdir(self, fullname: str) -> bool:
        return False

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        """
            10-AUG-71
        MFD DIRECTORY LISTING
          5753 FREE BLKS
            47 USER FILES
           612 USER BLKS
        SCR    115(0)      6   316
        BLD    215(0)     14    23

             06-JAN-79
         DIRECTORY LISTING  (REN)
           6133 FREE BLKS
              6 USER FILES
             26 USER BLKS
        """
        if options.get("uic"):
            # Listing of all UIC
            dt = date.today().strftime('%y-%b-%d').upper()
            sys.stdout.write("UIC\n\n")
            sys.stdout.write(f"     {dt}\n")
            sys.stdout.write(" MFD DIRECTORY LISTING)\n")
            mfd = MasterFileDirectory.read(self)
            for ufd in mfd.entries_list:
                sys.stdout.write(f"{ufd.uic} {ufd}\n")
            return

        uic, pattern = dos15_split_fullname(fullname=pattern, wildcard=True, uic=self.uic)
        entries = list(self.filter_entries_list(pattern, uic=uic, wildcard=True))
        if not entries:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), pattern)
        if not options.get("brief"):
            dt = date.today().strftime('%y-%b-%d').upper()
            used = sum(entry.get_length() for entry in entries if entry.is_active)
            sys.stdout.write(f"     {dt}\n")
            sys.stdout.write(f" DIRECTORY LISTING  ({uic})\n")
            sys.stdout.write(f" {len(entries):>6o} USER FILES\n")
            sys.stdout.write(f" {used:>6o} USER BLKS\n")
        for x in entries:
            if x.is_active:
                if options.get("brief"):
                    sys.stdout.write(f"{x.filename:<6};{x.extension:<3}\n")
                else:
                    creation_date = x.creation_date and x.creation_date.strftime("%d-%b-%y").upper() or ""
                    sys.stdout.write(f" {x.filename:<6} {x.extension:<3}  {x.length:>6o}  {creation_date}\n")
        # if not options.get("brief"):
        #     bitmap = self.read_bitmap()
        #     sys.stdout.write(f"{bitmap.free():<4o} FREE BLOCKS\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        # if options.get("bitmap"):
        #     # Display the bitmap
        #     file_number = int(arg) if arg and arg.isdigit() else None
        #     bitmap = ADSSBitmap.read(self, file_number)
        #     for i in range(0, bitmap.total_bits):
        #         sys.stdout.write(f"{i:>4d} {'[ ]' if bitmap.is_free(i) else '[X]'}  ")
        #         if i % 16 == 15:
        #             sys.stdout.write("\n")
        #     sys.stdout.write(f"\nUsed blocks: {bitmap.used()}\n")
        # elif arg:
        if arg:
            # Display the file entry
            entries = self.filter_entries_list(arg, wildcard=True)
            for entry in entries:
                sys.stdout.write(f"File number:              {entry.file_number}\n")
                sys.stdout.write(f"Filename:                 {entry.filename}\n")
                sys.stdout.write(f"Extension:                {entry.extension}\n")
                sys.stdout.write(f"Raw data link:            {entry.raw_data_link:06o}\n")
                sys.stdout.write(f"Active:                   {'Y' if entry.is_active else 'N'}\n")
                sys.stdout.write(f"First block number:       {entry.block_number}\n")
                sys.stdout.write(f"Size:                     {entry.get_length()}\n")
                sys.stdout.write(f"RIB:                      {entry.retrieval_information_block}\n")
                sys.stdout.write(f"RIB position:             {entry.rib_position}\n")
                sys.stdout.write(f"Creation date:            {entry.creation_date}\n")
                sys.stdout.write(f"Protection code:          {entry.protection_code}\n")
                blocks = str(list(entry.get_blocks()))
                sys.stdout.write(f"Blocks:                   {blocks}\n")
                sys.stdout.write("\n")
        else:
            # Display the directory entries
            sys.stdout.write("Num   Filename  Data link Block  Size  Date\n")
            sys.stdout.write("---   --------  --------- -----  ----  ----\n")
            full = bool(options.get("full", False))
            for entry in self.read_dir_entries():
                if full or entry.is_active:
                    block_number = f"{entry.block_number:4d}" if entry.is_active else "-"
                    length = f"{entry.get_length():4d}" if entry.is_active else "-"
                    sys.stdout.write(
                        f"{entry.file_number:>2}  {entry.filename:>6};{entry.extension:<3}  "
                        f"{entry.raw_data_link:06o} {block_number:>8}  {length:>4}  "
                        f"{entry.creation_date}\n"
                    )

    def dump(self, fullname: t.Optional[str], start: t.Optional[int] = None, end: t.Optional[int] = None) -> None:
        """Dump the content of a file or a range of blocks"""
        if fullname:
            entry = self.get_file_entry(fullname)
            if start is None:
                start = 0
            blocks = entry.get_blocks()
            if end is None or end > len(blocks) - 1:
                end = entry.get_length() - 1
            for block_number in range(start, end + 1):
                words = self.read_words_block(blocks[block_number])
                sys.stdout.write(f"\nBLOCK NUMBER   {blocks[block_number]:08} ({block_number:08})\n")
                oct_dump(words)
        else:
            if start is None:
                start = 0
                if end is None:  # full disk
                    end = (self.get_size() // WORDS_PER_BLOCK // 4) - 1
            elif end is None:  # one single block
                end = start
            for block_number in range(start, end + 1):
                words = self.read_words_block(block_number)
                sys.stdout.write(f"\nBLOCK NUMBER   {block_number:08}\n")
                oct_dump(words)

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.dev.get_size()

    def chdir(self, fullname: str) -> bool:
        """
        Change the current User Identification Code
        """
        mfd = MasterFileDirectory.read(self)
        fullname = sixbit_to_ascii(ascii_to_sixbit(fullname[0:3]))
        entry = mfd.get_entry(fullname)
        if entry is None:
            return False
        self.uic = entry.uic
        return True

    def get_pwd(self) -> str:
        """
        Get the current User Identification Code
        """
        return self.uic
