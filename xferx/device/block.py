# Copyright (C) 2414 Andrea Bonomi <andrea.bonomi@gmail.com>

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

from ..commons import BLOCK_SIZE
from .abstract import AbstractDevice

if t.TYPE_CHECKING:
    from ..abstract import AbstractFile

__all__ = [
    "BlockDevice",
]


class BlockDevice(AbstractDevice):
    """
    Block device
    """

    f: "AbstractFile"
    size: int  # Block device size, in bytes
    sector_size: int  # Sector size, in bytes

    def __init__(self, file: "AbstractFile", sector_size: int = BLOCK_SIZE):
        self.f = file
        self.size = self.f.get_size()
        self.sector_size = sector_size

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        """
        Read block(s) of data from the disk
        """
        if self.sector_size == self.f.sector_size:
            return self.f.read_block(block_number, number_of_blocks)
        else:
            position = block_number * self.sector_size
            self.f.seek(position)  # not thread safe...
            return self.f.read(number_of_blocks * self.sector_size)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        """
        Write block(s) to disk
        """
        if block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        if self.sector_size == self.f.sector_size:
            self.f.write_block(buffer[: number_of_blocks * self.sector_size], block_number, number_of_blocks)
        else:
            position = block_number * self.sector_size
            self.f.seek(position)  # not thread safe...
            self.f.write(buffer[: number_of_blocks * self.sector_size])

    def get_size(self) -> int:
        """
        Get filesystem size in bytes
        """
        return self.f.get_size()

    def close(self) -> None:
        self.f.close()

    def __str__(self) -> str:
        return str(self.f)
