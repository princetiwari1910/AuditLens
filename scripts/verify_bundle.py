#!/usr/bin/env python3
"""Tamper-evident evidence bundle verification script for AuditLens (WP7).

Validates the cryptographic integrity of an AuditLens evidence bundle ZIP:
- Computes SHA-256 for all bundled records, frames, and overlays.
- Confirms digests match manifest.json.
- Verifies manifest_hash matches canonical files mapping.
- Reports any altered, tampered, or missing files.

NOTE: Cryptographic verification guarantees data integrity; it does NOT certify legal compliance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile


def verify_bundle(zip_path: str | Path) -> tuple[bool, str]:
    """
    Verify integrity of an evidence bundle ZIP archive.
    Returns (is_valid, report_message).
    """
    path = Path(zip_path)
    if not path.exists():
        return False, f"❌ File not found: {path}"

    try:
        with zipfile.ZipFile(path, "r") as zf:
            namelist = zf.namelist()
            if "manifest.json" not in namelist:
                return False, "❌ Invalid bundle: manifest.json is missing from root of archive."

            manifest_bytes = zf.read("manifest.json")
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except Exception as exc:
                return False, f"❌ Malformed manifest.json: {exc}"

            files_map = manifest.get("files", {})
            if not files_map:
                return False, "❌ Empty or missing 'files' mapping in manifest.json."

            # Verify manifest_hash
            canonical_str = json.dumps(files_map, sort_keys=True)
            expected_manifest_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            recorded_manifest_hash = manifest.get("manifest_hash")
            if recorded_manifest_hash != expected_manifest_hash:
                return False, (
                    f"❌ Tampered manifest detected! Recorded manifest_hash '{recorded_manifest_hash}' "
                    f"does not match computed hash '{expected_manifest_hash}'."
                )

            # Check every file recorded in manifest
            mismatches: list[str] = []
            for filename, expected_sha in files_map.items():
                if filename not in namelist:
                    mismatches.append(f"Missing file: '{filename}'")
                    continue

                actual_bytes = zf.read(filename)
                actual_sha = hashlib.sha256(actual_bytes).hexdigest()
                if actual_sha != expected_sha:
                    mismatches.append(
                        f"Checksum mismatch for '{filename}': expected {expected_sha[:12]}..., got {actual_sha[:12]}..."
                    )

            if mismatches:
                details = "\n  - " + "\n  - ".join(mismatches)
                return False, f"❌ Bundle integrity check FAILED (tampering or corruption detected):{details}"

            audit_id = manifest.get("audit_id", "unknown")
            gen_time = manifest.get("generated_at", "unknown")
            disclaimer = manifest.get("disclaimer", "")

            msg = (
                f"✅ Bundle verified successfully.\n"
                f"  - Audit ID: {audit_id}\n"
                f"  - Generated: {gen_time}\n"
                f"  - Files Verified: {len(files_map)} files (SHA-256 match)\n"
                f"  - Legal Disclaimer: {disclaimer}"
            )
            return True, msg

    except zipfile.BadZipFile:
        return False, f"❌ Not a valid ZIP archive: {path}"
    except Exception as exc:
        return False, f"❌ Unexpected error during verification: {exc}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_bundle.py <path-to-bundle.zip>", file=sys.stderr)
        sys.exit(2)

    bundle_path = sys.argv[1]
    valid, message = verify_bundle(bundle_path)
    print(message)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
