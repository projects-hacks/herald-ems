"""Single-flight token admission. Speech wins; manual requests bypass only the rate bucket."""


class CaptureScheduler:
    def __init__(self, config: dict):
        self.config = config
        self.next_auto = float("-inf")
        self.in_flight = False

    def acquire(self, now: float, *, manual=False, speech_busy=False) -> bool:
        if self.in_flight or (self.config["skip_while_speech"] and speech_busy):
            return False
        if not manual and now < self.next_auto:
            return False
        self.in_flight = True
        if not manual:
            self.next_auto = now + 1 / self.config["auto_calls_per_s"]
        return True

    def release(self):
        self.in_flight = False
