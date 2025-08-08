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

from ..commons import ASCII, IMAGE, BlockDirection, Direction
from .block import BlockDevice

if t.TYPE_CHECKING:
    from ..abstract import AbstractFile

__all__ = [
    "BYTES_PER_WORD_18BIT",
    "WORDS_PER_BLOCK",
    "BlockDevice18Bit",
    "from_18bit_words_to_bytes",
    "from_bytes_to_18bit_words",
    "reverse_word",
]


BYTES_PER_WORD_18BIT = 4  # Each word is encoded in 4 bytes
WORDS_PER_BLOCK = 256  # Number of words per block


def from_18bit_words_to_bytes(words: list[int], file_type: str = ASCII) -> bytes:
    """
    Convert 18bit words to 3 bytes (IMAGE) or 2 bytes (ASCII)
    """
    data = bytearray()
    if file_type == ASCII:
        for word in words:
            data.append((word >> 9) & 0o177)
            data.append(word & 0o177)
    else:
        for word in words:
            data.append(((word >> 12) & 0o077) + 0x80)
            data.append(((word >> 6) & 0o077) + 0x80)
            data.append((word & 0o077) + 0x80)
    return bytes(data)


def from_bytes_to_18bit_words(data: t.Union[bytes, bytearray], file_type: str = ASCII) -> t.List[int]:
    """
    Convert 3 bytes to 18bit words, keeping only the lower 6 bits of each byte (IMAGE)
    or 2 bytes to 18bit words (ASCII)
    """
    words = []
    if file_type == ASCII:
        for i in range(0, len(data), 2):
            words.append((data[i] << 9) | data[i + 1])
    else:
        for i in range(0, len(data), 3):
            words.append(((data[i] - 0x80) << 12) | ((data[i + 1] - 0x80) << 6) | (data[i + 2] - 0x80))
    return words


def reverse_word(w: int) -> int:
    """
    Reverse the order of bits in a 18-bit word
    (used for backward reading/writing of DECtape blocks)
    """
    w = ~w
    return (
        ((w & 0o700000) >> 15)
        | ((w & 0o070000) >> 9)
        | ((w & 0o007000) >> 3)
        | ((w & 0o000700) << 3)
        | ((w & 0o000070) << 9)
        | ((w & 0o000007) << 15)
    )


class BlockDevice18Bit(BlockDevice):
    """
    Block device for 18-bit mode
    """

    words_per_block: int

    def __init__(
        self,
        file: "AbstractFile",
        words_per_block: int = WORDS_PER_BLOCK,
    ):
        super().__init__(file)
        self.words_per_block = words_per_block

    def read_block(
        self,
        block_number: int,
        number_of_blocks: int = 1,
    ) -> bytes:
        data = bytearray()
        for i in range(block_number, block_number + number_of_blocks):
            words = self.read_words_block(block_number)
            data.extend(from_18bit_words_to_bytes(words, IMAGE))
        return bytes(data)

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
        block_number: int = block.block_number if isinstance(block, BlockDirection) else block
        direction = block.direction if isinstance(block, BlockDirection) else Direction.FORWARD
        # Read the block
        self.f.seek(block_number * self.words_per_block * BYTES_PER_WORD_18BIT)
        buffer = self.f.read(self.words_per_block * BYTES_PER_WORD_18BIT)
        if len(buffer) < self.words_per_block * BYTES_PER_WORD_18BIT:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        words = list(struct.unpack(f"{self.words_per_block}I", buffer))
        # If the direction is backward, reverse the order of words and each word
        if direction == Direction.FORWARD:
            return words
        else:  # Direction.BACKWARD
            return [reverse_word(w) for w in reversed(words)]

    def write_words_block(
        self,
        block: t.Union[int, BlockDirection],
        words: t.List[int],
    ) -> None:
        """
        Write 256 18bit words as a block
        """
        block_number: int = block.block_number if isinstance(block, BlockDirection) else block
        direction = block.direction if isinstance(block, BlockDirection) else Direction.FORWARD
        # If the direction is backward, reverse the order of words and each word
        if direction == Direction.BACKWARD:
            words = [reverse_word(w) for w in reversed(words)]
        # Write the block
        self.f.seek(block_number * self.words_per_block * BYTES_PER_WORD_18BIT)
        buffer = struct.pack(f"{self.words_per_block}I", *words)
        self.f.write(buffer)
