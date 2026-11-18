import os
import re
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

VOICES = (
    "pt-BR-FranciscaNeural",
    "pt-BR-AntonioNeural",
    "pt-BR-ThalitaMultilingualNeural",
)


def enabled():
    return os.getenv("RADAR_NARRACAO") == "azure"


def synthesize(work, variant, stop):
    key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    region = os.getenv("AZURE_SPEECH_REGION", "").strip().lower()
    if not key or not re.fullmatch(r"[a-z0-9]+", region):
        raise ValueError("Preencha AZURE_SPEECH_KEY e AZURE_SPEECH_REGION no .env e reinicie o Radar.")
    voice = VOICES[variant - 1]
    for index in range(5):
        if stop.is_set():
            raise RuntimeError("Produção interrompida.")
        scene = work / f"scene-{index}"
        text = escape(scene.with_suffix(".txt").read_text(encoding="utf-8"))
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">'
            f'<voice name="{voice}">{text}</voice></speak>'
        )
        request = urllib.request.Request(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            data=ssml.encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                "User-Agent": "RadarShopeeAI",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                audio = response.read(4_000_000)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Azure Speech respondeu com HTTP {error.code} para {voice}. "
                               "Confira a chave, a região e a disponibilidade da voz.") from None
        except OSError:
            raise RuntimeError("O Radar não conseguiu acessar o Azure Speech.") from None
        if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise RuntimeError("O Azure Speech não retornou um áudio WAV.")
        scene.with_suffix(".wav").write_bytes(audio)
