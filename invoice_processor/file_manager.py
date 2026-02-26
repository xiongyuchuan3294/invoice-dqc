"""
File manager for invoice file post-processing.
"""
import shutil
from pathlib import Path
from typing import Optional

from models import InvoiceInfo, InvoiceStatus


class FileManager:
    """Handle output file operations after invoice selection."""

    def __init__(self, invoice_pool: str, output_base: str, month: str):
        self.invoice_pool = Path(invoice_pool)
        self.output_base = Path(output_base)
        self.month = month
        self._clear_output_dir()

    def _clear_output_dir(self):
        """Clear all historical files under output directory before each run."""
        self.output_base.mkdir(parents=True, exist_ok=True)

        for path in self.output_base.iterdir():
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except PermissionError:
                print(f"  Warning: skip locked path during cleanup - {path}")
            except FileNotFoundError:
                pass

    def process_file(self, invoice: InvoiceInfo) -> Optional[str]:
        """Process one invoice file and return destination path."""
        src = self.invoice_pool / invoice.original_name

        if not src.exists():
            print(f"  Warning: source file not found - {src}")
            return None

        if invoice.final_status == InvoiceStatus.SELECTED:
            return self._copy_selected(invoice)
        if invoice.final_status == InvoiceStatus.ERROR:
            return self._copy_error(invoice)
        if invoice.final_status == InvoiceStatus.UNUSED:
            return self._copy_unused(invoice)

        print(f"  Warning: unknown status - {invoice.final_status}")
        return None

    def _copy_selected(self, invoice: InvoiceInfo) -> str:
        """Copy selected invoice to month output directory."""
        target_dir = self.output_base / self.month
        target_dir.mkdir(parents=True, exist_ok=True)

        src = self.invoice_pool / invoice.original_name
        dst = target_dir / invoice.new_name

        shutil.copy2(str(src), str(dst))
        return str(dst)

    def _copy_error(self, invoice: InvoiceInfo) -> str:
        """Copy error invoice to errors output directory."""
        target_dir = self.output_base / "errors"
        target_dir.mkdir(parents=True, exist_ok=True)

        src = self.invoice_pool / invoice.original_name
        dst = target_dir / invoice.new_name

        shutil.copy2(str(src), str(dst))
        return str(dst)

    def _copy_unused(self, invoice: InvoiceInfo) -> str:
        """Copy unused invoice to unused output directory."""
        target_dir = self.output_base / "unused"
        target_dir.mkdir(parents=True, exist_ok=True)

        src = self.invoice_pool / invoice.original_name
        dst = target_dir / invoice.new_name

        shutil.copy2(str(src), str(dst))
        return str(dst)

    def ensure_directories(self):
        """Ensure all output directories exist."""
        (self.output_base / self.month).mkdir(parents=True, exist_ok=True)
        (self.output_base / "errors").mkdir(parents=True, exist_ok=True)
        (self.output_base / "unused").mkdir(parents=True, exist_ok=True)