import errno
import typing as t

from ..abstract import AbstractBlockFilesystem, AbstractFile
from ..device.abstract import AbstractDevice
from ..device.block import BlockDevice
from ..device.rx import RXBlockDevice

__all__ = [
    "AbstractRXBlockFilesystem",
]


class AbstractRXBlockFilesystem(AbstractBlockFilesystem):
    """Abstract base class for block-based filesystems with RX01/RX02 support."""

    dev: BlockDevice  # BlockDevice or RXBlockDevice

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"]):
        if isinstance(file_or_device, AbstractFile):
            self.dev = RXBlockDevice(file_or_device)
        elif isinstance(file_or_device, BlockDevice):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, "Not a valid block device")
