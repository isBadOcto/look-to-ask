"""Compare real local ASR on generated Mandarin test audio, never microphone recordings."""

import argparse
import base64
import json
import subprocess
import time
import unicodedata
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from look_to_ask.speech import load_model

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PHRASES = (
    "这个是什么意思，为什么这里会报错？",
    "请解释这段代码里的变量作用域。",
    "为什么这个函数返回的是空值？",
    "这里的线程同步和异步调用有什么区别？",
    "这个错误是因为权限不足还是路径不存在？",
    "请解释图片中这个按钮的用途。",
)


def generate():
    FIXTURES.mkdir(exist_ok=True)
    folder = str(FIXTURES).replace("'", "''")
    phrases = ",".join("'" + text.replace("'", "''") + "'" for text in PHRASES)
    code = f"""
    $ErrorActionPreference = 'Stop'
    $voice = New-Object -ComObject SAPI.SpVoice
    $token = @($voice.GetVoices()) |
        Where-Object {{ $_.GetDescription() -match 'Huihui' }} | Select-Object -First 1
    if (-not $token) {{ throw 'Windows Huihui SAPI voice is required; no fake fallback.' }}
    $voice.Voice = $token
    $phrases = @({phrases})
    for ($i = 0; $i -lt $phrases.Count; $i++) {{
        $stream = New-Object -ComObject SAPI.SpFileStream
        $stream.Format.Type = 22
        $stream.Open((Join-Path '{folder}' ('local-voice-asr-' + $i + '.wav')), 3, $false)
        try {{ $voice.AudioOutputStream = $stream; $voice.Speak($phrases[$i]) | Out-Null }}
        finally {{ $stream.Close() }}
    }}
    """
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(code.encode("utf-16-le")).decode(),
        ],
        check=True,
    )


def normalized(text):
    # Orthographic differences (including simplified/traditional) count as differences.
    return "".join(c.lower() for c in text if unicodedata.category(c)[0] not in "PZS")


def distance(reference, prediction):
    previous = list(range(len(prediction) + 1))
    for i, ref in enumerate(reference, 1):
        current = [i]
        for j, word in enumerate(prediction, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ref != word)))
        previous = current
    return previous[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate", action="store_true", help="Generate only tests-local SAPI WAVs"
    )
    parser.add_argument(
        "--models", nargs="+", choices=("base", "small", "medium"), default=["base", "small"]
    )
    parser.add_argument("--devices", nargs="+", choices=("cpu", "cuda"), default=["cpu"])
    parser.add_argument("--beams", nargs="+", type=int, choices=(1, 5), default=[1, 5])
    args = parser.parse_args()
    if args.generate:
        generate()
    audio = []
    for i in range(len(PHRASES)):
        rate, samples = wavfile.read(FIXTURES / f"local-voice-asr-{i}.wav")
        audio.append(
            np.asarray(resample_poly(samples.astype(np.float32) / 32768, 16000, rate), np.float32)
        )
    cache = Path.home() / ".cache/look-to-ask/whisper"
    for name in args.models:
        repository = cache / f"models--Systran--faster-whisper-{name}"
        reference = repository / "refs/main"
        snapshots = sorted((repository / "snapshots").glob("*"))
        if not reference.exists() and len(snapshots) != 1:
            raise RuntimeError(f"Prepare an unambiguous cached {name} model first")
        model_path = (
            repository / "snapshots" / reference.read_text().strip()
            if reference.exists()
            else snapshots[0]
        )
        for device in args.devices:
            started = time.perf_counter()
            model = load_model(
                str(model_path), device=device
            )  # Strict: no CPU fallback in benchmark.
            load_ms = round((time.perf_counter() - started) * 1000)
            try:
                # Measure first inference separately; steady-state numbers exclude it and loading.
                started = time.perf_counter()
                segments, _ = model.transcribe(
                    audio[0],
                    language="zh",
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                list(segments)
                first_ms = round((time.perf_counter() - started) * 1000)
                for beam in args.beams:
                    errors, characters, durations, outputs = 0, 0, [], []
                    for reference, samples in zip(PHRASES, audio, strict=True):
                        started = time.perf_counter()
                        segments, _ = model.transcribe(
                            samples,
                            language="zh",
                            beam_size=beam,
                            vad_filter=True,
                            condition_on_previous_text=False,
                        )
                        text = "".join(s.text for s in segments).strip()
                        durations.append(round((time.perf_counter() - started) * 1000))
                        reference, prediction = normalized(reference), normalized(text)
                        errors += distance(reference, prediction)
                        characters += len(reference)
                        outputs.append(text)
                    print(
                        json.dumps(
                            {
                                "model": name,
                                "revision": model_path.name,
                                "device": model.device,
                                "compute": model.compute_type,
                                "load_ms": load_ms,
                                "first_asr_ms": first_ms,
                                "beam": beam,
                                "errors": errors,
                                "reference_characters": characters,
                                "cer": round(errors / characters, 4),
                                "asr_ms": durations,
                                "synthetic_outputs": outputs,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            finally:
                model.close()


if __name__ == "__main__":
    main()
