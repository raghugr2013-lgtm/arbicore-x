"""Wave 5 · Evidence Signing — unit tests.

Covers canonical hashing, signer, verifier, algorithm registry, key
rotation, tamper detection, corrupted evidence, missing signatures,
historical verification.
"""
from __future__ import annotations

import base64
import copy
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arbicore.config.signing_config import KeyMaterial, SigningConfig
from arbicore.evidence.bundle import (
    canonical_json,
    evidence_hash,
    new_bundle,
)
from arbicore.evidence.signer import EvidenceSigner, EvidenceVerifier


# ---------- helpers ----------

def _make_key(version: str = "v1") -> KeyMaterial:
    priv = Ed25519PrivateKey.generate()
    sec = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return KeyMaterial(
        version=version,
        algorithm="ed25519",
        secret_b64=base64.b64encode(sec).decode(),
        public_b64=base64.b64encode(pub).decode(),
    )


def _cfg_with(keys, active=None) -> SigningConfig:
    return SigningConfig(
        enabled=True,
        active_key_version=active,
        keys={k.version: k for k in keys},
    )


# ---------- canonical hashing ----------

class TestCanonicalHash:
    def test_deterministic_across_permutations(self):
        a = {"b": 2, "a": 1, "c": [3, 1, 2]}
        b = {"a": 1, "c": [3, 1, 2], "b": 2}
        assert canonical_json(a) == canonical_json(b)

    def test_hash_deterministic(self):
        b = new_bundle("calibration", "m1", {"foo": [1, 2, 3]})
        # Two hashes on the exact same bundle yield same result.
        h1 = evidence_hash(b)
        h2 = evidence_hash(b)
        assert h1 == h2

    def test_hash_ignores_non_hashed_fields(self):
        b1 = new_bundle("calibration", "m1", {"foo": [1, 2]})
        b2 = copy.deepcopy(b1)
        # Change ONLY signature metadata (outside HASHED_FIELDS).
        b2["signature"] = "junk"
        b2["signing_key_version"] = "vX"
        assert evidence_hash(b1) == evidence_hash(b2)

    def test_hash_changes_with_payload(self):
        b1 = new_bundle("calibration", "m1", {"foo": 1})
        b2 = copy.deepcopy(b1)
        b2["payload"]["foo"] = 2
        assert evidence_hash(b1) != evidence_hash(b2)

    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})


# ---------- Signer (happy paths) ----------

class TestSigner:
    def test_unsigned_when_no_active_key(self):
        cfg = SigningConfig()  # active_key_version=None
        s = EvidenceSigner(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        out = s.sign_bundle(b)
        assert out["signature"] is None
        assert out["verification_status"] == "unsigned"
        assert out["unsigned_reason"]

    def test_sign_and_verify_roundtrip(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        v = EvidenceVerifier(cfg)
        b = new_bundle("calibration", "m1", {"foo": [1, 2]})
        signed = s.sign_bundle(b)
        assert signed["signature"]
        assert signed["verification_status"] == "signed"
        r = v.verify(signed)
        assert r["verified"] is True
        assert r["algorithm"] == "ed25519"

    def test_sign_is_deterministic(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        b = new_bundle("calibration", "m1", {"foo": [1, 2]},
                       created_at="2026-01-01T00:00:00+00:00")
        # Ed25519 signatures ARE deterministic per RFC 8032.
        out1 = s.sign_bundle(b)
        out2 = s.sign_bundle(dict(b))  # identical input
        assert out1["signature"] == out2["signature"]

    def test_stats_counters(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        s.sign_bundle(b)
        s.sign_bundle(b)
        assert s.stats["success_count"] == 2
        assert s.stats["failure_count"] == 0
        assert s.stats["last_signed_at"] is not None

    def test_signing_failure_isolated(self):
        # Corrupt the secret bytes so sign() raises internally.
        k = KeyMaterial(version="v1", algorithm="ed25519",
                        secret_b64="not_base64!", public_b64=None)
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        out = s.sign_bundle(b)
        # No raise; bundle marked unsigned + counter incremented.
        assert out["signature"] is None
        assert out["verification_status"] == "unsigned"
        assert s.stats["failure_count"] == 1

    def test_unknown_algorithm_falls_back_unsigned(self):
        k = KeyMaterial(version="v1", algorithm="future_algo",
                        secret_b64=base64.b64encode(b"\x00" * 32).decode(),
                        public_b64=base64.b64encode(b"\x00" * 32).decode())
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        out = s.sign_bundle(b)
        assert out["signature"] is None
        assert "no backend" in (out["unsigned_reason"] or "")


# ---------- Verifier (tamper + rotation + missing) ----------

class TestVerifier:
    def test_tamper_detected_via_hash(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        v = EvidenceVerifier(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        signed = s.sign_bundle(b)
        tampered = copy.deepcopy(signed)
        tampered["payload"]["foo"] = 999
        r = v.verify(tampered)
        assert r["verified"] is False
        assert r["bundle_hash_matches"] is False
        assert "mutated" in r["reason"]

    def test_signature_forgery_fails(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        v = EvidenceVerifier(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        b["signing_algorithm"] = "ed25519"
        b["signing_key_version"] = "v1"
        b["signature"] = base64.b64encode(b"\x00" * 64).decode()
        b["evidence_hash"] = evidence_hash(b)
        r = v.verify(b)
        assert r["verified"] is False

    def test_unsigned_bundle_returns_reason(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        v = EvidenceVerifier(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        r = v.verify(b)
        assert r["verified"] is False
        assert r["reason"] == "unsigned"

    def test_missing_metadata_reports_reason(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        v = EvidenceVerifier(cfg)
        b = new_bundle("calibration", "m1", {"foo": 1})
        b["signature"] = base64.b64encode(b"\x00" * 64).decode()
        b["evidence_hash"] = evidence_hash(b)
        # Missing signing_algorithm / signing_key_version.
        r = v.verify(b)
        assert r["verified"] is False
        assert "metadata missing" in r["reason"]

    def test_historical_verifies_after_rotation(self):
        # v1 signs a bundle; then v2 becomes active; v1 must still verify.
        k1 = _make_key("v1")
        cfg1 = _cfg_with([k1], active="v1")
        s1 = EvidenceSigner(cfg1)
        b = new_bundle("calibration", "m1", {"foo": [1, 2, 3]})
        signed = s1.sign_bundle(b)

        # Rotate: add v2, mark active, but keep v1 registered (public
        # material only — as per production key-rotation flow).
        k2 = _make_key("v2")
        k1_pub_only = KeyMaterial(version="v1", algorithm="ed25519",
                                  secret_b64=None, public_b64=k1.public_b64)
        cfg2 = _cfg_with([k1_pub_only, k2], active="v2")
        v2 = EvidenceVerifier(cfg2)
        r = v2.verify(signed)
        assert r["verified"] is True
        assert r["key_version"] == "v1"

    def test_missing_key_after_purge(self):
        # If v1 is purged entirely (public half removed), historical
        # bundles cannot be verified — they report a clear reason.
        k1 = _make_key("v1")
        cfg1 = _cfg_with([k1], active="v1")
        s1 = EvidenceSigner(cfg1)
        b = new_bundle("calibration", "m1", {"foo": 1})
        signed = s1.sign_bundle(b)

        cfg2 = _cfg_with([_make_key("v2")], active="v2")
        v = EvidenceVerifier(cfg2)
        r = v.verify(signed)
        assert r["verified"] is False
        assert "v1" in r["reason"]

    def test_corrupted_bundle_survives_verification(self):
        v = EvidenceVerifier(SigningConfig())
        # Missing required fields — must not raise.
        r = v.verify({})
        assert r["verified"] is False
        assert "unsigned" in r["reason"]


# ---------- Bundle roundtrip ----------

class TestBundleRoundtrip:
    def test_hash_carries_through_json_serialization(self):
        k = _make_key("v1")
        cfg = _cfg_with([k], active="v1")
        s = EvidenceSigner(cfg)
        v = EvidenceVerifier(cfg)
        b = new_bundle("adaptive_weights", "aw-1",
                       {"mode": "OBSERVE", "recommendations": [
                           {"signal_id": "x", "recommended_weight": 1.23},
                       ]})
        signed = s.sign_bundle(b)
        # Serialise + deserialise as we would over HTTP.
        wire = json.loads(json.dumps(signed))
        r = v.verify(wire)
        assert r["verified"] is True
