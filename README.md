# Tapo Human-Only CCTV (hardened modular version)

This is a revised version of the supplied modular Tapo project. It retains the supplied operating values while fixing the duplicate motion-detector call and improving camera recovery, recording finalization, Drive upload handling, and shutdown.

## Architecture

RTSP camera -> `camera.py` -> `motion.py` -> `human_detector.py` (YOLOv8n) -> `recorder.py` -> queued `drive_uploader.py` -> Google Drive.

`drive_cleanup.py` runs the configured 15-day retention cleanup in a background thread.

## Important configuration choice

The supplied modular `config.py` used camera IP `192.168.1.22`, while the older monolithic `main.py` used `192.168.1.151`. This package preserves the modular value (`192.168.1.22`) as the default. Confirm the actual camera IP before deployment; override it in `.env` if needed.

## Install / update

1. Back up the current project and stop the old service:
   ```bash
   sudo systemctl stop tapo_gate.service
   ```
2. Copy this project into `/home/pramod/Desktop/Work/Tapo` (do not copy credential files from the shared upload).
3. Activate the existing virtual environment and install dependencies:
   ```bash
   cd /home/pramod/Desktop/Work/Tapo
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and set the actual camera IP, username, password, and Drive folder ID:
   ```bash
   cp .env.example .env
   chmod 600 .env
   ```
5. Create a new Google OAuth Desktop/Web client secret after rotating the exposed client secret. Save the new file as `client_secrets.json` in this project directory. Do not reuse the uploaded secret.
6. Complete one-time Google authentication from a local terminal:
   ```bash
   source venv/bin/activate
   set -a
   source .env
   set +a
   python drive_uploader.py --auth
   chmod 600 mycreds.txt client_secrets.json
   ```
   The service itself does not open a browser. If the saved credentials are revoked/invalid, rerun this step.
7. Install the service:
   ```bash
   sudo cp tapo_gate.service /etc/systemd/system/tapo_gate.service
   sudo systemctl daemon-reload
   sudo systemctl enable tapo_gate.service
   sudo systemctl start tapo_gate.service
   ```

## Verify

```bash
sudo systemctl status tapo_gate.service
journalctl -u tapo_gate.service -f
```

Look for `Camera stream connected`, `Human-only Tapo detection started`, `Recording started`, and `Uploaded to Google Drive`.

## Key reliability changes

- `motion.detect(frame)` is called once per fresh frame.
- The RTSP worker reconnects with bounded exponential backoff and only publishes fresh frames.
- RTSP uses TCP by default to reduce packet-loss-related H.264 decode errors on unreliable Wi-Fi.
- YOLO is only invoked after motion is detected.
- VideoWriter open/write lifecycle is checked; files are finalized before upload.
- One upload worker serializes Drive API calls. Upload failures are retried; local files are retained if all attempts fail.
- SIGTERM/SIGINT causes orderly recording finalization and worker shutdown.
- Drive cleanup is isolated from the capture/recording loop.

## Security actions required

The files shared for review contained Google OAuth tokens/client secrets and camera credentials. Treat them as compromised:
- Revoke the exposed Google OAuth token(s) and rotate the OAuth client secret in Google Cloud.
- Change the Tapo camera password.
- Do not copy the uploaded `mycreds.txt`, `old_mycreds.txt`, or `client_secrets.json` into this package.
- Keep `.env`, `mycreds.txt`, and `client_secrets.json` private (`chmod 600`) and out of source control.

## Operational notes

- The RTSP endpoint is configured as `/stream1`, matching the supplied project.
- This package intentionally keeps the modular camera IP default `192.168.1.22`; the old monolithic script used `192.168.1.151`. Confirm which is correct.
- Drive cleanup checks up to 1,000 files returned by the current PyDrive2 list request per run. For a very large folder, use paginated Drive API listing.
- The application does not include push notifications or a web dashboard.


## Live preview when CCTV runs as a systemd daemon

The daemon publishes the latest camera frames on localhost at `http://127.0.0.1:8765/stream` when `ENABLE_LIVE_DISPLAY = 1`. The desktop viewer is a separate process, so minimizing or closing its window does not stop camera monitoring, detection, recording, or uploads.

After extracting this project into its final location, run once from a terminal:

```bash
cd /home/pramod/Desktop/Work/Tapo.New
./install_live_viewer_autostart.sh
```

Restart the existing `tapo_gate.service` once so the daemon starts its preview stream. The viewer will open automatically on the next Ubuntu desktop login. It retries while the daemon is starting. Press `q` or `Esc` in the viewer to close just the preview.
