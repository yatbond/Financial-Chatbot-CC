"""Download a file from Supabase Storage to a local temp path."""

import tempfile
import os
import httpx

from .config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY


def download_file(storage_path: str, bucket: str = "reports") -> str:
    """
    Downloads storage_path from the given bucket and returns the local temp file path.
    Caller is responsible for deleting the file after use.
    """
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }

    # Preserve the original file extension so openpyxl/xlrd can detect the format
    ext = os.path.splitext(storage_path)[1].lower() or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)

    with httpx.Client(follow_redirects=True, timeout=120) as client:
        with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                tmp.write(chunk)

    tmp.close()
    return tmp.name
