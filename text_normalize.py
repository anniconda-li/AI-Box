import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from artifacts import load_artifacts

try:
    from pypinyin import Style, lazy_pinyin
except ModuleNotFoundError:
    Style = None
    lazy_pinyin = None


FALLBACK_PINYIN = {
    "应": "ying",
    "英": "ying",
    "鹰": "ying",
    "婴": "ying",
    "膺": "ying",
    "瑛": "ying",
    "莺": "ying",
    "国": "guo",
    "玉": "yu",
    "邓": "deng",
    "等": "deng",
    "灯": "deng",
    "登": "deng",
    "瞪": "deng",
    "蹬": "deng",
    "公": "gong",
    "宫": "gong",
    "簋": "gui",
    "鬼": "gui",
    "轨": "gui",
    "贵": "gui",
    "盘": "pan",
    "盼": "pan",
    "攀": "pan",
    "龙": "long",
    "隆": "long",
    "钮": "niu",
    "扭": "niu",
    "牛": "niu",
    "带": "dai",
    "代": "dai",
    "盖": "gai",
    "该": "gai",
    "铜": "tong",
    "同": "tong",
    "盉": "he",
    "和": "he",
    "盒": "he",
    "禾": "he",
    "黑": "hei",
    "釉": "you",
    "油": "you",
    "蓝": "lan",
    "兰": "lan",
    "斑": "ban",
    "班": "ban",
    "花": "hua",
    "华": "hua",
    "口": "kou",
    "三": "san",
    "足": "zu",
    "洗": "xi",
    "喜": "xi",
    "束": "shu",
    "树": "shu",
    "竖": "shu",
    "腰": "yao",
    "要": "yao",
    "垂": "chui",
    "锤": "chui",
    "鳞": "lin",
    "林": "lin",
    "磷": "lin",
    "纹": "wen",
    "文": "wen",
    "升": "sheng",
    "生": "sheng",
    "鼎": "ding",
    "顶": "ding",
}


def env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def normalize_plain_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


@lru_cache(maxsize=4096)
def pinyin_key(text: str) -> str:
    if lazy_pinyin is not None and Style is not None:
        return "".join(
            lazy_pinyin(
                text,
                style=Style.NORMAL,
                errors="default",
            )
        ).lower()

    return "".join(FALLBACK_PINYIN.get(char, char.lower()) for char in text)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def artifact_terms(artifact: dict[str, Any]) -> list[str]:
    terms = [str(artifact.get("name") or ""), *[str(item) for item in artifact.get("aliases", [])]]
    deduped: list[str] = []
    for term in terms:
        cleaned = normalize_plain_text(term)
        if len(cleaned) < 2:
            continue
        if term not in deduped:
            deduped.append(term)
    return deduped


@lru_cache(maxsize=1)
def artifact_phonetic_terms() -> list[dict[str, object]]:
    terms: list[dict[str, object]] = []
    for artifact in load_artifacts().values():
        for term in artifact_terms(artifact):
            terms.append(
                {
                    "artifact_id": artifact["id"],
                    "artifact_name": artifact["name"],
                    "term": term,
                    "term_text": normalize_plain_text(term),
                    "term_pinyin": pinyin_key(term),
                    "term_length": len(normalize_plain_text(term)),
                }
            )
    return terms


def best_artifact_mention_match(text: str) -> dict[str, object] | None:
    compact = normalize_plain_text(text)
    if not compact:
        return None

    threshold = env_float("ASR_ARTIFACT_PHONETIC_THRESHOLD", 0.86)
    best: dict[str, object] | None = None

    for term_info in artifact_phonetic_terms():
        term_text = str(term_info["term_text"])
        artifact_name = str(term_info["artifact_name"])
        if term_text and term_text in compact:
            return {
                "start": compact.find(term_text),
                "end": compact.find(term_text) + len(term_text),
                "artifact_name": artifact_name,
                "score": 1.0,
                "matched_text": term_text,
            }

        term_length = int(term_info["term_length"])
        min_length = max(2, term_length - 1)
        max_length = min(len(compact), term_length + 1)
        for length in range(min_length, max_length + 1):
            for start in range(0, len(compact) - length + 1):
                candidate = compact[start : start + length]
                candidate_score = similarity(pinyin_key(candidate), str(term_info["term_pinyin"]))
                if candidate_score < threshold:
                    continue

                text_score = similarity(candidate, term_text)
                score = candidate_score * 0.85 + text_score * 0.15
                if best is None or score > float(best["score"]):
                    best = {
                        "start": start,
                        "end": start + length,
                        "artifact_name": artifact_name,
                        "score": score,
                        "matched_text": candidate,
                    }

    return best


def normalize_artifact_mentions(text: str) -> str:
    compact = normalize_plain_text(text)
    match = best_artifact_mention_match(text)
    if match is None:
        return text

    start = int(match["start"])
    end = int(match["end"])
    matched_text = compact[start:end]
    artifact_name = str(match["artifact_name"])
    if matched_text == artifact_name:
        return text

    return compact[:start] + artifact_name + compact[end:]
