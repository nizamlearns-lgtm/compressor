import os
import subprocess
import shutil
from PIL import Image


# ---------------------------------------------------
# Detect if file is an image
# ---------------------------------------------------
def is_image(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


# ---------------------------------------------------
# Image compression
# ---------------------------------------------------
def compress_image(path):
    base, ext = os.path.splitext(path)
    out_path = base + "_compressed" + ext.lower()

    with Image.open(path) as img:
        # Convert formats with transparency to RGB
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(
            out_path,
            optimize=True,
            quality=85  # Good balance
        )

    return out_path


# ---------------------------------------------------
# Helper: get CRF value based on quality preset
# ---------------------------------------------------
def get_crf(quality):
    if quality == "high":
        return 20
    if quality == "balanced":
        return 28
    if quality == "small":
        return 30
    if quality == "xs":
        return 32
    return 28  # default fallback


# ---------------------------------------------------
# Helper: resolution scaling filter
# ---------------------------------------------------
def get_scale_filter(resolution):
    if resolution == "720p":
        return "scale=-2:720"
    if resolution == "480p":
        return "scale=-2:480"
    if resolution == "360p":
        return "scale=-2:360"
    return None  # original resolution


# ---------------------------------------------------
# Video compression with user options
# ---------------------------------------------------
def compress_video(path, quality="balanced", codec="h265", resolution="original"):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install from ffmpeg.org and add to PATH.")

    base, ext = os.path.splitext(path)
    out_path = base + "_compressed" + ext

    crf = get_crf(quality)
    scale = get_scale_filter(resolution)

    # codec choice
    vcodec = "libx265" if codec == "h265" else "libx264"

    cmd = [
        ffmpeg, "-y",
        "-i", path,
        "-c:v", vcodec,
        "-crf", str(crf),
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "96k",
    ]

    # Add scaling only if selected
    if scale:
        cmd.extend(["-vf", scale])

    cmd.append(out_path)

    subprocess.run(cmd, check=True)
    return out_path
