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
import struct
import threading
import typing as t

from ..abstract import AbstractFile
from ..commons import BLOCK_SIZE, READ_FILE_FULL
from ..device.block import BlockDevice

__all__ = ["DiskCopy"]

# https://nulib.com/library/FTN.e00005.htm
# https://web.archive.org/web/20201028142058/https://wiki.68kmla.org/DiskCopy_4.2_format_specification

DISK_COPY_SIGNATURE = 0x0100
DISK_COPY_HEADER_FORMAT = '>B63sIIIIBBH'
DISK_COPY_HEADER_SIZE = struct.calcsize(DISK_COPY_HEADER_FORMAT)
assert DISK_COPY_HEADER_SIZE == 84

DISK_FORMAT_400K = 0  # 400k GCR CLV SSDD
DISK_FORMAT_800K = 1  # 800k GCR CLV DSDD
DISK_FORMAT_720K = 2  # 720k MFM CAV DSDD
DISK_FORMAT_1440K = 3  # 1.44MB MFM CAV DSHD


class DiskCopy(BlockDevice):
    name: str  # Image name
    data_size: int  # Data fork size in bytes
    tag_size: int  # Tag fork size in bytes
    data_checksum: int  # Checksum of data fork
    tag_checksum: int  # Checksum of tag fork
    disk_encoding: int  # Disk encoding
    disk_format: int  # Disk format
    data_block_count: int  # Number of data blocks

    def __init__(self, file: "AbstractFile"):
        super().__init__(file)
        self._lock = threading.Lock()
        buffer = self.f.read(DISK_COPY_HEADER_SIZE)
        (
            name_len,
            raw_name,
            self.data_size,
            self.tag_size,
            self.data_checksum,
            self.tag_checksum,
            self.disk_encoding,
            self.disk_format,
            signature,
        ) = struct.unpack_from(DISK_COPY_HEADER_FORMAT, buffer)
        # Validate signature
        if signature != DISK_COPY_SIGNATURE:
            raise OSError(errno.EIO, f"Invalid DiskCopy signature {signature:04x}")
        # Calculate number of blocks
        self.data_block_count = (self.data_size + BLOCK_SIZE - 1) // BLOCK_SIZE
        self.name = raw_name[:name_len].decode('ascii', errors='ignore').replace('\x00', '')

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
            position = block_number * BLOCK_SIZE + DISK_COPY_HEADER_SIZE
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
        with self._lock:
            self.f.seek(block_number * BLOCK_SIZE + DISK_COPY_HEADER_SIZE)
            self.f.write(buffer[0 : number_of_blocks * BLOCK_SIZE])

    def get_size(self) -> int:
        """
        Get data size in bytes
        """
        return self.f.get_size() - DISK_COPY_HEADER_SIZE

    def compute_data_checksum(self) -> int:
        """
        Compute the checksum of the data fork
        """
        checksum = 0
        for block_number in range(self.data_block_count):
            buffer = self.read_block(block_number)
            words = list(struct.unpack(">256H", buffer))
            for word in words:
                checksum = (checksum + word) & 0xFFFFFFFF
                checksum = ((checksum & 1) << 31) | ((checksum >> 1) & 0x7FFFFFFF)
        return checksum

    def close(self) -> None:
        # TODO - checksum
        # checksum = self.compute_data_checksum()
        # print(f"{self.data_checksum:04x} {checksum:04x} {self.data_size} {self.data_block_count} blocks")
        self.f.close()

    def __str__(self) -> str:
        return str(self.f)
