"""Cấu hình bot – đọc từ biến môi trường (.env)."""
import os
import time
from dotenv import dotenv_values

# Nạp file .env / bot.env ở thư mục gốc bot (cùng chỗ run.py). Giá trị trong file ĐƯỢC ƯU TIÊN hơn biến khai báo trên panel,
# để chỉ cần dán nguyên danh sách vào 1 file. Dòng để trống hoặc còn dạng <...> (chưa điền) được bỏ qua
# → bí mật đã khai trên panel Botkeep vẫn giữ nguyên.
ENV_FILE_INFO = {"path": None, "loaded": 0, "skipped": 0}
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# bot.env: tên file KHÔNG có dấu chấm đầu → hiện trong File Manager, host không tự ghi đè (khác .env)
_files = []
for _name in (".env", "bot.env"):
    for _dir in (_ROOT, os.getcwd()):
        _p = os.path.join(_dir, _name)
        if os.path.isfile(_p) and _p not in _files:
            _files.append(_p)
            break
for _cand in _files:                                 # bot.env nạp sau → thắng .env
    try:
        for _k, _v in dotenv_values(_cand).items():
            _v = (_v or "").strip()
            if not _k or not _v or (_v.startswith("<") and _v.endswith(">")):
                ENV_FILE_INFO["skipped"] += 1
                continue
            os.environ[_k] = _v
            ENV_FILE_INFO["loaded"] += 1
        ENV_FILE_INFO["path"] = ", ".join(os.path.basename(x) for x in _files)
    except Exception as _e:                          # file hỏng không được làm sập bot
        ENV_FILE_INFO["error"] = f"{os.path.basename(_cand)}: {_e}"

# Múi giờ cho log, báo cáo ngày, Telegram (mặc định Việt Nam)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")
os.environ["TZ"] = TIMEZONE
try:
    time.tzset()
except AttributeError:
    pass


def _raw(key, default):
    """Giá trị biến; để trống / sai định dạng → dùng mặc định trong code (không làm sập bot)."""
    v = (os.getenv(key) or "").strip()
    return v if v else str(default)


def _f(key, default):
    try:
        return float(_raw(key, default).replace(",", "."))
    except ValueError:
        return float(default)


def _i(key, default):
    try:
        return int(float(_raw(key, default)))
    except ValueError:
        return int(default)


def _b(key, default="false"):
    return _raw(key, default).lower() in ("1", "true", "yes", "on")


class Config:
    # ---- Chế độ ----
    MODE = os.getenv("MODE", "paper").lower()          # paper | live
    PAPER_START_BALANCE = _f("PAPER_START_BALANCE", 10)

    # ---- OKX ----
    OKX_API_KEY = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
    OKX_DEMO = _b("OKX_DEMO", "false")                 # dùng tài khoản demo của OKX (x-simulated-trading)

    # ---- Rủi ro ----
    LEVERAGE = _i("LEVERAGE", 10)
    # Rủi ro cơ bản 3%/lệnh (v3.1: 10% khiến 5 lệnh thua liên tiếp mất ~41% vốn – chuỗi thua như vậy là bình thường
    # với tỉ lệ thắng 35–45%). Rủi ro thực tế còn được nhân với hệ số tin tức (cùng/ngược chiều × trọng số tin
    # bộ tự học đo được) và chuỗi thua – xem risk.py.
    RISK_PER_TRADE = _f("RISK_PER_TRADE", 0.03)        # % vốn mất khi chạm SL (lệnh chất lượng chuẩn)
    RISK_MAX_MULT = _f("RISK_MAX_MULT", 1.5)           # trần hệ số rủi ro (tin tức ủng hộ mạnh + trọng số tin cao)
    RISK_MIN_MULT = _f("RISK_MIN_MULT", 0.35)          # không bao giờ xuống dưới 35% rủi ro cơ bản
    LOSS_STREAK_CUT = _f("LOSS_STREAK_CUT", 0.7)       # mỗi lệnh thua liên tiếp (từ lệnh thứ LOSS_STREAK_FROM) nhân rủi ro với 0.7
    # v3.2: co từ lệnh thua thứ 3 (trước: thứ 2). 4 lệnh thua liên tiếp là bình thường với tỉ lệ thắng ~40%; co quá sớm
    # làm bot vào rất nhỏ đúng lúc thị trường đổi chiều (5 ngày chạy ảo: 2 lệnh long cuối chỉ còn 0.35× rủi ro).
    LOSS_STREAK_FROM = _i("LOSS_STREAK_FROM", 3)
    MAX_OPEN_POSITIONS = _i("MAX_OPEN_POSITIONS", 2)   # tối đa 2 lệnh, nhưng tổng rủi ro đang mở ≤ MAX_TOTAL_RISK
    MAX_TOTAL_RISK = _f("MAX_TOTAL_RISK", 0.05)        # tổng % vốn có thể mất nếu mọi lệnh đang mở chạm SL
    MIN_LOT_RISK_MULT = _f("MIN_LOT_RISK_MULT", 2.0)   # lot tối thiểu của sàn làm rủi ro vượt 2× dự tính → bỏ tín hiệu
    MAX_DAILY_LOSS = _f("MAX_DAILY_LOSS", 0.12)        # dừng ngày nếu lỗ 12% vốn đầu ngày (~4 lệnh thua)
    MAX_DRAWDOWN = _f("MAX_DRAWDOWN", 0.30)            # dừng hẳn bot nếu DD từ đỉnh > 30%, chờ /resume
    MIN_RR = _f("MIN_RR", 1.5)                         # tỉ lệ lời/lỗ tối thiểu
    TAKER_FEE = _f("TAKER_FEE", 0.0005)                # OKX taker 0.05%
    SLIPPAGE = _f("SLIPPAGE", 0.0005)                  # mô phỏng trượt giá
    ATR_SL_MULT = _f("ATR_SL_MULT", 2.0)                # SL tối thiểu (ATR) – test 10 ngày: 2.0 tốt hơn 1.5
    ATR_TP_MULT = _f("ATR_TP_MULT", 3.0)
    TRAIL_ACTIVATE_R = _f("TRAIL_ACTIVATE_R", 1.2)     # kéo SL về hoà vốn khi lời 1.2R
    MAX_HOLD_HOURS = _f("MAX_HOLD_HOURS", 12)
    # ---- Cách thoát lệnh ("ăn sóng") ----
    EXIT_MODE = os.getenv("EXIT_MODE", "auto").strip().lower()     # auto (bộ tự học chọn, khởi đầu hybrid) | hybrid | fixed | trail
    TP1_R = _f("TP1_R", 1.0)                            # hybrid: chốt 50% khi lời 1R rồi SL về hoà vốn (tự học chọn lại)
    TP1_FRACTION = _f("TP1_FRACTION", 0.5)              # chốt 50%
    TRAIL_ATR_MULT = _f("TRAIL_ATR_MULT", 2.5)          # phần còn lại bám sóng: SL = đỉnh ∓ 2.5 ATR (altcoin nhiễu mạnh)
    TRAIL_TIGHTEN_R = _f("TRAIL_TIGHTEN_R", 4.0)        # lời ≥ 4R thì siết còn ...
    TRAIL_ATR_MULT_TIGHT = _f("TRAIL_ATR_MULT_TIGHT", 1.5)
    STALL_HOURS = _f("STALL_HOURS", 4)                  # đang bám sóng mà 4h không lập đỉnh mới → thoát
    RUNNER_MAX_HOLD_HOURS = _f("RUNNER_MAX_HOLD_HOURS", 24)
    RUNNER_MAX_TP_ATR = _f("RUNNER_MAX_TP_ATR", 10)     # TP an toàn rất xa cho phần bám sóng

    # ---- Quét coin ----
    TOP_N_COINS = _i("TOP_N_COINS", 50)
    # Loại BTC/ETH, stablecoin và các "token hoá" cổ phiếu / hàng hoá / chỉ số mà OKX niêm yết (không phải altcoin)
    _DEFAULT_EXCLUDE = (
        "BTC,ETH,USDC,USDT,DAI,TUSD,FDUSD,USDE,"
        "XAU,XAG,XPT,XPD,WTI,BRENT,NATGAS,"
        "TSLA,NVDA,AAPL,MSFT,AMZN,GOOGL,GOOG,META,COIN,MSTR,HOOD,CRCL,PLTR,AMD,INTC,MU,"
        "SNDK,SOXL,SKHYNIX,SPY,QQQ,SPX,NDX,DJI,TQQQ,SQQQ,NFLX,AVGO,ORCL,TSM,ASML,GME,AMC"
    )
    EXCLUDE = [s.strip().upper() for s in os.getenv("EXCLUDE", _DEFAULT_EXCLUDE).split(",") if s.strip()]
    # v4.0: chỉ quét hợp đồng crypto thường theo phân loại của OKX (instCategory=1, ruleType=normal, chưa có lịch gỡ).
    # Danh sách EXCLUDE ở trên không theo kịp: 05/11/2026 có 203 hợp đồng cổ phiếu/hàng hoá không nằm trong danh sách.
    CRYPTO_ONLY = _b("CRYPTO_ONLY", "true")
    TIMEFRAME = os.getenv("TIMEFRAME", "15m")
    HTF_TIMEFRAME = os.getenv("HTF_TIMEFRAME", "1h")
    SCAN_INTERVAL = _i("SCAN_INTERVAL", 300)           # giây giữa 2 lần quét tín hiệu
    MONITOR_INTERVAL = _i("MONITOR_INTERVAL", 20)      # giây giữa 2 lần kiểm tra SL/TP
    # v3.1: điểm 5.0 (dữ liệu 80 tín hiệu bóng: điểm 4.x–5.x không thua 6.x; chất lượng được phản ánh vào KHỐI LƯỢNG
    # thay vì chặn cứng – xem risk.quality_mult). Bộ tự học vẫn chỉnh trong 4.0–7.0.
    MIN_SCORE = _f("MIN_SCORE", 5.0)                   # điểm tối thiểu (kỹ thuật + dòng tiền + tin tức) để vào lệnh
    # ---- Cổng bắt buộc của tín hiệu ----
    MIN_ADX = _f("MIN_ADX", 20)                        # ADX 15m tối thiểu (lọc sideway)
    HTF_MIN_ADX = _f("HTF_MIN_ADX", 18)                # ADX 1h tối thiểu để công nhận xu hướng
    MIN_ATR_PCT = _f("MIN_ATR_PCT", 0.35)              # ATR% tối thiểu
    MIN_VOL_RATIO = _f("MIN_VOL_RATIO", 0.7)           # volume nến tín hiệu >= 70% trung bình 20 nến (lý do loại #1 là "volume yếu")
    BREAKOUT_VOL = _f("BREAKOUT_VOL", 1.5)
    MAX_EXT_ATR = _f("MAX_EXT_ATR", 1.0)               # giá cách EMA21 tối đa (ATR) – chống đuổi giá (backtest: >1 ATR lỗ)
    MAX_SL_ATR = _f("MAX_SL_ATR", 3.0)                 # SL theo cấu trúc xa hơn mức này → bỏ tín hiệu
    # v3.2: 0.6 → 0.3. 211 tín hiệu bóng: short khi BTC đang +0.3%/1h trở lên cho -0.60R (n=27, thắng 22%).
    BTC_GATE_CHG = _f("BTC_GATE_CHG", 0.3)             # BTC giảm/tăng quá % này trong 1h → cấm long/short altcoin
    # v3.2: không đánh ngược nhịp 1h của chính coin – short khi coin vừa tăng ≥0.5% trong 1h (hoặc long khi vừa giảm)
    # là "bắt đỉnh của nhịp hồi": 56 tín hiệu bóng cho -0.72R, thắng 18%; nhóm còn lại -0.13R.
    CHASE_1H_PCT = _f("CHASE_1H_PCT", 0.5)
    # v3.2: volume nến tín hiệu ≥ 1.5× trung bình là cao trào (climax), không phải xác nhận: 31 tín hiệu bóng -0.68R,
    # thắng 16% (volume < 1.5×: -0.16R). Trừ điểm thay vì cộng, và luật climax_volume chặn sẵn.
    CLIMAX_VOL = _f("CLIMAX_VOL", 1.5)
    # ADX 1h ≥ 35 = "xu hướng đã chạy lâu". v3.2 trừ 1 điểm (76 short bóng của 5 ngày: -0.44R). v4.2 BỎ điểm trừ:
    # kiểm chứng 89 ngày × 40 coin (tools/wf_results/2026-11-05) cho thấy nhóm này đảo dấu theo giai đoạn
    # (08–09: +0.33R, t=4.3; 10–11: -0.20R, t=-2.7) và bỏ điểm trừ tốt hơn ở CẢ HAI nửa (danh mục +8.5R so với +2.7R).
    # Luật late_trend vẫn trong danh mục → bộ tự học tự chặn khi nhóm này lỗ rõ. Đặt LATE_TREND_PENALTY=1 để trừ lại như v3.2.
    LATE_TREND_ADX = _f("LATE_TREND_ADX", 35)
    LATE_TREND_PENALTY = _f("LATE_TREND_PENALTY", 0)
    WICK_CLOSE_POS = _f("WICK_CLOSE_POS", 0.6)         # long: nến tín hiệu đóng >= 60% biên độ (short: <= 40%)
    # Luật chặn sẵn từ đầu (bộ tự học vẫn theo dõi bóng và tự gỡ nếu thực tế có lãi)
    # v3.1: chặn thêm phiên 0h–7h (giờ VN): 14 tín hiệu bóng chỉ thắng 1, kỳ vọng -0.89R. Bộ tự học sẽ gỡ nếu bóng có lãi.
    # v3.2: chặn thêm 13h–19h VN (06–12 UTC): lỗ ở backtest 10 ngày lẫn 5 ngày chạy ảo (-0.33..-0.76R mỗi khung 2h),
    # và nến volume cao trào (climax_volume). 14h–16h UTC (21h–23h VN, Mỹ mở cửa) là khung duy nhất có lãi rõ (+0.42R, n=27).
    # v4.0: thêm 3 luật tin tức chặn sẵn – coin có tin huỷ niêm yết (mọi hướng), long khi có tin hack/exploit,
    # short khi vừa có tin niêm yết sàn lớn (dễ bị ép giá). Vẫn theo dõi bóng → bộ tự học gỡ nếu thực tế có lãi.
    DEFAULT_BLOCKS = [x.strip() for x in os.getenv(
        "DEFAULT_BLOCKS", "setup_range,night_session,afternoon_session,climax_volume,"
                          "news_delist,news_hack_long,news_listing_short").split(",") if x.strip()]
    # Setup RANGE: đảo chiều tại biên Bollinger khi 1h đi ngang (có lệnh cả lúc thị trường sideway)
    RANGE_ENABLED = _b("RANGE_ENABLED", "true")
    RANGE_MAX_HTF_ADX = _f("RANGE_MAX_HTF_ADX", 25)      # ADX 1h phải dưới mức này
    RANGE_MAX_ADX = _f("RANGE_MAX_ADX", 25)              # ADX 15m phải dưới mức này
    RANGE_RSI_LONG = _f("RANGE_RSI_LONG", 35)            # long: RSI 15m <= 35 (short: >= 65) trong 3 nến gần nhất
    RANGE_CLOSE_POS = _f("RANGE_CLOSE_POS", 0.6)         # nến từ chối: long đóng >= 60% biên độ
    RANGE_MAX_SL_ATR = _f("RANGE_MAX_SL_ATR", 2.0)
    RANGE_MIN_RR = _f("RANGE_MIN_RR", 1.2)               # tối thiểu RR từ giá tới dải giữa
    RANGE_MIN_SCORE = _f("RANGE_MIN_SCORE", 4.5)        # điểm tối thiểu riêng cho setup range
    RSI_LONG_MIN = _f("RSI_LONG_MIN", 45); RSI_LONG_MAX = _f("RSI_LONG_MAX", 70)
    RSI_SHORT_MIN = _f("RSI_SHORT_MIN", 30); RSI_SHORT_MAX = _f("RSI_SHORT_MAX", 55)

    TIMEZONE = TIMEZONE
    # ---- Quyết định vào lệnh (v4.0: KHÔNG dùng AI – thuần kỹ thuật + tin tức, bộ tự học kiểm chứng) ----
    # Mỗi lượt quét thử lần lượt tối đa N ứng viên điểm cao nhất; vào được 1 lệnh thì dừng (các lệnh altcoin
    # cùng lượt thường cùng hướng BTC → vào nhiều lệnh một lúc chỉ là nhân đôi một rủi ro).
    ENTRY_CANDIDATES = _i("ENTRY_CANDIDATES", 3)
    TRADE_REVIEW = _b("TRADE_REVIEW", "true")                # tổng kết (theo quy tắc) sau mỗi lệnh đóng
    DAILY_REVIEW = _b("DAILY_REVIEW", "true")                # báo cáo tự học mỗi ngày (số liệu, không AI)
    DAILY_REVIEW_HOUR = _i("DAILY_REVIEW_HOUR", 7)           # giờ (theo TIMEZONE)

    # ---- Tin tức (từ điển + luật sự kiện, không AI) ----
    NEWS_ENABLED = _b("NEWS_ENABLED", "true")
    # RSS miễn phí, không cần key. Định dạng: tên|url, phân tách bằng dấu phẩy (hoặc chỉ url).
    _DEFAULT_FEEDS = (
        "CoinDesk|https://www.coindesk.com/arc/outboundfeeds/rss/,"
        "Cointelegraph|https://cointelegraph.com/rss,"
        "The Block|https://www.theblock.co/rss.xml,"
        "Decrypt|https://decrypt.co/feed,"
        "CryptoSlate|https://cryptoslate.com/feed/,"
        "Bitcoinist|https://bitcoinist.com/feed/,"
        "CryptoPotato|https://cryptopotato.com/feed/,"
        "U.Today|https://u.today/rss,"
        "NewsBTC|https://www.newsbtc.com/feed/,"
        "BeInCrypto|https://beincrypto.com/feed/"
    )
    NEWS_FEEDS = [x.strip() for x in _raw("NEWS_FEEDS", _DEFAULT_FEEDS).split(",") if x.strip()]
    NEWS_ANNOUNCEMENTS = _b("NEWS_ANNOUNCEMENTS", "true")    # thông báo niêm yết / huỷ niêm yết của OKX + Binance
    NEWS_FNG = _b("NEWS_FNG", "true")                        # chỉ số Fear & Greed (alternative.me)
    NEWS_REFRESH_MIN = _f("NEWS_REFRESH_MIN", 10)            # phút giữa 2 lần tải tin
    NEWS_TIMEOUT = _i("NEWS_TIMEOUT", 15)                    # giây tối đa cho 1 nguồn
    NEWS_WINDOW_H = _f("NEWS_WINDOW_H", 24)                  # chỉ tính bài trong 24h gần nhất cho điểm tin của coin
    NEWS_HALF_LIFE_H = _f("NEWS_HALF_LIFE_H", 6)             # bài 6h trước nặng bằng nửa bài vừa đăng
    # co về 0 khi ít bài: 1 bài lẻ (dù rất mạnh) chỉ kéo độ lệch tới ~0.4; cần nhiều bài cùng chiều mới đủ mạnh
    NEWS_SHRINK = _f("NEWS_SHRINK", 1.0)
    NEWS_MIN_BIAS = _f("NEWS_MIN_BIAS", 0.15)                # |độ lệch tin| dưới mức này coi như không có tin
    # Điểm cộng/trừ tối đa từ tin tức = NEWS_SCORE_MAX × trọng số tin (NEWS_WEIGHT, bộ tự học chỉnh 0–2)
    NEWS_SCORE_MAX = _f("NEWS_SCORE_MAX", 1.5)
    NEWS_WEIGHT = _f("NEWS_WEIGHT", 1.0)
    # Lệnh đang mở gặp tin xấu MỚI (đăng sau lúc vào lệnh, coin nằm trong tiêu đề) → đóng ngay:
    # long: delist, hack | short: listing. Để trống để tắt.
    NEWS_EXIT_EVENTS = [x.strip() for x in os.getenv("NEWS_EXIT_EVENTS", "delist,hack,listing").split(",") if x.strip()]

    # ---- Lớp bảo vệ (v4.1, kiểu freqtrade – xem protections.py) ----
    PROTECT_ENABLED = _b("PROTECT_ENABLED", "true")
    PROTECT_SIDE_LOSSES = _i("PROTECT_SIDE_LOSSES", 3)         # ≥ 3 lệnh thật cùng phía đóng lỗ …
    PROTECT_SIDE_HOURS = _f("PROTECT_SIDE_HOURS", 12)          # … trong 12h → khoá phía đó
    PROTECT_SHADOW_MIN = _i("PROTECT_SHADOW_MIN", 10)          # hoặc ≥ 10 coin có tín hiệu cùng phía (kể cả không vào) …
    PROTECT_SHADOW_SL_SHARE = _f("PROTECT_SHADOW_SL_SHARE", 0.8)   # … mà ≥ 80% chạm SL trước khi lời 1R …
    PROTECT_SHADOW_HOURS = _f("PROTECT_SHADOW_HOURS", 12)      # … trong 12h gần nhất
    PROTECT_LOCK_HOURS = _f("PROTECT_LOCK_HOURS", 6)           # thời gian khoá phía
    PROTECT_PAIR_LOSS_HOURS = _f("PROTECT_PAIR_LOSS_HOURS", 6)     # coin vừa thua → nghỉ 6h
    PROTECT_PAIR_REPEAT_HOURS = _f("PROTECT_PAIR_REPEAT_HOURS", 24)  # thua 2 lần trong 24h → nghỉ tới hết 24h
    PROTECT_MIN_AGE_DAYS = _f("PROTECT_MIN_AGE_DAYS", 10)      # bỏ hợp đồng niêm yết chưa đủ 10 ngày

    # ---- Tự học ----
    LEARN_MODE = os.getenv("LEARN_MODE", "").strip().lower()  # auto | suggest | off (trống: paper=auto, live=suggest)
    LEARN_MIN_SAMPLES = _i("LEARN_MIN_SAMPLES", 30)           # số tín hiệu tối thiểu trước khi thay đổi gì
    # v3.2: 1.3 → 2.0. Với t ≥ 1.3 (p một phía ≈ 0.10) và ~25 nhóm được so cùng lúc, bộ tự học "học" nhiễu rồi đảo ngược
    # sau 48h (5 ngày chạy ảo: trọng số pullback 1.0→1.2→1.0, vwap 1.0→1.17→0.97, chặn cả phía short sau 2 ngày xấu).
    LEARN_MIN_T = _f("LEARN_MIN_T", 2.0)                      # |kỳ vọng| / sai số chuẩn ≥ 2.0 (≈97.5% một phía) mới coi là khác 0
    LEARN_EXIT_MIN_SAMPLES = _i("LEARN_EXIT_MIN_SAMPLES", 60)  # đổi cách thoát lệnh cần ≥ 60 tín hiệu so theo cặp
    LEARN_COOLDOWN_H = _f("LEARN_COOLDOWN_H", 48)             # mỗi tham số đổi tối đa 1 lần / 48h (chống nhảy qua lại)
    LEARN_WINDOW_DAYS = _i("LEARN_WINDOW_DAYS", 21)           # chỉ học từ dữ liệu N ngày gần nhất
    # v4.0: kiểm soát tỉ lệ phát hiện sai (Benjamini–Hochberg) khi thử ~30 luật + trigger cùng lúc; 0 = tắt
    LEARN_FDR_Q = _f("LEARN_FDR_Q", 0.10)

    # ---- Telegram ----
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # ---- Nhiều instance (Render + Botkeep chạy song song) ----
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()          # Postgres dùng chung; trống = SQLite 1 máy
    INSTANCE_NAME = os.getenv("INSTANCE_NAME", "") or os.getenv("RENDER_SERVICE_NAME", "") or os.uname().nodename
    LEADER_TTL = _i("LEADER_TTL", 90)                              # giây; leader mất liên lạc quá lâu → máy kia tiếp quản
    PEER_URL = os.getenv("PEER_URL", "").strip()                   # URL /health của instance kia (giữ Render không ngủ)
    SELF_URL = os.getenv("SELF_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    KEEPALIVE_INTERVAL = _i("KEEPALIVE_INTERVAL", 240)

    # ---- Zoom Team Chat ----
    ZOOM_WEBHOOK_URL = os.getenv("ZOOM_WEBHOOK_URL", "").strip()          # Incoming Webhook (gửi thông báo)
    ZOOM_WEBHOOK_TOKEN = os.getenv("ZOOM_WEBHOOK_TOKEN", "").strip()
    ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "").strip()              # Chatbot (nhận lệnh) – tuỳ chọn
    ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "").strip()
    ZOOM_BOT_JID = os.getenv("ZOOM_BOT_JID", "").strip()
    ZOOM_SECRET_TOKEN = (os.getenv("ZOOM_SECRET_TOKEN") or os.getenv("ZOOM_BOT_SECRET_TOKEN") or "").strip()  # Access > Secret Token
    ZOOM_VERIFICATION_TOKEN = os.getenv("ZOOM_VERIFICATION_TOKEN", "").strip()   # cơ chế xác thực cũ (nếu không có Secret Token)
    ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID", "").strip()
    ZOOM_TO_JID = os.getenv("ZOOM_TO_JID", "").strip()                    # tuỳ chọn: JID nhận thông báo cố định
    ZOOM_ALLOWED_USERS = os.getenv("ZOOM_ALLOWED_USERS", "").strip()      # tuỳ chọn: email/JID tự được cấp quyền

    PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()                      # vd https://okx.bot-keep.xyz – dùng cho OAuth redirect
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "").strip()                # hiện trên trang /privacy, /support

    # ---- Dashboard ----
    # Render cấp PORT; một số host (Botkeep) cấp SERVER_PORT / APP_PORT – bot nhận cái nào có
    DASHBOARD_PORT = _i("PORT", 0) or _i("SERVER_PORT", 0) or _i("APP_PORT", 0) or _i("DASHBOARD_PORT", 8080)
    DASHBOARD_USER = os.getenv("DASHBOARD_USER", "")
    DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")

    DATA_DIR = os.getenv("DATA_DIR", "data")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


cfg = Config()
