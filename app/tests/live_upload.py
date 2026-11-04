"""Drive the real UI: start the endpoint, send one image, watch every stage. Leaves the endpoint running.

    .venv/bin/python app/tests/live_upload.py
"""
import json, os, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.update(AWS_CONFIG_FILE=str(ROOT/".aws/config"), AWS_SHARED_CREDENTIALS_FILE=str(ROOT/".aws/credentials"), AWS_PROFILE="mlops", AWS_REGION="ap-southeast-2")
import boto3
from playwright.sync_api import sync_playwright
URL = "http://127.0.0.1:8000"; SH = ROOT/"app/.shots"; SH.mkdir(exist_ok=True)
REQ = boto3.Session(profile_name="mlops", region_name="ap-southeast-2").resource("dynamodb").Table("plateloop-requests")
val = json.load(open(ROOT/"data/original/val.json")); gold = {i["file_name"] for i in json.load(open(ROOT/"golden/annotations.json"))["images"]}
clean = set(json.load(open(ROOT/"report/experiments/clean_holdout_ids.json"))["clean_ids"])
photo = ROOT/"data/original/images"/next(i["file_name"] for i in val["images"] if i["id"] in clean and i["file_name"] not in gold)
log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"]); pg = b.new_page(viewport={"width": 1360, "height": 1000})
    pg.on("console", lambda m: log("console.error: " + m.text[:150]) if m.type == "error" else None)
    pg.goto(URL + "/?live=1#/detect"); pg.wait_for_selector("#nav a.on")
    pg.wait_for_function("(() => { const c = document.querySelector('#page .card'); return c && c.innerText.includes('Detector') && !c.innerText.includes('Checking'); })()", timeout=20000)
    pg.set_input_files('input[type="file"]', str(photo)); pg.wait_for_function("document.querySelector('.imgbox').style.display==='inline-block'")
    log(f"endpoint strip: {pg.inner_text('#page .card').replace(chr(10), ' ')[:140]} | Detect disabled={pg.get_by_role('button', name='Detect plates').is_disabled()} | reason='{pg.inner_text('#whyDisabled')}'")
    pg.screenshot(path=str(SH/"live1_off.png"))
    if "Off" in pg.inner_text("#page .card"):
        pg.once("dialog", lambda d: d.accept()); pg.get_by_role("button", name="Start endpoint").click(); log("clicked Start endpoint")
        pg.wait_for_selector(".bar.ind"); log(f"starting: '{pg.inner_text('#page .card').replace(chr(10), ' ')[:150]}' | disabled={pg.get_by_role('button', name='Detect plates').is_disabled()} | reason='{pg.inner_text('#whyDisabled')}'")
        pg.screenshot(path=str(SH/"live2_starting.png"))
    t0 = time.time(); last = ""
    while pg.get_by_role("button", name="Detect plates").is_disabled():          # no reload: the page must unlock itself
        cur = pg.inner_text("#page .card").replace(chr(10), " ")[:120]
        if cur != last: log(f"strip status -> {cur}"); last = cur
        if time.time() - t0 > 600: sys.exit("never unlocked")
        time.sleep(5)
    log(f"Detect button unlocked by itself after {int(time.time()-t0)}s; strip: {pg.inner_text('#page .card').replace(chr(10), ' ')[:140]}")
    pg.screenshot(path=str(SH/"live3_ready.png"))
    rows_before = REQ.scan(Select="COUNT")["Count"]
    btn = pg.get_by_role("button", name="Detect plates"); btn.click(); log("clicked Detect once")
    try: pg.get_by_role("button", name="Sending…").wait_for(timeout=3000); log("button now reads 'Sending…' and is disabled=%s" % pg.get_by_role("button", name="Sending…").is_disabled())
    except Exception: log("(send finished before 'Sending…' could be observed)")
    seen = []; t1 = time.time()
    while time.time() - t1 < 150:
        steps = pg.evaluate("[...document.querySelectorAll('#tracker .row')].map(r => r.innerText.replace(/\\s+/g,' ').trim())") if pg.locator('#tracker').count() else []
        if steps and steps != (seen[-1] if seen else None): seen.append(steps); log("tracker: " + " | ".join(steps))
        if steps and len(steps) == 4 and steps[3].startswith(("✓")) : break
        time.sleep(1.5)
    pg.screenshot(path=str(SH/"live4_done.png"))
    log(f"requests table rows: {rows_before} -> {REQ.scan(Select='COUNT')['Count']}")
    first_id = pg.inner_text("dd.mono"); log("request id: " + first_id)
    # identical image again -> must be recognised, no second row
    btn.click(); pg.wait_for_selector("text=already processed", timeout=60000)
    log(f"re-sent same image -> banner: '{pg.inner_text('.banner')[:90]}' | rows now {REQ.scan(Select='COUNT')['Count']}")
    pg.screenshot(path=str(SH/"live5_duplicate.png"))
    pg.goto(URL + "/?live=2#/requests"); pg.wait_for_selector(".thumb img", timeout=20000)
    log(f"Requests page: {pg.locator('.thumb').count()} item(s), status pill '{pg.locator('.thumb .pill').first.inner_text()}', new-highlight={pg.locator('.thumb.new').count()}")
    pg.screenshot(path=str(SH/"live6_requests.png"))
    b.close()
