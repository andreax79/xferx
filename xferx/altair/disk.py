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
import typing as t

from ..abstract import AbstractFile
from ..commons import BLOCK_SIZE, TrackSector
from ..device.block import BlockDevice

__all__ = ["AltairDisk"]

SECTOR_SIZE = 128  # bytes per sector
SECTORS_PER_TRACK = 26  # sectors per track
TRACKS = 77  # tracks per disk
TOTAL_SECTORS = TRACKS * SECTORS_PER_TRACK  # total sectors per disk
# Sector interleave map is (logical sector number -> physical sector number)
SECTOR_ORDER = (1, 10, 19, 2, 11, 20, 3, 12, 21, 4, 13, 22, 5, 14, 23, 6, 15, 24, 7, 16, 25, 8, 17, 26, 9, 18)


class AltairDisk(BlockDevice):
    """
    Altair floppy disk
    """

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the floppy
        """
        if block_number < 0 or number_of_blocks < 0 or block_number + number_of_blocks > TOTAL_SECTORS:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        result = bytearray()
        for logical in range(block_number, block_number + number_of_blocks):
            track, sector = divmod(logical, SECTORS_PER_TRACK)
            data = self.read_sector(TrackSector(track, sector))
            if len(data) != SECTOR_SIZE:
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            result.extend(data)
        return bytes(result)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) of data to the floppy
        """
        if (
            block_number < 0
            or number_of_blocks < 0
            or block_number + number_of_blocks > TOTAL_SECTORS
            or len(buffer) < number_of_blocks * SECTOR_SIZE
        ):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        for index in range(number_of_blocks):
            track, sector = divmod(block_number + index, SECTORS_PER_TRACK)
            start = index * SECTOR_SIZE
            self.write_sector(buffer[start : start + SECTOR_SIZE], TrackSector(track, sector))

    def read_sector(self, address: TrackSector) -> bytes:
        """
        Read a sector of data from the floppy
        """
        if address.track < 0 or address.track >= TRACKS or address.sector < 0 or address.sector > SECTORS_PER_TRACK:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        block_number = address.track * SECTORS_PER_TRACK + SECTOR_ORDER[address.sector] - 1
        return super().read_block(block_number)

    def write_sector(self, buffer: t.Union[bytes, bytearray], address: TrackSector) -> None:
        """
        Write a sector of data to the floppy
        """
        if address.track < 0 or address.track >= TRACKS or address.sector < 0 or address.sector > SECTORS_PER_TRACK:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        block_number = address.track * SECTORS_PER_TRACK + SECTOR_ORDER[address.sector] - 1
        super().write_block(buffer, block_number)
