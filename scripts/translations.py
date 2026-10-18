"""Update Qt TS sources from tr() calls, or compile reviewed translations to QM."""

import argparse
import ast
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/look_to_ask"
CATALOG = PACKAGE / "translations/en.ts"


def update():
    previous = {}
    if CATALOG.exists():
        for message in ET.parse(CATALOG).findall(".//message"):
            previous[message.findtext("source")] = message.find("translation")
    sources = {}
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
            ):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                raise ValueError(f"tr() needs a literal source: {path.name}:{node.lineno}")
            sources.setdefault(node.args[0].value, []).append((path.name, node.lineno))
    root = ET.Element("TS", version="2.1", language="en", sourcelanguage="zh_CN")
    context = ET.SubElement(root, "context")
    ET.SubElement(context, "name").text = "LookToAsk"
    for source, locations in sources.items():
        message = ET.SubElement(context, "message")
        for filename, line in locations:
            ET.SubElement(message, "location", filename="../" + filename, line=str(line))
        ET.SubElement(message, "source").text = source
        translation = previous.get(source)
        if translation is None:
            translation = ET.Element("translation", type="unfinished")
        message.append(translation)
    CATALOG.parent.mkdir(exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(CATALOG, encoding="utf-8", xml_declaration=True)
    print(f"Updated {len(sources)} translation messages: {CATALOG}")


def compile_catalog():
    for message in ET.parse(CATALOG).findall(".//message"):
        translation = message.find("translation")
        if translation is None or translation.get("type") or not translation.text:
            raise ValueError("Finish every translation before building")
        source_fields = [
            item[1:]
            for item in Formatter().parse(message.findtext("source"))
            if item[1] is not None
        ]
        translated_fields = [
            item[1:] for item in Formatter().parse(translation.text) if item[1] is not None
        ]
        if sorted(source_fields) != sorted(translated_fields):
            raise ValueError("Translation changed a format placeholder")
    executable = Path(sys.executable).with_name("pyside6-lrelease.exe")
    command = str(executable) if executable.exists() else shutil.which("pyside6-lrelease")
    if not command:
        raise RuntimeError("Install project dependencies to use pyside6-lrelease")
    subprocess.run([command, str(CATALOG), "-qm", str(CATALOG.with_suffix(".qm"))], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("update", "compile"))
    args = parser.parse_args()
    update() if args.action == "update" else compile_catalog()
