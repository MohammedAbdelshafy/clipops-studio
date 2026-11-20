#!/usr/bin/env python3
"""Render the original synthetic editorial proofs. Run after make_fixtures.py."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot_edit import render
from pilot_qc import inspect_export, validate_source


def proof(fixtures, evidence, source_name, sample_name, style, platform, settings, cue_count):
    source = fixtures / f"{source_name}.mp4"
    if not (fixtures / f"{source_name}.json").is_file():
        raise SystemExit(f"Generate {source_name}.mp4 and .json with tools/make_fixtures.py")
    transcript = json.loads((fixtures / f"{source_name}.json").read_text())
    if transcript.get("synthetic") is not True:
        raise ValueError("Sample evidence must use generated synthetic fixtures")
    segments = transcript["segments"]
    begin = round(max(0, segments[0]["start"] - .18), 3)
    end = round(segments[cue_count - 1]["end"] + .18, 3)
    output = evidence / f"{sample_name}.mp4"
    started = time.monotonic()
    result = render(source, output, begin, end, segments, style, platform, **settings)
    rendered = time.monotonic()
    audit = inspect_export(output, result["duration"], result["dimensions"],
                           segments=result["captions"], source_info=validate_source(source))
    checked = time.monotonic()
    for field in ("file", "srt", "vtt"):
        result[field] = Path(result[field]).name
    report = {
        "source": source.name,
        "sample": output.name,
        "synthetic": True,
        "audio_language": transcript["audio_language"],
        "caption_language": transcript["caption_language"],
        "timing": transcript["timing_source"],
        "render": result,
        "quality": audit,
        "runtime_seconds": {"render": round(rendered - started, 3), "quality_control": round(checked - rendered, 3)},
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "size_bytes": output.stat().st_size,
        "review": "Unapproved synthetic preview",
    }
    (evidence / f"{sample_name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{output.name}  render {rendered - started:.2f}s  QC {checked - rendered:.2f}s  {audit['passed']}", flush=True)
    return report


def contact_sheet(evidence, reports):
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO

    width = 206
    heights = [round(width * r["render"]["dimensions"][1] / r["render"]["dimensions"][0]) for r in reports]
    sheet = Image.new("RGB", (width * 4 + 68, sum(h + 68 for h in heights) + 6), "#f1ebde")
    pen = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("DejaVuSans.ttf", 13)
    row_top = 0
    for height, report in zip(heights, reports):
        title = f"{report['sample']}     {report['render']['dimensions'][0]} × {report['render']['dimensions'][1]}"
        pen.text((16, 12 + row_top), title, fill="#202d2a", font=font)
        duration = report["render"]["duration"]
        for col, fraction in enumerate((.06, .34, .65, .87)):
            seconds = duration * fraction
            data = subprocess.check_output([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", str(seconds),
                "-i", str(evidence / report["sample"]), "-frames:v", "1", "-vf", f"scale={width}:{height}",
                "-threads", "1", "-f", "image2pipe", "-c:v", "png", "-",
            ])
            with Image.open(BytesIO(data)) as frame:
                sheet.paste(frame.convert("RGB"), (16 + col * (width + 10), 36 + row_top))
            pen.text((16 + col * (width + 10), 40 + height + row_top), f"{seconds:.1f}s", fill="#405249", font=font)
        row_top += height + 68
    sheet.save(evidence / "render-contact-sheet.jpg", quality=94, subsampling=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    args.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    podcast = proof(args.fixtures, args.evidence, "studio", "podcast-split", "podcast", "shorts",
                    {"framing": "split", "speaker_positions": {"host": .28, "guest": .72}}, 4)
    lesson = proof(args.fixtures, args.evidence, "lesson", "arabic-lesson", "egyptian", "reels",
                   {"framing": "contain"}, 4)
    detail = args.fixtures / "fashion-detail.mp4"
    fashion = proof(args.fixtures, args.evidence, "fashion", "fashion-lookbook", "fashion", "square",
                    {"framing": "contain", "cutaways": [{"path": detail, "at": 4.0, "until": 8.8,
                                                         "rights_confirmed": True}]}, 4)
    reports = [podcast, lesson, fashion]
    contact_sheet(args.evidence, reports)
    if not all(rep["quality"]["passed"] for rep in reports):
        raise SystemExit("Sample failed export quality control; inspect its JSON report")


if __name__ == "__main__":
    main()
