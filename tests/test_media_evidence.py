"""Ending a call deletes its agentic-capture stills too (herald/api/media.py + herald/capture/reading.py)."""
import threading
from types import SimpleNamespace

from herald.api.media import dispose_incident_media


def _incident(media_ids, facts=()):
    return SimpleNamespace(lock=threading.RLock(), media_ids=media_ids, transcripts=[], facts=list(facts),
                           media_disposal=None, ended_at=None)


def test_registered_evidence_is_deleted_and_other_files_are_kept(tmp_path):
    audio, photo = tmp_path / "audio", tmp_path / "photos"
    evidence = photo / "auto"
    for d in (audio, photo, evidence):
        d.mkdir(parents=True)
    (evidence / "auto_0123456789.jpg").write_bytes(b"x")
    (evidence / "auto_aaaaaaaaaa.jpg").write_bytes(b"other call")
    (photo / "p_0123456789.jpg").write_bytes(b"x")
    inc = _incident({"audio": set(), "photo": {"p_0123456789"}, "evidence": {"auto_0123456789"}})
    out = dispose_incident_media(inc, audio_dir=audio, photo_dir=photo, evidence_dir=evidence)
    assert out["deleted"]["evidence"] == ["auto_0123456789"] and out["deleted"]["photo"] == ["p_0123456789"]
    assert not (evidence / "auto_0123456789.jpg").exists()
    assert (evidence / "auto_aaaaaaaaaa.jpg").exists()          # never registered to this call: untouched


def test_evidence_referenced_by_a_fact_is_found_even_if_registration_was_missed(tmp_path):
    evidence = tmp_path / "photos" / "auto"
    evidence.mkdir(parents=True)
    (evidence / "auto_bbbbbbbbbb.jpg").write_bytes(b"x")
    fact = SimpleNamespace(provenance=SimpleNamespace(audio_id=None, photo_id="auto_bbbbbbbbbb"), verify=None)
    inc = _incident({"audio": set(), "photo": set()}, [fact])
    out = dispose_incident_media(inc, audio_dir=tmp_path / "a", photo_dir=tmp_path / "photos", evidence_dir=evidence)
    assert out["deleted"]["evidence"] == ["auto_bbbbbbbbbb"]


def test_without_an_evidence_directory_nothing_outside_known_dirs_is_touched(tmp_path):
    inc = _incident({"audio": set(), "photo": set(), "evidence": {"auto_cccccccccc"}})
    out = dispose_incident_media(inc, audio_dir=tmp_path, photo_dir=tmp_path)
    assert out["deleted"]["evidence"] == [] and out["invalid"]["evidence"] == ["auto_cccccccccc"]
