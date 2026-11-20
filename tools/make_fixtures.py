#!/usr/bin/env python3
"""Generate original animated, voiced fixtures locally. FFmpeg needs flite and librsvg.

python3 tools/make_fixtures.py /tmp/clipops-fixtures --hour

The lesson uses eSpeak NG's Arabic voice when installed. Its fallback includes
accurately labeled Arabic translations of English synthesized lines. This tool
does not download models or contact any service.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import wave

FPS = 24
RATE = 24000
ART = Path(__file__).with_name("fixture_art.svg")

# Speaker, language, speech, optional synchronized English translation.
STUDIO = [
    ("host", "en", "Why did our best interview lose its audience?", ""),
    ("guest", "en", "We started with a biography. The real story came later.", ""),
    ("host", "en", "What happened when you moved the question to the opening?", ""),
    ("guest", "en", "The answer finally had context. Now we could hear the surprise.", ""),
    ("host", "en", "How do you choose the right pause?", ""),
    ("guest", "en", "Listen to the breath before the answer. That silence carries meaning.", ""),
    ("host", "en", "Which take do you keep if both sound clean?", ""),
    ("guest", "en", "Keep the one where the speaker changes their mind.", ""),
    ("host", "en", "So the first cut begins with listening.", ""),
    ("guest", "en", "Exactly. Leave the reason inside the story.", ""),
]
FASHION = [
    ("guest", "en", "What makes a good work jacket?", ""),
    ("guest", "en", "Start with the pockets. Each one has a purpose.", ""),
    ("guest", "en", "Follow the double stitch along the edge.", ""),
    ("guest", "en", "Turn the collar and see how it holds its shape.", ""),
    ("guest", "en", "One cut. Three details. Look a little closer.", ""),
]
LESSON = [
    ("guest", "ar", "ليه لون القميص بيتغير في الفيديو؟", "Why does the shirt change color on camera?"),
    ("guest", "ar", "نور الشباك بيتغير طول اليوم.", "Window light changes throughout the day."),
    ("guest", "en", "Set the white balance before recording.", ""),
    ("guest", "ar", "حط الكارت الرمادي جنب القماش.", "Place the grey card beside the fabric."),
    ("guest", "ar", "صوّر عينة صغيرة وراجع اللون.", "Record a small sample and check the color."),
    ("guest", "en", "Check the fabric in the same light as the model.", ""),
    ("guest", "ar", "كده تقدر تقارن اللقطات بنفسك.", "Now you can compare the shots yourself."),
]


def ffmpeg(*args, cwd=None):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    subprocess.run(command, cwd=cwd, check=True)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audio(lines, temp, name, espeak):
    samples = array("h", [0]) * (RATE // 3)
    cues = []
    rng = random.Random(4103)
    for index, (speaker, language, sentence, translation) in enumerate(lines):
        phrase, wav = temp / "phrase.txt", temp / "phrase.wav"
        spoken = translation if language == "ar" and not espeak else sentence
        phrase.write_text(spoken, encoding="utf-8")
        if language == "ar" and espeak:
            subprocess.run([espeak, "-v", "ar", "-s", "147", "-f", str(phrase), "-w", str(wav)], check=True)
            ffmpeg("-i", wav, "-ar", RATE, "-ac", 1, "-f", "s16le", temp / "phrase.pcm")
        else:
            voice = "rms" if speaker == "host" else "slt"
            ffmpeg("-f", "lavfi", "-i", f"flite=textfile=phrase.txt:voice={voice}",
                   "-ar", RATE, "-ac", 1, "-f", "s16le", "phrase.pcm", cwd=temp)
        speech = array("h")
        speech.frombytes((temp / "phrase.pcm").read_bytes())
        if sys.byteorder != "little":
            speech.byteswap()
        active = [i for i, value in enumerate(speech) if abs(value) >= 64]
        if not active:
            raise ValueError("Speech synthesizer produced silence")
        # Measure cues from the scheduled utterance and its actual waveform.
        first = max(0, active[0] - RATE // 40)
        last = min(len(speech), active[-1] + RATE // 30)
        start = len(samples) / RATE
        samples.extend(speech[first:last])
        end = len(samples) / RATE
        cues.append({"start": round(start, 3), "end": round(end, 3),
                     "text": sentence, "speaker": speaker})
        pause = 1.35 if index == 3 else .38
        samples.extend([0] * round(pause * RATE))
    frame_count = math.ceil((len(samples) / RATE + .3) * FPS)
    samples.extend([0] * (frame_count * (RATE // FPS) - len(samples)))
    # Short low-level background noise; the longer pause stays genuinely silent.
    for i in range(round(RATE * .6), min(len(samples), RATE * 3)):
        samples[i] = min(32767, max(-32768, samples[i] + rng.randrange(-45, 46)))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(temp / "track.wav"), "wb") as out:
        out.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())
    metadata = {
        "title": {"studio": "The editing room", "lesson": "Light studies", "fashion": "Cloth study"}[name],
        "synthetic": True,
        "timing_source": "Scheduled utterances, measured from synthesized PCM. Cue-level only.",
        "audio_language": "ar+en" if name == "lesson" and espeak else "en",
        "caption_language": "ar+en" if name == "lesson" else "en",
        "speakers": {"host": "Synthetic RMS", "guest": "Synthetic SLT and/or eSpeak Arabic"},
        "segments": cues,
    }
    if name == "lesson":
        metadata["arabic_voice"] = "Generic synthetic Arabic with Egyptian-script prompts" if espeak else "English audio with authored Arabic translations"
    return metadata, frame_count


def placed_face(name, x, y, scale, *, mouth=False):
    if mouth:
        marks = ('<ellipse cx="143" cy="200" rx="11" ry="4" fill="#5c3a32"/>'
                 if name == "host" else '<ellipse cx="141" cy="197" rx="11" ry="3.7" fill="#713d31"/>')
        content = marks
    else:
        content = f'<use xlink:href="#{name}"/>'
    return f'<g transform="translate({x} {y}) scale({scale})">{content}</g>'


def scene(name):
    if name == "studio":
        width, height = 1280, 720
        speakers = {"host": (83, 54, 1.94), "guest": (621, 53, 1.94)}
        decor = """
        <rect width="1280" height="720" fill="url(#studio)"/>
        <path d="M0 0H576L242 720H0Z" fill="#70694c" opacity=".67"/>
        <path d="M0 0H432L106 720H0Z" fill="#a69162" opacity=".21"/>
        <rect x="1000" width="280" height="720" fill="url(#ribs)"/>
        <circle cx="1040" cy="194" r="95" fill="none" stroke="#cbb386" stroke-width="2" opacity=".3"/>
        <circle cx="1040" cy="194" r="80" fill="none" stroke="#cbb386" opacity=".28"/>
        <g fill="#e5d6b4" font-family="DejaVu Sans"><text x="52" y="53" font-size="18" font-weight="bold" letter-spacing="4">FIELD RECORDINGS</text><text x="1227" y="53" text-anchor="end" font-size="15" letter-spacing="3">THE EDITING ROOM</text></g>
        <path d="M52 72H1228" stroke="#d3c2a0" opacity=".36"/>"""
        foreground = """
        <rect y="663" width="1280" height="57" fill="#6f563d"/><rect y="666" width="1280" height="6" fill="#ac8a61"/>
        <path d="M0 701Q430 686 720 696T1280 692M0 709Q300 695 640 704" fill="none" stroke="#4f4536" opacity=".65" stroke-width="2"/>
        <use xlink:href="#mic" transform="translate(378 452) scale(1.9)"/>
        <use xlink:href="#mic" transform="translate(879 456) scale(-1.85 1.85)"/>
        <rect x="534" y="610" width="37" height="48" rx="7" fill="#b9b49b"/><ellipse cx="552" cy="611" rx="18" ry="5" fill="#e1d8ba"/>
        <rect x="735" y="613" width="33" height="46" rx="6" fill="#71837a"/><ellipse cx="751" cy="614" rx="16" ry="5" fill="#a7ada0"/>"""
    elif name == "fashion":
        width = height = 1080
        speakers = {}
        decor = """
        <rect width="1080" height="1080" fill="#e6dfcc"/>
        <path d="M0 0H510L57 1080H0Z" fill="#f1eada"/>
        <path d="M1080 0V1080H724Z" fill="#b6b6a2"/>
        <path d="M77 83H1000" fill="none" stroke="#8f927f" stroke-width="2"/>
        <text x="79" y="67" font-family="DejaVu Sans" letter-spacing="4" font-weight="bold" font-size="17" fill="#4b5144">FIELD RECORDINGS</text>
        <text x="998" y="67" text-anchor="end" font-family="DejaVu Sans" letter-spacing="4" font-size="16" fill="#4b5144">GARMENT STUDIES</text>
        <text x="74" y="184" font-family="DejaVu Serif" font-size="77" letter-spacing="-4" fill="#36453b">Cloth study</text>
        <text x="78" y="226" font-family="DejaVu Sans" font-weight="bold" font-size="15" letter-spacing="5" fill="#566653">THE WORK JACKET</text>
        <path d="M555 0V187" stroke="#9d957e" stroke-width="3"/>
        <use xlink:href="#jacket" transform="translate(131 132) scale(2.3)"/>
        """
        foreground = ""
    else:
        width, height = 1080, 1920
        speakers = {"guest": (24, 383, 3.3)}
        decor = """
        <rect width="1080" height="1920" fill="url(#lesson)"/>
        <path d="M0 0H562L0 1130Z" fill="#f5edd4" opacity=".63"/>
        <path d="M1080 112V1468L566 1588Z" fill="#8b9380" opacity=".48"/>
        <g fill="none" stroke="#f6efd9" opacity=".56"><circle cx="791" cy="625" r="230"/><circle cx="791" cy="625" r="248"/></g>
        <g fill="#303f35"><text x="81" y="112" font-family="DejaVu Sans" font-size="23" font-weight="bold" letter-spacing="6">FIELD RECORDINGS</text>
        <text x="73" y="271" font-family="DejaVu Serif" font-size="105" letter-spacing="-7">Light studies</text></g>
        <path d="M82 321H993" stroke="#5b6755" stroke-width="2" opacity=".65"/>
        <text x="83" y="381" font-family="DejaVu Sans" font-size="20" fill="#3e4c40" letter-spacing="5">COLOUR  /  CAMERA WORKSHOP</text>"""
        foreground = """
        <path d="M0 1494Q340 1454 589 1487T1080 1461V1920H0Z" fill="#586050"/>
        <path d="M0 1517Q340 1474 589 1505T1080 1484" fill="none" stroke="#a9a88a" stroke-width="3"/>
        <g transform="translate(725 1448) rotate(-11)">
          <rect x="0" y="0" width="207" height="115" rx="3" fill="#2a3d3b"/>
          <rect x="11" y="10" width="53" height="93" fill="#b87657"/><rect x="76" y="10" width="53" height="93" fill="#d5bb91"/><rect x="142" y="10" width="53" height="93" fill="#829386"/>
        </g>"""
    people = "".join(placed_face(key, *pose) for key, pose in speakers.items())
    return width, height, decor + people + foreground, speakers


def rasterize(body, width, height, dest):
    # The fixture contains only our bundled vector definitions, with no remote references.
    svg = ART.read_text(encoding="utf-8").replace("<svg ", f'<svg width="{width}" height="{height}" ', 1)
    svg = svg.replace("</svg>", body + "</svg>")
    src = dest.with_suffix(".svg")
    src.write_text(svg, encoding="utf-8")
    ffmpeg("-i", src, "-frames:v", 1, "-threads", 1, dest)


def make_clip(directory, name, espeak):
    temp_parent = directory.resolve()
    with tempfile.TemporaryDirectory(prefix=".generating-", dir=temp_parent) as td:
        temp = Path(td)
        metadata, count = audio({"studio": STUDIO, "lesson": LESSON, "fashion": FASHION}[name], temp, name, espeak)
        width, height, artwork, positions = scene(name)
        rasterize(artwork, width, height, temp / "scene.png")
        layers = []
        for speaker, (x, y, scale) in positions.items():
            # Small cropped overlays animate the speaking sound without re-decoding a full-screen PNG.
            left, top = int(x + scale * 121), int(y + scale * 185)
            size = int(42 * scale)
            mouth = placed_face(speaker, x - left, y - top, scale, mouth=True)
            rasterize(mouth, size, size, temp / f"{speaker}.png")
            turns = [f"between(t,{s['start']},{s['end']})" for s in metadata["segments"] if s["speaker"] == speaker]
            on = f"gt(sin(t*28+sin(t*9)),0)*({'+'.join(turns)})"
            layers.append((speaker, left, top, on))
        args = ["-loop", "1", "-framerate", str(FPS), "-i", temp / "scene.png"]
        filters = []
        prev = "[0:v]"
        for i, (speaker, x, y, on) in enumerate(layers, 1):
            args.extend(["-loop", "1", "-framerate", str(FPS), "-i", temp / f"{speaker}.png"])
            filters.append(f"{prev}[{i}:v]overlay={x}:{y}:enable='{on}'[layer{i}]")
            prev = f"[layer{i}]"
        # Slow camera movement throughout the silent pauses as well as speech.
        filters.append(f"{prev}scale={width + 64}:{height + 64},crop={width}:{height}:x='32+25*sin(t*.29)':y='32+18*cos(t*.36)',setsar=1[v]")
        args.extend(["-i", temp / "track.wav", "-filter_complex_threads", "1",
                     "-filter_complex", ";".join(filters), "-map", "[v]", "-map", f"{len(layers) + 1}:a:0",
                     "-frames:v", str(count), "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                     "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                     "-ar", "48000", "-movflags", "+faststart", temp / "ready.mp4"])
        ffmpeg(*args)
        if name == "fashion":
            detail = """
            <rect width="1080" height="1080" fill="#3c4941"/>
            <ellipse cx="665" cy="576" rx="540" ry="640" fill="#596253"/>
            <use xlink:href="#jacket" transform="translate(-747 -674) rotate(-10 1250 1150) scale(8.1)"/>
            <path d="M66 81H374" stroke="#f7e8c8" stroke-width="2"/>
            <text x="66" y="67" font-family="DejaVu Sans" font-size="19" fill="#fcf4de" letter-spacing="4">STITCH DETAIL</text>"""
            rasterize(detail, width, height, temp / "detail.png")
            ffmpeg("-loop", "1", "-framerate", str(FPS), "-i", temp / "detail.png",
                   "-t", "5", "-vf", "scale=1170:1170,crop=1080:1080:x='36+24*sin(t*.4)':y='35+27*cos(t*.5)'",
                   "-c:v", "libx264", "-crf", "20", "-threads", "2", "-preset", "veryfast",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", temp / "fashion-detail.mp4")
            (temp / "fashion-detail.mp4").replace(directory / "fashion-detail.mp4")
        (temp / "ready.mp4").replace(directory / f"{name}.mp4")
        write_json(directory / f"{name}.json", metadata)
        print(f"{name}  {count / FPS:.3f}s  {width} × {height}  {len(metadata['segments'])} cues", flush=True)


def make_hour(directory):
    clip = directory / "studio.mp4"
    # Repeat the complete scene and preserve each genuine pause at seams.
    with tempfile.TemporaryDirectory(prefix=".hour-", dir=directory) as td:
        temp = Path(td)
        metadata = json.loads((directory / "studio.json").read_text())
        raw_duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "csv=p=0", str(clip)], text=True))
        # Match both audio and video packet boundaries and keep encoder priming out of each loop by using PCM.
        period = math.ceil(raw_duration * 25) / 25
        ffmpeg("-i", clip, "-vf", "scale=384:216,fps=25,tpad=stop_mode=clone:stop_duration=1",
               "-af", "aresample=8000,apad", "-t", str(period), "-c:v", "libx264", "-threads", "1",
               "-crf", "27", "-preset", "veryfast", "-bf", "0", "-c:a", "pcm_s16le", temp / "period.mkv")
        ffmpeg("-stream_loop", "-1", "-i", temp / "period.mkv", "-t", "3600", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "24k", "-ar", "16000", "-movflags", "+faststart", temp / "hour.mp4")
        (temp / "hour.mp4").replace(directory / "hour.mp4")
    original = metadata["segments"]
    metadata["segments"] = [dict(s, start=round(i*period+s["start"], 3), end=round(i*period+s["end"], 3))
                            for i in range(math.ceil(3600/period)) for s in original if i*period+s["end"] <= 3600]
    metadata.update({"title": "One-hour duplicate-suppression fixture", "repeated_period_seconds": period})
    write_json(directory / "hour.json", metadata)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--only", choices=["studio", "lesson", "fashion", "hour"])
    p.add_argument("--hour", action="store_true", help="also create a full 3600-second repeated-dialogue MP4")
    p.add_argument("--espeak", help="local espeak-ng executable for the Arabic voice", default=shutil.which("espeak-ng"))
    args = p.parse_args()
    directory = args.directory.expanduser().resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ["studio", "lesson", "fashion"]:
        if args.only is None or args.only == name:
            make_clip(directory, name, args.espeak)
    if args.only == "hour" or args.hour:
        make_hour(directory)
    # Narrow fixed corruption fixture, built locally for the intake validator.
    (directory / "corrupt.mp4").write_bytes(b"ClipOps intentionally invalid synthetic fixture.\n")


if __name__ == "__main__":
    main()
