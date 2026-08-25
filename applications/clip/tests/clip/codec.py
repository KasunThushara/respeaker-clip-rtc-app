"""
OGG Opus encoding utilities for reSpeaker Clip.

Provides OGG Opus file creation from raw Opus frames without external dependencies.
The device sends Opus frames with 2-byte little-endian length prefix:
  [2-byte LE length][Opus frame data]...
"""

import struct
from pathlib import Path
from typing import List


# ============================================================================
# OGG CRC32 (OGG-specific polynomial 0x04C11DB7)
# ============================================================================

def _ogg_crc32_init():
    """Generate CRC32 lookup table for OGG (polynomial 0x04C11DB7)."""
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = (crc << 1) ^ 0x04C11DB7
            else:
                crc = crc << 1
            crc &= 0xFFFFFFFF
        table.append(crc)
    return table


_OGG_CRC_TABLE = _ogg_crc32_init()


def ogg_crc32(data: bytes) -> int:
    """Calculate OGG CRC32 (uses different polynomial than IEEE CRC32)."""
    crc = 0
    for byte in data:
        crc = ((crc << 8) ^ _OGG_CRC_TABLE[((crc >> 24) ^ byte) & 0xFF]) & 0xFFFFFFFF
    return crc


# ============================================================================
# Raw Opus frame parser
# ============================================================================

def parse_raw_opus_frames(raw_data: bytes) -> List[bytes]:
    """
    Parse raw Opus frames from device format.

    Device format: [2-byte LE length][Opus frame]...

    Args:
        raw_data: Raw binary data from device

    Returns:
        List of Opus frame data bytes
    """
    frames = []
    offset = 0

    # Find first valid frame (allow larger range for stereo)
    while offset < min(200, len(raw_data)):
        if offset + 2 > len(raw_data):
            break
        frame_len = struct.unpack('<H', raw_data[offset:offset + 2])[0]
        if 10 <= frame_len <= 500:  # Wider range for stereo
            break
        offset += 2

    # Parse all frames
    while offset < len(raw_data):
        if offset + 2 > len(raw_data):
            break

        frame_len = struct.unpack('<H', raw_data[offset:offset + 2])[0]
        offset += 2

        # Allow larger frames for stereo (up to ~500 bytes for 64kbps stereo)
        if frame_len < 10 or frame_len > 1000:
            break

        if offset + frame_len > len(raw_data):
            break

        frames.append(raw_data[offset:offset + frame_len])
        offset += frame_len

    return frames


# ============================================================================
# OGG Opus Writer (no external dependencies)
# ============================================================================

class OggOpusWriter:
    """
    Simple OGG Opus file writer.

    Creates a valid OGG Opus file from raw Opus packets.
    No external dependencies required.

    Opus internally runs at 48kHz; granule positions use this rate.
    """

    OPUS_INTERNAL_RATE = 48000

    def __init__(self, filename: str, sample_rate: int = 16000, channels: int = 1):
        """
        Args:
            filename: Output file path
            sample_rate: Input sample rate (written to OpusHead)
            channels: Number of audio channels (1=mono, 2=stereo)
        """
        self.file = open(filename, 'wb')
        self.sample_rate = sample_rate
        self.channels = channels
        self.serial = 0x12345678
        self.page_seq = 0
        self.granule = 0
        # Granule is in Opus internal rate (48kHz), 20ms = 960 samples
        self.frame_size = self.OPUS_INTERNAL_RATE // 50

    def _write_page(self, granule: int, header_type: int, data: bytes):
        """Write an OGG page."""
        # Build segment table
        segment_table = []
        remaining = len(data)
        while remaining > 0:
            seg_size = min(255, remaining)
            segment_table.append(seg_size)
            remaining -= seg_size

        if not segment_table:
            segment_table = [0]

        # Build page header (27 bytes + segment table)
        header = bytearray()
        header.extend(b'OggS')                      # Capture pattern (4)
        header.append(0)                             # Stream structure version (1)
        header.append(header_type)                   # Header type (1)
        header.extend(struct.pack('<Q', granule))    # Granule position (8)
        header.extend(struct.pack('<I', self.serial))  # Bitstream serial number (4)
        header.extend(struct.pack('<I', self.page_seq))  # Page sequence number (4)
        header.extend(struct.pack('<I', 0))          # CRC checksum (4) - placeholder
        header.append(len(segment_table))            # Number of page segments (1)
        header.extend(bytes(segment_table))          # Segment table (N)

        # Calculate CRC over header + data
        page_data = bytes(header) + data
        crc = ogg_crc32(page_data)

        # Insert CRC into header (at offset 22)
        struct.pack_into('<I', header, 22, crc)

        # Write complete page
        self.file.write(bytes(header) + data)
        self.page_seq += 1

    def write_header(self):
        """Write OpusHead and OpusTags pages."""
        # OpusHead packet
        opus_head = bytearray()
        opus_head.extend(b'OpusHead')        # Magic signature (8)
        opus_head.append(1)                   # Version (1)
        opus_head.append(self.channels)       # Output channel count (1)
        opus_head.extend(struct.pack('<H', 312))  # Pre-skip (2)
        opus_head.extend(struct.pack('<I', self.sample_rate))  # Input sample rate (4)
        opus_head.extend(struct.pack('<H', 0))   # Output gain (2)
        opus_head.append(0)                   # Channel mapping family (1)

        # First page: BOS (beginning of stream)
        self._write_page(0, 0x02, bytes(opus_head))

        # OpusTags packet
        opus_tags = bytearray()
        opus_tags.extend(b'OpusTags')         # Magic signature (8)
        vendor = b'reSpeaker Clip'
        opus_tags.extend(struct.pack('<I', len(vendor)))
        opus_tags.extend(vendor)
        opus_tags.extend(struct.pack('<I', 0))  # User comment list length (4)

        # Second page
        self._write_page(0, 0x00, bytes(opus_tags))

    def write_packet(self, opus_data: bytes):
        """Write an Opus audio packet."""
        self.granule += self.frame_size
        self._write_page(self.granule, 0x00, opus_data)

    def close(self):
        """Close file."""
        self.file.close()


def convert_to_ogg_opus(input_file: Path, output_file: Path,
                        sample_rate: int = 16000, channels: int = 1) -> bool:
    """
    Convert raw Opus frames to OGG Opus format.

    No external dependencies required!

    Args:
        input_file: Path to raw Opus data file
        output_file: Path to output OGG file
        sample_rate: Input sample rate in Hz
        channels: Number of audio channels

    Returns:
        True if successful, False otherwise
    """
    with open(input_file, 'rb') as f:
        raw_data = f.read()

    if len(raw_data) == 0:
        return False

    frames = parse_raw_opus_frames(raw_data)
    if not frames:
        return False

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)

        writer = OggOpusWriter(str(output_file), sample_rate, channels)
        writer.write_header()

        for frame in frames:
            writer.write_packet(frame)

        writer.close()

        duration = len(frames) * 20 / 1000  # 20ms per frame
        print(f"  Created: {output_file.name} "
              f"({_fmt_bytes(output_file.stat().st_size)}, {duration:.1f}s)")
        return True

    except Exception as e:
        print(f"  Error converting: {e}")
        return False


def _fmt_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"
