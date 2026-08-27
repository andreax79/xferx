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

import typing as t
from ..commons import (
    ASCII,
    IMAGE,
    pairwise,
)
from ..device.block_18bit import (
    from_18bit_words_to_bytes,
    from_bytes_to_18bit_words,
)

__all__ = [
    "ascii_to_five_seven",
    "five_seven_to_ascii",
    "decode_block_format",
    "encode_block_format",
    "is_six_bit",
]

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


def encode_block_format(
    data: t.Union[bytes, bytearray], file_mode: str, words_per_block: int
) -> t.Iterator[t.List[int]]:
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
            for part in split_data(bytes(line), 256 - 6):  # TODO check with long lines
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
        for part in split_data(bytes(data), 26 * 3):
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


def is_six_bit(content: t.Union[bytes, bytearray]) -> bool:
    """
    Check if all the bytes are representable in 6 bit
    """
    return all(x < (1 << 6) for x in content)
