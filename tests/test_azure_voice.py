import io
import tempfile
import unittest
import wave
from pathlib import Path
from threading import Event
from unittest.mock import patch

from radar import azure_voice


class AzureVoiceTests(unittest.TestCase):
    def test_sends_correct_voice_and_writes_wav_for_every_scene(self):
        data = io.BytesIO()
        with wave.open(data, "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x00" * 50)

        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {
            "AZURE_SPEECH_KEY": "test-token", "AZURE_SPEECH_REGION": "eastus",
        }), patch("radar.azure_voice.urllib.request.urlopen",
                  side_effect=lambda *args, **kwargs: io.BytesIO(data.getvalue())) as request:
            folder = Path(directory)
            for index in range(5):
                (folder / f"scene-{index}.txt").write_text("Veja A & B.", encoding="utf-8")
            for index, voice in enumerate(azure_voice.VOICES, 1):
                azure_voice.synthesize(folder, index, Event())
                batch = request.call_args_list[-5:]
                self.assertEqual(len(batch), 5)
                for call in batch:
                    payload = call.args[0]
                    self.assertIn(voice, payload.data.decode())
                    self.assertIn("A &amp; B", payload.data.decode())
                    self.assertEqual(payload.full_url, "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1")
            self.assertEqual(request.call_count, 15)
            self.assertEqual((folder / "scene-4.wav").read_bytes(), data.getvalue())

    def test_missing_credentials_block_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("radar.azure_voice.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "AZURE_SPEECH_KEY"):
                azure_voice.synthesize(Path("."), 1, Event())
            request.assert_not_called()
