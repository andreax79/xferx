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
import struct
import sys
import typing as t

from .commons import TrackSector, hex_dump
from .native import NativeFile

if t.TYPE_CHECKING:
    from .abstract import AbstractFile

___all__ = [
    "IMDDiskImage",
    "IMDTrack",
    "IMDSector",
]

# ImageDisk, A Diskette Imaging program for Soft-Sector Formats, Pag 26
# https://oldcomputers-ddns.org/public/pub/manuals/imd.pdf

EOF = 0x1A  # End of file marker in IMD files
TRACK_HEADER_FORMAT = "BBBBB"
TRACK_HEADER_SIZE = struct.calcsize(TRACK_HEADER_FORMAT)

SECTOR_HEAD_MAP = 0x40  # Bit indicating presence of sector head map
SECTOR_CYLINDER_MAP = 0x80  # Bit indicating presence of sector cylinder map

# Sector Data Record Type
UNAVAILABLE = 0  # Sector data unavailable - could not be read
NORMAL = 1  # Normal data: (Sector Size) bytes follow
COMPRESSED = 2  # Compressed: All bytes in sector have same value (xx)
DELETED = 3  # Normal data with "Deleted-Data address mark"
DELETED_COMPRESSED = 4  # Compressed with "Deleted-Data address mark"
DATA_ERROR = 5  # Normal data read with data error
DATA_ERROR_COMPRESSED = 6  # Compressed read with data error
DATA_ERROR_DELETED = 7  # Deleted data read with data error
DATA_ERROR_DELETED_COMPRESSED = 8  # Compressed, Deleted read with data error

RECORD_TYPES = {
    UNAVAILABLE: "Unavailable",
    NORMAL: "Normal",
    COMPRESSED: "Compressed",
    DELETED: "Deleted",
    DELETED_COMPRESSED: "Deleted, Compressed",
    DATA_ERROR: "Data Error",
    DATA_ERROR_COMPRESSED: "Data Error, Compressed",
    DATA_ERROR_DELETED: "Data Error, Deleted",
    DATA_ERROR_DELETED_COMPRESSED: "Data Error, Deleted, Compressed",
}


class IMDSector:
    """
    Sector Data Record

    +---------------------------------------+
    | Sector Data Record Type               |  1 byte
    +---------------------------------------+
    | Data                                  |  record_size - 1 bytes
    /                                       /
    |                                       |
    +---------------------------------------+

    """

    track: "IMDTrack"  # Reference to the track this sector belongs to
    record_type: int  # Type of the record
    record_size: int  # Record size in bytes, including the record type byte
    data: bytes  # The actual data of the sector

    def __init__(self, track: "IMDTrack") -> None:
        self.track = track
        self.record_type = 0
        self.record_size = 0
        self.data = b""

    @classmethod
    def read(cls, track: "IMDTrack", buffer: bytes, position: int) -> "IMDSector":
        self = cls(track)
        self.record_type = int(buffer[position])
        # Determine the size of the record based on its type
        if self.record_type == UNAVAILABLE:
            # 1 byte for the record type, no data
            self.record_size = 1 + 0
            self.data = b""
        elif self.record_type in (
            COMPRESSED,
            DELETED_COMPRESSED,
            DATA_ERROR_COMPRESSED,
            DATA_ERROR_DELETED_COMPRESSED,
        ):
            # 1 byte for the record type, 1 byte for compressed data
            self.record_size = 1 + 1
            tmp = buffer[position + 1]
            self.data = bytes([tmp] * track.sector_size)  # Fill with the compressed value
        else:
            # 1 byte for the record type, sector_size bytes for data
            self.record_size = 1 + track.sector_size
            self.data = buffer[position + 1 : position + self.record_size]
        return self

    def __str__(self) -> str:
        return f"{self.record_size:5} bytes {RECORD_TYPES[self.record_type]}"


class IMDTrack:
    """
    Track
    ImageDisk, A Diskette Imaging program for Soft-Sector Formats, Pag 26
    https://oldcomputers-ddns.org/public/pub/manuals/imd.pdf

    +---------------------------------------+
    |  Mode value (0-5)                     |   1 byte
    +---------------------------------------+
    |  Cylinder (0-n)                       |   1 byte
    +---------------------------------------+
    |  SCM  |  SHM  | Head (0-1)            |   1 byte
    +---------------------------------------+
    |  Number of sectors in track (1-n)     |   1 byte
    +---------------------------------------+
    |  Sector size (0-6)                    |   1 byte
    +---------------------------------------+
    |  Sector numbering map                 |   sectors_per_track bytes
    /                                       /
    +---------------------------------------+
    |  Sector cylinder map (optional)       |   sectors_per_track bytes (if present)
    /                                       /
    +---------------------------------------+
    |  Sector head map (optional)           |   sectors_per_track bytes (if present)
    /                                       /
    +---------------------------------------+
    |  Sector data records                  |   variable length
    /                                       /
    +---------------------------------------+

    """

    disk: "IMDDiskImage"  # Reference to the disk image
    mode: int  # Data transfer rate and density
    cylinder: int  # Cylinder number
    head: int  # Head number (0 or 1)
    sectors_per_track: int  # Number of sectors in this track
    sector_size: int  # Size of each sector in bytes
    sector_numbering_map: t.List[int]  # Map of sector numbers
    sector_cylinder_map: t.Optional[t.List[int]]  # Sector cylinder map
    sector_head_map: t.Optional[t.List[int]]  # Sector head map
    sector_data_records: t.List["IMDSector"]  # Sector data records
    track_size: int  # Size of the track in bytes

    def __init__(self, disk: "IMDDiskImage") -> None:
        self.disk = disk
        self.mode = 0
        self.cylinder = 0
        self.head = 0
        self.sectors_per_track = 0
        self.sector_size = 0
        self.sector_numbering_map = []
        self.sector_cylinder_map = None
        self.sector_head_map = None
        self.sector_data_records = []

    @classmethod
    def read(cls, disk: "IMDDiskImage", buffer: bytes, position: int) -> "IMDTrack":
        initial_position = position
        self = cls(disk)
        (
            self.mode,
            self.cylinder,
            raw_head,
            self.sectors_per_track,
            raw_sector_size,
        ) = struct.unpack_from(TRACK_HEADER_FORMAT, buffer, position)
        self.head = raw_head & 0x01
        self.sector_size = 1 << (7 + raw_sector_size)
        position += TRACK_HEADER_SIZE
        # Read sector numbering map
        self.sector_numbering_map = list(buffer[position : position + self.sectors_per_track])
        position += self.sectors_per_track
        # Read optional sector cylinder map
        if raw_head & SECTOR_CYLINDER_MAP:
            self.sector_cylinder_map = list(buffer[position : position + self.sectors_per_track])
            position += self.sectors_per_track
        # Read optional sector head map
        if raw_head & SECTOR_HEAD_MAP:
            self.sector_head_map = list(buffer[position : position + self.sectors_per_track])
            position += self.sectors_per_track
        # Read sector data records
        for _ in range(self.sectors_per_track):
            sector_record = IMDSector.read(self, buffer, position)
            position += sector_record.record_size
            self.sector_data_records.append(sector_record)
        # Calculate the size of the track
        self.track_size = position - initial_position
        return self


class IMDDiskImage:
    """
    Represents an IMD disk image

    ImageDisk, A Diskette Imaging program for Soft-Sector Formats, Pag 26
    https://oldcomputers-ddns.org/public/pub/manuals/imd.pdf

    The overall layout of an ImageDisk .IMD image file is:

    +---------------------------------------+
    | IMD v.vv: dd/mm/yyyy hh:mm:ss         |  ASCII Header
    | Comment (ASCII only)                  |  variable length
    +---------------------------------------+
    | EOF (0x1A) byte                       |  1 byte
    +---------------------------------------+
    | Tracks Data                           |
    | ...                                   |
    /                                       /
    |                                       |
    +---------------------------------------+

    """

    f: "AbstractFile"  # File object representing the disk image
    ascii_header: str  # ASCII header of the disk image
    tracks: list["IMDTrack"]  # List of tracks in the disk image

    def __init__(self, file: "AbstractFile") -> None:
        self.f = file
        self.ascii_header = ""
        self.tracks = []

        buffer = self.f.read()
        try:
            ascii_header, track_data = buffer.split(bytes([EOF]), 1)
        except Exception:
            raise OSError(errno.EIO, "Invalid IMD file format: Missing EOF marker")
        if not ascii_header.startswith(b"IMD "):
            raise OSError(errno.EIO, "Invalid IMD file format: Missing 'IMD' header")
        self.ascii_header = ascii_header.decode("ascii")
        # Read the tracks data
        position = 0
        while position < len(track_data):
            track = IMDTrack.read(self, track_data, position)
            position += track.track_size
            self.tracks.append(track)

    def read_sector(self, address: TrackSector) -> bytes:
        """
        Read a sector from the disk image
        """
        track = self.tracks[address.track]
        sector_index = track.sector_numbering_map[address.sector]
        sector = track.sector_data_records[sector_index]
        return sector.data


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python imd.py <path_to_imd_file> [track sector]")
        sys.exit(1)
    file = NativeFile(sys.argv[1])
    disk = IMDDiskImage(file)
    if len(sys.argv) >= 4:
        track_number = int(sys.argv[2])
        sector_number = int(sys.argv[3])
        address = TrackSector(track=track_number, sector=sector_number)
        try:
            data = disk.read_sector(address)
            print(f"Data from track {track_number}, sector {sector_number}")
            hex_dump(data)
        except IndexError:
            print(f"Invalid track {track_number} or sector {sector_number}.")
    else:
        print(f"Loaded IMD disk image with {len(disk.tracks)} tracks.")
        print(f"{disk.ascii_header}")
        for i, track in enumerate(disk.tracks):
            print(
                f"Track {i}: Mode={track.mode}, Cylinder={track.cylinder}, Head={track.head}, "
                f"Sectors={track.sectors_per_track}, Sector Size={track.sector_size} bytes"
            )
            for j, sector in enumerate(track.sector_data_records):
                print(f"  Sector {j:3}:  {sector}")
