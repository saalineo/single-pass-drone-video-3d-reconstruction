import base64
import datetime
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_provenance_manifest(
    mission_id: str,
    product_name: str,
    input_hashes: dict,
    software_versions: dict,
    model_shas: dict,
    stage_metrics: dict,
    private_key_bytes: bytes | None = None,
) -> dict:
    """Creates a signed provenance dictionary matching architect/04 §6."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest = {
        "mission_id": mission_id,
        "product": product_name,
        "generated_at": now_utc,
        "inputs": input_hashes,
        "software": software_versions,
        "models": model_shas,
        "stage_metrics": stage_metrics,
        "input_hashes": input_hashes,  # compatibility alias
    }

    # Canonical JSON string for signature
    canonical_payload = json.dumps(manifest, sort_keys=True).encode("utf-8")

    if private_key_bytes:
        priv = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        signature = priv.sign(canonical_payload)
        sig_b64 = base64.b64encode(signature).decode("utf-8")
    else:
        # Default ephemeral pipeline signing key
        priv = ed25519.Ed25519PrivateKey.generate()
        signature = priv.sign(canonical_payload)
        sig_b64 = base64.b64encode(signature).decode("utf-8")

    manifest["signature"] = {
        "alg": "ed25519",
        "signer": "pipeline-identity",
        "sig": sig_b64,
    }
    return manifest
