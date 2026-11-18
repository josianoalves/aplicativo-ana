"""Montagem vertical local com voz SAPI e mídia previamente autorizada."""

import math
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
import textwrap
import wave

from . import azure_voice


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}
PALETTES = (("0x151C31", "0xFFD276"), ("0x25202F", "0xFFC5DE"), ("0x102F2C", "0xB5F5D8"))

_SPEECH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $available = @($voice.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'pt-BR'
    })
    if ($env:RADAR_VOICE) {
        $available = @($available | Where-Object { $_.VoiceInfo.Name -eq $env:RADAR_VOICE })
    }
    if ($available.Count -eq 0) {
        throw 'Nenhuma voz brasileira SAPI disponivel. Instale uma voz pt-BR no Windows ou revise RADAR_VOICE.'
    }
    $voice.SelectVoice($available[0].VoiceInfo.Name)
    $voice.Rate = 1
    0..4 | ForEach-Object {
        $base = Join-Path $env:RADAR_SPEECH_DIR "scene-$_"
        $text = [IO.File]::ReadAllText("$base.txt", [Text.Encoding]::UTF8)
        $voice.SetOutputToWaveFile("$base.wav")
        $voice.Speak($text)
        $voice.SetOutputToNull()
    }
} finally {
    $voice.Dispose()
}
"""


def _run(args: list[str], work: Path, stop: Event, env: dict | None = None) -> None:
    if stop.is_set():
        raise RuntimeError("Produção interrompida.")
    log = work / "process.log"
    with log.open("wb") as stream:
        with subprocess.Popen(
            args, cwd=work, stdin=subprocess.DEVNULL, stdout=stream,
            stderr=subprocess.STDOUT, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as child:
            while child.poll() is None:
                if stop.wait(0.15):
                    child.kill()
                    child.wait()
                    raise RuntimeError("Produção interrompida.")
            status = child.returncode
    if status:
        details = log.read_bytes()[-1800:].decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Falha na produção ({Path(args[0]).name}, código {status}). {details}")


def _ffmpeg() -> str:
    binary = os.environ.get("RADAR_FFMPEG") or shutil.which("ffmpeg")
    if binary:
        found = shutil.which(binary)
        if not found:
            raise RuntimeError("RADAR_FFMPEG precisa apontar para um executável FFmpeg válido.")
        return found
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as exc:
        raise RuntimeError("Instale as dependências do Radar para habilitar a produção de vídeo.") from exc
    return get_ffmpeg_exe()


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as recording:
        return recording.getnframes() / recording.getframerate()


def _wrap(value: str, width: int) -> str:
    return "\n".join(textwrap.wrap(value, width=width))


def _scene_filter(is_image: bool, index: int, variant: int) -> str:
    background, accent = PALETTES[(variant - 1) % len(PALETTES)]
    if is_image:
        # Zoom leve centrado. A mídia inteira aparece no começo de cada cena.
        slope = (0.0008, 0.0014, 0.0020)[(variant - 1) % 3]
        zoom = f"1+{slope}*on" if (index + variant) % 2 else f"max(1,1.13-{slope}*on)"
        visual = (
            "scale=1920:1920:force_original_aspect_ratio=decrease,"
            f"pad=1920:1920:(ow-iw)/2:(oh-ih)/2:{background},"
            f"zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1080x1080:fps=30"
        )
    else:
        visual = (
            "scale=1080:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad=1080:1080:(ow-iw)/2:(oh-ih)/2:{background},fps=30"
        )
    return (
        visual + ",setsar=1,"
        f"pad=1080:1920:0:390:{background},"
        f"drawbox=x=478:y=115:w=124:h=8:color={accent}:t=fill,"
        "drawtext=fontfile=font.ttf:textfile=title.txt:expansion=none:"
        "fontsize=52:fontcolor=white:x=(w-tw)/2:y=152:line_spacing=10,"
        f"drawtext=fontfile=font.ttf:textfile=caption-{index}.txt:expansion=none:"
        f"fontsize=44:fontcolor={accent}:x=(w-tw)/2:y=1510:line_spacing=9,"
        "format=yuv420p"
    )


def render(
    product: dict, script: dict, media: Path, output: Path,
    duration: int, variant: int, music: Path | None, stop: Event,
) -> None:
    """Gera um MP4 H.264/AAC 1080×1920. Cada cena tem narração e legenda próprias."""
    if type(duration) is not int or not 15 <= duration <= 45:
        raise ValueError("A duração deve estar entre 15 e 45 segundos.")
    if type(variant) is not int or not 1 <= variant <= 3:
        raise ValueError("A variação deve ser 1, 2 ou 3.")
    segments = script.get("segments")
    if not isinstance(segments, list) or len(segments) != 5:
        raise ValueError("O roteiro de vídeo precisa de cinco segmentos.")
    if any(not isinstance(segment, str) or not segment.strip() or len(segment) > 180 for segment in segments):
        raise ValueError("Cada segmento do roteiro deve conter de 1 a 180 caracteres.")
    if len(segments[0]) > 90:
        raise ValueError("O gancho de três segundos deve ter até 90 caracteres.")
    media = Path(media).resolve()
    if not media.is_file() or media.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        raise ValueError("Selecione uma imagem ou vídeo autorizado em formato aceito.")
    if music is not None:
        music = Path(music).resolve()
        if not music.is_file() or music.suffix.lower() not in MUSIC_EXTENSIONS:
            raise ValueError("Selecione uma faixa de música autorizada em formato aceito.")
    if stop.is_set():
        raise RuntimeError("Produção interrompida.")
    font = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialbd.ttf"
    use_azure = azure_voice.enabled()
    shell = None if use_azure else shutil.which("powershell.exe")
    if not font.is_file():
        raise RuntimeError("A produção precisa da fonte Arial do Windows.")
    if not use_azure and not shell:
        raise RuntimeError("A narração do Windows precisa do Windows PowerShell.")
    binary = _ffmpeg()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".radar-render-", dir=output.parent) as directory:
        work = Path(directory)
        shutil.copyfile(font, work / "font.ttf")
        name = " ".join(str(product["name"]).split())
        (work / "title.txt").write_text(_wrap(textwrap.shorten(name, width=105, placeholder="…"), 32), encoding="utf-8")
        for index, segment in enumerate(segments):
            line = " ".join(segment.split())
            (work / f"scene-{index}.txt").write_text(line, encoding="utf-8")
            (work / f"caption-{index}.txt").write_text(_wrap(line, 37), encoding="utf-8")

        if use_azure:
            azure_voice.synthesize(work, variant, stop)
        else:
            _run([shell, "-NoProfile", "-NonInteractive", "-Command", _SPEECH_SCRIPT], work, stop,
                 dict(os.environ, RADAR_SPEECH_DIR=str(work)))
        is_image = media.suffix.lower() in IMAGE_EXTENSIONS
        common = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-filter_threads", "2"]
        lengths = (3, *((duration - 3) / 4 for _ in range(4)))
        for index, length in enumerate(lengths):
            source = ["-loop", "1", "-framerate", "30"] if is_image else ["-stream_loop", "-1"]
            audio = f"scene-{index}.wav"
            tempo = max(1, _duration(work / audio) / (length - 0.12))
            _run(common + source + [
                "-i", str(media), "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
                "-vf", _scene_filter(is_image, index, variant),
                "-af", f"atempo={tempo:.5f},apad", "-t", str(length),
                "-c:v", "libx264", "-preset", "veryfast", "-threads", "4", "-crf", "21",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", f"clip-{index}.mp4",
            ], work, stop)

        (work / "sequence.txt").write_text(
            "".join(f"file 'clip-{index}.mp4'\n" for index in range(5)), encoding="utf-8",
        )
        join = common + ["-f", "concat", "-safe", "1", "-i", "sequence.txt"]
        if music is None:
            join += ["-c", "copy"]
        else:
            join += [
                "-stream_loop", "-1", "-i", str(music), "-filter_complex_threads", "2",
                "-filter_complex", "[1:a]volume=0.12[bed];[0:a][bed]amix=inputs=2:duration=first:normalize=0[mix]",
                "-map", "0:v:0", "-map", "[mix]", "-c:v", "copy", "-c:a", "aac",
            ]
        _run(join + ["-movflags", "+faststart", "result.mp4"], work, stop)
        if stop.is_set():
            raise RuntimeError("Produção interrompida.")
        (work / "result.mp4").replace(output)
