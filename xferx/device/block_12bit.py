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

import struct
import typing as t

from .block import BlockDevice
from .rx import (
    RX01_SECTOR_SIZE,
    RX02_SECTOR_SIZE,
    get_sector_size,
    rx_extract_12bit_words,
    rx_pack_12bit_words,
    rxfactr_12bit,
)

if t.TYPE_CHECKING:
    from ..abstract import AbstractFile

__all__ = [
    "BlockDevice12Bit",
    "RXBlockDevice12Bit",
]


class BlockDevice12Bit(BlockDevice):
    """
    Block device for 12-bit mode
    """

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as 256 12bit words
        """
        data = self.read_block(block_number)
        return [x & 0o7777 for x in struct.unpack("<256H", data)]

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write 256 12bit words as a block
        """
        data = struct.pack("<256H", *words)
        self.write_block(data, block_number)

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        return self.f.read_block(block_number, number_of_blocks)

    def write_block(
        self,
        buffer: bytes,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        self.f.write_block(buffer, block_number, number_of_blocks)


class RXBlockDevice12Bit(BlockDevice12Bit):
    """
    Block device for 12-bit mode
    Supports RX01 and RX02 devices.
    """

    def __init__(self, file: "AbstractFile"):
        super().__init__(file)
        self.sector_size = get_sector_size(self.size)
        # self.is_rx = self.sector_size in (RX01_SECTOR_SIZE, RX02_SECTOR_SIZE)

    @property
    def is_rx(self) -> bool:
        """
        True if this device is a RX01/RX02
        """
        return self.sector_size in (RX01_SECTOR_SIZE, RX02_SECTOR_SIZE)

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as 256 12bit words
        """
        if self.is_rx:
            # Read the sectors
            result = []
            for position in rxfactr_12bit(block_number, self.sector_size):
                self.f.seek(position)
                data = self.f.read(self.sector_size)
                result.extend(rx_extract_12bit_words(data, 0, self.sector_size))
            return result
        else:
            data = self.read_block(block_number)
            return [x & 0o7777 for x in struct.unpack("<256H", data)]

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write 256 12bit words as a block
        """
        if self.is_rx:
            if self.sector_size == RX01_SECTOR_SIZE:
                words_per_sector = 64
            elif self.sector_size == RX02_SECTOR_SIZE:
                words_per_sector = 128
            for i, position in enumerate(rxfactr_12bit(block_number, self.sector_size)):
                words_position = i * words_per_sector
                sector_data = rx_pack_12bit_words(words, words_position, self.sector_size)
                self.f.seek(position)
                self.f.write(sector_data)
        else:
            data = struct.pack("<256H", *words)
            self.write_block(data, block_number)
