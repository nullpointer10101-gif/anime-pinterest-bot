import os
import requests
import subprocess
import tempfile
from PIL import Image

TMP_DIR = tempfile.gettempdir()

# Pinterest limits
MAX_IMAGE_MB = 20
MAX_VIDEO_MB = 1900
MAX_IMAGE_PIXELS = 10000 * 10000


def download_image(url: str, pin_id: str) -> str | None:
    """
    Download an image from URL. Returns local file path or None on failure.
    Validates size and converts to JPEG if needed.
    """
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        ext = ".jpg"
        local_path = os.path.join(TMP_DIR, f"{pin_id}{ext}")

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Validate with Pillow
        img = Image.open(local_path)
        img.verify()

        # Check file size
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        if size_mb > MAX_IMAGE_MB:
            # Resize down
            img = Image.open(local_path)
            img.thumbnail((3000, 3000), Image.LANCZOS)
            img.save(local_path, "JPEG", quality=85)

        return local_path

    except Exception as e:
        print(f"[media] Image download failed for {pin_id}: {e}")
        return None


def download_video(url: str, pin_id: str) -> str | None:
    """
    Download a video pin using yt-dlp (handles Pinterest m3u8 streams).
    Returns local file path or None on failure.
    """
    try:
        local_path = os.path.join(TMP_DIR, f"{pin_id}.mp4")

        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--merge-output-format", "mp4",
                "-o", local_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            print(f"[media] yt-dlp error: {result.stderr}")
            return None

        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        if size_mb > MAX_VIDEO_MB:
            print(f"[media] Video too large ({size_mb:.0f}MB), skipping")
            return None

        return local_path

    except Exception as e:
        print(f"[media] Video download failed for {pin_id}: {e}")
        return None


def cleanup(path: str):
    """Delete a temp file after posting."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
