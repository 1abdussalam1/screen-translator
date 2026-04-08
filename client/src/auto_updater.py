import asyncio
import logging
import subprocess
import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QDialogButtonBox, QWidget
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)


def _version_tuple(v: str) -> tuple:
    """Convert version string to comparable tuple."""
    try:
        return tuple(int(x) for x in v.strip().split('.'))
    except ValueError:
        return (0,)


class UpdateDialog(QDialog):
    """Dialog shown when a new update is available."""

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle('تحديث جديد متاح')
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        version = update_info.get('version', '?')
        title_label = QLabel(f'تحديث جديد متاح (v{version})')
        title_font = title_label.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        release_notes = update_info.get('release_notes', '')
        if release_notes:
            notes_label = QLabel(release_notes)
            notes_label.setWordWrap(True)
            layout.addWidget(notes_label)

        layout.addWidget(QLabel('هل تريد التحديث الآن؟'))

        btn_layout = QHBoxLayout()
        update_btn = QPushButton('تحديث الآن')
        update_btn.setDefault(True)
        later_btn = QPushButton('لاحقاً')
        update_btn.clicked.connect(self.accept)
        later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(later_btn)
        layout.addLayout(btn_layout)


class DownloadProgressDialog(QDialog):
    """Dialog that shows download progress for the update."""

    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle('تنزيل التحديث')
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._status_label = QLabel('جاري تنزيل التحديث...')
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        self._size_label = QLabel('')
        layout.addWidget(self._size_label)

        cancel_btn = QPushButton('إلغاء')
        cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(cancel_btn)

        self._cancelled = False

    def _on_cancel(self) -> None:
        self._cancelled = True
        self.cancelled.emit()
        self.reject()

    def update_progress(self, downloaded: int, total: int) -> None:
        """Update progress bar and size label."""
        if total > 0:
            pct = int(downloaded / total * 100)
            self._progress_bar.setValue(pct)
        else:
            self._progress_bar.setRange(0, 0)  # indeterminate

        def _fmt(b):
            if b < 1024:
                return f'{b} B'
            elif b < 1024 * 1024:
                return f'{b / 1024:.1f} KB'
            else:
                return f'{b / 1024 / 1024:.1f} MB'

        if total > 0:
            self._size_label.setText(f'{_fmt(downloaded)} / {_fmt(total)}')
        else:
            self._size_label.setText(f'{_fmt(downloaded)}')

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class AutoUpdater(QObject):
    """Handles checking for, downloading, and installing updates."""

    def __init__(self, parent=None):
        super().__init__(parent)

    async def check_for_updates(
        self,
        api_client,
        current_version: str,
        parent_widget=None
    ) -> None:
        """
        Check for updates and prompt user if one is available.
        Non-blocking when integrated with qasync.
        """
        try:
            update_info = await api_client.check_update(current_version)
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
            return

        if update_info is None:
            logger.info("No updates available.")
            return

        logger.info(f"Update available: {update_info.get('version')}")

        # Show update dialog (non-blocking via Qt event loop)
        dialog = UpdateDialog(update_info, parent=parent_widget)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            logger.info("User declined update.")
            return

        download_url = update_info.get('download_url', '')
        if not download_url:
            logger.error("No download URL in update info.")
            return

        await self._download_and_install(api_client, download_url, parent_widget)

    async def _download_and_install(
        self,
        api_client,
        download_url: str,
        parent_widget=None
    ) -> None:
        """Download the installer and run it, then exit."""
        progress_dialog = DownloadProgressDialog(parent=parent_widget)
        progress_dialog.show()

        installer_path: Optional[str] = None
        error_msg: Optional[str] = None

        def on_progress(downloaded: int, total: int) -> None:
            if not progress_dialog.is_cancelled:
                progress_dialog.update_progress(downloaded, total)
                # Process Qt events to keep UI responsive
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()

        try:
            installer_path = await api_client.download_update(download_url, on_progress)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed: {e}")

        progress_dialog.accept()

        if progress_dialog.is_cancelled:
            logger.info("User cancelled download.")
            if installer_path:
                try:
                    import os
                    os.remove(installer_path)
                except OSError:
                    pass
            return

        if error_msg:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                parent_widget,
                'خطأ في التنزيل',
                f'فشل تنزيل التحديث:\n{error_msg}'
            )
            return

        if installer_path:
            logger.info(f"Launching installer: {installer_path}")
            try:
                subprocess.Popen([installer_path], shell=True)
                sys.exit(0)
            except Exception as e:
                logger.error(f"Failed to launch installer: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    parent_widget,
                    'خطأ',
                    f'فشل تشغيل المثبّت:\n{e}'
                )
