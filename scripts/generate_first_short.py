import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "https://api.magichour.ai"
KEY = os.environ.get("MAGIC_HOUR_API_KEY")
if not KEY:
    raise SystemExit("Missing MAGIC_HOUR_API_KEY GitHub Actions secret.")

headers = {
    "Authorization": f"Bearer {KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def request(url, method="GET", data=None, extra_headers=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url, data=body, headers={**headers, **(extra_headers or {})}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Magic Hour API HTTP {exc.code}: {detail[:1200]}")

# Always inspect the account before any generation request.
account = request(f"{BASE}/v1/account")
print("Magic Hour account check completed.")
print("Credit/plan fields:", json.dumps({
    k: v for k, v in account.items()
    if any(word in k.lower() for word in ("credit", "plan", "subscription", "balance"))
}, ensure_ascii=False))

if os.environ.get("ALLOW_MAGIC_HOUR_CREDITS", "").lower() != "true":
    print("SAFE STOP: account checked; no generation request was sent and no credits were used.")
    sys.exit(0)

duration = int(os.environ.get("VIDEO_DURATION_SECONDS", "5"))
if duration not in (5, 10):
    raise SystemExit("VIDEO_DURATION_SECONDS must be 5 or 10.")

# LTX-2.5 480p estimate: 24 credits/second. API remains the final authority.
estimated_cost = duration * 24
balance = account.get("credits", account.get("credit_balance", account.get("balance")))
if isinstance(balance, (int, float)) and balance < estimated_cost:
    raise SystemExit(
        f"Safe stop: estimated {estimated_cost} credits needed, account reports {balance}. "
        "No generation request was sent."
    )

prompt = Path("scripts/viral_short_prompt.txt").read_text(encoding="utf-8").strip()
payload = {
    "name": "GiggleToons - Billi Doctor Aur Hichki Wala Puppy",
    "end_seconds": duration,
    "aspect_ratio": "9:16",
    "resolution": "480p",
    "model": "ltx-2.5",
    "audio": True,
    "style": {"prompt": prompt},
}

run_id = os.environ.get("GITHUB_RUN_ID", str(int(time.time())))
idempotency_key = f"giggletoons-billi-doctor-hiccups-{duration}s-run-{run_id}"
created = request(
    f"{BASE}/v1/text-to-video",
    method="POST",
    data=payload,
    extra_headers={"Idempotency-Key": idempotency_key},
)

project_id = created.get("id")
if not project_id:
    raise SystemExit(f"Magic Hour did not return a project ID: {created}")

print(
    f"Project created: {project_id}; estimated cost: {estimated_cost}; "
    f"API-reported charge: {created.get('credits_charged', 'not reported')}"
)

for attempt in range(60):
    info = request(f"{BASE}/v1/video-projects/{project_id}")
    status = info.get("status")
    print(f"Render status: {status}")
    if status == "complete":
        downloads = info.get("downloads") or []
        if not downloads or not downloads[0].get("url"):
            raise SystemExit("Render completed but Magic Hour returned no download URL.")
        output = Path("output/giggletoons_billi_doctor_hiccups_short.mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(downloads[0]["url"], output)
        print(
            f"Saved video: {output}; {output.stat().st_size} bytes; "
            f"{info.get('width')}x{info.get('height')}; "
            f"API-reported charge: {info.get('credits_charged', 'not reported')}"
        )
        print("IMPORTANT: inspect the downloaded MP4 for Urdu audio clarity and watermark before publishing.")
        break
    if status in ("error", "canceled"):
        raise SystemExit(f"Magic Hour render {status}: {info.get('error')}")
    time.sleep(20)
else:
    raise SystemExit(
        f"Timed out waiting for project {project_id}. Check this project in Magic Hour; "
        "do not submit a duplicate generation."
    )
