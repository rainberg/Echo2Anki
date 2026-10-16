"""德语→中文翻译模块。

翻译引擎优先级（2026-10 起）：
1. DeepL API Free —— 官方接口，免费层每把密钥 50 万字符/月，质量最佳；
   需环境变量 DEEPL_API_KEYS（逗号分隔可配多把，密钥失效/配额用尽
   自动切换下一把）或 DEEPL_API_KEY（单把），未配置则跳过。
2. Google 免费接口（googleapis 直调，带超时/重试）—— 对数据中心
   服务器 IP 会 429（2026-10 事故根因），仅家庭网络出口可靠。
3. MyMemory —— 最终兜底，保证翻译链路始终有界返回。
"""

import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# DeepL 免费层密钥以 ":fx" 结尾，必须走 api-free.deepl.com
DEEPL_API = "https://api-free.deepl.com/v2/translate"
GOOGLE_API = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_API = "https://api.mymemory.translated.net/get"

def _load_deepl_keys() -> list[str]:
    """支持 DEEPL_API_KEYS（逗号分隔多把）或 DEEPL_API_KEY（单把）。"""
    raw = os.environ.get("DEEPL_API_KEYS") or os.environ.get("DEEPL_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


DEEPL_API_KEYS = _load_deepl_keys()
_deepl_key_idx = 0  # 当前使用的 key 下标（失效/超额时自动切换下一把）

_SESSION: Optional[requests.Session] = None


class _PermanentAPIError(Exception):
    """密钥无效 / 配额用尽等重试无意义的 DeepL 错误。"""


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) anki-app/2.0"
    return _SESSION


def _translate_deepl(text: str, api_key: str, timeout: float = 15.0) -> str:
    """DeepL API Free：官方引擎，免费层 50 万字符/月，de→zh 质量最佳。"""
    resp = _get_session().post(
        DEEPL_API,
        data={"text": text, "source_lang": "DE", "target_lang": "ZH"},
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
        timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise _PermanentAPIError(f"key rejected (HTTP {resp.status_code})")
    if resp.status_code == 456:
        raise _PermanentAPIError("quota exceeded (HTTP 456)")
    if resp.status_code != 200:
        raise RuntimeError(f"DeepL HTTP {resp.status_code}: {resp.text[:120]}")
    translations = (resp.json() or {}).get("translations") or []
    if not translations:
        logger.warning("DeepL 200 but empty translations — body=%r", resp.text[:200])
        return ""
    # DeepL 响应字段是 "text"（注意不是 MyMemory 的 "translatedText"）
    return (translations[0].get("text") or "") if translations else ""


def _deepl_translate_with_failover(text: str) -> str:
    """多密钥故障切换：401/403/456 换下一把 key，瞬时错误同 key 重试一次。"""
    global _deepl_key_idx
    n = len(DEEPL_API_KEYS)
    for offset in range(n):
        idx = (_deepl_key_idx + offset) % n
        for attempt in (1, 2):
            try:
                result = _translate_deepl(text, DEEPL_API_KEYS[idx])
                _deepl_key_idx = idx  # 记住当前可用 key
                return result
            except _PermanentAPIError as exc:
                logger.warning("DeepL key#%d unusable: %s — switch to next", idx, exc)
                break
            except Exception as exc:
                logger.warning(
                    "DeepL failed (key#%d, attempt %d/2): %s", idx, attempt, exc
                )
                if attempt < 2:
                    time.sleep(1.0)
    return ""


def _translate_google(text: str, timeout: float = 10.0) -> str:
    resp = _get_session().get(
        GOOGLE_API,
        params={"client": "gtx", "sl": "de", "tl": "zh-CN", "dt": "t", "q": text},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Google HTTP {resp.status_code}")
    data = resp.json()
    if not data or not data[0]:
        return ""
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def _translate_mymemory(text: str, timeout: float = 10.0) -> str:
    resp = _get_session().get(
        MYMEMORY_API,
        params={"q": text, "langpair": "de|zh-CN"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"MyMemory HTTP {resp.status_code}")
    data = resp.json()
    status = data.get("responseStatus")
    if str(status) != "200":
        raise RuntimeError(f"MyMemory status {status}: {data.get('responseDetails', '')}")
    return (data.get("responseData") or {}).get("translatedText") or ""


def translate_de_to_zh(
    text: str,
    max_retries: int = 3,
    base_delay: float = 1.5,
) -> str:
    """单句德→中翻译：DeepL 优先，Google 次之，MyMemory 兜底。"""
    if not text or not text.strip():
        return ""

    if DEEPL_API_KEYS:
        result = _deepl_translate_with_failover(text)
        if result:
            return result

    result = ""
    for attempt in range(1, max_retries + 1):
        try:
            result = _translate_google(text)
            break
        except Exception as exc:
            logger.warning(
                "Google translate failed (attempt %d/%d): %s", attempt, max_retries, exc
            )
            if attempt < max_retries:
                time.sleep(base_delay * attempt)
    if not result:
        try:
            result = _translate_mymemory(text)
        except Exception as exc:
            logger.warning("MyMemory fallback failed: %s", exc)
    return result
