import re

CJK_PATTERN = re.compile(r"[一-鿿㐀-䶿]")
WORD_PATTERN = re.compile(r"[a-zA-Z]+")

# Common Bahasa Malaysia function words. Deliberately a closed, explicit list
# rather than a general-purpose language-ID library: off-the-shelf detectors
# (e.g. langdetect) do not reliably distinguish Malay from Indonesian, and
# this only needs to separate en/ms/zh for PROJECT_SPEC.md §43 — a rule-based
# marker-word heuristic is simpler and more testable than a wrong "accurate"
# answer. Expect false negatives on BM text that happens to avoid these words.
BAHASA_MALAYSIA_MARKERS = {
    "yang", "dan", "untuk", "dengan", "tidak", "adalah", "saya", "kami",
    "kita", "ini", "itu", "akan", "boleh", "perlu", "sila", "kepada",
    "daripada", "sebab", "kena", "buat", "selalu", "setiap", "hari",
    "sangat", "juga", "atau", "pada", "dalam", "ada", "tak", "nak",
}

CJK_RATIO_THRESHOLD = 0.15
BM_DOMINANT_RATIO_THRESHOLD = 0.25
BM_MIXED_RATIO_THRESHOLD = 0.08


def detect_language(text: str) -> str:
    if not text or not text.strip():
        return "unknown"

    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"

    cjk_count = len(CJK_PATTERN.findall(text))
    if cjk_count / len(letters) >= CJK_RATIO_THRESHOLD:
        return "zh"

    words = [w.lower() for w in WORD_PATTERN.findall(text)]
    if not words:
        return "unknown"

    bm_hits = sum(1 for w in words if w in BAHASA_MALAYSIA_MARKERS)
    bm_ratio = bm_hits / len(words)

    if bm_ratio >= BM_DOMINANT_RATIO_THRESHOLD:
        return "ms"
    if bm_ratio >= BM_MIXED_RATIO_THRESHOLD:
        return "mixed"
    return "en"
