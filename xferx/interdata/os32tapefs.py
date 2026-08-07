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
import math
import os
import struct
import sys
import typing as t
from datetime import datetime, timedelta

from ..abstract import AbstractDirectoryEntry, AbstractFile, AbstractFilesystem
from ..commons import ASCII, READ_FILE_FULL, filename_match
from ..device.abstract import AbstractDevice
from ..device.tape import Tape
from .os32fs import (
    records_to_ascii,
    os32_split_fullname,
    date_to_os32,
    os32_to_date,
    format_time,
    ANY_ACCOUNT,
    FILE_TYPES,
    CO_FILE_TYPE,
    EC_FILE_TYPE,
    IN_FILE_TYPE,
    NB_FILE_TYPE,
    LR_FILE_TYPE,
    IT_FILE_TYPE,
    OS32_BLOCK_SIZE,
)

__all__ = [
    "OS32TapeFile",
    "OS32TapeFilesystem",
]

VOLUME_HEADER_FORMAT = ">4s6xB B 2B 2x I 4x 4s8s3sB"
VOLUME_HEADER_SIZE = 80
FILE_INFORMATION_BLOCK_FORMAT = ">H H b b H H H 8s 3s b H H I I"
FILE_INFORMATION_BLOCK_SIZE = 80


class OS32TapeFile(AbstractFile):
    entry: "FileInformationBlock"
    closed: bool
    size: int  # size in bytes
    content: bytes  # file content

    def __init__(self, entry: "FileInformationBlock"):
        self.entry = entry
        self.closed = False
        entry.fs.dev.tape_seek(entry.tape_pos)
        entry.fs.dev.tape_read_forward()  # skip the header
        self.content = entry.fs.dev.tape_read_file()
        self.size = len(self.content)

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the file
        """
        if number_of_blocks == READ_FILE_FULL:
            number_of_blocks = self.entry.num_of_records
        if (
            self.closed
            or block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > self.entry.num_of_records
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        return self.content[block_number * OS32_BLOCK_SIZE : (block_number + number_of_blocks) * OS32_BLOCK_SIZE]

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

    def get_size(self) -> int:
        """
        Get file size in bytes
        """
        return self.size

    def get_block_size(self) -> int:
        """
        Get file block size in bytes (always 256 bytes)
        """
        return OS32_BLOCK_SIZE

    def close(self) -> None:
        """
        Close the file
        """
        self.closed = True

    def __str__(self) -> str:
        return self.entry.fullname


class FileInformationBlock(AbstractDirectoryEntry):
    """
    File Information Block (FIB) - 80 bytes

        +-------------------------------------+------------------+------------------+
     0  |             Attributes              |                 ???                 |
        +-------------------------------------+------------------+------------------+
     4  |    Write key     |    Read key      |            Record length            |
        +-------------------------------------+------------------+------------------+
     8  |                    Current sector / Number logical records                |
        +---------------------------------------------------------------------------+
    12  |                                Filename                                   |
        |                                                                           |
        +--------------------------------------------------------+------------------+
    20  |              Extension                                 |  Account (low)   |
        +-------------------------------------+------------------+------------------+
    24  |             Block size ???          |         Index block size ???        |
        +-------------------------------------+-------------------------------------+
    28  |                             Date file allocated                           |
        +---------------------------------------------------------------------------+
    32  |                            Date file last written                         |
        +---------------------------------------------------------------------------+
        |                                                                           |
        /                                    ...                                    /
    76  |                                                                           |
        +---------------------------------------------------------------------------+

    OS/32 System Support Utilities Reference Manual, Pag 35
    https://bitsavers.org/pdf/interdata/32bit/os32/1984_7.2/48-031F00R02_SysSupportUtil_1984.pdf
    """

    fs: "OS32TapeFilesystem"
    attributes: int = 0  # File attributes
    write_key: int = 0
    read_key: int = 0
    record_length: int = 0  # Record length, in bytes
    num_of_records: int = 0  # Number of disk records
    filename: str = ""  # File name, up to 8 characters
    extension: str = ""  # File extension, up to 3 characters
    account: int = 0  # Account number, 0-65535
    block_size: int = 0  # Block size, in number of 256 bytes sectors
    index_block_size: int = 0  # Size of the index block, in number of 256 bytes sectors
    raw_creation_date: int = 0  # Creation date and time
    raw_last_mod_date: int = 0  # Last modification date and time
    tape_pos: int = 0  # tape position (before file header)

    def __init__(self, fs: "OS32TapeFilesystem"):
        self.fs = fs

    @classmethod
    def read(
        cls,
        fs: "OS32TapeFilesystem",
        buffer: bytes,
        tape_pos: int,
    ) -> "FileInformationBlock":
        self = FileInformationBlock(fs)
        self.tape_pos = tape_pos
        (
            self.attributes,
            _,
            self.write_key,
            self.read_key,
            self.record_length,
            _,
            self.num_of_records,
            filename,
            extension,
            self.account,
            self.block_size,
            self.index_block_size,
            self.raw_creation_date,
            self.raw_last_mod_date,
        ) = struct.unpack_from(FILE_INFORMATION_BLOCK_FORMAT, buffer, 0)
        self.filename = filename.decode("ascii", errors="ignore").rstrip("\0 ")
        self.extension = extension.decode("ascii", errors="ignore").rstrip("\0 ")
        if self.is_contiguous:
            self.num_of_records = self.index_block_size
            self.index_block_size = 0
        # print([x for x in buffer][28:32])
        # self.size = size - FILE_INFORMATION_BLOCK_SIZE
        return self

    @property
    def fullname(self) -> str:
        """
        Full name of the file, including account number
        """
        return f"{self.basename}/{self.account}"

    @property
    def basename(self) -> str:
        """
        File name with extension
        """
        if not self.extension:
            return self.filename
        else:
            return f"{self.filename}.{self.extension}"

    @property
    def last_mod_date(self) -> t.Optional[datetime]:
        """
        Last modification date
        """
        return os32_to_date(self.raw_last_mod_date)

    @property
    def creation_date(self) -> t.Optional[datetime]:
        """
        Creation date
        """
        return os32_to_date(self.raw_creation_date)

    @property
    def is_contiguous(self) -> bool:
        """
        Contiguous file
        """
        return self.raw_file_type == CO_FILE_TYPE

    @property
    def is_extended_contiguous(self) -> bool:
        """
        Extended contiguous file
        """
        return self.raw_file_type == EC_FILE_TYPE

    @property
    def is_indexed(self) -> bool:
        """
        Indexed file
        """
        return self.raw_file_type == IN_FILE_TYPE

    @property
    def is_nonbuffered_indexed(self) -> bool:
        """
        Nonbuffered indexed file
        """
        return self.raw_file_type == NB_FILE_TYPE

    @property
    def is_long_record(self) -> bool:
        """
        Long record file
        """
        return self.raw_file_type == LR_FILE_TYPE

    @property
    def raw_file_type(self) -> int:
        """
        Raw file type
        """
        return self.attributes & 7

    @property
    def file_type(self) -> t.Optional[str]:
        """
        File type
        """
        try:
            return FILE_TYPES[self.raw_file_type][0]
        except KeyError:
            return "??"

    def get_length(self, fork: t.Optional[str] = None) -> int:
        """
        Get the length in 256 bytes blocks
        """
        return self.num_of_records

    def get_size(self, fork: t.Optional[str] = None) -> int:
        """
        Get file size in bytes
        """
        return self.get_length() * self.get_block_size()

    def get_block_size(self) -> int:
        """
        Get file block size in bytes (always 256 bytes)
        """
        return OS32_BLOCK_SIZE

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

    def open(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> OS32TapeFile:
        """
        Open a file
        """
        return OS32TapeFile(self)

    def read_bytes(self, file_mode: t.Optional[str] = None, fork: t.Optional[str] = None) -> bytes:
        """
        Get the content of the file
        """
        data = super().read_bytes(file_mode, fork)
        if file_mode == ASCII and self.record_length > 0:
            return records_to_ascii(data, self.record_length, self.num_of_records)
        else:
            return data

    def __str__(self) -> str:
        creation_date = format_time(self.creation_date)
        last_mod_date = format_time(self.last_mod_date)
        if self.is_contiguous:
            return (
                f"{self.filename:<8s}.{self.extension:<3s}/{self.account:05d} {self.file_type:>2s} "
                f"               "
                f"{self.num_of_records:>7} {creation_date} {last_mod_date} "
                f"{self.write_key:02X}{self.read_key:02X}"
            )
        else:
            return (
                f"{self.filename:<8s}.{self.extension:<3s}/{self.account:05d} {self.file_type:>2s} "
                f"{self.block_size:>4}/{self.index_block_size:<3} {self.record_length:>5} "
                f"{self.num_of_records:>7} {creation_date} {last_mod_date} "
                f"{self.write_key:02X}{self.read_key:02X}"
            )

    def __repr__(self) -> str:
        return str(self)


class VolumeHeader:
    """
    Volume header - 80 bytes
    """

    name: str = ""  # Volume name
    rev: str = ""  # Backup revision and update number
    creation_date: t.Optional[datetime] = None  # Creation date
    buffer_size: int = 0  # Size of the buffer used to transfer data
    select_vol: str = ""  # Select volume name
    select_filename: str = ""  # Select file name
    select_extension: str = ""  # Select file extension
    select_account: int = 0  # Select account number

    @classmethod
    def read(cls, fs: "OS32TapeFilesystem") -> "VolumeHeader":
        fs.dev.tape_rewind()
        buffer = fs.dev.tape_read_forward()
        if len(buffer) != VOLUME_HEADER_SIZE:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        self = VolumeHeader()
        (
            name,
            buffer_size,
            _,
            rev_major,
            rev_minor,
            creation_date,
            select_vol,
            select_filename,
            select_extension,
            self.select_account,
        ) = struct.unpack_from(VOLUME_HEADER_FORMAT, buffer, 0)
        self.name = name.decode("ascii", errors="ignore").rstrip("\0 ")
        self.rev = f"{rev_major:02}-{rev_minor:02}"
        self.buffer_size *= OS32_BLOCK_SIZE
        self.select_vol = select_vol.decode("ascii", errors="ignore").rstrip("\0 ")
        self.select_filename = select_filename.decode("ascii", errors="ignore").rstrip("\0 ")
        self.select_extension = select_extension.decode("ascii", errors="ignore").rstrip("\0 ")
        # The date format is different from the one used in the File Information Block
        try:
            t = creation_date >> 16
            year = 1900 + (t >> 9)
            if year < 1970:
                year += 100
            month = t // 32 % 16
            day = t % 32
            t = creation_date & 0xFFFF
            h = t // 60
            m = t % 60
            self.creation_date = datetime(year, month, day, h, m)
        except Exception:
            self.creation_date = None
        return self


class OS32TapeFilesystem(AbstractFilesystem):
    """
    Disk Backup Utility Magnetic Tape Format

        +-------------------------------------+
        |          Volume header              |  80 bytes
        +-------------------------------------+
        |     File Information Block (FIB)    |  80 bytes
        +-------------------------------------+
        |              Data                   |
        +-------------------------------------+
        |               EOF                   |
        +-------------------------------------+
        |     File Information Block (FIB)    |  80 bytes
        +-------------------------------------+
        |              Data                   |
        +-------------------------------------+
        |               EOF                   |
        /               ...                   /
        |               EOv                   |
        +-------------------------------------+

    OS/32 System Support Utilities Reference Manual, Pag 35
    https://bitsavers.org/pdf/interdata/32bit/os32/1984_7.2/48-031F00R02_SysSupportUtil_1984.pdf
    """

    fs_name = "os32mt"
    fs_description = "Interdata OS/32 Backup Tape Format"
    fs_platforms = ["interdata"]
    fs_entry_metadata = [
        "creation_date",
        "last_mod_date",
        "file_type",
        "index_block_size",
        "block_size",
        "record_length",
        "num_of_records",
    ]

    dev: Tape

    volume_name: str = ""  # Volume name
    volume_rev: str = ""  # Backup revision
    volume_creation_date: t.Optional[datetime] = None  # Creation date

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"]):
        if isinstance(file_or_device, AbstractFile):
            self.dev = Tape(file_or_device)
        elif isinstance(file_or_device, Tape):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, f"Invalid device type for {self.fs_description} filesystem")

    @classmethod
    def mount(
        cls,
        file_or_dev: t.Union["AbstractFile", "AbstractDevice"],
        strict: t.Union[bool, str] = True,
        **kwargs: t.Union[bool, str],
    ) -> "OS32TapeFilesystem":
        """
        Mount the filesystem from a file or device
        """
        self = cls(file_or_dev)
        self.dev.tape_rewind()
        if strict:
            VolumeHeader.read(self)
        return self

    def read_file_headers(self, account: int = ANY_ACCOUNT) -> t.Iterator["FileInformationBlock"]:
        """Read file headers"""
        self.dev.tape_rewind()
        volume_header = self.dev.tape_read_forward()
        assert len(volume_header) == VOLUME_HEADER_SIZE, "Invalid volume header size"
        try:
            while True:
                tape_pos = self.dev.tape_pos
                header, _ = self.dev.tape_read_header()
                if header:
                    entry = FileInformationBlock.read(self, header, tape_pos)
                    if account == ANY_ACCOUNT or entry.account == account:
                        yield entry
        except EOFError:
            pass

    def filter_entries_list(
        self,
        pattern: t.Optional[str],
        include_all: bool = False,
        expand: bool = True,
        wildcard: bool = True,
        account: t.Optional[int] = None,
    ) -> t.Iterator["FileInformationBlock"]:
        if account is None:
            account = ANY_ACCOUNT
        account, filename_pattern = os32_split_fullname(fullname=pattern, wildcard=wildcard, account=account)
        for entry in self.read_file_headers(account=account):
            if filename_match(entry.basename, filename_pattern, wildcard) and (
                entry.account == account or account == ANY_ACCOUNT
            ):
                yield entry

    @property
    def entries_list(self) -> t.Iterator["FileInformationBlock"]:
        for entry in self.read_file_headers(account=ANY_ACCOUNT):
            yield entry

    def get_file_entry(self, fullname: str) -> "FileInformationBlock":
        """
        Get the directory entry for a file
        """
        account, filename = os32_split_fullname(fullname=fullname, wildcard=False, account=ANY_ACCOUNT)
        try:
            return next(self.filter_entries_list(filename, account=account, wildcard=False))
        except StopIteration:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fullname)

    def show_accounts(self, volume_id: str, options: t.Dict[str, bool]) -> None:
        """
        Listing of all UIC
        """
        accounts = set()
        for entry in self.entries_list:
            accounts.add(entry.account)
        sys.stdout.write(f"  ACT")
        for account in sorted(accounts):
            sys.stdout.write(f"{account}\n")

    def dir(self, volume_id: str, pattern: t.Optional[str], options: t.Dict[str, bool]) -> None:
        """
        List the files in the filesystem
        """
        if options.get("uic"):
            self.show_accounts(volume_id, options)
            return
        if not options.get("brief"):
            volume_header = VolumeHeader.read(self)
            creation_date = format_time(volume_header.creation_date)
            sys.stdout.write(f"\nInput:     {volume_id}:\n\n")
            sys.stdout.write("           Header Information from Input Tape:\n\n")
            sys.stdout.write(
                f"           Volume: {volume_header.name:>4}:   "
                f"Date Created {creation_date}   "
                f"BACKUP Rev.: {volume_header.rev}\n\n"
            )
            if volume_header.select_vol:
                select = f"{volume_header.select_vol}:{volume_header.select_filename}.{volume_header.select_extension}/{volume_header.select_account}"
            else:
                select = "** All **"
            sys.stdout.write(f"           Size: {volume_header.buffer_size / 1024:.2f}K   Select: {select}\n\n")
            sys.stdout.write("Files Selected:\n\n")
            sys.stdout.write("Filename......... Type Dbs/Ibs Lrecl Records Date Created.. Date Written.. Keys\n\n")
        for x in self.filter_entries_list(pattern, include_all=False, wildcard=True):
            if options.get("brief"):
                # For brief mode, print only the file name
                sys.stdout.write(f"{x.basename}\n")
            else:
                # Print file information
                creation_date = format_time(x.creation_date)
                last_mod_date = format_time(x.last_mod_date)
                if x.is_indexed or x.is_nonbuffered_indexed:
                    # DBS     - the data block size (in sectors)
                    # IBS     - the index block size (in sectors)
                    # RECL    - the record length in bytes
                    dbs_ibs_recl = f"{x.block_size:>3}/{x.index_block_size:<3} {x.record_length:>5}"
                elif x.is_extended_contiguous:
                    dbs_ibs_recl = f"{x.block_size:>3}/{x.index_block_size:<3}"
                else:
                    dbs_ibs_recl = ""  # TODO

                sys.stdout.write(
                    f"{x.filename:<8}.{x.extension:<3}/{x.account:05} {x.file_type}  "
                    f"{dbs_ibs_recl:13} "
                    f"{x.num_of_records:>7} "
                    f"{creation_date} "
                    f"{last_mod_date} "
                    f"{x.write_key:02X}{x.read_key:02X}\n"
                )
        sys.stdout.write("\n")

    def examine(self, arg: t.Optional[str], options: t.Dict[str, t.Union[bool, str]]) -> None:
        pass

    #     if arg:
    #         self.dump(arg)
    #     else:
    #         sys.stdout.write("     Filename    UIC    Access Date         Size\n")
    #         sys.stdout.write("     --------    ---    ------ ----         -----\n")
    #         for entry in self.read_file_headers(uic=ANY_UIC):
    #             sys.stdout.write(f"{entry}\n")

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.dev.get_size()

    def isdir(self, fullname: str) -> bool:
        """
        Check if the given path is an account number
        """
        try:
            int(fullname)
            return True
        except Exception:
            return False
