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
import struct
import typing as t

from .block import BlockDevice

if t.TYPE_CHECKING:
    from ..abstract import AbstractFile

__all__ = [
    "BYTES_PER_WORD_36BIT",
    "WORDS_PER_BLOCK_36BIT",
    "BlockDevice36Bit",
]


BYTES_PER_WORD_36BIT = 8
WORDS_PER_BLOCK_36BIT = 128
WORD_MASK_36BIT = (1 << 36) - 1


class BlockDevice36Bit(BlockDevice):
    """
    Block device for PDP-10 36-bit words
    """

    words_per_block: int

    def __init__(
        self,
        file: "AbstractFile",
        words_per_block: int = WORDS_PER_BLOCK_36BIT,
    ):
        super().__init__(file, sector_size=words_per_block * BYTES_PER_WORD_36BIT)
        self.words_per_block = words_per_block

    def read_block(self, block_number: int, number_of_blocks: int = 1) -> bytes:
        if block_number < 0 or number_of_blocks < 0:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        self.f.seek(block_number * self.sector_size)
        data = self.f.read(number_of_blocks * self.sector_size)
        if len(data) != number_of_blocks * self.sector_size:
            raise OSError(errno.EIO, "Short PDP-10 block")
        return data

    def read_words_block(self, block_number: int) -> t.List[int]:
        """Read a block of PDP-10 36-bit words from an image."""
        data = self.read_block(block_number)
        words = struct.unpack(f"<{self.words_per_block}Q", data)
        return [word & WORD_MASK_36BIT for word in words]

    def write_words_block(self, block_number: int, words: t.List[int]) -> None:
        """Write a block of PDP-10 36-bit words to an image."""
        if block_number < 0 or len(words) != self.words_per_block:
            raise OSError(errno.EIO, "Invalid PDP-10 block size")
        data = struct.pack(f"<{self.words_per_block}Q", *(word & WORD_MASK_36BIT for word in words))
        self.f.seek(block_number * self.sector_size)
        self.f.write(data)
