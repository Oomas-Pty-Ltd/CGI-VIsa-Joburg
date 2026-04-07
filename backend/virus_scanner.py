"""
====================================================================
VIRUS / MALWARE SCANNER
====================================================================
Checks uploaded files for known threats before any processing.

Detection layers (in order):
  1. EICAR Standard Antivirus Test File signature  (TC 3.1)
  2. Executable / script magic-byte signatures
  3. VirusTotal SHA-256 hash lookup (optional — set VIRUSTOTAL_API_KEY)

Fail-open design: if a scan step errors (e.g. no network to VirusTotal)
it logs a warning and continues, so legitimate uploads are never blocked
by an infrastructure issue.
====================================================================
"""
import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# ── EICAR Standard Antivirus Test File ───────────────────────────────────────
# The official test string used by all major AV products to verify scanning.
# Harmless by itself; presence in any file is a deliberate test or an attack.
_EICAR_SIGNATURE = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}"
    b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)

# ── Executable / script magic bytes ──────────────────────────────────────────
# These should never appear in legitimate image/PDF uploads.
_BLOCKED_MAGIC: list[tuple[bytes, str]] = [
    (b"MZ",       "Windows PE executable"),
    (b"\x7FELF",  "Linux ELF executable"),
    (b"#!/",      "Unix shell script"),
    (b"#!python", "Python script"),
    (b"#!perl",   "Perl script"),
    (b"#!ruby",   "Ruby script"),
]


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

async def scan_bytes(data: bytes, filename: str = "upload") -> dict:
    """
    Scan raw file bytes for malware.

    Returns:
        {"clean": True}
        {"clean": False, "threat": "<human-readable description>"}
    """
    # 1. EICAR test string — works anywhere in the payload
    if _EICAR_SIGNATURE in data:
        logger.warning("[VIRUS_SCAN] EICAR test file detected — filename=%s", filename)
        return {"clean": False, "threat": "EICAR-STANDARD-ANTIVIRUS-TEST-FILE"}

    # 2. Magic-byte executable/script check (first 8 bytes)
    header = data[:8]
    for magic, label in _BLOCKED_MAGIC:
        if header[: len(magic)] == magic:
            logger.warning(
                "[VIRUS_SCAN] Blocked file signature (%s) — filename=%s", label, filename
            )
            return {"clean": False, "threat": label}

    # 3. VirusTotal hash lookup (only if API key is configured)
    vt_key = os.environ.get("VIRUSTOTAL_API_KEY", "").strip()
    if vt_key:
        vt = await _virustotal_scan(data, filename, vt_key)
        if not vt["clean"]:
            return vt

    return {"clean": True}


async def scan_base64(b64_data: str, filename: str = "upload") -> dict:
    """
    Scan a base64-encoded file.  Decodes first, then calls scan_bytes().

    Returns same dict as scan_bytes().
    """
    try:
        raw = base64.b64decode(b64_data)
    except Exception as exc:
        # Can't decode → not a valid file → let the LLM format check handle it
        logger.warning(
            "[VIRUS_SCAN] base64 decode failed for %s (%s) — skipping scan", filename, exc
        )
        return {"clean": True}
    return await scan_bytes(raw, filename)


# ─────────────────────────────────────────────────────────────────────────────
# VIRUSTOTAL
# ─────────────────────────────────────────────────────────────────────────────

async def _virustotal_scan(data: bytes, filename: str, api_key: str) -> dict:
    """
    Look up the file's SHA-256 hash in VirusTotal's database.

    Flags if:
      - 1+ engines report MALICIOUS
      - 3+ engines report SUSPICIOUS

    Returns {"clean": True} on any network/API error (fail-open).
    """
    file_hash = hashlib.sha256(data).hexdigest()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://www.virustotal.com/api/v3/files/{file_hash}",
                headers={"x-apikey": api_key},
            )

        if resp.status_code == 404:
            # Hash not in VT database — unknown/new file, treat as clean
            return {"clean": True}

        if resp.status_code == 200:
            stats = (
                resp.json()
                .get("data", {})
                .get("attributes", {})
                .get("last_analysis_stats", {})
            )
            malicious  = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)

            if malicious > 0:
                logger.warning(
                    "[VIRUS_SCAN] VirusTotal: %d engine(s) flagged %s as malicious (hash=%s)",
                    malicious, filename, file_hash,
                )
                return {
                    "clean": False,
                    "threat": f"VirusTotal: {malicious} engine(s) flagged this file as malicious",
                }

            if suspicious >= 3:
                logger.warning(
                    "[VIRUS_SCAN] VirusTotal: %d engine(s) flagged %s as suspicious",
                    suspicious, filename,
                )
                return {
                    "clean": False,
                    "threat": f"VirusTotal: {suspicious} engine(s) flagged this file as suspicious",
                }

    except Exception as exc:
        logger.warning(
            "[VIRUS_SCAN] VirusTotal check failed (fail-open) — filename=%s error=%s",
            filename, exc,
        )

    return {"clean": True}
