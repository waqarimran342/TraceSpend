"""Measure the pipeline on synthetic receipts. Run: python -m tools.eval"""
import time

from app.audit.engine import run_audit
from app.pipeline.capture_fix import fix
from app.pipeline.ocr import mean_conf, read_words
from app.pipeline.parser import build_lines
from app.pipeline.restore import restore
from tools.make_samples import make

KINDS = ["clean", "wrong_total", "wrong_subtotal", "duplicate", "wrong_tax"]
AUGS = ["none", "tilt", "shadow", "blur", "fade"]
CONF_MIN = 85  # same threshold the app uses for "needs review"


def read(gray):
    words = read_words(gray)
    return build_lines(words), mean_conf(words)


def fields_ok(lines, truth):
    ok = 0
    for k in ("subtotal", "tax", "total"):
        v = next((l["amount"] for l in lines if l["kind"] == k), None)
        ok += 1 if v is not None and abs(float(v) - truth[k]) < 0.01 else 0
    return ok


def main():
    ok = total_fields = caught = injected = false_alarms = review_flags = clean = 0
    fade_before = fade_after = fade_n = 0
    conf_before = conf_after = 0.0
    times, seed = [], 0
    for kind in KINDS:
        for aug in AUGS:
            seed += 1
            img, truth = make(seed, kind, aug)
            t = time.time()
            fixed, _ = fix(img)
            lines, conf = read(fixed)
            if aug == "fade":  # same logic as the app's Restore button
                lines2, conf2 = read(restore(fixed))
                fade_n += 3
                fade_before += fields_ok(lines, truth)
                fade_after += fields_ok(lines2, truth)
                conf_before += conf
                conf_after += conf2
                if conf2 >= conf:
                    lines = lines2
            times.append(time.time() - t)
            low = {l["id"] for l in lines if l["conf"] < CONF_MIN}
            bad = [f for f in run_audit(lines, tax_rate=16) if f["severity"] in ("red", "amber")]
            sure = [f for f in bad if not (set(f["line_ids"]) & low)]
            if kind == "clean":
                clean += 1
                false_alarms += 1 if sure else 0
                review_flags += 1 if (bad and not sure) else 0
            else:
                injected += 1
                caught += 1 if bad else 0
            ok += fields_ok(lines, truth)
            total_fields += 3
            print(f"{kind:15} {aug:7} findings={len(bad)} confident={len(sure)}")
    n_fade = fade_n // 3
    print("\n=== RESULTS (synthetic receipts) ===")
    print(f"Receipts tested:           {seed}")
    print(f"Fields read correctly:     {ok}/{total_fields} ({100 * ok / total_fields:.0f}%)")
    print(f"Injected errors caught:    {caught}/{injected}")
    print(f"False alarms (clean, confident readings): {false_alarms}/{clean}")
    print(f"Clean receipts flagged for review (shaky digit, shown yellow): {review_flags}/{clean}")
    print(f"Faded receipts, fields correct: {fade_before}/{fade_n} before restore -> {fade_after}/{fade_n} after")
    if n_fade:
        print(f"Faded receipts, mean OCR confidence: {conf_before / n_fade:.0f}% -> {conf_after / n_fade:.0f}%")
    print(f"Avg time per receipt:      {sum(times) / len(times):.1f}s")


if __name__ == "__main__":
    main()