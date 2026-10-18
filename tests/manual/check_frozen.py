"""Check a real frozen program from an empty cwd; no camera, microphone or screen capture."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--speech-fixture", type=Path)
    args = parser.parse_args()
    executable, output = args.executable.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONPATH", "PYTHONHOME", "QT_QPA_PLATFORM")
    }
    env["PATH"] = os.pathsep.join(
        (str(Path(os.environ["WINDIR"]) / "System32"), os.environ["WINDIR"])
    )
    env["LOCALAPPDATA"] = str(output / "local-data")
    summaries = []
    for mode, language in (
        ("check", None),
        ("check-engine", None),
        ("check-speech", None),
        ("smoke-ui", "en"),
        ("smoke-ui", "zh"),
    ):
        if language:
            settings_path = Path(env["LOCALAPPDATA"]) / "LookToAsk/settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps({"ui_language": language}), "utf-8")
        report = output / (mode + ("-" + language if language else "") + ".json")
        report.unlink(missing_ok=True)
        started = time.perf_counter()
        command = [str(executable), "--" + mode, "--report", str(report)]
        if mode == "check-speech":
            command += ["--speech-model", "base", "--speech-device", "cpu"]
            if args.speech_fixture:
                command += ["--speech-fixture", str(args.speech_fixture.resolve())]
        result = subprocess.run(
            command,
            cwd=output,
            env=env,
            timeout=120,
        )
        data = json.loads(report.read_text("utf-8")) if report.exists() else {}
        summaries.append(
            {
                "mode": mode,
                "exit_code": result.returncode,
                "seconds": round(time.perf_counter() - started, 2),
                **data,
            }
        )
        print(summaries[-1], flush=True)
        if result.returncode != 0 or not data.get("ok") or not data.get("frozen"):
            raise SystemExit("FROZEN_CHECK_FAILED")
        if language and data.get("ui_language") != language:
            raise SystemExit("FROZEN_UI_LANGUAGE_FAILED")
        if language and not data.get("license_notice_loaded"):
            raise SystemExit("FROZEN_LICENSE_NOTICE_MISSING")
    (output / "summary.json").write_text(json.dumps(summaries, indent=2), "utf-8")
    print(
        "FROZEN_CHECK_OK (real packaged dependencies/engine/speech/UI; no hardware or external AI)"
    )


if __name__ == "__main__":
    main()
