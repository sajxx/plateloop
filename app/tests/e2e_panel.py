"""Browser test of the whole control panel (Playwright, system Chromium).

    .venv/bin/python app/tests/e2e_panel.py            # safe: never starts or stops the paid endpoint, never touches data it did not create
    .venv/bin/python app/tests/e2e_panel.py --live     # also starts the endpoint from the UI, sends images, stops it, waits for retraining
                                                       # (do not use the panel yourself while this runs)

The panel must already be running (scripts/panel.sh). Test data is created under ids starting "pw-" and removed afterwards.
Writes app/tests/last_run.json and screenshots of failures to app/.shots/.
"""
import base64
import json
import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ["AWS_CONFIG_FILE"] = str(ROOT / ".aws" / "config")
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(ROOT / ".aws" / "credentials")
os.environ.update(AWS_PROFILE="mlops", AWS_REGION="ap-southeast-2", AWS_DEFAULT_REGION="ap-southeast-2")

import boto3  # noqa: E402
import yaml  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

URL = "http://127.0.0.1:8000"
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
BUCKET, P = CFG["aws"]["bucket"], CFG["project"]
OFFLINE = "--live" not in sys.argv
ONLY = next((a.split("=", 1)[1].lower() for a in sys.argv if a.startswith("--only=")), "")
SHOTS = ROOT / "app" / ".shots"
SHOTS.mkdir(exist_ok=True)

sess = boto3.Session(profile_name="mlops", region_name="ap-southeast-2")
s3, sm, ddb = sess.client("s3"), sess.client("sagemaker"), sess.resource("dynamodb")
REQ, STATE = ddb.Table(f"{P}-requests"), ddb.Table(f"{P}-state")
SK_IMAGE = "783357654285.dkr.ecr.ap-southeast-2.amazonaws.com/sagemaker-scikit-learn:1.4-2-cpu-py3"

results = []
issues = []          # console errors, page errors, failed API calls seen during the run


def api(path):
    import urllib.request
    req = urllib.request.Request(f"{URL}/api/{path}", headers={"X-PlateLoop": "1"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def check(name, fn, *a):
    if ONLY and ONLY not in name.lower():
        return
    t = time.time()
    try:
        note = fn(*a)
        results.append({"name": name, "ok": True, "note": note or "", "s": round(time.time() - t, 1)})
        print(f"  PASS  {name}" + (f"  [{note}]" if note else ""), flush=True)
    except Exception as e:
        try:
            page.screenshot(path=str(SHOTS / ("FAIL-" + "".join(c if c.isalnum() else "_" for c in name)[:50] + ".png")))
        except Exception:
            pass
        msg = str(e).strip().splitlines()[0][:300] if str(e).strip() else repr(e)
        results.append({"name": name, "ok": False, "note": msg, "s": round(time.time() - t, 1)})
        print(f"  FAIL  {name}  -> {msg}", flush=True)
        if os.environ.get("TRACE"):
            traceback.print_exc()


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


_nav = [0]


def goto(route):
    """Load a fresh document (a hash-only change would reuse stale page state) and wait for the page to render."""
    _nav[0] += 1
    page.goto(f"{URL}/?n={_nav[0]}#/{route}")
    page.wait_for_selector(f'#nav a[data-id="{route}"].on', timeout=30000)
    page.wait_for_function("document.querySelector('#page') && !document.querySelector('#page .spinner')", timeout=30000)
    page.wait_for_timeout(300)


def title():
    return page.inner_text("#title")


def toast_text(timeout=8000):
    page.wait_for_selector("#toasts .toast", timeout=timeout)
    return page.inner_text("#toasts .toast:last-child")


def card(heading):
    return page.locator(".card", has=page.locator("h2", has_text=heading)).last


def canvas_sig():
    return page.evaluate("document.querySelector('.imgbox canvas').toDataURL()")


def wait_canvas():
    page.wait_for_function("(() => { const b = document.querySelector('.imgbox'); return b && b.style.display === 'inline-block' && document.querySelector('.imgbox canvas').width !== 300; })()", timeout=20000)
    page.wait_for_timeout(300)


def no_toast(ms=1500):
    page.wait_for_timeout(ms)
    need(page.locator("#toasts .toast").count() == 0, "a toast appeared after cancelling: " + (page.inner_text("#toasts") if page.locator("#toasts .toast").count() else ""))


def count_rects(stroke):
    return page.evaluate("""(c) => [...document.querySelectorAll('.imgbox svg rect')].filter(r => r.getAttribute('stroke') === c).length""", stroke)


# ---------------------------------------------------------------- test data
val = json.load(open(ROOT / "data/original/val.json"))
gold_ann = json.load(open(ROOT / "golden/annotations.json"))
gold_files = {i["file_name"] for i in gold_ann["images"]}
clean = set(json.load(open(ROOT / "report/experiments/clean_holdout_ids.json"))["clean_ids"])
pool = [i for i in val["images"] if i["id"] in clean and i["file_name"] not in gold_files]
boxes_of = {}
for a in val["annotations"]:
    x, y, w, h = a["bbox"]
    boxes_of.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
pool = [i for i in pool if i["id"] in boxes_of][:8]
PHOTO = ROOT / "data/original/images" / pool[0]["file_name"]


def seed_review(n=4):
    ids = []
    for k in range(n):
        im, iid = pool[k + 1], f"pw-review-{k}"
        key = f"raw/test/{iid}.jpg"
        s3.upload_file(str(ROOT / "data/original/images" / im["file_name"]), BUCKET, key)
        live = boxes_of[im["id"]]
        nova = [[b[0] + 6, b[1] + 4, b[2] + 9, b[3] + 5] for b in live]
        rec = {"image_id": iid, "s3_key": key, "width": im["width"], "height": im["height"], "status": "quarantined",
               "boxes": [], "live": live, "nova": nova}
        s3.put_object(Bucket=BUCKET, Key=f"quarantine/{iid}.json", Body=json.dumps(rec))
        REQ.put_item(Item={"image_id": iid, "s3_key": key, "ts": "2026-01-01T00:00:00+00:00", "label_status": "quarantined",
                           "detections": "[]", "n_detections": 0, "top_confidence": "0", "model_version": "v1",
                           "brightness": "0", "blur_score": "0"})
        ids.append(iid)
    return ids


def cleanup_pw():
    for r in REQ.scan()["Items"]:
        if r["image_id"].startswith("pw-") or r.get("s3_key", "").startswith("raw/test/pw-"):
            REQ.delete_item(Key={"image_id": r["image_id"]})
    for pre in ("raw/test/pw-", "labels/auto/pw-", "quarantine/pw-"):
        for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=pre).get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=o["Key"])


MINE = []            # request ids this run created through the UI; only these are ever deleted


def cleanup_mine():
    for iid in MINE:
        item = REQ.get_item(Key={"image_id": iid}).get("Item")
        REQ.delete_item(Key={"image_id": iid})
        for k in ([item["s3_key"]] if item and item.get("s3_key") else []) + [f"labels/auto/{iid}.json", f"quarantine/{iid}.json"]:
            s3.delete_object(Bucket=BUCKET, Key=k)
    MINE.clear()


# ================================================================= tests
def t_shell():
    page.goto(URL + "/")
    page.wait_for_selector("#nav a")
    names = page.locator("#nav a").all_inner_texts()
    names = [n.split("\n")[0].strip() for n in names]
    need(names == ["Overview", "Detect", "Gallery", "Requests", "Label review", "Retraining", "Models", "Monitoring", "Evaluation", "Logs"], f"nav = {names}")
    page.wait_for_selector("#sidefoot .pill")
    foot = page.inner_text("#sidefoot")
    need("ap-southeast-2" in foot and "2462" in foot, "footer missing region/account: " + foot.replace("\n", " "))
    need(page.title() == "License Plate MLOps Console", "page title")


def t_nav_each():
    titles = {"overview": "Overview", "detect": "Detect", "gallery": "Gallery", "requests": "Requests", "review": "Label review", "retrain": "Retraining",
              "models": "Models", "monitoring": "Monitoring", "evaluation": "Evaluation", "logs": "Logs"}
    for rid, t in titles.items():
        page.click(f'#nav a[data-id="{rid}"]')
        page.wait_for_function(f"document.querySelector('#title').textContent === {json.dumps(t)}")
        page.wait_for_function("!document.querySelector('#page .spinner')", timeout=30000)
        need(page.locator(f'#nav a[data-id="{rid}"].on').count() == 1, f"{rid} not highlighted")
        need(page.url.endswith("#/" + rid), "url hash for " + rid)
        need(not page.locator("#page .banner.red").count(), f"{rid} shows an error banner: " + (page.locator("#page .banner.red").first.inner_text() if page.locator("#page .banner.red").count() else ""))
    return "10 pages"


def t_deeplink():
    page.goto(URL + "/#/models")
    page.wait_for_function("document.querySelector('#title').textContent === 'Models'")
    page.goto(URL + "/#/nope")
    page.wait_for_function("document.querySelector('#title').textContent === 'Overview'")
    need(page.locator("#nav a.on").inner_text().startswith("Overview"), "fallback highlight")


def t_overview():
    goto("overview")
    ov = api("overview")
    kp = page.locator(".g4 > .card.kpi")
    need(kp.count() == 4, f"{kp.count()} KPI tiles")
    vals = [kp.nth(i).locator(".v").inner_text() for i in range(4)]
    need(vals[0] == str(ov["requests_total"]), f"images processed {vals[0]} vs {ov['requests_total']}")
    need(vals[2] == str(ov["quarantine"]), f"review KPI {vals[2]} vs {ov['quarantine']}")
    ep = card("Detector endpoint")
    need(ov["endpoint"]["status"] in ("Off", "InService", "Creating", "Deleting", "Updating"), "unknown status")
    need(ov["api_url"] in ep.inner_text(), "API URL not shown")
    rows = card("Deployed stacks").locator("tbody tr")
    need(rows.count() == 6, f"{rows.count()} stacks listed (want 6)")
    bad = [r for r in rows.all_inner_texts() if "COMPLETE" not in r.upper() or "ROLLBACK" in r.upper()]
    need(not bad, f"unhealthy stack rows {bad}")
    need(card("Alarms").locator("tbody tr").count() == 4, "alarm rows")
    need("$" in card("Monthly budget").inner_text() and "of $20" in card("Monthly budget").inner_text(), "budget card")
    return f"endpoint {ov['endpoint']['status']}, {ov['requests_total']} images"


def t_overview_links():
    goto("overview")
    card("Retraining").get_by_text("Open →").click()
    page.wait_for_function("document.querySelector('#title').textContent === 'Retraining'")
    goto("overview")
    card("Alarms").get_by_text("Open →").click()
    page.wait_for_function("document.querySelector('#title').textContent === 'Monitoring'")


def t_stale_render():
    """Leaving a page while its data is still loading must not let it overwrite the page you moved to."""
    delay = "(() => { const f = window.fetch; window.fetch = (u, o) => /\\/api\\/(overview|retrain|models|monitoring|requests)/.test(String(u)) ? new Promise(r => setTimeout(r, 2500)).then(() => f(u, o)) : f(u, o); })()"
    marks = {"detect": ".drop", "gallery": ".thumbs", "requests": "select", "review": "text=Pictures where the two models disagreed", "retrain": ".steps, .empty",
             "models": "text=Registered versions", "monitoring": "text=Top confidence", "evaluation": "text=Accuracy by evaluation set", "logs": ".logbox"}
    ctx2 = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx2.new_page(); pg.add_init_script(delay)
    bad = []
    try:
        for src in ("overview", "retrain", "monitoring"):
            for dst, marker in marks.items():
                if dst == src:
                    continue
                pg.goto(f"{URL}/?s={src}{dst}#/{src}")
                pg.wait_for_selector(f'#nav a[data-id="{src}"].on')
                pg.click(f'#nav a[data-id="{dst}"]')                      # leave while the slow request is in flight
                try:
                    pg.wait_for_selector(marker, timeout=15000)               # the page we moved to has rendered
                except Exception:
                    bad.append(f"{src}->{dst}: expected content never appeared"); continue
                pg.wait_for_timeout(3200)                                     # the old request lands after this (it was 2.5 s)
                txt = pg.inner_text("#page")
                foreign = {"overview": "Deployed stacks", "retrain": "Run history", "models": "Registered versions", "monitoring": "Share of images with no plate", "requests": "No requests match"}[src]
                titles = {"detect": "Detect", "gallery": "Gallery", "requests": "Requests", "review": "Label review", "retrain": "Retraining", "models": "Models", "monitoring": "Monitoring", "evaluation": "Evaluation", "logs": "Logs"}
                if foreign in txt and foreign not in {"models": "Registered versions", "monitoring": "Share of images with no plate", "requests": "No requests match", "retrain": "Run history"}.get(dst, ""):
                    bad.append(f"{src}->{dst}: overwritten by '{foreign}'")
                elif pg.locator(marker).count() == 0:
                    bad.append(f"{src}->{dst}: content replaced after rendering")
                elif pg.inner_text("#title") != titles[dst]:
                    bad.append(f"{src}->{dst}: wrong title")
    finally:
        ctx2.close()
    need(not bad, "stale page overwrote the new one: " + "; ".join(bad[:6]))
    return "27 slow-navigation combinations"


def t_start_dismissed():
    goto("overview")
    if api("overview")["endpoint"]["status"] != "Off":
        return "skipped (endpoint not off)"
    msgs = []
    page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
    page.get_by_role("button", name="Start endpoint").click()
    page.wait_for_timeout(1500)
    need(msgs and "5–10 minutes" in msgs[0] and "$0.10" in msgs[0], "confirm text: " + str(msgs))
    need(api("overview")["endpoint"]["status"] == "Off", "endpoint started although the dialog was dismissed")
    no_toast(0)
    need(page.get_by_role("button", name="Start endpoint").is_enabled(), "button should be usable again after cancelling")


def t_detect_controls():
    goto("detect")
    sel = page.locator("select").first
    opts = sel.locator("option").count()
    need(opts == 151, f"{opts} sample options (want 150 + placeholder)")
    need(page.get_by_role("button", name="Detect plates").is_disabled(), "detect enabled before an image is chosen")
    # sample with ground truth
    g = next(i for i in api("golden")["items"] if len(i["gt"]) == 1)
    sel.select_option(g["file"])
    wait_canvas()
    need(count_rects("#16a34a") == 1, f"ground-truth boxes drawn: {count_rects('#16a34a')}")
    box = page.locator("#saveBox")
    need(box.is_disabled() and not box.is_checked(), "golden sample must not be savable")
    need("never saved" in page.inner_text("#saveNote"), "golden note")
    off = api("endpoint")["status"] == "Off"
    btn = page.get_by_role("button", name="Detect plates")
    if off:
        need(btn.is_disabled() and "Start the detector above first" in page.inner_text("#whyDisabled"), "detect must be locked while the endpoint is off, with a reason")
    # sliders really repaint the canvas
    base = canvas_sig()
    rng = page.locator('input[type="range"]')
    need(rng.count() == 3, "three sliders")
    rng.nth(0).fill("0.3"); page.wait_for_timeout(300)
    dark = canvas_sig(); need(dark != base, "brightness did nothing")
    rng.nth(1).fill("5"); page.wait_for_timeout(300)
    blur = canvas_sig(); need(blur != dark, "blur did nothing")
    rng.nth(2).fill("40"); page.wait_for_timeout(300)
    noisy = canvas_sig(); need(noisy != blur, "noise did nothing")
    need(page.locator(".slider .mono").nth(0).inner_text() == "0.30", "brightness label")
    page.get_by_role("button", name="Reset").click(); page.wait_for_timeout(400)
    need(canvas_sig() == base, "reset did not restore the image")
    need(rng.nth(0).input_value() == "1" and rng.nth(1).input_value() == "0" and rng.nth(2).input_value() == "0", "reset values")
    return "sliders repaint + reset"


def t_detect_upload():
    goto("detect")
    page.set_input_files('input[type="file"]', str(PHOTO))
    wait_canvas()
    box = page.locator("#saveBox")
    need(box.is_enabled() and box.is_checked(), "uploads should default to Save")
    need("monitoring" in page.inner_text("#saveNote"), "upload note")
    need(count_rects("#16a34a") == 0, "no ground truth for uploads")
    box.uncheck(); need(not box.is_checked(), "checkbox toggles")


def t_detect_drop():
    goto("detect")
    b64 = base64.b64encode(PHOTO.read_bytes()).decode()
    page.evaluate("""(b64) => { const bin = atob(b64), arr = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const dt = new DataTransfer(); dt.items.add(new File([arr], 'drop.jpg', {type: 'image/jpeg'}));
      const el = document.querySelector('.drop'); el.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true})); window.__over = el.classList.contains('over');
      el.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""", b64)
    need(page.evaluate("window.__over"), "drop zone did not highlight on dragover")
    wait_canvas()


def t_detect_offline():
    goto("detect")
    if api("endpoint")["status"] != "Off":
        return "skipped (endpoint not off)"
    strip = page.locator("#page .card").first
    need("Off" in strip.inner_text() and "switched off" in strip.inner_text(), "strip should say the detector is off")
    need(strip.get_by_role("button", name="Start endpoint").is_visible(), "start button in the strip")
    page.set_input_files('input[type="file"]', str(PHOTO)); wait_canvas()
    need(page.get_by_role("button", name="Detect plates").is_disabled(), "send must stay locked while off")
    need("Start the detector above first" in page.inner_text("#whyDisabled"), "reason shown")
    msgs = []
    page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
    strip.get_by_role("button", name="Start endpoint").click(); page.wait_for_timeout(800)
    need(msgs and "4–6 minutes" in msgs[0], "confirm text")
    need(api("endpoint")["status"] == "Off", "cancel must not start it")
    return "send is locked with a reason; start is confirmable"


def t_failed_send_leaves_nothing():
    """A send while the detector is off is refused and must not leave a stored image or a row behind."""
    import urllib.error
    import urllib.request
    if api("endpoint")["status"] != "Off":
        return "skipped (endpoint not off)"
    before_raw = {o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="raw/").get("Contents", [])}
    key = "img-pwtest-offline-" + str(int(time.time()))
    req = urllib.request.Request(api("overview")["api_url"] + "/predict", data=PHOTO.read_bytes(), method="POST",
                                 headers={"content-type": "image/jpeg", "Idempotency-Key": key})
    try:
        code = urllib.request.urlopen(req, timeout=60).status
    except urllib.error.HTTPError as e:
        code = e.code
    need(code == 503, f"expected 503, got {code}")
    need(REQ.get_item(Key={"image_id": key}).get("Item") is None, "a claim row was left behind")
    after_raw = {o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="raw/").get("Contents", [])}
    need(after_raw == before_raw, f"an image was stored although the send failed: {after_raw - before_raw}")
    bad = urllib.request.Request(api("overview")["api_url"] + "/predict", data=PHOTO.read_bytes(), method="POST", headers={"content-type": "image/jpeg", "Idempotency-Key": "bad key!"})
    try:
        urllib.request.urlopen(bad, timeout=30); c2 = 200
    except urllib.error.HTTPError as e:
        c2 = e.code
    need(c2 == 400, f"malformed key should be refused (got {c2})")
    return "503 leaves no image or row; malformed key refused"


def t_idle_setting():
    goto("overview")
    sel = page.locator("#idleSel")
    need(sel.locator("option").count() == 6, "auto-shutdown options")
    before = api("endpoint")["idle_minutes"]
    try:
        sel.select_option("60")
        need("Auto-shutdown updated" in toast_text(), "toast")
        page.wait_for_function("document.querySelector('#idleSel').value === '60'", timeout=10000)
        need(api("endpoint")["idle_minutes"] == 60, "setting not stored")
        need(page.locator("#idleSel").input_value() == "60", "select should keep the new value")
    finally:
        api_post = __import__("urllib.request").request.Request(URL + "/api/endpoint/idle", data=json.dumps({"minutes": before}).encode(), method="POST", headers={"X-PlateLoop": "1", "Content-Type": "application/json"})
        __import__("urllib.request").request.urlopen(api_post)
    return "stored and restored"


def images_ok():
    """True images, not broken icons: every visible thumbnail decoded."""
    page.wait_for_selector(".thumb img")
    for _ in range(12):                       # thumbnails are lazy-loaded: scroll through the page so all of them load
        page.mouse.wheel(0, 700); page.wait_for_timeout(250)
    page.wait_for_function("[...document.querySelectorAll('.thumb img')].length > 0 && [...document.querySelectorAll('.thumb img')].every(i => i.complete)", timeout=45000)
    page.evaluate("window.scrollTo(0, 0); document.querySelector('main').scrollTo(0, 0)")
    broken = page.evaluate("[...document.querySelectorAll('.thumb img')].filter(i => i.naturalWidth === 0).length")
    if broken:                                # a network blip can kill one request: retry the failed ones once
        page.evaluate("[...document.querySelectorAll('.thumb img')].filter(i => i.naturalWidth === 0).forEach(i => { const u = i.src; i.src = ''; i.src = u; })")
        page.wait_for_timeout(4000)
        broken = page.evaluate("[...document.querySelectorAll('.thumb img')].filter(i => i.naturalWidth === 0).length")
    return broken


def t_gallery():
    goto("gallery")
    tabs = page.locator("#page .row .btn.sm")
    need([t.strip() for t in tabs.all_inner_texts()[:5]] == ["Golden set", "Training set", "Auto-labelled", "Saved uploads", "Retraining data"], "tabs")
    need("150 images" in page.inner_text("#page"), "golden count")
    need(page.locator(".thumb").count() == 48, f"{page.locator('.thumb').count()} thumbnails on page 1")
    need(images_ok() == 0, "broken thumbnails on the golden tab")
    need(page.locator(".thumb svg rect").count() >= 40, "ground-truth boxes missing")
    # paging
    page.get_by_role("button", name="Next →").click(); page.wait_for_selector("text=Page 2 of 4")
    need(page.get_by_role("button", name="← Previous").is_enabled(), "previous enabled on page 2")
    page.get_by_role("button", name="← Previous").click(); page.wait_for_selector("text=Page 1 of 4")
    # search
    page.fill('#actions input[type="text"]', "xemay"); page.wait_for_function("document.querySelectorAll('.thumb').length > 0 && document.querySelectorAll('.thumb').length < 48", timeout=15000)
    need(all("xemay" in t for t in page.locator(".thumb .mono").all_inner_texts()), "search results should all match")
    page.fill('#actions input[type="text"]', ""); page.wait_for_function("document.querySelectorAll('.thumb').length === 48", timeout=15000)
    # viewer with prev/next, arrow keys, close
    page.locator(".thumb").first.click(); page.wait_for_selector("#modal:not([hidden])")
    first = page.inner_text("#modalbox h2")
    need("1 of 150" in page.inner_text("#modalbox"), "viewer counter")
    need(page.locator("#modalbox button", has_text="←").is_disabled(), "prev disabled on first image")
    page.keyboard.press("ArrowRight"); page.wait_for_function(f"document.querySelector('#modalbox h2').textContent !== {json.dumps(first)}")
    need("2 of 150" in page.inner_text("#modalbox"), "arrow key moved on")
    page.locator("#modalbox button", has_text="←").click(); page.wait_for_function(f"document.querySelector('#modalbox h2').textContent === {json.dumps(first)}")
    page.wait_for_function("document.querySelector('#modalbox img') && document.querySelector('#modalbox img').complete && document.querySelector('#modalbox img').naturalWidth > 0", timeout=20000)
    need(page.locator("#modalbox svg rect").count() >= 1, "box overlay in viewer")
    page.keyboard.press("Escape"); page.wait_for_selector("#modal", state="hidden")
    # training set
    page.get_by_role("button", name="Training set").click(); page.wait_for_selector("text=The 2,000 original images")
    need("Page 1 of 42" in page.inner_text("#page"), "training pages")
    need(images_ok() == 0, "broken thumbnails on the training tab")
    # labelled / uploads / run data
    page.get_by_role("button", name="Auto-labelled").click(); page.wait_for_selector("text=Images labelled automatically")
    n_lab = page.locator(".thumb").count()
    page.get_by_role("button", name="Saved uploads").click(); page.wait_for_selector("text=Every image sent through the live system")
    n_raw = page.locator(".thumb").count()
    page.get_by_role("button", name="Retraining data").click(); page.wait_for_selector("text=The exact images and labels a retraining run used")
    n_run = page.locator(".thumb").count()
    if n_run:
        need(page.locator("#actions select").is_visible() and page.locator("#actions select option").count() >= 1, "run selector")
        need(images_ok() == 0, "broken thumbnails on run data")
    return f"golden 150, train 2000, labels shown {n_lab}, uploads {n_raw}, run data {n_run}"


def t_requests_ui():
    goto("requests")
    sel = page.locator("#actions select")
    need(sel.locator("option").count() == 7, "filter options")
    n = page.locator(".thumb").count()
    if n == 0:
        need("No requests match" in page.inner_text("#page"), "empty state")
        return "empty state (0 requests)"
    first = page.locator(".thumb").first
    need(first.locator("svg rect").count() >= 0 and first.locator("img").count() == 1, "thumb content")
    first.click(); page.wait_for_selector("#modal:not([hidden])")
    need("Request" in page.inner_text("#modalbox") and page.locator("#modalbox dl").count() == 1, "modal details")
    page.keyboard.press("Escape"); page.wait_for_selector("#modal", state="hidden")
    first.click(); page.wait_for_selector("#modal:not([hidden])")
    page.get_by_role("button", name="Close").click(); page.wait_for_selector("#modal", state="hidden")
    first.click(); page.wait_for_selector("#modal:not([hidden])")
    page.mouse.click(5, 5); page.wait_for_selector("#modal", state="hidden")
    sel.select_option("no_plate"); page.wait_for_timeout(300)
    need(page.locator(".thumb").count() <= n, "filter increased the count")
    sel.select_option("all")
    return f"{n} thumbnails, modal closes 3 ways, filter ok"


def t_review_empty():
    goto("review")
    need("Nothing waiting for review" in page.inner_text("#page"), "empty state")
    need(not page.locator("#reviewBadge:visible").count(), "badge visible when empty")


def counters_now():
    return {i["key"]: int(i["n"]) for i in STATE.scan()["Items"] if "n" in i}


def t_review_flow():
    cleanup_pw()
    base = counters_now()
    ids = seed_review(4)
    try:
        goto("overview")
        need(page.locator(".g4 > .card.kpi").nth(2).locator(".v").inner_text() == "4", "KPI should read 4")
        page.get_by_text("Review now →").click()
        page.wait_for_function("document.querySelector('#title').textContent === 'Label review'")
        page.wait_for_selector("#page .card img")
        cards = page.locator("#page .grid.g2 > .card")
        need(cards.count() == 4, f"{cards.count()} review cards")
        need(page.evaluate("[...document.querySelectorAll('#page svg rect')].some(r => r.getAttribute('stroke') === '#ea580c')"), "Nova boxes missing")
        need(page.evaluate("[...document.querySelectorAll('#page svg rect')].some(r => r.getAttribute('stroke') === '#2563eb')"), "detector boxes missing")
        page.wait_for_function("document.querySelector('#reviewBadge') && document.querySelector('#reviewBadge').textContent === '4'", timeout=20000)
        want = {}
        for label, action, iid in [("Use detector", "live", ids[0]), ("Use Nova", "nova", ids[1]), ("No plate", "none", ids[2]), ("Discard", "discard", ids[3])]:
            before = page.locator("#page .grid.g2 > .card").count()
            page.locator("#page .grid.g2 > .card").first.get_by_role("button", name=label, exact=True).click()
            need("Saved" in toast_text(), "no toast after " + label)
            page.wait_for_function(f"document.querySelectorAll('#page .grid.g2 > .card').length === {before - 1} || document.querySelector('#page .empty')")
            want[iid] = action
        need("Nothing waiting for review" in page.inner_text("#page"), "empty state after resolving all")
        need(s3.list_objects_v2(Bucket=BUCKET, Prefix="quarantine/pw-").get("KeyCount", 0) == 0, "quarantine not cleared")
        got = {}
        for iid in ids:
            try:
                got[iid] = json.loads(s3.get_object(Bucket=BUCKET, Key=f"labels/auto/{iid}.json")["Body"].read())["status"]
            except Exception:
                got[iid] = None
        need(got[ids[0]] == "accepted_reviewed" and got[ids[1]] == "accepted_reviewed" and got[ids[2]] == "no_plate" and got[ids[3]] is None, f"label files {got}")
        rows = {i: REQ.get_item(Key={"image_id": i})["Item"]["label_status"] for i in ids}
        need(rows[ids[0]] == "accepted_reviewed" and rows[ids[2]] == "no_plate" and rows[ids[3]] == "discarded", f"row statuses {rows}")
        c = counters_now()
        need(c.get("new_labels", 0) - base.get("new_labels", 0) == 3, f"new_labels went {base.get('new_labels', 0)} -> {c.get('new_labels', 0)} (want +3)")
        page.wait_for_function("!document.querySelector('#reviewBadge') || document.querySelector('#reviewBadge').hidden", timeout=20000)
        return "all 4 actions persisted (S3, DynamoDB, counters)"
    finally:
        cleanup_pw()
        for k in ("new_labels", "labels_accepted"):           # put the counters back exactly as they were
            STATE.put_item(Item={"key": k, "n": base.get(k, 0)})


def t_models_flow():
    goto("models")
    need("Live model" in page.inner_text("#page") and "v1" in page.inner_text("#page"), "live model card")
    need("0.761" in page.inner_text("#page"), "baseline text")
    made_group = False
    try:
        sm.describe_model_package_group(ModelPackageGroupName=CFG["release"]["model_group"])
    except Exception:
        sm.create_model_package_group(ModelPackageGroupName=CFG["release"]["model_group"]); made_group = True
    arn = sm.create_model_package(
        ModelPackageGroupName=CFG["release"]["model_group"], ModelApprovalStatus="PendingManualApproval",
        CustomerMetadataProperties={"version": "v99", "run_id": "pw-test", "base_version": "v1", "ap50_live": "0.7610", "ap50_candidate": "0.7900"},
        InferenceSpecification={"Containers": [{"Image": SK_IMAGE, "ModelDataUrl": f"s3://{BUCKET}/models/v1/model.tar.gz"}],
                                "SupportedContentTypes": ["image/jpeg"], "SupportedResponseMIMETypes": ["application/json"]})["ModelPackageArn"]
    try:
        goto("models")
        row = page.locator("tbody tr", has_text="v99")
        need(row.count() == 1, "seeded version not listed")
        need("Awaiting approval" in row.inner_text() and "0.761 → 0.790" in row.inner_text(), "row content: " + row.inner_text().replace("\n", " "))
        msgs = []
        page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
        row.get_by_role("button", name="Approve & deploy").click(); page.wait_for_timeout(1500)
        need(msgs and "v99" in msgs[0], "approve confirm text " + str(msgs))
        no_toast(0)
        need(sm.describe_model_package(ModelPackageName=arn)["ModelApprovalStatus"] == "PendingManualApproval", "approved despite dismiss")
        need(not STATE.get_item(Key={"key": "current_model_version"}).get("Item"), "deploy ran although dismissed")
        row.get_by_role("button", name="Reject").click()
        page.wait_for_selector("#toasts .toast:has-text('Rejected')", timeout=15000)
        page.wait_for_function("document.querySelector('tbody tr') && document.body.innerText.includes('Rejected')", timeout=15000)
        need(sm.describe_model_package(ModelPackageName=arn)["ModelApprovalStatus"] == "Rejected", "reject not persisted")
        return "approve dialog (dismissed safely) + reject persisted"
    finally:
        sm.delete_model_package(ModelPackageName=arn)
        if made_group:
            sm.delete_model_package_group(ModelPackageGroupName=CFG["release"]["model_group"])


def t_retrain_page():
    goto("retrain")
    need(page.locator(".step").count() == 6, "six stages")
    names = [n.strip() for n in page.locator(".step .n").all_inner_texts()]
    need(names == ["Prepare data", "Fine-tune", "Evaluate", "Release rule", "Compare", "Register"], f"stage names {names}")
    need(page.locator("table tbody tr.click").count() >= 2, "run history rows")
    d = api("retrain")
    running = d["lock"].get("status") == "running"
    btn = page.locator("#actions button")
    need(btn.count() == 1, "one header action")
    need(btn.inner_text() == ("Stop run" if running else "Start retraining"), f"header button '{btn.inner_text()}' vs running={running}")
    need("Triggers" in page.inner_text("#page") and "of 200" in page.inner_text("#page"), "trigger card")
    return ("run in progress" if running else "idle") + f", {page.locator('table tbody tr.click').count()} runs"


def t_retrain_history_select():
    goto("retrain")
    rows = page.locator("table tbody tr.click")
    last = rows.nth(rows.count() - 1)
    rid = last.locator("td").first.inner_text()
    last.click()
    page.wait_for_function(f"document.querySelector('#page h2').textContent.includes({json.dumps(rid)})", timeout=15000)
    need(page.locator("table tbody tr.sel").count() == 1, "selected row highlight")
    need(page.locator(".step.failed").count() + page.locator(".step.done").count() + page.locator(".step.running").count() >= 1, "stages coloured")


def t_retrain_start_dismissed():
    goto("retrain")
    if page.locator("#actions button").inner_text() != "Start retraining":
        return "skipped (a run is in progress; Stop deliberately not clicked)"
    before = len(api("retrain")["runs"])
    msgs = []
    page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
    page.locator("#actions button").click(); page.wait_for_timeout(1500)
    need(msgs and "$1" in msgs[0], "confirm text")
    need(len(api("retrain")["runs"]) == before, "run started although dismissed")
    no_toast(0)


def t_monitoring_ui():
    goto("monitoring")
    need(page.locator("#actions select option").count() == 4, "range options")
    need(page.locator(".card .pill").count() >= 4, "alarm tiles")
    for v in ("1", "6", "24", "168"):
        page.locator("#actions select").select_option(v); page.wait_for_timeout(1200)
        need(not page.locator("#page .banner.red").count(), "error after range " + v)
    need("Alarm below 0.7" in page.inner_text("#page"), "confidence note")
    return f"{page.locator('canvas').count()} charts with data"


def t_evaluation_ui():
    goto("evaluation")
    kp = [k.strip() for k in page.locator(".g4 > .card.kpi .v").all_inner_texts()]
    need(kp == ["0.92", "0.77", "0.76", "16.9 ms"], f"KPIs {kp}")
    n = page.evaluate("[...document.querySelectorAll('canvas')].filter(c => Chart.getChart(c)).length")
    need(n == 6, f"{n} charts drawn (want 6)")
    need(page.locator("table tbody tr").count() == 4, "dataset table rows")
    sizes = page.evaluate("[...document.querySelectorAll('canvas')].map(c => c.clientWidth * c.clientHeight)")
    need(all(s > 5000 for s in sizes), f"chart sizes {sizes}")


def t_logs_ui():
    goto("logs")
    sel = page.locator("#actions select").first
    need(sel.locator("option").count() == 8, "log sources")
    minutes = page.locator("#actions select").nth(1)
    minutes.select_option("1440")
    outcomes = {}
    for src in sel.locator("option").all_inner_texts():
        sel.select_option(src); page.wait_for_timeout(900)
        need(not page.locator("#page .banner.red").count(), "error loading " + src)
        outcomes[src] = len(page.locator(".logbox > div").all())
    sel.select_option("training (CodeBuild)"); page.wait_for_timeout(1000)
    find = page.locator('#actions input[type="text"]')
    find.fill("zzzz-nothing-matches"); page.wait_for_timeout(300)
    need("No log lines" in page.inner_text(".logbox"), "filter should empty the list")
    find.fill("")
    live = page.locator('#actions input[type="checkbox"]'); live.uncheck(); need(not live.is_checked(), "live toggle"); live.check()
    return "lines per source: " + ", ".join(f"{k.split(' ')[0]}={v}" for k, v in outcomes.items())


def t_layout():
    problems = []
    for w, h in ((1360, 900), (820, 900)):
        page.set_viewport_size({"width": w, "height": h})
        for rid in ("overview", "detect", "gallery", "requests", "review", "retrain", "models", "monitoring", "evaluation", "logs"):
            goto(rid)
            over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if over > 2:
                problems.append(f"{rid}@{w}: +{over}px")
        if w == 820:
            need(page.locator("#nav").is_visible(), "nav hidden on narrow screens")
            page.click('#nav a[data-id="logs"]'); page.wait_for_function("document.querySelector('#title').textContent === 'Logs'")
    page.set_viewport_size({"width": 1360, "height": 900})
    need(not problems, "horizontal overflow: " + "; ".join(problems))
    return "no overflow at 1360 and 820 px; nav usable when narrow"


def t_security():
    import urllib.error
    import urllib.request

    def status(path, method="GET", data=None, headers=None):
        req = urllib.request.Request(URL + "/api/" + path, data=data, method=method, headers=headers or {})
        try:
            return urllib.request.urlopen(req, timeout=30).status
        except urllib.error.HTTPError as e:
            return e.code
    need(status("endpoint/stop", "POST", b"{}", {"Content-Type": "application/json"}) == 403, "POST without header must be refused")
    need(status("retrain/start", "POST", b"{}") == 403, "retrain start without header must be refused")
    h = {"X-PlateLoop": "1"}
    need(status("image?key=../../etc/passwd", headers=h) == 400, "path traversal")
    need(status("image?key=models/v1/MANIFEST.json", headers=h) == 400, "key outside allowed prefixes")
    need(status("logs?source=nope", headers=h) == 400, "unknown log source")
    need(status("review/..%2Fevil", "POST", b'{"action":"live"}', {**h, "Content-Type": "application/json"}) in (400, 404, 405), "bad review id")
    need(status("models/approval", "POST", b'{"arn":"x","status":"Approved"}', {**h, "Content-Type": "application/json"}) == 400, "bad approval arn")
    need(status("retrain/stop", "POST", b'{"run_id":"a/b"}', {**h, "Content-Type": "application/json"}) == 400, "bad run id")
    return "8 hostile requests refused"


# ---------------------------------------------------------------- endpoint lifecycle
def t_start_endpoint():
    goto("overview")
    need(api("overview")["endpoint"]["status"] == "Off", "endpoint should be off before the lifecycle test")
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Start endpoint").click()
    need("starting" in toast_text().lower(), "start toast")
    page.wait_for_selector(".bar.ind", timeout=20000)
    ep = card("Detector endpoint")
    need("Creating" in ep.inner_text() or "creating" in ep.inner_text().lower(), "status not shown as creating")
    need("elapsed" in ep.inner_text() and "updates by itself" in ep.inner_text(), "progress text")
    page.wait_for_function("document.querySelector('#sidefoot').innerText.includes('Creating')", timeout=30000)
    return "progress bar + elapsed time + sidebar pill"


def wait_running(timeout_s=900):
    t = time.time()
    while time.time() - t < timeout_s:
        if api("overview")["endpoint"]["status"] == "InService":
            return round(time.time() - t)
        time.sleep(15)
    raise AssertionError("endpoint never reached InService")


def t_overview_flips_running():
    goto("overview")
    page.wait_for_function("document.querySelector('#page').innerText.includes('Running') && !document.querySelector('.bar.ind')", timeout=60000)
    need(page.get_by_role("button", name="Stop endpoint").is_visible(), "Stop button missing once running")
    need("Running since" in page.inner_text("#page"), "running-since row")


def t_detect_live_preview():
    goto("detect")
    before_rows = REQ.scan(Select="COUNT")["Count"]
    g = next(i for i in api("golden")["items"] if len(i["gt"]) >= 1)
    page.locator("select").first.select_option(g["file"])
    wait_canvas()
    page.get_by_role("button", name="Detect plates").click()
    page.wait_for_selector(".kpi .l:has-text('Plates found')", timeout=60000)
    n = int(page.locator(".g3 .kpi .v").first.inner_text())
    need(n >= 1, "no plate found on a golden sample")
    need("not saved" in page.inner_text("#page"), "preview label")
    need(count_rects("#2563eb") >= n and count_rects("#16a34a") == len(g["gt"]), f"overlay boxes blue={count_rects('#2563eb')} green={count_rects('#16a34a')}")
    need(page.locator("table tbody tr").count() >= n, "detections table")
    need(REQ.scan(Select="COUNT")["Count"] == before_rows, "preview must not store anything")
    base_conf = api("requests")["total"]
    # drift: darker + blurrier, second run adds to the history table
    rng = page.locator('input[type="range"]'); rng.nth(0).fill("0.2"); rng.nth(1).fill("4"); page.wait_for_timeout(400)
    page.get_by_role("button", name="Detect plates").click()
    page.wait_for_selector("text=Recent runs on this page", timeout=60000)
    need(page.locator("text=Recent runs on this page").count() == 1, "history card")
    return f"{n} plate(s), GT overlay, nothing stored, drift run recorded"


def t_detect_live_saved():
    goto("detect")
    page.set_input_files('input[type="file"]', str(PHOTO))
    wait_canvas()
    need(page.locator("#saveBox").is_checked(), "save should be on")
    before = REQ.scan(Select="COUNT")["Count"]
    btn = page.get_by_role("button", name="Detect plates")
    btn.click()
    need(page.get_by_role("button", name="Sending…").is_disabled(), "button must lock while sending")
    page.wait_for_selector("#tracker")
    page.wait_for_function("document.querySelector('#tracker').innerText.includes('Saved to the system') && document.querySelector('#tracker .row:nth-of-type(3)').innerText.includes('✓')", timeout=90000)
    iid = page.inner_text("dd.mono"); MINE.append(iid)
    need(iid.startswith("img-"), "request id should be the idempotency key: " + iid)
    need(REQ.scan(Select="COUNT")["Count"] == before + 1, "saved image missing from the table")
    page.wait_for_function("document.querySelector('#tracker .row:nth-of-type(4)').innerText.includes('✓')", timeout=150000)
    steps = page.evaluate("[...document.querySelectorAll('#tracker .row')].map(r => r.innerText.replace(/\\s+/g,' ').trim())")
    need(len(steps) == 4 and all(x.startswith("✓") for x in steps), f"tracker steps {steps}")
    need(page.locator("#tracker a[href='#/requests']").count() == 1, "link to Requests")
    # the same image again: recognised, nothing new created
    page.wait_for_function("!document.querySelector('button.btn.primary').textContent.includes('Sending')")
    btn.click()
    page.wait_for_selector("text=already processed", timeout=60000)
    need(REQ.scan(Select="COUNT")["Count"] == before + 1, "a duplicate request was created")
    need(page.locator(".banner", has_text="Process again").count() == 1, "process-again button")
    # process again on purpose: a new request
    page.get_by_role("button", name="Process again as a new request").click()
    page.wait_for_function("document.querySelector('dd.mono') && document.querySelector('dd.mono').textContent !== " + json.dumps(iid), timeout=90000)
    MINE.append(page.inner_text("dd.mono"))
    need(REQ.scan(Select="COUNT")["Count"] == before + 2, "process-again should add exactly one request")
    return "tracker 4/4, duplicate recognised, process-again adds one"


def t_requests_after_save():
    goto("requests")
    page.wait_for_selector(".thumb", timeout=20000)
    need(page.locator(f'.thumb img[src*="{MINE[0]}"]').count() == 1, "the saved image is not listed in Requests")
    need(page.locator(f'.thumb.new').count() >= 1, "new items should be highlighted")
    item = api(f"request/{MINE[0]}")
    need(item["label_status"] != "processing", "request stuck in processing")
    st_ = item["label_status"]
    t = time.time()
    while st_ in ("pending", "processing") and time.time() - t < 150:
        time.sleep(8); st_ = api(f"request/{MINE[0]}")["label_status"]
    need(st_ not in ("pending", "processing"), "labeller did not label the saved image within 150 s")
    goto("gallery"); page.get_by_role("button", name="Saved uploads").click(); page.wait_for_selector("text=Every image sent through the live system")
    page.wait_for_selector(f'.thumb img[src*="{MINE[0]}"]', timeout=20000)
    return f"listed in Requests and Gallery; auto-labelled as '{st_}'"


def t_monitoring_data():
    t = time.time()
    while time.time() - t < 240:
        goto("monitoring")
        if page.locator(".chart canvas").count() >= 4:
            break
        time.sleep(20)
    n = page.locator(".chart canvas").count()
    need(n >= 4, f"only {n} charts have data after 4 minutes")
    return f"{n} charts populated"


def t_logs_live():
    goto("logs")
    page.locator("#actions select").nth(1).select_option("15")
    page.locator("#actions select").first.select_option("ingest"); page.wait_for_timeout(1500)
    need(page.locator(".logbox > div").count() >= 1, "no ingest lines after a request")
    page.locator("#actions select").first.select_option("endpoint"); page.wait_for_timeout(1500)
    return f"endpoint log lines: {page.locator('.logbox > div').count()}"


def t_stop_endpoint():
    goto("overview")
    page.get_by_role("button", name="Stop endpoint").click()
    need("stopping" in toast_text().lower(), "stop toast")
    page.wait_for_function("document.querySelector('#page').innerText.includes('Shutting down') || document.querySelector('#page').innerText.includes('Off')", timeout=30000)
    t = time.time()
    while time.time() - t < 400:
        if api("overview")["endpoint"]["status"] == "Off":
            break
        time.sleep(10)
    need(api("overview")["endpoint"]["status"] == "Off", "endpoint did not shut down")
    goto("overview")
    need(page.get_by_role("button", name="Start endpoint").is_visible(), "Start button should return")


def t_retrain_final():
    t = time.time()
    while time.time() - t < 1500:
        d = api("retrain")
        if d["lock"].get("status") != "running":
            break
        time.sleep(20)
    goto("retrain")
    d = api("retrain")
    need(d["lock"].get("status") != "running", "run still running after 25 minutes")
    det = d["detail"]
    states = page.locator(".step").evaluate_all("els => els.map(e => e.className.replace('step ', ''))")
    outcome = det.get("outcome") or det["status"]
    if det["status"] == "SUCCEEDED":
        need(all(s in ("done", "skipped") for s in states), f"stage states {states}")
        need(page.locator("canvas").count() == 1, "metrics chart missing")
        need("release rule" in page.inner_text("#page").lower(), "rule sentence")
        need(page.locator("text=Training data").count() == 1, "dataset card")
    return f"{det['status']} / {outcome}; stages {states}"


# ================================================================= run
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: issues.append(f"console.{m.type}: {m.text[:200]}") if m.type == "error" else None)
    page.on("pageerror", lambda e: issues.append(f"pageerror: {str(e)[:200]}"))
    page.on("response", lambda r: issues.append(f"HTTP {r.status} {r.url.replace(URL, '')} {r.text()[:300]}") if r.status >= 400 and "/api/" in r.url else None)

    print("Phase 1: shell and pages with the endpoint off")
    check("shell: title, nav order, sidebar footer", t_shell)
    check("navigation: all 10 pages, highlight, hash, no error banner", t_nav_each)
    check("deep link and unknown route", t_deeplink)
    check("overview: KPIs, endpoint card, stacks, alarms, budget", t_overview)
    check("overview: links to Retraining and Monitoring", t_overview_links)
    check("overview: Start endpoint confirm can be cancelled", t_start_dismissed)
    check("overview: auto-shutdown setting is stored", t_idle_setting)
    check("failed send while the detector is off leaves nothing behind", t_failed_send_leaves_nothing)
    check("navigation while data is still loading never shows the wrong page", t_stale_render)
    check("detect: sample picker, GT boxes, sliders repaint, reset", t_detect_controls)
    check("detect: file upload", t_detect_upload)
    check("detect: drag and drop", t_detect_drop)
    check("detect: endpoint-off banner and link", t_detect_offline)
    check("gallery: tabs, images load, boxes, paging, search, viewer", t_gallery)
    check("requests page (filter, modal)", t_requests_ui)
    check("review: empty state", t_review_empty)
    check("review: all four actions end to end", t_review_flow)
    check("models: baseline, approve dialog, reject", t_models_flow)

    started = False
    if not OFFLINE:
        if api("endpoint")["status"] != "Off":
            sys.exit("--live needs the endpoint to be off to start with; stop it first")
        print("Phase 2: start the endpoint from the UI and test other pages while it boots")
        check("endpoint: start from UI shows progress", t_start_endpoint)
        started = api("overview")["endpoint"]["status"] in ("Creating", "InService")
    check("retraining page: stages, history, trigger card", t_retrain_page)
    check("retraining: select a past run", t_retrain_history_select)
    check("retraining: start confirm can be cancelled", t_retrain_start_dismissed)
    check("monitoring: alarms and range selector", t_monitoring_ui)
    check("evaluation: KPIs and 6 charts", t_evaluation_ui)
    check("logs: every source, filter, live toggle", t_logs_ui)
    check("layout: no overflow, narrow-screen nav", t_layout)
    check("security: hostile requests refused", t_security)

    if started:
        print("Phase 3: endpoint running")
        try:
            secs = wait_running()
            print(f"  endpoint InService after waiting {secs}s more")
            check("overview flips to Running with Stop button", t_overview_flips_running)
            check("detect (golden sample, preview): boxes, nothing stored", t_detect_live_preview)
            check("detect (upload, saved): stored via the public API", t_detect_live_saved)
            check("requests: saved image appears and gets auto-labelled", t_requests_after_save)
            check("monitoring: charts populate from real traffic", t_monitoring_data)
            check("logs: ingest and endpoint lines", t_logs_live)
        finally:
            check("endpoint: stop from UI, returns to Off", t_stop_endpoint)
            cleanup_mine()

    if not OFFLINE:
        print("Phase 4: retraining run")
        check("retraining: final state of the run is shown correctly", t_retrain_final)

    browser.close()

passed = sum(r["ok"] for r in results)
real_issues = [i for i in dict.fromkeys(issues)]
print(f"\n{passed}/{len(results)} checks passed")
if real_issues:
    print("browser/API issues seen:"); [print("  -", i) for i in real_issues]
json.dump({"results": results, "issues": real_issues, "when": time.strftime("%Y-%m-%d %H:%M:%S")}, open(ROOT / "app/tests/last_run.json", "w"), indent=1)
sys.exit(0 if passed == len(results) else 1)
