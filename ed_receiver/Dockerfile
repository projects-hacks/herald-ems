# Mock ED receiver: plain FastAPI, no AI, no GPU. Meant to run on a DIFFERENT machine/network from the Nano so
# the link between the two can be degraded for real (ed_receiver/app.py docstring). Any arch, any box.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

# The receiver labels keys, lays out the board and colours vitals from the reviewed config, and builds the
# received-data report with herald's pure-Python vocabulary/scoring/reporting modules (no model, no GPU, no extra
# pip dependency): /api/meta, /api/handoff and /ingest need both directories.
COPY config/ config/
COPY herald/ herald/
COPY ed_receiver/ ed_receiver/

ENV PORT=8200
EXPOSE 8200

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/state', timeout=3)" || exit 1

CMD ["sh", "-c", "python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port ${PORT}"]
