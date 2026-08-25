"""
Unified progress display for file synchronization.

All sync tools (BLE, WiFi, CLI, Web, record.py) use SyncProgress
for consistent progress bar and speed display.
"""

import sys
import time
from typing import Optional, Callable


try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class SyncProgress:
    """
    Unified file sync progress display.

    Usage:
        >>> p = SyncProgress(total_files=30, total_bytes=1048576)
        >>> p.update("0015.opus", 3, 500000, current_file_bytes=250000, current_file_total=450000)
        >>> p.finish()

    Output format (tqdm):
        [3/30] 0015.opus | 45.2 KB/s

    Output format (fallback):
        [3/30] 0015.opus  45.2 KB/s  =========>........  56%  ETA: 12s
    """

    def __init__(self, total_files: int = 0, total_bytes: int = 0,
                 use_tqdm: bool = True, desc: str = "Sync"):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.desc = desc
        self.start_time = time.time()
        self.last_bytes = 0
        self.last_time = self.start_time
        self.current_speed = 0.0

        # tqdm progress bar
        self._use_tqdm = use_tqdm and HAS_TQDM
        self._pbar = None
        if self._use_tqdm and self.total_bytes > 0:
            try:
                self._pbar = tqdm(
                    total=self.total_bytes,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=desc,
                    leave=False,
                    ncols=80,
                    file=sys.stdout,
                )
            except Exception:
                self._use_tqdm = False

    def update(self, filename: str, file_count: int, total_bytes: int,
               current_file_bytes: int = 0, current_file_total: int = 0):
        """Update progress display.

        Args:
            filename: Name of the file being received
            file_count: Number of files received so far
            total_bytes: Total bytes received so far
            current_file_bytes: Bytes received for current file
            current_file_total: Total size of current file (0 if unknown)
        """
        now = time.time()
        elapsed = now - self.last_time

        # Calculate speed (smoothed)
        if elapsed > 0.3:
            delta = total_bytes - self.last_bytes
            if delta > 0:
                self.current_speed = delta / elapsed
            self.last_bytes = total_bytes
            self.last_time = now

        if self._pbar is not None:
            # Update tqdm
            desc_str = f"[{file_count}/{self.total_files}] {filename[:12]:<12}"
            try:
                self._pbar.set_description(desc_str, refresh=True)
                delta = total_bytes - (self._pbar.n if hasattr(self._pbar, 'n') else 0)
                if delta > 0:
                    self._pbar.update(delta)
            except Exception:
                # tqdm error, fallback to text
                self._fallback_print(filename, file_count, total_bytes,
                                     current_file_bytes, current_file_total)
        else:
            self._fallback_print(filename, file_count, total_bytes,
                                 current_file_bytes, current_file_total)

    def _fallback_print(self, filename: str, file_count: int, total_bytes: int,
                        current_file_bytes: int = 0, current_file_total: int = 0):
        """Print progress without tqdm."""
        from .utils import format_bytes, format_speed

        # Calculate percentage
        if self.total_bytes > 0:
            pct = total_bytes * 100 / self.total_bytes
        else:
            pct = 0

        # Build progress bar (40 chars wide)
        bar_width = 40
        filled = int(bar_width * pct / 100) if pct < 100 else bar_width
        bar = "=" * filled + "." * (bar_width - filled)
        if pct >= 100:
            bar = "=" * bar_width

        # ETA calculation
        if self.current_speed > 0 and self.total_bytes > 0:
            remaining_bytes = self.total_bytes - total_bytes
            if remaining_bytes > 0:
                eta = remaining_bytes / self.current_speed
                from .utils import format_duration
                eta_str = format_duration(eta)
            else:
                eta_str = "0s"
        else:
            eta_str = "--"

        # File progress (for current file)
        if current_file_total > 0:
            file_pct = current_file_bytes * 100 / current_file_total
            file_info = f" [{file_pct:.0f}%]"
        else:
            file_info = ""

        line = (f"\r  [{file_count}/{self.total_files}] {filename}  "
                f"{format_speed(self.current_speed)}  "
                f"{bar}  {pct:.0f}%  ETA: {eta_str}{file_info}")
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self, success: bool = True):
        """Mark progress as complete."""
        if self._pbar is not None:
            try:
                self._pbar.close()
            except Exception:
                pass

        if not self._use_tqdm:
            elapsed = time.time() - self.start_time
            from .utils import format_bytes, format_speed
            status = "Complete" if success else "Failed"
            avg_speed = self.last_bytes / elapsed if elapsed > 0 else 0
            print(f"\r  {status} in {elapsed:.1f}s — "
                  f"{format_bytes(self.last_bytes)}, "
                  f"avg {format_speed(avg_speed)}")
