"""
File transfer handling for reSpeaker Clip device.

Provides high-level file download and session sync functionality.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any

from .client import ClipDevice
from .commands import ClipCommands
from .exceptions import TransferError, TimeoutError, StateError


class FileTransfer:
    """
    Handle file transfer operations for reSpeaker Clip.

    Provides methods for downloading individual files and syncing sessions.

    Example:
        >>> async with ClipDevice() as device:
        ...     transfer = FileTransfer(device)
        ...     await transfer.download_session("20240101_120000", Path("./downloads"))
    """

    def __init__(self, device: ClipDevice, commands: Optional[ClipCommands] = None):
        """
        Initialize file transfer handler.

        Args:
            device: Connected ClipDevice instance
            commands: Optional ClipCommands instance (will create if None)
        """
        self.device = device
        self.commands = commands or ClipCommands(device)
        self._canceled = False

    async def download_session(
        self,
        session_id: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        stop_recording: bool = False,
        continuous: bool = False,
        timeout: float = 300.0,
        start_file: Optional[str] = None,
        session_info: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Download all files from a recording session.

        Args:
            session_id: Session ID to download
            output_dir: Directory to save files
            progress_callback: Optional callback(filename, received, total)
            stop_recording: Stop recording after starting download
            continuous: Keep waiting for new files (for active recordings)
            timeout: Maximum wait time in seconds
            start_file: Optional filename to start from (e.g., "0012.opus")
            session_info: Optional pre-fetched session info (avoids redundant AT+LIST call)

        Returns:
            Dict with download results including file count and paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Clear state
        self.device._clear_file_state()
        self.device._downloading = True
        self.device._transfer_complete = False
        self._canceled = False

        # Get session info with audio format details (if not provided)
        if session_info is None:
            try:
                session_info = await self.commands.get_session_info(session_id)
            except Exception:
                # Fallback to list_sessions if get_session_info fails
                sessions = await self.commands.list_sessions()
                session_info = None
                for s in sessions:
                    if s.id == session_id:
                        session_info = s
                        break

        # Save session.json immediately (so format info is available even if sync is interrupted)
        if session_info:
            session_json = {
                "session_id": session_id,
                "mode": session_info.mode,
                "channels": session_info.channels,
                "sample_rate": session_info.sample_rate,
            }
            session_json_path = output_dir / "session.json"
            session_json_path.write_text(json.dumps(session_json, indent=2))

        # Start download
        if start_file:
            response = await self.device.send_command(f"AT+DOWNLOAD={session_id}:{start_file}")
        else:
            response = await self.device.send_command(f"AT+DOWNLOAD={session_id}")
        if not response.get("ok"):
            raise TransferError(response.get("error", "Failed to start download"))

        # Wait for download to start
        await asyncio.sleep(0.5)

        # Optionally stop recording
        if stop_recording:
            await asyncio.sleep(1.0)
            state = await self.commands.get_state()
            if state.state == "RECORDING":
                await self.commands.stop_recording()

        # Wait for files
        result = await self._wait_for_session_files(
            session_id,
            output_dir,
            progress_callback,
            continuous,
            timeout,
        )

        # Merge files (use all local .opus files to handle resume correctly)
        local_opus = list(output_dir.glob("*.opus"))
        if local_opus:
            merged_path = output_dir / f"{session_id}.opus"
            await self._merge_all_opus_files(output_dir, merged_path)
            result["merged_file"] = str(merged_path)

        # Add session.json path to result (already saved at start)
        if session_info:
            result["session_json"] = str(output_dir / "session.json")
            # Include format info in result to avoid redundant get_session_info call
            result["channels"] = session_info.channels
            result["sample_rate"] = session_info.sample_rate
            result["audio_mode"] = session_info.mode

        return result

    async def _wait_for_session_files(
        self,
        session_id: str,
        output_dir: Path,
        progress_callback: Optional[Callable[[str, int, int], None]],
        continuous: bool,
        timeout: float,
    ) -> Dict[str, Any]:
        """Wait for all session files to be received."""
        start_time = time.time()
        last_file_time = time.time()
        # In continuous mode, use longer timeout to accommodate long segment durations
        # (segment duration can be up to 300 seconds when not syncing)
        no_file_timeout = 120.0 if continuous else 300.0

        files_received = []

        while time.time() - start_time < timeout:
            await asyncio.sleep(0.5)

            # Check for cancellation
            if self._canceled:
                raise TransferError("Transfer canceled")

            # Check for completed files
            for filename, data in list(self.device._session_files.items()):
                if filename not in [f["name"] for f in files_received]:
                    # Save file
                    file_path = output_dir / filename

                    # Skip if already exists with same size
                    if file_path.exists():
                        existing_size = file_path.stat().st_size
                        if existing_size == len(data):
                            files_received.append({
                                "name": filename,
                                "path": str(file_path),
                                "size": len(data),
                            })
                            last_file_time = time.time()

                            if progress_callback:
                                total_size = sum(f["size"] for f in files_received)
                                progress_callback(filename, len(files_received), total_size)
                            continue

                    # File doesn't exist or size differs, write it
                    file_path.write_bytes(data)
                    files_received.append({
                        "name": filename,
                        "path": str(file_path),
                        "size": len(data),
                    })
                    last_file_time = time.time()
                    start_time = time.time()  # Reset timeout when receiving files

                    if progress_callback:
                        total_size = sum(f["size"] for f in files_received)
                        progress_callback(filename, len(files_received), total_size)

            # Check if transfer is complete (check device flag, not FileTransfer flag)
            if self.device._transfer_complete:
                # Before breaking, check one more time for any pending files
                for filename, data in list(self.device._session_files.items()):
                    if filename not in [f["name"] for f in files_received]:
                        # Save file
                        file_path = output_dir / filename

                        # Skip if already exists with same size
                        if file_path.exists():
                            existing_size = file_path.stat().st_size
                            if existing_size == len(data):
                                files_received.append({
                                    "name": filename,
                                    "path": str(file_path),
                                    "size": len(data),
                                })
                                last_file_time = time.time()

                                if progress_callback:
                                    total_size = sum(f["size"] for f in files_received)
                                    progress_callback(filename, len(files_received), total_size)
                                continue

                        # File doesn't exist or size differs, write it
                        file_path.write_bytes(data)
                        files_received.append({
                            "name": filename,
                            "path": str(file_path),
                            "size": len(data),
                        })
                        last_file_time = time.time()

                        if progress_callback:
                            total_size = sum(f["size"] for f in files_received)
                            progress_callback(filename, len(files_received), total_size)
                break

            # Exit conditions
            if not continuous:
                # Non-continuous mode: exit after timeout with no new files
                if time.time() - last_file_time > no_file_timeout:
                    break
            # Continuous mode: only exit on transfer_complete from device
            # (device sets _transfer_complete when recording stops)

        # Final check for any remaining files before returning
        for filename, data in list(self.device._session_files.items()):
            if filename not in [f["name"] for f in files_received]:
                # Save file
                file_path = output_dir / filename

                # Skip if already exists with same size
                if file_path.exists():
                    existing_size = file_path.stat().st_size
                    if existing_size == len(data):
                        files_received.append({
                            "name": filename,
                            "path": str(file_path),
                            "size": len(data),
                        })
                        continue

                # File doesn't exist or size differs, write it
                file_path.write_bytes(data)
                files_received.append({
                    "name": filename,
                    "path": str(file_path),
                    "size": len(data),
                })

        # Fetch bookmarks after all files are downloaded and save as JSON
        bookmarks = []
        bookmarks_path = output_dir / "bookmarks.json"
        try:
            bookmarks = await self.commands.get_bookmarks(session_id)
        except Exception as e:
            # Don't fail sync if bookmarks fetch fails
            pass

        # Always create bookmarks.json (empty if no bookmarks)
        # Simplified format: only offset in seconds
        bookmarks_data = [
            {"offset": b.offset}
            for b in bookmarks
        ]
        bookmarks_path.write_text(json.dumps(bookmarks_data, indent=2))

        return {
            "session_id": session_id,
            "files": files_received,
            "total_size": sum(f["size"] for f in files_received),
            "file_count": len(files_received),
            "bookmarks": bookmarks,
            "bookmarks_path": str(bookmarks_path),
        }

    async def _merge_opus_files(self, files: List[Dict], output_path: Path) -> None:
        """
        Merge Opus files into single file.

        Args:
            files: List of file dicts with 'path' key
            output_path: Output file path
        """
        # Sort by filename (should be 0001.opus, 0002.opus, etc.)
        sorted_files = sorted(files, key=lambda f: f["name"])

        with open(output_path, "wb") as outfile:
            for file_info in sorted_files:
                file_path = Path(file_info["path"])
                if file_path.exists():
                    outfile.write(file_path.read_bytes())

    async def _merge_all_opus_files(self, output_dir: Path, output_path: Path) -> None:
        """Merge all .opus files in output_dir (for resume: includes pre-existing files)."""
        opus_files = sorted(output_dir.glob("*.opus"), key=lambda f: f.name)
        with open(output_path, "wb") as outfile:
            for f in opus_files:
                outfile.write(f.read_bytes())

    async def cancel(self) -> None:
        """Cancel the current transfer."""
        self._canceled = True
        try:
            await self.commands.cancel_transfer()
        except Exception:
            pass


class SessionSync(FileTransfer):
    """
    Enhanced session synchronization with resume support.

    Provides intelligent sync that:
    - Detects existing local files
    - Resumes from last downloaded file
    - Deletes sessions from device after successful sync
    - Shows progress with optional tqdm integration

    Example:
        >>> async with ClipDevice() as device:
        ...     sync = SessionSync(device)
        ...     await sync.sync("20240101_120000", Path("./downloads"))
    """

    def __init__(self, device: ClipDevice, commands: Optional[ClipCommands] = None):
        super().__init__(device, commands)

    async def sync(
        self,
        session_id: str,
        output_dir: Path,
        delete_after: bool = False,
        continuous: bool = False,
        force: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        session_info: Optional[Any] = None,
        start_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sync a session with resume support.

        Args:
            session_id: Session ID to sync
            output_dir: Directory to save files
            delete_after: Delete session from device after successful sync
            continuous: Keep waiting for new files
            force: Force re-sync from beginning (ignore synced status)
            progress_callback: Optional callback(filename, file_count, total_size)
            session_info: Optional pre-fetched session info (avoids redundant AT+LIST call)
            start_file: Override start file (e.g., "0015.opus"), ignores auto-detected resume

        Returns:
            Dict with sync results
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check for existing files
        existing_files = sorted(output_dir.glob("*.opus"))

        # Get session info from device (includes synced_files count)
        # Use provided session_info if available to avoid redundant AT+LIST call
        if session_info is None:
            try:
                session_info = await self.commands.get_session_info(session_id)
            except Exception:
                # Fallback to list_sessions if get_session_info fails
                sessions = await self.commands.list_sessions()
                for s in sessions:
                    if s.id == session_id:
                        session_info = s
                        break

        if session_info:
            total_files = session_info.files
            synced_files = getattr(session_info, 'synced_files', 0)
        else:
            total_files = 0
            synced_files = 0

        # Check if already synced (all files exist locally)
        # Skip this check in continuous mode or when force=True - always check for new files
        # Do this check BEFORE calculating start_file to avoid incorrect resumption
        if not force and not continuous and total_files > 0 and synced_files >= total_files:
            merged_path = output_dir / f"{session_id}.opus"
            result = {
                "session_id": session_id,
                "files": [{"name": f.name, "path": str(f), "size": f.stat().st_size}
                         for f in existing_files],
                "file_count": len(existing_files),
                "total_size": sum(f.stat().st_size for f in existing_files),
                "status": "already_synced",
            }
            if merged_path.exists():
                result["merged_file"] = str(merged_path)
            else:
                # Need to merge files even if already synced
                await self._merge_all_opus_files(output_dir, merged_path)
                if merged_path.exists():
                    result["merged_file"] = str(merged_path)
            # Delete from device if requested (even for already-synced sessions)
            if delete_after and not continuous:
                try:
                    await self.commands.delete_session(session_id)
                except Exception:
                    pass
            return result

        # Determine start file based on synced_files from device
        # If force=True or start_file override provided, ignore synced_files
        if start_file is None and not force and synced_files > 0 and synced_files < total_files:
            # Start from the file after the last synced file
            next_num = synced_files + 1
            start_file = f"{next_num:04d}.opus"
        elif start_file is None and existing_files:
            # Fallback: check local files if device doesn't have synced info
            # Only accept NNNN.opus format (4-digit sequential files)
            import re
            for f in reversed(existing_files):
                match = re.match(r'^(\d{4})$', f.stem)
                if match:
                    last_num = int(match.group(1))
                    next_num = last_num + 1
                    # Validate against total_files to prevent requesting non-existent files
                    if total_files > 0 and next_num > total_files:
                        # All files already synced, skip this session
                        break
                    start_file = f"{next_num:04d}.opus"
                    break

        # Log sync info (use logging to avoid interfering with progress bar)
        import logging
        logger = logging.getLogger(__name__)
        if force:
            logger.info(f"Force re-sync from beginning ({total_files} files total)")
        elif start_file:
            logger.debug(f"Resuming from: {start_file} (synced: {synced_files}/{total_files})")
        else:
            logger.debug(f"Starting from beginning ({total_files} files total)")

        # Download with merge (start_file is calculated above)
        # In continuous mode, use a very long timeout since recording may be long
        # Pass session_info to avoid redundant AT+LIST call
        result = await self.download_session(
            session_id,
            output_dir,
            progress_callback=progress_callback,
            continuous=continuous,
            start_file=start_file,
            timeout=86400.0 if continuous else 300.0,  # 24 hours for continuous, 5 min otherwise
            session_info=session_info,
        )

        # Delete from device if requested
        # Note: In continuous mode, recording is still active so we should not delete
        if delete_after and not continuous and result["file_count"] > 0:
            try:
                await self.commands.delete_session(session_id)
            except Exception:
                pass

        return result

    async def sync_all(
        self,
        output_dir: Path,
        delete_after: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sync all sessions from device.

        Args:
            output_dir: Base directory for downloads
            delete_after: Delete sessions after successful sync
            progress_callback: Optional callback(filename, file_count, total_size)

        Returns:
            List of sync results for each session
        """
        sessions = await self.commands.list_sessions()
        results = []

        for session in sessions:
            session_dir = output_dir / session.id
            try:
                result = await self.sync(
                    session.id,
                    session_dir,
                    delete_after,
                    continuous=False,
                    progress_callback=progress_callback,
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "session_id": session.id,
                    "error": str(e),
                    "status": "failed",
                })

        return results
