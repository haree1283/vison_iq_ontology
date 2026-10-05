"""Refine plate reading on saved crops -- INDIAN PLATES ONLY, no false readings.
Per track: best crops by sharpness -> clarity filter (upscale, denoise, deskew, CLAHE, sharpen) -> PaddleOCR ->
strict Indian-format check (scripts/v8/indian_plate.py). A plate is CONFIRMED only when >= MIN_CROPS different frames
agree on the same number with good confidence; near-duplicate misreads in one video are merged. Everything else is
written to raw/plates_rejected.txt (with the reason) and never reported. Test-only output."""
import os, sys, glob, shutil, collections, cv2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v8"))
from indian_plate import read_plate, enhance, sharpness, edit_distance
from paddleocr import PaddleOCR

ROOT = os.environ.get("PLATES_ROOT", "runs/plates")
TOPK = 8            # sharpest crops per track that get OCR'd
MIN_CROPS = 2       # different frames that must agree on the same plate
MIN_MEAN = 0.85     # mean OCR confidence of the agreeing reads
MIN_BEST = 0.93     # at least one agreeing read this confident
MIN_H = 12          # crops shorter than this (px) are too small to read reliably
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                lang="en", enable_mkldnn=False)

summary = []
for vdir in sorted(glob.glob(f"{ROOT}/*/")):
    name = os.path.basename(vdir.rstrip("/")); RAW = f"{vdir}raw"
    tracks = collections.defaultdict(list)
    for f in glob.glob(f"{RAW}/crops/*.png"):
        tracks[os.path.basename(f).split("_")[0]].append(f)
    rejected = []
    votes = collections.defaultdict(dict)                    # plate -> {frame: (score, crop_file)} across the video
    for tid, files in sorted(tracks.items()):
        crops = [(f, cv2.imread(f)) for f in files]
        crops = [(f, c) for f, c in crops if c is not None and c.shape[0] >= MIN_H]
        if not crops:
            rejected.append((tid, "", 0, 0.0, "crops too small")); continue
        crops = sorted(crops, key=lambda fc: sharpness(fc[1]), reverse=True)[:TOPK]
        got = False
        for f, c in crops:
            reads = [(plate, sc * (1.0 - 0.05 * fixes)) for plate, sc, fixes in read_plate(ocr, c)]
            if not reads: continue
            plate, sc = max(reads, key=lambda r: r[1])       # one vote per frame: its most confident reading
            frame = os.path.basename(f).split("_")[1]
            if sc > votes[plate].get(frame, (0.0, ""))[0]: votes[plate][frame] = (sc, f)
            got = True
        if not got: rejected.append((tid, "", 0, 0.0, "no Indian-format reading"))
    confirmed = []
    for plate, fr in votes.items():
        scores = [v[0] for v in fr.values()]
        n, mean, best = len(scores), sum(scores) / len(scores), max(scores)
        if n < MIN_CROPS or mean < MIN_MEAN or best < MIN_BEST:
            why = f"only {n} frame(s) agree" if n < MIN_CROPS else f"low confidence (mean {mean:.2f}, best {best:.2f})"
            rejected.append(("-", plate, n, round(mean, 3), why)); continue
        confirmed.append(dict(text=plate, frames=n, conf=round(mean, 3), crop=max(fr.values())[1], tracks=[plate]))
    # one entry per real plate: readings 1-2 characters apart in the same video are misreads of the same plate
    merged = []
    for c in sorted(confirmed, key=lambda c: (c["frames"], c["conf"]), reverse=True):
        for k in merged:
            if abs(len(k["text"]) - len(c["text"])) <= 1 and edit_distance(k["text"], c["text"]) <= 2:
                k["frames"] += c["frames"]; k["tracks"] += c["tracks"]
                rejected.append((c["tracks"][0], c["text"], c["frames"], c["conf"], f"merged into {k['text']}")); break
        else:
            merged.append(c)
    ud = f"{vdir}unique"; shutil.rmtree(ud, ignore_errors=True); os.makedirs(ud)
    with open(f"{vdir}plates_unique.txt", "w") as fh:
        fh.write("# plate_text\tocr_conf\tstatus\tframes_agreeing\tclear_image\toriginal_crop\n")
        for k in merged:
            crop = cv2.imread(k["crop"])
            cv2.imwrite(f"{ud}/{k['text']}.png", enhance(crop))                 # the cleaned, readable plate
            cv2.imwrite(f"{ud}/{k['text']}_original.png", crop)
            fh.write(f"{k['text']}\t{k['conf']:.3f}\tVALID\t{k['frames']}\tunique/{k['text']}.png\tunique/{k['text']}_original.png\n")
            summary.append((name, k["text"], k["conf"], "VALID", k["frames"], f"{name}/unique/{k['text']}.png"))
    with open(f"{RAW}/plates_rejected.txt", "w") as fh:
        fh.write("# track\tbest_indian_reading\tframes_agreeing\tmean_conf\treason\n")
        for r in rejected: fh.write("\t".join(map(str, r)) + "\n")
    print(f"{name[:45]:45s} raw_tracks={len(tracks):3d} unique_plates={len(merged):3d} valid={len(merged):3d} rejected={len(rejected):3d}", flush=True)
with open(f"{ROOT}/all_plates_unique.txt", "w") as fh:
    fh.write("# video\tplate_text\tocr_conf\tstatus\tframes_agreeing\tclear_image\n")
    for r in summary: fh.write("\t".join(map(str, r)) + "\n")
