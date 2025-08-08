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
import typing as t

from ..abstract import AbstractBlockFilesystem, AbstractFile
from ..commons import TrackSector
from ..device.abstract import AbstractDevice
from .disk import AppleDisk

__all__ = [
    "AbstractAppleDiskFilesystem",
]


class AbstractAppleDiskFilesystem(AbstractBlockFilesystem):
    """Abstract base class for Apple filesystems"""

    dev: AppleDisk

    def __init__(self, file_or_device: t.Union["AbstractFile", "AbstractDevice"]):
        if isinstance(file_or_device, AbstractFile):
            self.dev = AppleDisk(file_or_device)
        elif isinstance(file_or_device, AppleDisk):
            self.dev = file_or_device
        else:
            raise OSError(errno.EIO, f"Invalid device type for {self.fs_description} filesystem")

    def read_sector(self, address: TrackSector) -> bytes:
        return self.dev.read_sector(address)

    def write_sector(self, buffer: t.Union[bytes, bytearray], address: TrackSector) -> None:
        self.dev.write_sector(buffer, address)
