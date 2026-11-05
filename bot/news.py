"""Phân tích tin tức – thuần quy tắc, KHÔNG dùng AI.

Nguồn miễn phí, không cần API key:
  1. RSS của các trang tin crypto lớn (NEWS_FEEDS): CoinDesk, Cointelegraph, The Block, Decrypt, CryptoSlate…
  2. Thông báo sàn: OKX (niêm yết / huỷ niêm yết) và Binance (New Cryptocurrency Listing / Delisting)
  3. Chỉ số Fear & Greed (alternative.me) – tâm lý chung của thị trường

Xử lý mỗi bài (tiêu đề + đoạn mô tả):
  - Nhận diện coin: $SOL, (SOL), SOL viết hoa (chỉ mã đang có hợp đồng USDT-SWAP trên OKX) hoặc tên riêng (Solana).
    Mã trùng từ/viết tắt thông dụng (ONE, GAS, NOT, NFT…) chỉ được nhận khi viết dạng $MÃ hoặc (MÃ).
  - Điểm cảm xúc: từ điển riêng cho crypto (surge/rally/listing… dương; hack/delist/plunge… âm), đảo dấu và giảm
    nửa khi có phủ định ngay trước ("not", "denies", "fails to"…), nén về −1..+1.
  - Nhãn sự kiện: delist, hack, listing, unlock, lawsuit, etf, partnership, upgrade (mỗi loại có thời hạn hiệu lực).
Tổng hợp cho 1 coin: trung bình có trọng số theo độ mới (half-life NEWS_HALF_LIFE_H), co về 0 khi ít bài
→ "news_bias" −1..+1. Tin tức chỉ là BẰNG CHỨNG: bộ tự học đo xem tin cùng chiều / ngược chiều thực tế thắng
hay thua (trọng số news_w, các luật news_*), không tin mù quáng vào từ điển.
Lỗi mạng của nguồn nào thì bỏ qua nguồn đó, không bao giờ làm hỏng vòng lặp giao dịch.
"""
import email.utils
import hashlib
import html
import logging
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .config import cfg

log = logging.getLogger("news")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OKXAltcoinBot/4.0; +rss-reader)",
           "Accept": "application/rss+xml, application/atom+xml, application/xml, application/json;q=0.9, */*;q=0.5"}
MAX_BYTES = 3_000_000          # chặn phản hồi bất thường (feed lỗi / bị chèn)
KEEP_NEWS_H = 48               # giữ bài báo 48h (cửa sổ chấm điểm mặc định 24h)
KEEP_ANN_H = 8 * 24            # giữ thông báo sàn 8 ngày (sự kiện huỷ niêm yết có hiệu lực 7 ngày)
MAX_ARTICLES = 900
FNG_URL = "https://api.alternative.me/fng/?limit=1"
OKX_ANN_URL = "https://www.okx.com/api/v5/support/announcements?annType={}"
OKX_ANN_TYPES = ("announcements-delistings", "announcements-new-listings")
BINANCE_ANN_URL = ("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
                   "?type=1&catalogId={}&pageNo=1&pageSize=10")
BINANCE_CATALOGS = {48: "listing", 161: "delist"}

# Thời gian hiệu lực của từng loại sự kiện (giờ)
EVENT_WINDOW_H = {"delist": 168, "hack": 48, "listing": 48, "unlock": 72, "lawsuit": 72, "etf": 72,
                  "partnership": 48, "upgrade": 48}
EVENT_NAMES = {"delist": "huỷ niêm yết", "hack": "hack/exploit", "listing": "niêm yết sàn lớn", "unlock": "mở khoá token",
               "lawsuit": "kiện tụng/điều tra", "etf": "ETF", "partnership": "hợp tác/tích hợp", "upgrade": "nâng cấp mạng"}

_EVENT_RX = {
    "delist": re.compile(r"\bdelist(?:s|ed|ing)?\b|\bwill (?:remove|cease)\b|\bremoval of\b|\bcease trading\b", re.I),
    "hack": re.compile(r"\b(?:hack(?:s|ed|er|ers)?|exploit(?:s|ed)?|drain(?:s|ed)?|stolen|breach(?:es|ed)?|"
                       r"compromised|attackers?)\b", re.I),
    "listing": re.compile(r"\b(?:will list|to list|lists|listed on|new listing|listing of)\b|"
                          r"\b(?:will )?launch(?:es)?\b.{0,45}\b(?:perpetual|spot trading|futures)\b", re.I),
    "unlock": re.compile(r"\bunlock(?:s|ed|ing)?\b", re.I),
    "lawsuit": re.compile(r"\b(?:lawsuit|sues|sued|indict(?:s|ed|ment)?|subpoena(?:s|ed)?|charged)\b", re.I),
    "etf": re.compile(r"\betfs?\b", re.I),
    "partnership": re.compile(r"\bpartner(?:s|ship|ships|ed)?\b|\bintegrat(?:es|ed|ion)\b", re.I),
    "upgrade": re.compile(r"\b(?:mainnet|hard fork|network upgrade|upgrade)\b", re.I),
}

# Từ điển cảm xúc crypto: (mẫu regex, trọng số). Dương = tốt cho giá, âm = xấu cho giá.
_LEXICON = (
    # ---- giá / dòng tiền tăng
    (r"surg(?:e|es|ed|ing)", 2.0), (r"soar(?:s|ed|ing)?", 2.0), (r"skyrocket(?:s|ed|ing)?", 2.5),
    (r"rall(?:y|ies|ied|ying)", 1.5), (r"jump(?:s|ed|ing)?", 1.5), (r"climb(?:s|ed|ing)?", 1.0),
    (r"gain(?:s|ed|ing)?", 1.0), (r"rebound(?:s|ed|ing)?", 1.0), (r"recover(?:s|ed|ing|y)?", 1.0),
    (r"reclaim(?:s|ed|ing)?", 1.0), (r"ris(?:e|es|ing)|rose", 1.0), (r"break(?:s|ing)? out|breakouts?", 1.5),
    (r"all[- ]time highs?|record highs?|new highs?", 2.0), (r"bullish", 1.5), (r"outperform(?:s|ed|ing)?", 1.0),
    (r"(?:\d+[- ](?:day|week|month|year)|multi[- ]year|yearly|monthly|weekly) highs?", 1.5),
    (r"hits? (?:a |an |new |fresh |\d{4} )*highs?", 1.0), (r"growth", 0.5), (r"surpass(?:es|ed)?", 1.0),
    (r"pump(?:s|ed|ing)?", 1.0), (r"upside", 0.5), (r"higher", 0.5), (r"up \d+(?:\.\d+)?%", 1.0),
    (r"inflows?", 1.5), (r"accumulat(?:e|es|ed|ing|ion)", 1.0), (r"buybacks?", 1.5), (r"burn(?:s|ed)?", 0.5),
    # ---- sự kiện tốt
    (r"partner(?:s|ship|ships|ed)?", 1.5), (r"integrat(?:e|es|ed|ion)", 1.0), (r"collaborat(?:e|es|ed|ion)", 1.0),
    (r"adopt(?:s|ed|ion)", 1.0), (r"approv(?:e|es|ed|al)", 1.5), (r"will list|to list|lists|listed on|listing", 1.5),
    (r"mainnet", 1.0), (r"launch(?:es|ed)?", 0.5), (r"upgrade[sd]?", 0.5), (r"raises? \$", 1.0),
    (r"funding round", 1.0), (r"milestone", 1.0), (r"wins?|won", 0.5),
    # ---- giá / dòng tiền giảm
    (r"plung(?:e|es|ed|ing)", -2.0), (r"plummet(?:s|ed|ing)?", -2.0), (r"crash(?:es|ed|ing)?", -2.0),
    (r"tumbl(?:e|es|ed|ing)", -1.5), (r"slump(?:s|ed|ing)?", -1.5), (r"sink(?:s|ing)?|sank|sunk", -1.5),
    (r"dump(?:s|ed|ing)?", -1.5), (r"drop(?:s|ped|ping)?", -1.0), (r"fall(?:s|ing)?|fell", -1.0),
    (r"declin(?:e|es|ed|ing)", -1.0), (r"slid(?:e|es|ing)?|slip(?:s|ped|ping)?", -1.0), (r"sell[- ]?offs?", -1.5),
    (r"bearish", -1.5), (r"lower", -0.5), (r"down \d+(?:\.\d+)?%", -1.0), (r"loss(?:es)?", -1.0),
    (r"liquidat(?:ion|ions|ed)", -1.0), (r"outflows?", -1.5), (r"capitulat(?:e|es|ion)", -1.5),
    (r"correction", -0.5), (r"downside", -0.5), (r"selling pressure", -1.5), (r"fears?", -0.5),
    (r"(?:\d+[- ](?:day|week|month|year)|multi[- ]year|yearly|monthly|weekly) lows?", -1.5),
    (r"hits? (?:a |an |new |fresh |\d{4} )*lows?", -1.0),
    # ---- sự kiện xấu
    (r"hack(?:s|ed|er|ers)?", -3.0), (r"exploit(?:s|ed)?", -3.0), (r"drain(?:s|ed)?", -2.5),
    (r"stolen|steal(?:s|ing)?", -2.5), (r"breach(?:es|ed)?", -2.0), (r"attack(?:s|ed|er|ers)?", -1.5),
    (r"phishing", -1.0), (r"scam(?:s|mer|mers)?", -2.0), (r"fraud(?:ulent)?", -2.0), (r"rug ?pull(?:s|ed)?", -3.0),
    (r"ponzi", -2.0), (r"delist(?:s|ed|ing)?", -3.0), (r"remov(?:e|es|ed|al)", -0.5),
    (r"suspend(?:s|ed)?|suspension", -1.5), (r"halt(?:s|ed)?", -1.5), (r"outage", -1.0), (r"lawsuit", -1.5),
    (r"sues|sued", -1.5), (r"charged", -1.0), (r"investigat(?:e|es|ed|ion|ing)", -1.0), (r"probes?", -1.0),
    (r"subpoena(?:s|ed)?", -1.5), (r"arrest(?:s|ed)?", -1.5), (r"ban(?:s|ned)?", -1.5), (r"crackdown", -1.5),
    (r"fined", -1.0), (r"bankrupt(?:cy)?|insolven(?:t|cy)", -2.5), (r"collaps(?:e|es|ed)", -2.5),
    (r"depeg(?:s|ged)?", -2.5), (r"unlock(?:s|ed|ing)?", -1.0), (r"vulnerabilit(?:y|ies)", -1.5),
    (r"warn(?:s|ing|ed)?", -0.5), (r"freez(?:e|es)|froze|frozen", -1.0), (r"reject(?:s|ed|ion)?", -1.5),
    (r"delay(?:s|ed)?", -1.0),
)
_LEX_RX = [(re.compile(r"\b(?:" + p + r")\b", re.I), w) for p, w in _LEXICON]
_NEGATORS = {"not", "no", "never", "without", "denies", "deny", "denied", "fails", "failed", "unlikely", "cannot",
             "won't", "isn't", "aren't", "doesn't", "didn't", "can't", "avoid", "avoids", "avoided"}
_WORD_RX = re.compile(r"[a-z0-9']+")

# Tên riêng → mã (chỉ những tên KHÔNG trùng từ tiếng Anh thông dụng; mã viết hoa đã nhận diện riêng)
NAMES = {
    "solana": "SOL", "ripple": "XRP", "dogecoin": "DOGE", "cardano": "ADA", "toncoin": "TON", "chainlink": "LINK",
    "polkadot": "DOT", "litecoin": "LTC", "bitcoin cash": "BCH", "hedera": "HBAR", "aptos": "APT", "arbitrum": "ARB",
    "near protocol": "NEAR", "internet computer": "ICP", "filecoin": "FIL", "uniswap": "UNI", "aave": "AAVE",
    "algorand": "ALGO", "injective": "INJ", "the graph": "GRT", "fetch.ai": "FET", "bittensor": "TAO",
    "worldcoin": "WLD", "celestia": "TIA", "starknet": "STRK", "polygon": "POL", "zcash": "ZEC", "ethena": "ENA",
    "ondo finance": "ONDO", "pyth network": "PYTH", "dogwifhat": "WIF", "floki": "FLOKI", "pepe": "PEPE",
    "pi network": "PI", "hyperliquid": "HYPE", "pump.fun": "PUMP", "ethereum classic": "ETC", "lido dao": "LDO",
    "eigenlayer": "EIGEN", "berachain": "BERA", "notcoin": "NOT", "the sandbox": "SAND", "decentraland": "MANA",
    "axie infinity": "AXS", "kaspa": "KAS", "vechain": "VET", "theta network": "THETA", "dydx": "DYDX",
    "synthetix": "SNX", "pendle": "PENDLE", "ether.fi": "ETHFI", "layerzero": "ZRO", "zksync": "ZK",
    "chiliz": "CHZ", "apecoin": "APE", "ronin network": "RON", "mina protocol": "MINA", "jasmycoin": "JASMY",
    "sei network": "SEI", "magic eden": "ME", "wormhole": "W", "fartcoin": "FARTCOIN", "pudgy penguins": "PENGU",
    "aerodrome": "AERO", "raydium": "RAY", "helium": "HNT", "render network": "RENDER", "arweave": "AR",
    "akash network": "AKT", "kaito": "KAITO", "world liberty financial": "WLFI", "pancakeswap": "CAKE",
    "sushiswap": "SUSHI", "yearn finance": "YFI", "tezos": "XTZ", "zilliqa": "ZIL", "ravencoin": "RVN",
    "kusama": "KSM", "cronos": "CRO", "dymension": "DYM", "altlayer": "ALT", "manta network": "MANTA",
    "zetachain": "ZETA", "hamster kombat": "HMSTR", "catizen": "CATI", "terra classic": "LUNC", "shiba inu": "SHIB",
    "avalanche network": "AVAX", "sui network": "SUI", "stellar lumens": "XLM", "cosmos hub": "ATOM",
    "official trump": "TRUMP", "story protocol": "IP", "sonic labs": "S", "jupiter exchange": "JUP",
    "bonk": "BONK", "tron": "TRX", "trx": "TRX", "bnb chain": "BNB", "binance coin": "BNB", "monad": "MON",
}
_NAME_RX = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(NAMES, key=len, reverse=True)) + r")\b", re.I)
# Viết tắt / từ thông dụng trùng mã coin: chỉ nhận khi viết $MÃ hoặc (MÃ) (riêng thông báo sàn thì nhận luôn)
AMBIGUOUS = {
    "NFT", "DAO", "DEX", "CEX", "ETF", "SEC", "USA", "CEO", "CFO", "CTO", "IPO", "FED", "CPI", "GDP", "IRS", "DOJ",
    "FBI", "AML", "KYC", "TVL", "APY", "APR", "ATH", "ATL", "FUD", "RWA", "OTC", "API", "ONE", "GAS", "NOT", "MOVE",
    "PEOPLE", "MEME", "ACT", "LAYER", "TRUMP", "MAJOR", "BANK", "PUMP", "SUN", "CORE", "OPEN", "REAL", "SAFE", "FLOW",
    "POWER", "PRIME", "STORY", "GAME", "HOT", "TOP", "BIG", "NEW", "ALL", "CAT", "DOG", "DOGS", "GOAT", "MAGIC",
    "PARTI", "USUAL", "DEGEN", "SUPER", "WAVES", "LIVE", "NEWS", "WATCH", "BREAKING", "UPDATE", "AI", "ID", "IP",
    "ME", "OM", "OP", "AR", "ZK", "OKX", "FTX", "USD", "USDT", "USDC", "UTC", "GMT", "EST", "PST", "THE", "AND",
}
# Mã ≥ 4 ký tự trùng tên dự án ("Cetus", "Pendle", "Kaito") được nhận cả khi viết thường – trừ các mã là từ tiếng Anh
# thông dụng / tên người (headline kiểu Title Case: "Traders Eye Fed Move" không phải MOVE; "hits new high" không phải HIGH).
COMMON_WORDS = {
    "AXIS", "BABY", "BAND", "BASED", "BEAT", "BILL", "BLEND", "BLUR", "CHIP", "COMP", "CORE", "DASH", "DATA", "EDEN",
    "EDGE", "FLOCK", "FLOW", "GALA", "GRAM", "GRASS", "HOME", "HYPE", "INIT", "KITE", "LAYER", "LIGHT", "LINK", "LUNA",
    "MAGIC", "MASK", "MEGA", "MEME", "MINA", "MOVE", "NEAR", "NIGHT", "ORDER", "PEOPLE", "PIPPIN", "PROS", "PROVE",
    "PUMP", "QUANT", "RAVE", "RECALL", "RENDER", "RIVER", "ROBO", "SAND", "SATS", "SENT", "SHELL", "SIGN", "SOON",
    "SPACE", "STABLE", "SUSHI", "SYRUP", "THETA", "TRUMP", "TRUST", "TRUTH", "TURBO", "USELESS", "VIRTUAL", "ZETA",
    "ALGO", "ATOM", "AZTEC", "SAHARA", "BRETT", "BARD", "AEON", "AERO", "BIGTIME", "ALLO", "MUBARAK", "SAPIEN", "ZAMA",
    "ECHO", "ALPHA", "BETA", "GAMMA", "DELTA", "OMEGA", "SIGMA", "TOKEN", "CHAIN", "BLOCK", "COIN", "CASH", "GOLD",
    "SILVER", "MOON", "STAR", "FIRE", "WATER", "EARTH", "WIND", "LIFE", "LOVE", "HOPE", "HERO", "KING", "QUEEN", "LORD",
    "ZERO", "HIGH", "FAST", "SLOW", "OPEN", "CLOSE", "LONG", "SHORT", "PEACE", "BULL", "BEAR", "WHALE", "SHARK", "FROG",
    "GAME", "PLAY", "WORLD", "EARN", "SWAP", "BOOST", "SAFE", "REAL", "PRIME", "POWER", "SUPER", "MAJOR", "BANK",
    "STORY", "WAVES", "DOGS", "GOAT", "OPENAI", "ANTHROPIC", "APPLE", "META", "TESLA",
}
_WORD4_RX = re.compile(r"(?<![A-Za-z0-9$])([A-Za-z][A-Za-z0-9]{3,14})(?![A-Za-z0-9])")
_DOLLAR_RX = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,11})\b")
_PAREN_RX = re.compile(r"\(([A-Z0-9]{2,12})\)")
_CAPS_RX = re.compile(r"(?<![A-Za-z0-9$])([A-Z0-9]{2,15})(?![A-Za-z0-9])")
_QUOTE_SUFFIX = ("USDT", "USDC", "USD", "PERP")
_TAG_RX = re.compile(r"<[^>]+>")
_SPACE_RX = re.compile(r"\s+")
_BOILER_RX = re.compile(r"The post .{0,300}? appeared first on .{0,120}?\.?$|Continue reading.*$|Read more.*$", re.I | re.S)


def clean_text(s, limit=600):
    """Bỏ thẻ HTML, giải mã &amp;…, gọn khoảng trắng, bỏ câu quảng cáo cuối bài RSS."""
    s = html.unescape(_TAG_RX.sub(" ", s or ""))
    s = _BOILER_RX.sub("", s)
    return _SPACE_RX.sub(" ", s).strip()[:limit]


def parse_time(s):
    """RFC-822 (RSS pubDate) hoặc ISO-8601 (Atom). Không có múi giờ → coi là UTC. Lỗi → None."""
    if not s:
        return None
    s = s.strip()
    d = None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def sentiment(text):
    """Tổng trọng số từ điển trong `text`; phủ định trong 3 từ đứng trước → đảo dấu và giảm nửa."""
    total, hits = 0.0, []
    low = text.lower()
    for rx, w in _LEX_RX:
        for m in rx.finditer(low):
            before = _WORD_RX.findall(low[max(0, m.start() - 40):m.start()])[-3:]
            ww = -0.5 * w if any(b in _NEGATORS for b in before) else w
            total += ww
            hits.append(m.group(0))
    return total, hits


def score_article(title, desc=""):
    """Điểm cảm xúc −1..+1 của 1 bài: tiêu đề tính đủ, mô tả tính một nửa (300 ký tự đầu)."""
    t, hits = sentiment(title or "")
    d, hits2 = sentiment((desc or "")[:300])
    raw = t + 0.5 * d
    return round(math.tanh(raw / 3.0), 3), hits + hits2


def detect_events(title):
    """Nhãn sự kiện trong TIÊU ĐỀ (mô tả hay nhắc chuyện cũ → dễ báo nhầm)."""
    return sorted(k for k, rx in _EVENT_RX.items() if rx.search(title or ""))


# Sự kiện chỉ gán cho coin đứng GẦN từ khoá trong tiêu đề (số từ): "Binance hackers move stolen Solana" là chuyện
# của Binance, không phải Solana bị hack; "Cetus Protocol hacked" mới là của Cetus.
EVENT_NEAR = {"hack": 4, "delist": 12, "listing": 12, "unlock": 6, "lawsuit": 8, "etf": 10, "partnership": 8,
              "upgrade": 8}
_REV_NAMES = {}
for _n, _t in NAMES.items():
    _REV_NAMES.setdefault(_t, []).append(_n)


def _word_index(low, pos):
    return len(_WORD_RX.findall(low[:pos]))


def event_coins(title, coins, events, structured=False):
    """{coin: [sự kiện]} cho các coin trong tiêu đề. structured=True (thông báo sàn): mọi coin nhận mọi sự kiện."""
    if not events or not coins:
        return {}
    if structured:
        return {c: sorted(events) for c in coins}
    low = (title or "").lower()
    words = _WORD_RX.findall(low)
    out = {}
    for c in coins:
        pats = [re.escape(c.lower())] + [re.escape(n) for n in _REV_NAMES.get(c, [])]
        cps = [_word_index(low, m.start()) for m in re.finditer(r"\b(?:" + "|".join(pats) + r")\b", low)]
        for ev in events:
            eps = [_word_index(low, m.start()) for m in _EVENT_RX[ev].finditer(low)]
            eps = [e for e in eps if not _NEGATORS.intersection(words[max(0, e - 2):e])]   # "not hacked", "denies exploit"
            near = EVENT_NEAR.get(ev, 8)
            for p in cps:
                if ev == "hack" and "stolen" in words[max(0, p - 2):p]:      # "stolen Solana": coin là tang vật
                    continue
                if any(abs(p - e) <= near for e in eps):
                    out.setdefault(c, []).append(ev)
                    break
    return {c: sorted(set(v)) for c, v in out.items()}


def _strip_quote(tok):
    for q in _QUOTE_SUFFIX:
        if tok.endswith(q) and len(tok) > len(q) + 1:
            return tok[:-len(q)]
    return tok


def detect_coins(text, universe, strict=True):
    """Tập mã coin nhắc tới trong `text`. universe: tập mã giao dịch được (rỗng = chưa biết → chỉ nhận
    $MÃ, (MÃ) và tên riêng). strict=False (thông báo sàn – tiêu đề có cấu trúc) → nhận cả mã trùng từ thông dụng."""
    found = set()
    if not text:
        return found
    known = universe or set()

    def ok(code):
        return (not known) or code in known

    for m in _DOLLAR_RX.finditer(text):
        c = m.group(1).upper()
        if ok(c) and not c.isdigit():
            found.add(c)
    for m in _PAREN_RX.finditer(text):
        c = _strip_quote(m.group(1))
        if ok(c) and not c.isdigit():
            found.add(c)
    if known:
        for m in _CAPS_RX.finditer(text):
            c = _strip_quote(m.group(1))
            if c in known and any(ch.isalpha() for ch in c) and (not strict or (c not in AMBIGUOUS and len(c) >= 3)):
                found.add(c)
        for m in _WORD4_RX.finditer(text):                   # tên dự án = mã, viết thường / Title Case
            c = m.group(1).upper()
            if c in known and c not in AMBIGUOUS and c not in COMMON_WORDS:
                found.add(c)
    for m in _NAME_RX.finditer(text):
        c = NAMES.get(m.group(1).lower())
        if c and ok(c):
            found.add(c)
    return found


def _decay(age_s):
    return 0.5 ** (max(age_s, 0.0) / 3600.0 / max(cfg.NEWS_HALF_LIFE_H, 0.1))


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el, *names):
    for ch in el:
        if _local(ch.tag) in names:
            if _local(ch.tag) == "link" and not (ch.text or "").strip():
                return ch.get("href") or ""
            return "".join(ch.itertext())
    return ""


def parse_feed(raw, src):
    """RSS 2.0 / Atom → danh sách bài thô {title, desc, url, ts}."""
    root = ET.fromstring(raw)
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = clean_text(_child(el, "title"), 300)
        if not title:
            continue
        out.append({"src": src, "kind": "news", "title": title,
                    "desc": clean_text(_child(el, "description", "summary", "content", "encoded"), 500),
                    "url": (_child(el, "link", "guid") or "").strip()[:400],
                    "ts": parse_time(_child(el, "pubDate", "published", "updated", "date"))})
    return out


def _aid(a):
    key = (a.get("src", "") + "|" + (a.get("url") or a.get("title") or "")).encode("utf-8", "ignore")
    return hashlib.sha1(key).hexdigest()[:16]


def default_feeds():
    out = []
    for i, item in enumerate(cfg.NEWS_FEEDS):
        name, sep, url = item.partition("|")
        if not sep:
            url, name = name, re.sub(r"^www\.", "", (re.findall(r"//([^/]+)", name) or [f"feed{i}"])[0])
        out.append((name.strip(), url.strip()))
    return out


class NewsHub:
    """Kho tin tức dùng chung: luồng nền làm mới mỗi NEWS_REFRESH_MIN phút (chỉ máy leader tải tin, máy dự phòng đọc
    bản lưu trong DB), quét tín hiệu hỏi coin()/market() – chỉ tính trên dữ liệu trong bộ nhớ, không gọi mạng."""

    def __init__(self, store=None):
        self.store = store
        self._lock = threading.RLock()
        self.articles = {}          # id -> bài đã phân tích
        self.status = {}            # nguồn -> {ok, n, err, ts, ms}
        self.fng = None             # {value, cls, ts}
        self.universe = set()
        self.last_refresh = 0.0
        self.last_fng = 0.0
        self.enabled = cfg.NEWS_ENABLED
        self.feeds = default_feeds()
        self._load()

    # ------------------------------------------------------------ lưu / nạp (DB kv – máy dự phòng & khởi động lại)
    def _load(self):
        if not self.store:
            return
        try:
            d = self.store.get("news_cache") or {}
        except Exception as e:
            log.debug("news load: %s", e)
            return
        arts = {a["id"]: a for a in (d.get("articles") or []) if isinstance(a, dict) and a.get("id")}
        with self._lock:
            if arts:
                self.articles = arts
            self.status = d.get("status") or self.status
            self.fng = d.get("fng") or self.fng
            self.last_refresh = float(d.get("ts") or self.last_refresh or 0)
            if self.universe:
                self._detect_all()

    def _save(self):
        if not self.store:
            return
        with self._lock:
            arts = sorted(self.articles.values(), key=lambda a: -a["ts"])[:MAX_ARTICLES]
            slim = [{k: a.get(k) for k in ("id", "ts", "seen", "src", "kind", "title", "desc", "url", "w", "score",
                                           "events", "hint")} for a in arts]
            data = {"v": 1, "ts": self.last_refresh, "articles": slim, "status": self.status, "fng": self.fng}
        try:
            self.store.set("news_cache", data)
        except Exception as e:
            log.warning("news: không lưu được bộ nhớ đệm (%s)", e)

    # ------------------------------------------------------------ danh sách coin để nhận diện
    def set_universe(self, bases):
        bases = {str(b).upper() for b in bases if b} - set(cfg.EXCLUDE)
        if not bases or bases == self.universe:
            return
        with self._lock:
            self.universe = bases
            self._detect_all()

    def _detect(self, a):
        strict = a.get("kind") != "ann"
        title_c = detect_coins(a["title"], self.universe, strict=strict)
        if a.get("hint"):                       # thông báo sàn: mã lấy từ cấu trúc tiêu đề (XYZUSDT, X/USDT)
            title_c |= {c for c in a["hint"] if not self.universe or c in self.universe}
        desc_c = detect_coins(a.get("desc") or "", self.universe, strict=True) - title_c
        a["coins"] = {**{c: 0.5 for c in desc_c}, **{c: 1.0 for c in title_c}}
        a["coin_ev"] = event_coins(a["title"], title_c, a.get("events") or [], structured=not strict)

    def _detect_all(self):
        for a in self.articles.values():
            self._detect(a)

    # ------------------------------------------------------------ tải dữ liệu
    @staticmethod
    def _get(url, timeout=None):
        r = requests.get(url, headers=HEADERS, timeout=timeout or cfg.NEWS_TIMEOUT, stream=True)
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > MAX_BYTES:
                r.close()
                raise ValueError("phản hồi quá lớn")
        return bytes(buf)

    def _fetch_feed(self, name, url):
        return parse_feed(self._get(url), name)

    def _fetch_okx(self):
        import json
        out = []
        for t in OKX_ANN_TYPES:
            d = json.loads(self._get(OKX_ANN_URL.format(t)))
            for page in d.get("data") or []:
                for x in page.get("details") or []:
                    ts = float(x.get("pTime") or 0) / 1000 or None
                    out.append({"src": "OKX", "kind": "ann", "title": clean_text(x.get("title"), 300), "desc": "",
                                "url": (x.get("url") or "")[:400], "ts": ts, "ann_type": t})
        return out

    def _fetch_binance(self):
        import json
        out = []
        for cat in BINANCE_CATALOGS:
            d = json.loads(self._get(BINANCE_ANN_URL.format(cat)))
            for c in ((d.get("data") or {}).get("catalogs") or []):
                for x in c.get("articles") or []:
                    code = x.get("code") or ""
                    out.append({"src": "Binance", "kind": "ann", "title": clean_text(x.get("title"), 300), "desc": "",
                                "url": f"https://www.binance.com/en/support/announcement/{code}" if code else "",
                                "ts": float(x.get("releaseDate") or 0) / 1000 or None})
        return out

    def _fetch_fng(self):
        import json
        d = json.loads(self._get(FNG_URL))
        x = (d.get("data") or [{}])[0]
        v = int(float(x.get("value")))
        return {"value": v, "cls": x.get("value_classification") or "", "ts": float(x.get("timestamp") or time.time())}

    def refresh(self, force=False):
        """Tải tất cả nguồn song song (tối đa NEWS_TIMEOUT giây/nguồn), phân tích bài mới, dọn bài cũ, lưu DB."""
        if not self.enabled:
            return 0
        jobs = {name: (self._fetch_feed, (name, url)) for name, url in self.feeds}
        if cfg.NEWS_ANNOUNCEMENTS:
            jobs["OKX"] = (self._fetch_okx, ())
            jobs["Binance"] = (self._fetch_binance, ())
        results, status = {}, {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as pool:
            futs = {name: (pool.submit(fn, *args), time.time()) for name, (fn, args) in jobs.items()}
            for name, (fut, t0) in futs.items():
                try:
                    items = fut.result(timeout=cfg.NEWS_TIMEOUT * 2 + 5)
                    results[name] = items
                    status[name] = {"ok": True, "n": len(items), "err": "", "ts": time.time(),
                                    "ms": int((time.time() - t0) * 1000)}
                except Exception as e:
                    status[name] = {"ok": False, "n": 0, "err": f"{type(e).__name__}: {str(e)[:120]}", "ts": time.time(),
                                    "ms": int((time.time() - t0) * 1000)}
        if cfg.NEWS_FNG and (force or time.time() - self.last_fng > 3600 or not self.fng):
            t0 = time.time()
            try:
                self.fng = self._fetch_fng()
                self.last_fng = time.time()
                status["Fear&Greed"] = {"ok": True, "n": 1, "err": "", "ts": time.time(), "ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                status["Fear&Greed"] = {"ok": False, "n": 0, "err": f"{type(e).__name__}: {str(e)[:120]}",
                                        "ts": time.time(), "ms": int((time.time() - t0) * 1000)}
        elif "Fear&Greed" in self.status:
            status["Fear&Greed"] = self.status["Fear&Greed"]
        added = self.ingest([a for items in results.values() for a in items])
        with self._lock:
            self.status = status
            self.last_refresh = time.time()
        self._save()
        bad = [k for k, v in status.items() if not v["ok"]]
        log.info("Tin tức: +%d bài mới, đang giữ %d | nguồn lỗi: %s | %s", added, len(self.articles),
                 ", ".join(bad) or "không", describe(self.market()))
        return added

    def ingest(self, raw_items, now=None):
        """Thêm bài (chưa phân tích) vào kho: chấm điểm, gắn nhãn sự kiện, nhận diện coin, dọn bài cũ."""
        now = now or time.time()
        added = 0
        with self._lock:
            for a in raw_items:
                if not a.get("title"):
                    continue
                a = dict(a)
                a["ts"] = min(float(a.get("ts") or now), now)        # giờ đăng tương lai (lệch đồng hồ) → bây giờ
                a["seen"] = now                                      # lúc bot biết tin (≥ giờ đăng, trễ tối đa 1 chu kỳ)
                a["id"] = _aid(a)
                if a["id"] in self.articles:
                    continue
                if now - a["ts"] > (KEEP_ANN_H if a.get("kind") == "ann" else KEEP_NEWS_H) * 3600:
                    continue
                a["desc"] = (a.get("desc") or "")[:300]              # chỉ 300 ký tự đầu được chấm điểm
                a["score"], hits = score_article(a["title"], a["desc"])
                a["hits"] = hits[:8]
                a["events"] = detect_events(a["title"])
                if a.get("kind") == "ann":
                    a["w"] = 2.0                                    # thông báo chính thức của sàn nặng gấp đôi
                    if a.get("ann_type") == "announcements-delistings" and "delist" not in a["events"] \
                            and re.search(r"\bdelist|\bremov", a["title"], re.I):
                        a["events"] = sorted(set(a["events"]) | {"delist"})
                    a["hint"] = sorted(_announcement_tickers(a["title"]))
                else:
                    a["w"] = 1.0
                a.pop("ann_type", None)
                self._detect(a)
                self.articles[a["id"]] = a
                added += 1
            for k in [k for k, a in self.articles.items()
                      if now - a["ts"] > (KEEP_ANN_H if a.get("kind") == "ann" else KEEP_NEWS_H) * 3600]:
                del self.articles[k]
            if len(self.articles) > MAX_ARTICLES:
                for k in sorted(self.articles, key=lambda k: self.articles[k]["ts"])[:len(self.articles) - MAX_ARTICLES]:
                    del self.articles[k]
        return added

    # ------------------------------------------------------------ luồng nền
    def start(self, is_leader=lambda: True):
        if not self.enabled:
            log.info("Tin tức: tắt (NEWS_ENABLED=false)")
            return

        def loop():
            time.sleep(3)
            last_load = 0.0
            while True:
                try:
                    every = max(60.0, cfg.NEWS_REFRESH_MIN * 60)
                    if is_leader():
                        if time.time() - self.last_refresh >= every:
                            self.refresh()
                    elif time.time() - last_load >= every:
                        last_load = time.time()
                        self._load()                   # máy dự phòng: đọc tin leader đã tải (để web hiển thị)
                except Exception as e:
                    log.warning("Tin tức: làm mới lỗi (%s)", str(e)[:160])
                time.sleep(20)

        threading.Thread(target=loop, daemon=True, name="news").start()

    # ------------------------------------------------------------ truy vấn (không gọi mạng)
    def _snapshot(self):
        with self._lock:
            return list(self.articles.values())

    def coin(self, base, now=None):
        """Bối cảnh tin tức của 1 coin: news_bias (−1..+1), news_n (số bài trong NEWS_WINDOW_H),
        news_events (sự kiện còn hiệu lực, chỉ tính khi coin nằm trong TIÊU ĐỀ), news_head (tiêu đề nổi bật nhất)."""
        if not self.enabled:
            return {}
        base = str(base).upper()
        now = now or time.time()
        win = cfg.NEWS_WINDOW_H * 3600
        num = den = 0.0
        n, events, head, head_w = 0, {}, None, -1.0
        for a in self._snapshot():
            rel = (a.get("coins") or {}).get(base)
            if not rel:
                continue
            age = now - a["ts"]
            for ev in (a.get("coin_ev") or {}).get(base, ()):
                if age <= EVENT_WINDOW_H.get(ev, 48) * 3600:
                    events[ev] = max(events.get(ev, 0), a["ts"])
            if age > win:
                continue
            n += 1
            w = rel * a.get("w", 1.0) * _decay(age)
            num += w * a["score"]
            den += w
            hw = w * (abs(a["score"]) + 0.1)
            if hw > head_w:
                head, head_w = a, hw
        bias = num / (den + cfg.NEWS_SHRINK) if den else 0.0
        out = {"news_bias": round(max(-1.0, min(1.0, bias)), 2), "news_n": n, "news_events": sorted(events)}
        if head:
            out["news_head"] = f"[{head['src']}] {head['title'][:110]}"
        return out

    def market(self, now=None):
        """Tâm lý chung: mkt_news (−1..+1, mọi bài trong 12h, co về 0 mạnh hơn), Fear & Greed."""
        if not self.enabled:
            return {}
        now = now or time.time()
        num = den = 0.0
        n = 0
        for a in self._snapshot():
            age = now - a["ts"]
            if a.get("kind") == "ann" or age > 12 * 3600:
                continue
            n += 1
            w = _decay(age)
            num += w * a["score"]
            den += w
        out = {"mkt_news": round(num / (den + 2.0), 2) if den else 0.0, "mkt_news_n": n}
        if self.fng and now - float(self.fng.get("ts") or 0) < 3 * 86400:
            out["fng"] = int(self.fng["value"])
            out["fng_cls"] = self.fng.get("cls") or ""
        return out

    def adverse_events(self, base, side, since_ts, kinds):
        """Sự kiện bất lợi cho vị thế `side` của coin `base` mà bot biết SAU lúc vào lệnh (since_ts), coin nằm gần
        từ khoá trong tiêu đề. long: delist, hack; short: listing. Trả về [(sự kiện, ts, tiêu đề)] mới nhất trước.
        Bài đăng trước lúc vào tối đa 1,5 chu kỳ làm mới vẫn tính (bot chưa kịp biết khi vào lệnh); bài cũ hơn thì không
        (vd. khởi động lại với kho trống: tin hack 2 ngày trước không làm đóng lệnh mở hôm qua)."""
        bad = ({"delist", "hack"} if side == "long" else {"listing"}) & set(kinds or ())
        if not bad or not self.enabled:
            return []
        base = str(base).upper()
        lag = cfg.NEWS_REFRESH_MIN * 60 * 1.5 + 300
        out = []
        for a in self._snapshot():
            if a["ts"] <= since_ts - lag or float(a.get("seen") or a["ts"]) <= since_ts:
                continue
            for ev in (a.get("coin_ev") or {}).get(base, ()):
                if ev in bad:
                    out.append((ev, a["ts"], f"[{a['src']}] {a['title'][:140]}"))
        return sorted(out, key=lambda x: -x[1])

    def hot(self, n=8, now=None):
        """Coin được nhắc nhiều nhất trong NEWS_WINDOW_H: [(mã, số bài, bias)]."""
        now = now or time.time()
        cnt = {}
        for a in self._snapshot():
            if now - a["ts"] > cfg.NEWS_WINDOW_H * 3600:
                continue
            for c, rel in (a.get("coins") or {}).items():
                if rel >= 1.0:
                    cnt[c] = cnt.get(c, 0) + 1
        top = sorted(cnt.items(), key=lambda x: -x[1])[:n]
        return [(c, k, self.coin(c, now).get("news_bias", 0.0)) for c, k in top]

    def headlines(self, limit=40):
        arts = sorted(self._snapshot(), key=lambda a: -a["ts"])[:limit]
        return [{"ts": a["ts"], "src": a["src"], "kind": a.get("kind"), "title": a["title"], "url": a.get("url"),
                 "score": a["score"], "events": a.get("events") or [], "coins": sorted((a.get("coins") or {}).keys())[:6]}
                for a in arts]

    def public(self):
        """Dữ liệu cho dashboard / Telegram."""
        return {"enabled": self.enabled, "ts": self.last_refresh, "refresh_min": cfg.NEWS_REFRESH_MIN,
                "n": len(self.articles), "status": self.status, "market": self.market(),
                "hot": self.hot(), "headlines": self.headlines(40), "event_names": EVENT_NAMES}


def _announcement_tickers(title):
    """Mã coin trong tiêu đề thông báo sàn: XYZUSDT, XYZ/USDT, danh sách 'A, B, C and D', (XYZ)."""
    out = set()
    for m in re.finditer(r"\b([A-Z0-9]{2,15})(?:USDT|USDC|USD)\b", title):
        out.add(m.group(1))
    for m in re.finditer(r"\b([A-Z0-9]{2,15})/(?:USDT|USDC|USD)\b", title):
        out.add(m.group(1))
    for m in _PAREN_RX.finditer(title):
        out.add(_strip_quote(m.group(1)))
    lst = re.search(r"(?:delist|list|remove|launch|support)\s+((?:[A-Z0-9]{2,15}(?:,\s*|\s+and\s+|\s*&\s*))+[A-Z0-9]{2,15})\b",
                    title)
    if lst:
        out |= set(re.findall(r"[A-Z0-9]{2,15}", lst.group(1)))
    out = {_strip_quote(c) for c in out}
    return {c for c in out if any(ch.isalpha() for ch in c) and c not in {"OKX", "USD", "USDT", "USDC", "UTC", "API"}}


def describe(ctx):
    """Chuỗi ngắn cho log / Telegram."""
    ctx = ctx or {}
    parts = []
    if ctx.get("fng") is not None:
        parts.append(f"F&G {ctx['fng']} ({ctx.get('fng_cls', '')})")
    if "mkt_news" in ctx:
        parts.append(f"tin thị trường {ctx['mkt_news']:+.2f} ({ctx.get('mkt_news_n', 0)} bài/12h)")
    if ctx.get("news_n"):
        parts.append(f"tin coin {ctx.get('news_bias', 0):+.2f} ({ctx['news_n']} bài)")
    if ctx.get("news_events"):
        parts.append("sự kiện: " + ", ".join(EVENT_NAMES.get(e, e) for e in ctx["news_events"]))
    return " | ".join(parts)
