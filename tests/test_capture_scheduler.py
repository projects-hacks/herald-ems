from herald.capture.config import capture_config
from herald.capture.scheduler import CaptureScheduler


def test_rate_single_flight_manual_and_speech_priority():
    scheduler = CaptureScheduler(capture_config()["rate"])
    assert not scheduler.acquire(0, speech_busy=True)
    assert scheduler.acquire(0)
    assert not scheduler.acquire(1, manual=True)
    scheduler.release()
    assert not scheduler.acquire(9)
    assert not scheduler.acquire(9, manual=True, speech_busy=True)
    assert scheduler.acquire(9, manual=True)
    scheduler.release()
    assert scheduler.acquire(10)
