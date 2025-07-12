import typing
from collections import OrderedDict

if typing.TYPE_CHECKING:
    from .device.block import BlockDevice

__all__ = [
    "BlockCache",
]

DEFAULT_CACHE_SIZE = 1024  # 1024 blocks


class BlockCache:
    dev: "BlockDevice"
    cache: OrderedDict[int, bytes]
    max_size: int

    def __init__(self, dev: "BlockDevice", max_size: int = DEFAULT_CACHE_SIZE):
        self.dev = dev
        self.cache = OrderedDict()
        self.max_size = max_size

    def read_block(self, block_number: int = 0) -> bytes:
        if block_number in self.cache:
            # Mark the block as most recently used
            self.cache.move_to_end(block_number)
            return self.cache[block_number]

        block_data = self.dev.read_block(block_number)
        self.cache[block_number] = block_data
        # Mark the block as most recently used
        self.cache.move_to_end(block_number)

        # If cache exceeds max_size, remove the least recently used item
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

        return block_data

    def write_block(self, buffer: bytes, block_number: int) -> None:
        self.dev.write_block(buffer, block_number)
        self.cache[block_number] = buffer
        self.cache.move_to_end(block_number)

        # If cache exceeds max_size, remove the least recently used item
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
