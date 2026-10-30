import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from downloader import get_ffmpeg_dir


class TestFFmpegDiscovery(unittest.TestCase):
    def test_ffmpeg_dir_dev_mode_found(self):
        """No ambiente de dev com executáveis na raiz, get_ffmpeg_dir deve retornar o diretório."""
        d = get_ffmpeg_dir()
        if os.path.exists("ffmpeg.exe") and os.path.exists("ffprobe.exe"):
            self.assertIsNotNone(d)
            self.assertTrue(os.path.exists(os.path.join(d, "ffmpeg.exe")))
            self.assertTrue(os.path.exists(os.path.join(d, "ffprobe.exe")))

    def test_ffmpeg_dir_dev_mode_missing(self):
        """Se algum binário estiver ausente, deve retornar None para fallback no PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_downloader_path = os.path.join(tmpdir, "downloader.py")
            with patch("downloader.__file__", fake_downloader_path), patch.object(sys, "frozen", False, create=True):
                self.assertIsNone(get_ffmpeg_dir())

                # Apenas ffmpeg.exe presente
                open(os.path.join(tmpdir, "ffmpeg.exe"), "w").close()
                self.assertIsNone(get_ffmpeg_dir())

                # Ambos presentes
                open(os.path.join(tmpdir, "ffprobe.exe"), "w").close()
                res = get_ffmpeg_dir()
                self.assertEqual(res, tmpdir)

    def test_ffmpeg_dir_frozen_meipass(self):
        """Em modo frozen PyInstaller com _MEIPASS, deve encontrar os binários em _MEIPASS."""
        with tempfile.TemporaryDirectory() as meipass_dir, tempfile.TemporaryDirectory() as exe_dir:
            open(os.path.join(meipass_dir, "ffmpeg.exe"), "w").close()
            open(os.path.join(meipass_dir, "ffprobe.exe"), "w").close()
            fake_exe = os.path.join(exe_dir, "VideoDownloader.exe")

            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", meipass_dir, create=True), \
                 patch.object(sys, "executable", fake_exe):
                self.assertEqual(get_ffmpeg_dir(), meipass_dir)

    def test_ffmpeg_dir_frozen_exe_fallback(self):
        """Em modo frozen sem os binários em _MEIPASS, mas ao lado do executável, deve encontrar na pasta do exe."""
        with tempfile.TemporaryDirectory() as meipass_dir, tempfile.TemporaryDirectory() as exe_dir:
            fake_exe = os.path.join(exe_dir, "VideoDownloader.exe")
            open(os.path.join(exe_dir, "ffmpeg.exe"), "w").close()
            open(os.path.join(exe_dir, "ffprobe.exe"), "w").close()

            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", meipass_dir, create=True), \
                 patch.object(sys, "executable", fake_exe):
                self.assertEqual(get_ffmpeg_dir(), exe_dir)


if __name__ == "__main__":
    unittest.main()
