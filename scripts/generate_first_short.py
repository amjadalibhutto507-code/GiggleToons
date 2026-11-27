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

headers = {"Authorization": f"Bearer {KEY}", "Accept": "application/json", "Content-Type": "application/json"}

def request(url, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Magic Hour API HTTP {e.code}: {detail[:1200]}")

# Read account balance first; no purchases or top-ups are ever attempted.
account = request(f"{BASE}/v1/account")
print("Magic Hour account check completed.")
print("Account response (sensitive fields omitted):", json.dumps({
    k: v for k, v in account.items()
    if any(word in k.lower() for word in ("credit", "plan", "subscription", "balance"))
}, ensure_ascii=False))

prompt = """Create a premium, highly expressive, original 3D animated comedy scene for a family-friendly YouTube Short, vertical 9:16. Two original characters with consistent designs: a tiny chubby orange kitten wearing a slightly oversized blue hoodie, and a clever green parrot with a tiny red cap. Photoreal-quality 3D fur and feathers, cinematic soft studio lighting, richly detailed cozy Pakistani kitchen, realistic physics, expressive eyes and clear readable body language, smooth fluid character animation, dynamic camera push-in, crisp sound design and natural character voices. Start immediately with a strong visual hook: the kitten is secretly dragging an enormous golden fried chicken drumstick across the kitchen counter, much bigger than its body. The parrot suddenly swings into frame and loudly says in natural conversational Pakistani Urdu: 'Oye! Yeh kis ka dinner chura rahe ho?' The kitten freezes, slowly looks straight at camera, then confidently replies in Urdu: 'Main quality check kar raha hoon!' At the exact punchline, the drumstick slips, bounces once, and lands perfectly on the parrot's head like a silly hat. The parrot gives a shocked deadpan stare; kitten bursts into silent giggles. End on a composition and pose that can loop naturally to the opening. Funny, wholesome, instantly understandable visual comedy, excellent lip sync if supported, no subtitles, no captions, no logos, no watermark, no extra limbs, no character morphing, no scene cuts, no copyrighted characters or music."""

payload = {
    "name": "GiggleToons - Quality Check Chicken Prank",
    "end_seconds": 10,
    "aspect_ratio": "9:16",
    "resolution": "480p",
    "model": "ltx-2.5",
    "audio": True,
    "style": {"prompt": prompt}
}

# A fixed idempotency key prevents accidental duplicate charges if this workflow is retried.
idem = "giggletoons-first-short-quality-check-v1"
req = urllib.request.Request(
    f"{BASE}/v1/text-to-video",
    data=json.dumps(payload).encode(),
    headers={**headers, "Idempotency-Key": idem},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=90) as res:
        created = json.loads(res.read().decode())
except urllib.error.HTTPError as e:
    detail = e.read().decode(errors="replace")
    raise SystemExit(f"Generation request rejected (HTTP {e.code}); no video was downloaded. {detail[:1500]}")

project_id = created.get("id")
if not project_id:
    raise SystemExit(f"Magic Hour did not return a project ID: {created}")
print(f"Project created: {project_id}; estimated credits charged: {created.get('credits_charged', 'not reported')}")

for attempt in range(60):
    info = request(f"{BASE}/v1/video-projects/{project_id}")
    status = info.get("status")
    print(f"Render status: {status}")
    if status == "complete":
        downloads = info.get("downloads") or []
        if not downloads or not downloads[0].get("url"):
            raise SystemExit("Render completed but no download URL was returned.")
        video_url = downloads[0]["url"]
        out = Path("output/giggletoons_quality_check_short.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(video_url, out)
        print(f"Saved video: {out}; {out.stat().st_size} bytes; {info.get('width')}x{info.get('height')}; {info.get('credits_charged')} credits.")
        break
    if status in ("error", "canceled"):
        raise SystemExit(f"Magic Hour render {status}: {info.get('error')}")
    time.sleep(20)
else:
    raise SystemExit(f"Timed out waiting for project {project_id}; do not submit a duplicate. Check this project in Magic Hour.")
