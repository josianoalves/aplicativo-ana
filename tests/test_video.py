"""Validação de vídeo por leitura real dos streams FFmpeg."""

import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Timer
import unittest
from unittest.mock import patch

from radar.video import _ffmpeg, _run, render


@unittest.skipUnless(os.name == "nt", "Produção de vídeo local no Windows")
class VideoTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.output = self.folder / "vídeo final.mp4"
        self.image = self.folder / "mídia autorizada.png"
        self.product = {"id": "demo", "name": "Caneca vermelha — edição básica"}
        self.script = {
            "segments": [
                "Olha essa caneca!", "Ela tem acabamento vermelho.",
                "Veja como fica na mesa.", "Confira as medidas na página.",
                "Toque no produto para ver os detalhes.",
            ]
        }

    def make_source(self, filters, destination):
        subprocess.run(
            [_ffmpeg(), "-v", "error", "-f", "lavfi", *filters, str(destination)],
            check=True, capture_output=True, timeout=20,
        )

    def assert_streams(self, filename, duration):
        result = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-i", str(filename), "-map", "0:v:0",
             "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"],
            check=True, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
        )
        self.assertRegex(result.stderr, r"Video: h264[^\n]+1080x1920")
        self.assertRegex(result.stderr, r"Audio: aac")
        peak = re.search(r"max_volume: (-?[0-9.]+) dB", result.stderr)
        self.assertIsNotNone(peak, result.stderr)
        self.assertGreater(float(peak[1]), -35, "A faixa de áudio deveria ser audível")
        match = re.search(r"Duration: 00:00:([0-9.]+)", result.stderr)
        self.assertIsNotNone(match, result.stderr)
        self.assertAlmostEqual(float(match[1]), duration, delta=0.2)

    def test_image_and_video_variants_with_pt_br_narration_and_optional_music(self):
        self.make_source(["-i", "color=c=red:s=640x480", "-frames:v", "1", "-threads", "1"], self.image)
        render(self.product, self.script, self.image, self.output, 15, 1, None, Event())
        self.assert_streams(self.output, 15)

        source = self.folder / "trecho.mp4"
        music = self.folder / "faixa.wav"
        self.make_source(["-i", "testsrc2=size=480x640:rate=30", "-t", "1", "-threads", "1"], source)
        self.make_source(["-i", "sine=frequency=300", "-t", "1"], music)
        alternate = self.folder / "variação.mp4"
        render(self.product, self.script, source, alternate, 16, 2, music, Event())
        self.assert_streams(alternate, 16)

        third = self.folder / "variação 3.mp4"
        render(self.product, self.script, source, third, 45, 3, None, Event())
        self.assert_streams(third, 45)

    def test_invalid_requests_and_stop_leave_no_output(self):
        stop = Event()
        with self.assertRaisesRegex(ValueError, "duração"):
            render(self.product, self.script, self.image, self.output, 14, 1, None, stop)
        with self.assertRaisesRegex(ValueError, "variação"):
            render(self.product, self.script, self.image, self.output, 15, 4, None, stop)
        with self.assertRaisesRegex(ValueError, "cinco segmentos"):
            render(self.product, {}, self.image, self.output, 15, 1, None, stop)
        with self.assertRaisesRegex(ValueError, "imagem ou vídeo"):
            render(self.product, self.script, self.image, self.output, 15, 1, None, stop)
        self.image.touch()
        with self.assertRaisesRegex(ValueError, "faixa"):
            render(self.product, self.script, self.image, self.output, 15, 1, self.image, stop)
        stop.set()
        with self.assertRaisesRegex(RuntimeError, "interrompida"):
            render(self.product, self.script, self.image, self.output, 15, 1, None, stop)
        self.assertFalse(self.output.exists())

    def test_voice_failure_cleans_up_temporary_files(self):
        self.image.touch()
        with patch.dict(os.environ, {"RADAR_VOICE": "voz-inexistente"}):
            with self.assertRaisesRegex(RuntimeError, "Nenhuma voz brasileira SAPI"):
                render(self.product, self.script, self.image, self.output, 15, 1, None, Event())
        self.assertEqual(list(self.folder.iterdir()), [self.image])

    def test_stop_terminates_an_active_process(self):
        stop = Event()
        child_marker = self.folder / "child-finished"
        timer = Timer(0.5, stop.set)
        timer.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "interrompida"):
                _run([sys.executable, "-c", "import pathlib, time; time.sleep(3); pathlib.Path('child-finished').touch()"],
                     self.folder, stop)
        finally:
            timer.join()
        self.assertFalse(child_marker.exists())
