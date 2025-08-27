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

import sys
import traceback
import typing as t
from datetime import date
from pathlib import Path

from .abstract import AbstractDirectoryEntry, AbstractFile, AbstractFilesystem
from .apple2.appledosfs import AppleDOSFilesystem
from .apple2.pascalfs import PascalFilesystem
from .apple2.prodosfs import ProDOSFilesystem
from .commons import ASCII, DECTAPE, DECTAPE_EXT, splitdrive
from .native import NativeFilesystem
from .nova.dgdosdumpfs import DGDOSDumpFilesystem
from .nova.dgdosfs import DGDOSFilesystem
from .nova.dgdosmagtapefs import DGDOSMagTapeFilesystem
from .pdp7.decsysfs import DECSysFilesystem
from .pdp7.unix0fs import UNIX0Filesystem
from .pdp8.cos300fs import COS300Filesystem
from .pdp8.dmsfs import DMSFilesystem
from .pdp8.os8fs import OS8Filesystem
from .pdp8.tss8fs import TSS8Filesystem
from .pdp11.caps11fs import CAPS11Filesystem
from .pdp11.dos11fs import DOS11Filesystem
from .pdp11.dos11magtapefs import DOS11MagTapeFilesystem
from .pdp11.files11fs import Files11Filesystem
from .pdp11.rstsfs import RSTSFilesystem
from .pdp11.rt11fs import RT11Filesystem
from .pdp11.solofs import SOLOFilesystem
from .pdp15.adssfs import ADSSFilesystem
from .pdp15.dos15fs import DOS15Filesystem
from .unix.unix1fs import UNIX1Filesystem
from .unix.unix4fs import UNIX4Filesystem
from .unix.unix5fs import UNIX5Filesystem
from .unix.unix6fs import UNIX6Filesystem
from .unix.unix7fs import UNIX7Filesystem

__all__ = [
    "Volumes",
    "DEFAULT_VOLUME",
    "FILESYSTEMS",
]

DEFAULT_VOLUME = "DK"
SYSTEM_VOLUME = "SY"
FILESYSTEMS: t.Dict[str, t.Type[AbstractFilesystem]] = {
    "caps11": CAPS11Filesystem,
    "caps8": CAPS11Filesystem,
    "dos11": DOS11Filesystem,
    "dos11mt": DOS11MagTapeFilesystem,
    "files11": Files11Filesystem,
    "rt11": RT11Filesystem,
    "solo": SOLOFilesystem,
    "unix0": UNIX0Filesystem,
    "unix1": UNIX1Filesystem,
    "unix4": UNIX4Filesystem,
    "unix5": UNIX5Filesystem,
    "unix6": UNIX6Filesystem,
    "unix7": UNIX7Filesystem,
    "rsts": RSTSFilesystem,
    "os8": OS8Filesystem,
    "dms": DMSFilesystem,
    "tss8": TSS8Filesystem,
    "cos300": COS300Filesystem,
    "cos310": COS300Filesystem,
    "adss": ADSSFilesystem,
    "dos15": DOS15Filesystem,
    "prodos": ProDOSFilesystem,
    "pascal": PascalFilesystem,
    "appledos": AppleDOSFilesystem,
    "decsys": DECSysFilesystem,
    "dgdos": DGDOSFilesystem,
    "dgdosmt": DGDOSMagTapeFilesystem,
    "dgdosdump": DGDOSDumpFilesystem,
}


class Volumes(object):
    """
    Logical Device Names

    SY: System volume, the device from which this program was started
    DK: Default storage volume (initially the same as SY:)
    """

    volumes: t.Dict[str, AbstractFilesystem]  # volume id -> fs
    logical: t.Dict[str, str]  # local id -> volume id
    defdev: str  # Default device, DK

    def __init__(self) -> None:
        self.volumes: t.Dict[str, AbstractFilesystem] = {}
        self.logical: t.Dict[str, str] = {}
        if self._drive_letters():
            # windows
            for letter in self._drive_letters():
                # Add all available drive letters as native filesystems
                try:
                    self.volumes[letter] = NativeFilesystem(Path(f"{letter.upper()}:\\"))
                    self.volumes[letter].target = letter
                    self.volumes[letter].source = letter
                except Exception:
                    pass
            cwd = Path.cwd()
            is_unc = cwd.root == "\\"
            if not is_unc:
                current_drive = cwd.drive.split(":", 1)[0].upper()
            else:
                # Add a special volume for UNC paths
                self.volumes["UNC"] = NativeFilesystem(cwd)
                self.volumes["UNC"].source = cwd.anchor
                self.volumes["UNC"].target = "UNC"
                current_drive = "UNC"
            self.logical[SYSTEM_VOLUME] = current_drive
            self.defdev = current_drive
        else:
            # posix
            self.volumes["N"] = NativeFilesystem()
            self.volumes["N"].source = "/"
            self.volumes["N"].target = "N"
            self.logical[SYSTEM_VOLUME] = "N"
            self.defdev = SYSTEM_VOLUME

    def _drive_letters(self) -> list[str]:
        """
        Get the list of available drive letters on Windows
        """
        try:
            import string
            from ctypes import windll  # type: ignore

            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for c in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(c)
                bitmask >>= 1
            return drives
        except Exception:
            return []

    def canonical_volume(self, volume_id: str, cmd: str = "KMON") -> str:
        """
        Convert a volume id into canonical form
        """
        if not volume_id:
            volume_id = DEFAULT_VOLUME
        else:
            volume_id = volume_id.upper()
            if volume_id.endswith(":"):
                volume_id = volume_id[:-1]
        return volume_id

    def get_volume(self, volume_id: str, cmd: str = "KMON") -> AbstractFilesystem:
        """
        Get a filesystem by volume id
        """
        volume_id = self.canonical_volume(volume_id, cmd=cmd)
        if volume_id == DEFAULT_VOLUME:
            volume_id = self.defdev
        volume_id = self.logical.get(volume_id, volume_id)
        try:
            return self.volumes[volume_id]
        except KeyError:
            raise Exception(f"?{cmd}-F-Illegal volume {volume_id}:")

    def chdir(self, path: str) -> bool:
        """
        Change current directory
        """
        volume_id, fullname = splitdrive(path)
        volume_id = self.canonical_volume(volume_id)
        try:
            fs = self.get_volume(volume_id)
        except Exception:
            return False
        if fullname and not fs.chdir(fullname):
            return False
        if volume_id != DEFAULT_VOLUME:
            self.set_default_volume(volume_id)
        return True

    def get_pwd(self) -> str:
        """
        Get current volume and directory
        """
        try:
            pwd = self.get_volume(self.defdev).get_pwd()
            return f"{self.defdev}:{pwd}"
        except Exception:
            return f"{self.defdev}:???"

    def set_default_volume(self, volume_id: str, cmd: str = "KMON") -> None:
        """
        Set the default volume
        """
        volume_id = self.canonical_volume(volume_id, cmd=cmd)
        if volume_id != DEFAULT_VOLUME:
            self.get_volume(volume_id, cmd=cmd)
            self.defdev = volume_id

    def assign(self, volume_id: str, logical: str, verbose: bool = False, cmd: str = "KMON") -> None:
        """
        Associate a logical device name with a device
        """
        volume_id = self.canonical_volume(volume_id)
        volume_id = self.logical.get(volume_id, volume_id)
        logical = self.canonical_volume(logical)
        if logical == DEFAULT_VOLUME:
            self.set_default_volume(volume_id, cmd=cmd)
        else:
            self.get_volume(volume_id, cmd=cmd)
            self.logical[logical] = volume_id

    def deassign(self, volume_id: str, verbose: bool = False, cmd: str = "KMON") -> None:
        """
        Removes logical device name assignments
        """
        volume_id = self.canonical_volume(volume_id)
        if volume_id == DEFAULT_VOLUME or not volume_id in self.logical:
            raise Exception(f"?{cmd}-W-Logical name not found {volume_id}:")
        del self.logical[volume_id]

    def mount(
        self,
        path: str,
        logical: str,
        fstype: t.Optional[str] = None,
        device_type: t.Optional[str] = None,
        verbose: bool = False,
        cmd: str = "MOUNT",
    ) -> None:
        """
        Mount a file to a logical disk unit
        """
        logical = self.canonical_volume(logical)
        if logical == DEFAULT_VOLUME or not logical:
            raise Exception(f"?{cmd}-F-Illegal volume {logical}:")
        volume_id, fullname = splitdrive(path)
        fs = self.get_volume(volume_id, cmd=cmd)
        kwargs: t.Dict[str, t.Union[bool, str]] = {}
        device_type = device_type or self.guess_device_type(fullname)
        if device_type:
            kwargs["device_type"] = device_type
        try:
            filesystem = FILESYSTEMS.get(fstype or "rt11", RT11Filesystem)
            entry = fs.get_file_entry(fullname)
            self.volumes[logical] = filesystem.mount(entry.open(), **kwargs)
            self.volumes[logical].target = logical
            self.volumes[logical].source = f"{volume_id}:{entry.fullname}"
            sys.stdout.write(f"?{cmd}-I-Disk {path} mounted to {logical}:\n")
        except Exception as ex:
            if verbose:
                traceback.print_exc()
            message = getattr(ex, "strerror", "") or str(ex)
            raise Exception(f"?{cmd}-F-Error mounting {path} to {logical}: {message}\n")

    def dismount(self, volume_id: str, cmd: str = "DISMOUNT") -> None:
        """
        Disassociates a logical disk assignment from a file
        """
        volume_id = self.canonical_volume(volume_id)
        if volume_id == DEFAULT_VOLUME:
            raise Exception(f"?{cmd}-F-Illegal volume {volume_id}:")
        try:
            fs = self.get_volume(volume_id, cmd=cmd)
        except Exception:
            raise Exception(f"?{cmd}-F-Illegal volume {volume_id}:")
        self.volumes = {k: v for k, v in self.volumes.items() if v != fs}

    def guess_device_type(self, path: str) -> t.Optional[str]:
        """
        Guess the filesystem type based on the file extension
        """
        path = path.lower()
        try:
            _, extension = path.split(".", 1)
        except Exception:
            return None
        if extension in DECTAPE_EXT:
            return DECTAPE
        return None

    def initialize(
        self, target: str, options: t.Dict[str, t.Union[str, bool]], cmd: str = "INITIALIZE"
    ) -> "AbstractFilesystem":
        """
        Initialize a filesystem
        """
        fs = self.get_volume(target, cmd=cmd)
        return fs.initialize(fs.dev, **options)

    def filter_entries_list(
        self, pattern: str, include_all: bool = False, expand: bool = True, cmd: str = "KMON"
    ) -> t.Iterator["AbstractDirectoryEntry"]:
        """
        Filter directory entries based on a pattern
        """
        volume_id, pattern = splitdrive(pattern)
        fs = self.get_volume(volume_id, cmd=cmd)
        yield from fs.filter_entries_list(pattern=pattern, include_all=include_all, expand=expand)

    def get_file_entry(self, fullname: str, cmd: str = "KMON") -> "AbstractDirectoryEntry":
        """
        Get the directory entry for a file
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.get_file_entry(fullname)

    def write_bytes(
        self,
        fullname: str,
        content: t.Union[bytes, bytearray],
        creation_date: t.Optional[date] = None,
        file_type: t.Optional[str] = None,
        file_mode: t.Optional[str] = None,
        cmd: str = "KMON",
    ) -> None:
        """
        Write content to a file
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.write_bytes(
            fullname=fullname, content=content, creation_date=creation_date, file_type=file_type, file_mode=file_mode
        )

    def create_file(
        self,
        fullname: str,
        number_of_blocks: int,
        creation_date: t.Optional[date] = None,
        file_type: t.Optional[str] = None,
        cmd: str = "CREATE",
    ) -> t.Optional["AbstractDirectoryEntry"]:
        """
        Create a new file with a given length in number of blocks
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.create_file(
            fullname=fullname, number_of_blocks=number_of_blocks, creation_date=creation_date, file_type=file_type
        )

    def create_directory(
        self,
        fullname: str,
        options: t.Dict[str, t.Union[str, bool]],
        cmd: str = "CREATE",
    ) -> t.Optional["AbstractDirectoryEntry"]:
        """
        Create a new directory
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.create_directory(fullname=fullname, options=options)

    def isdir(self, fullname: str, cmd: str) -> bool:
        """
        Check if the given path is a directory
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.isdir(fullname)

    def dir(self, pattern: str, options: t.Dict[str, bool], cmd: str = "DIR") -> None:
        """
        List directory contents
        """
        volume_id, pattern = splitdrive(pattern)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.dir(volume_id, pattern, options)

    def examine(self, arg: str, options: t.Dict[str, t.Union[bool, str]], cmd: str = "EXAMINE") -> None:
        """
        Examine the filesystem
        """
        volume_id, fullname = splitdrive(arg)
        fs = self.get_volume(volume_id, cmd=cmd)
        fs.examine(fullname, options)

    def exists(self, fullname: str, cmd: str = "KMON") -> bool:
        """
        Check if the given path exists
        """
        try:
            volume_id, fullname = splitdrive(fullname)
            fs = self.get_volume(volume_id, cmd=cmd)
            fs.get_file_entry(fullname)
            return True
        except FileNotFoundError:
            return False

    def open_file(self, fullname: str, file_mode: t.Optional[str] = None, cmd: str = "KMON") -> "AbstractFile":
        """
        Open a file
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        entry = fs.get_file_entry(fullname)
        return entry.open(file_mode)

    def read_bytes(self, fullname: str, file_mode: t.Optional[str] = None, cmd: str = "KMON") -> bytes:
        """
        Get the content of a file
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.read_bytes(fullname=fullname, file_mode=file_mode)

    def read_text(
        self, fullname: str, encoding: str = "ascii", errors: str = "ignore", file_mode: str = ASCII, cmd: str = "KMON"
    ) -> str:
        """
        Get the content of a file as text
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.read_text(fullname=fullname, encoding=encoding, errors=errors, file_mode=file_mode)

    def dump(
        self, fullname: str, start: t.Optional[int] = None, end: t.Optional[int] = None, cmd: str = "DUMP"
    ) -> None:
        """
        Dump the content of a file or a range of blocks
        """
        volume_id, fullname = splitdrive(fullname)
        fs = self.get_volume(volume_id, cmd=cmd)
        fs.dump(fullname=fullname, start=start, end=end)

    def get_types(self, cmd: str, volume_id: str) -> t.List[str]:
        """
        Get the list of the supported file types
        """
        fs = self.get_volume(volume_id, cmd=cmd)
        return fs.get_types()


#     def read_block(
#         self,
#         block_number: int,
#         number_of_blocks: int = 1,
#     ) -> bytes:
#         return fd.read_block(block_number, number_of_blocks)
#
#     def write_block(
#         self,
#         buffer: t.Union[bytes, bytearray],
#         block_number: int,
#         number_of_blocks: int = 1,
#     ) -> None:
#         fs.write_block(buffer, block_number, number_of_blocks)
