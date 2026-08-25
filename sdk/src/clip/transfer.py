"""Streaming, integrity-checked Clip recording downloads."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable
import zlib

from .exceptions import ProtocolError, TransferError, TransferTimeoutError
from .models import DownloadResult, DownloadedFile, SessionDetails
from .protocol import DataFrame, FileEndFrame, FileStartFrame, TransferDoneFrame, decode_file_frame
from .transports.base import BaseTransport
from .validation import session_id

if TYPE_CHECKING:
    from .client import ClipClient

ProgressCallback = Callable[[str, int, int], None]


class FileReceiver:
    """Consumes binary frames and writes one file at a time to disk.

    A successful file is never exposed at its final path until the total byte
    count and FILE_END CRC32 both match.  UDP failures are NACKed so firmware
    can retransmit the file; BLE failures become terminal because BLE frames
    are link-layer reliable.
    """

    def __init__(
        self,
        transport: BaseTransport,
        session: str,
        output_dir: Path,
        *,
        udp: bool,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.transport = transport
        self.session_id = session_id(session)
        self.output_dir = output_dir
        self.udp = udp
        self.progress = progress
        self.done = asyncio.Event()
        self.error: Exception | None = None
        self._handle = None
        self._part_path: Path | None = None
        self._final_path: Path | None = None
        self._filename: str | None = None
        self._expected_size = 0
        self._received = 0
        self._crc32 = 0
        self._expected_sequence = 0
        self._file_invalid = False
        self._files: list[DownloadedFile] = []
        self.transferred_file_count = 0

    @property
    def files(self) -> tuple[DownloadedFile, ...]:
        return tuple(self._files)

    def feed(self, raw_frame: bytes) -> None:
        if self.error is not None or self.done.is_set():
            return
        try:
            frame = decode_file_frame(raw_frame, udp=self.udp)
            if isinstance(frame, FileStartFrame):
                self._on_file_start(frame)
            elif isinstance(frame, DataFrame):
                self._on_data(frame)
            elif isinstance(frame, FileEndFrame):
                self._on_file_end(frame)
            elif isinstance(frame, TransferDoneFrame):
                self._on_transfer_done(frame)
        except ProtocolError as exc:
            # UDP packet loss/corruption is recoverable at FILE_END: retain
            # state, discard this DATA frame, and NACK once the full-file CRC
            # arrives so firmware retransmits the file.
            if self.udp and raw_frame and raw_frame[0] == 0x01 and self._handle is not None:
                self._file_invalid = True
                return
            self._fail(TransferError(str(exc)))
        except Exception as exc:
            self._fail(exc if isinstance(exc, TransferError) else TransferError(str(exc)))

    async def wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self.done.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._close_current(remove_part=True)
            raise TransferTimeoutError(f"transfer of session {self.session_id} timed out") from exc
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        self._close_current(remove_part=True)

    def _on_file_start(self, frame: FileStartFrame) -> None:
        if self._handle is not None:
            raise TransferError("received FILE_START before previous file ended")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # `decode_file_frame` validated the logical name.  Resolve anyway so a
        # future protocol extension cannot turn a filename into path traversal.
        final_path = (self.output_dir / frame.filename).resolve()
        root = self.output_dir.resolve()
        if final_path.parent != root:
            raise TransferError("firmware supplied a filename outside the output directory")
        part_path = final_path.with_name(final_path.name + ".part")
        try:
            part_path.unlink(missing_ok=True)
            handle = part_path.open("wb")
        except OSError as exc:
            raise TransferError(f"cannot open {part_path}: {exc}") from exc
        self._handle = handle
        self._part_path = part_path
        self._final_path = final_path
        self._filename = frame.filename
        self._expected_size = frame.size
        self._received = 0
        self._crc32 = 0
        self._expected_sequence = 0
        self._file_invalid = False

    def _on_data(self, frame: DataFrame) -> None:
        if self._handle is None or self._filename is None:
            raise TransferError("received DATA without FILE_START")
        if frame.sequence != self._expected_sequence:
            self._file_invalid = True
        sequence_mask = 0x0FFF if self.udp else 0xFFFF
        self._expected_sequence = (frame.sequence + 1) & sequence_mask
        self._handle.write(frame.payload)
        self._received += len(frame.payload)
        self._crc32 = zlib.crc32(frame.payload, self._crc32) & 0xFFFFFFFF
        if self.progress is not None:
            self.progress(self._filename, self._received, self._expected_size)

    def _on_file_end(self, frame: FileEndFrame) -> None:
        if self._handle is None or self._filename is None:
            raise TransferError("received FILE_END without FILE_START")
        success = (
            not self._file_invalid
            and self._received == self._expected_size
            and self._crc32 == frame.crc32
        )
        if not success:
            self._close_current(remove_part=True)
            if self.udp:
                self.transport.send_file_ack(False)
                return
            raise TransferError("BLE file failed length, sequence, or CRC32 validation")

        assert self._handle is not None and self._part_path is not None and self._final_path is not None
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._handle = None
        os.replace(self._part_path, self._final_path)
        downloaded = DownloadedFile(
            name=self._filename,
            path=str(self._final_path),
            size_bytes=self._received,
        )
        self._files.append(downloaded)
        self._part_path = None
        self._final_path = None
        self._filename = None
        if self.udp:
            self.transport.send_file_ack(True)

    def _on_transfer_done(self, frame: TransferDoneFrame) -> None:
        if self._handle is not None:
            raise TransferError("received TRANSFER_DONE before FILE_END")
        if frame.session_id != self.session_id:
            raise TransferError(
                f"TRANSFER_DONE belongs to {frame.session_id}, not requested {self.session_id}"
            )
        self.transferred_file_count = frame.file_count
        self.done.set()

    def _close_current(self, *, remove_part: bool) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None
        if remove_part and self._part_path is not None:
            self._part_path.unlink(missing_ok=True)
        self._part_path = None
        self._final_path = None
        self._filename = None

    def _fail(self, error: Exception) -> None:
        self._close_current(remove_part=True)
        self.error = error
        self.done.set()


async def download_session(
    client: "ClipClient",
    details: SessionDetails,
    destination: Path,
    *,
    start_file: str | None = None,
    timeout: float = 300.0,
    progress: ProgressCallback | None = None,
) -> DownloadResult:
    """Download a session through an already connected client.

    Metadata is saved before transfer starts.  This makes interrupted syncs
    inspectable and permits a later resume without losing audio parameters.
    """
    output_dir = (Path(destination) / details.session_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "session_id": details.session_id,
        "files": details.files,
        "size_bytes": details.size_bytes,
        "bookmarks": details.bookmarks,
        "channels": details.channels,
        "sample_rate_hz": details.sample_rate_hz,
        "mode": details.mode,
    }
    (output_dir / "session.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    receiver = FileReceiver(
        client.transport,
        details.session_id,
        output_dir,
        udp=client.transport.uses_udp_file_frames,
        progress=progress,
    )
    client.transport.set_file_frame_handler(receiver.feed)
    try:
        await client.start_download(details.session_id, start_file=start_file)
        await receiver.wait(timeout)
    except Exception:
        if client.transport.is_connected:
            try:
                await client.cancel_download()
            except Exception:
                pass
        raise
    finally:
        client.transport.set_file_frame_handler(None)
        receiver.close()

    return DownloadResult(
        session_id=details.session_id,
        files=receiver.files,
        expected_files=receiver.transferred_file_count,
        output_dir=str(output_dir),
    )
