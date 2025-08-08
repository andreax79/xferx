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

from ..commons import BLOCK_SIZE
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
    "DECtape12Bit",
    "RXBlockDevice12Bit",
    "COSRXBlockDevice12Bit",
]

BYTES_PER_WORD = 2  # Each word is encoded in 2 bytes
BLOCK_SIZE_WORDS = 256  # Size of a block in words (12-bit mode)
COS_TRACKS = 77  # Number of tracks in a COS RX01 disk image
COS_SECTORS_PER_TRACK = 26  # Number of sectors per track in COS RX01 disk image
COS_SECTORS_PER_BLOCK = 3  # Number of sectors per block in COS RX01 disk image
DECTAPE_BLOCK_SIZE = 129  # DECtape block size in words
DECTAPE_BLOCKS_PER_DEVICE_BLOCK = 2  # Number of DECtape blocks per device block


class BlockDevice12Bit(BlockDevice):
    """
    Block device for 12-bit mode
    """

    block_size_words: int = BLOCK_SIZE_WORDS  # Size of a block in bytes
    block_offset_bytes: int = 0  # Offset in bytes for the blocks

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as `block_words` 12bit words
        """
        data = self.read_block(block_number)
        return [x & 0o7777 for x in struct.unpack(f"<{self.block_size_words}H", data)]

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write `block_words` 12bit words as a block
        """
        data = struct.pack(f"<{self.block_size_words}H", *words)
        self.write_block(data, block_number)

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        data = bytearray()
        for i in range(block_number, block_number + number_of_blocks):
            position = i * self.block_size_words * BYTES_PER_WORD + self.block_offset_bytes
            self.f.seek(position)
            data += self.f.read(self.block_size_words * BYTES_PER_WORD)
        return bytes(data)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        for i in range(block_number, block_number + number_of_blocks):
            position = i * self.block_size_words * BYTES_PER_WORD + self.block_offset_bytes
            self.f.seek(position)
            self.f.write(buffer[: self.block_size_words * BYTES_PER_WORD])
            buffer = buffer[self.block_size_words * BYTES_PER_WORD :]


def cos_sector_position(sector: int, sector_size: int) -> int:
    """
    Calculate the position of a sector in a COS RX01 disk image
    """
    track = 1 + (sector // COS_SECTORS_PER_TRACK)
    sector_in_track = (sector * COS_SECTORS_PER_BLOCK) % COS_SECTORS_PER_TRACK
    return ((track * COS_SECTORS_PER_TRACK) + sector_in_track) * sector_size


class DECtape12Bit(BlockDevice12Bit):
    """
    DECtape block device
    OS/8 only uses 128 words out of 129 in a PDP-8 DECtape block
    """

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        data = bytearray()
        for i in range(number_of_blocks * DECTAPE_BLOCKS_PER_DEVICE_BLOCK):
            self.f.seek(block_number * DECTAPE_BLOCK_SIZE * 4 + i)
            data += self.f.read(BLOCK_SIZE // DECTAPE_BLOCKS_PER_DEVICE_BLOCK)
        return bytes(data)

    def write_block(
        self,
        buffer: t.Union[bytes, bytearray],
        block_number: int,
        number_of_blocks: int = 1,
    ) -> None:
        for i in range(number_of_blocks * DECTAPE_BLOCKS_PER_DEVICE_BLOCK):
            self.f.seek(block_number * DECTAPE_BLOCK_SIZE * 4 + i)
            pos = i * BLOCK_SIZE // DECTAPE_BLOCKS_PER_DEVICE_BLOCK
            self.f.write(buffer[pos : pos + BLOCK_SIZE // DECTAPE_BLOCKS_PER_DEVICE_BLOCK])


class RXBlockDevice12Bit(BlockDevice12Bit):
    """
    Block device for 12-bit
    """

    def __init__(self, file: "AbstractFile", cos_support: bool = False):
        super().__init__(file)
        self.sector_size = get_sector_size(self.size)
        self.cos_support = cos_support
        self.is_rx = self.sector_size == RX01_SECTOR_SIZE

    def read_sector(self, sector: int) -> bytes:
        """
        Read a sector from the disk image (for COS RX01 floppy)
        """
        position = cos_sector_position(sector, self.sector_size)
        self.f.seek(position)
        return self.f.read(self.sector_size)

    def write_sector(self, buffer: t.Union[bytes, bytearray], sector: int) -> None:
        """
        Write a sector to the disk image (for COS RX01 floppy)
        """
        position = cos_sector_position(sector, self.sector_size)
        self.f.seek(position)
        self.f.write(buffer)

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as `block_size_words` 12bit words
        """
        if self.is_rx:
            # RX01/RX02 12-bit mode
            result = []
            for position in rxfactr_12bit(block_number, self.sector_size):
                self.f.seek(position)
                data = self.f.read(self.sector_size)
                result.extend(rx_extract_12bit_words(data, 0, self.sector_size))
            return result
        else:
            # Non-RX mode, read as block_size_words 12-bit words
            data = self.read_block(block_number)
            return [x & 0o7777 for x in struct.unpack(f"<{self.block_size_words}H", data)]

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write `block_size_words` 12bit words as a block
        """
        if self.is_rx:
            # RX01/RX02 12-bit mode
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
            # Non-RX mode, write as `block_size_words` 12-bit words
            data = struct.pack(f"<{self.block_size_words}H", *words)
            self.write_block(data, block_number)


class COSRXBlockDevice12Bit(RXBlockDevice12Bit):
    """
    Block device for 12-bit
    Supports RX01 and RX02 devices and RX01 in COS byte mode
    """

    def __init__(self, file: "AbstractFile"):
        super().__init__(file)
        self.sector_size = get_sector_size(self.size)
        self.is_rx = self.sector_size == RX01_SECTOR_SIZE

    def read_words_block(self, block_number: int) -> t.List[int]:
        """
        Read a block as `block_size_words` 12bit words
        """
        if self.is_rx:
            # COS RX01 byte mode
            sector = block_number * COS_SECTORS_PER_BLOCK
            data = self.read_sector(sector) + self.read_sector(sector + 1) + self.read_sector(sector + 2)
            words: t.List[int] = []
            for i in range(self.sector_size):
                words.append(data[self.sector_size + 2 * i] + ((data[i] >> 4) << 8))
                words.append(data[self.sector_size + 2 * i + 1] + ((data[i] & 0x0F) << 8))
            return words
        else:
            # Non-RX mode, read as `block_size_words` 12-bit words
            data = self.read_block(block_number)
            return [x & 0o7777 for x in struct.unpack(f"<{self.block_size_words}H", data)]

    def write_words_block(
        self,
        block_number: int,
        words: t.List[int],
    ) -> None:
        """
        Write `block_size_words` 12bit words as a block
        """
        if self.is_rx:
            # COS RX01 byte mode
            sector = block_number * COS_SECTORS_PER_BLOCK
            buffer = bytearray(self.sector_size * COS_SECTORS_PER_BLOCK)
            for i in range(self.sector_size):
                word1 = words[2 * i]
                word2 = words[2 * i + 1]
                # High bits
                buffer[i] = ((word1 >> 8) << 4) | (word2 >> 8 & 0x0F)
                # Low bits
                buffer[self.sector_size + 2 * i] = word1 & 0xFF
                buffer[self.sector_size + 2 * i + 1] = word2 & 0xFF
            # Write the sectors
            self.write_sector(buffer[: self.sector_size], sector)
            self.write_sector(buffer[self.sector_size : 2 * self.sector_size], sector + 1)
            self.write_sector(buffer[2 * self.sector_size :], sector + 2)
        elif self.is_rx:
            # RX01/RX02 12-bit mode
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
            # Non-RX mode, write as `block_size_words` 12-bit words
            data = struct.pack(f"<{self.block_size_words}H", *words)
            self.write_block(data, block_number)
