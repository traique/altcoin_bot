"""Kiểm tra bộ lọc & quyết định: cổng BTC, chống râu nến, SL cấu trúc, trigger động lượng không cộng trùng,
điểm dòng tiền, điểm & luật tin tức, quyết định thuần quy tắc (v4.0, không AI)."""
import os, sys, random
os.environ.setdefault("DATA_DIR", "/tmp/okx_test_strategy")
sys.path.insert(0, os.path.dirname(__file__))
from types import SimpleNamespace as NS
from bot.config import cfg
from bot import strategy as S
from bot.indicators import to_frame, enrich

def row(**k):
    base = dict(adx=30, atr_pct=1.0, vol_ratio=1.2, close=101, open=100, ema21=100.5, atr=1.0, rsi=60, close_pos=0.8)
    base.update(k); return NS(**base)

# 1) cổng BTC
assert S._gates(row(), "long", 1, {"btc_trend_1h": -1}) == "BTC đang xu hướng giảm"
assert S._gates(row(), "long", 1, {"btc_trend_1h": 0, "btc_chg_1h": -0.7}) == "BTC đang xu hướng giảm"
assert S._gates(row(), "long", 1, {"btc_trend_1h": 0, "btc_chg_1h": -0.3}) == ""
assert S._gates(row(close=99, open=100, ema21=99.5, rsi=40, close_pos=0.2), "short", -1, {"btc_trend_1h": 1}) == "BTC đang xu hướng tăng"
assert S._gates(row(close=99, open=100, ema21=99.5, rsi=40, close_pos=0.2), "short", -1, {"btc_chg_1h": 0.8}) == "BTC đang xu hướng tăng"
assert S._gates(row(), "long", 1, None) == ""
print("✓ cổng BTC")

# 2) chống râu nến
W = cfg.WICK_CLOSE_POS
assert "râu trên" in S._gates(row(close_pos=W - 0.05), "long", 1)
assert S._gates(row(close_pos=W + 0.01), "long", 1) == ""
assert "râu dưới" in S._gates(row(close=99, open=100, ema21=99.5, rsi=40, close_pos=1 - W + 0.05), "short", -1)
assert S._gates(row(close=99, open=100, ema21=99.5, rsi=40, close_pos=1 - W - 0.01), "short", -1) == ""
assert "chạy quá xa" in S._gates(row(close=102, ema21=100.5), "long", 1)      # cách EMA21 1.5 ATR > MAX_EXT_ATR
print("✓ chống râu nến")

# 3) SL theo cấu trúc – không bao giờ kéo vào giữa râu
df = NS(low=[95, 99, 99.5, 99.6, 99.7, 99.8], high=[101] * 6)
sl, tp = S._levels(df, "long", 100, 1.0)
assert abs(sl - (95 - 0.15)) < 1e-9, sl          # dưới đáy cấu trúc, không bị gọt về 97.5
df2 = NS(low=[99.2] * 6, high=[101] * 6)
sl2, _ = S._levels(df2, "long", 100, 1.0)
assert abs(sl2 - (100 - cfg.ATR_SL_MULT)) < 1e-9, sl2   # đáy gần → dùng ATR_SL_MULT × ATR
print("✓ SL cấu trúc: đáy xa → SL", round(sl, 2), "(diagnose sẽ bỏ vì > MAX_SL_ATR)")

# 4) trigger động lượng không cộng trùng
r = NS(ema9=3, ema21=2, ema50=1, close=1, ema200=5, adx=10, vol_ratio=1, close_pos=0.5, body_pct=0.3, vwap=9)
h = NS(di_plus=0, di_minus=1, macd_hist=-1, rsi=40, adx=20)
fr = NS(row=lambda i: r); hf = NS(row=lambda i: h)
s_mom, _ = S._score(fr, hf, "long", ["MACD cắt lên", "EMA9 cắt lên EMA21"], 0, 0)
s_one, _ = S._score(fr, hf, "long", ["MACD cắt lên"], 0, 0)
s_mix, _ = S._score(fr, hf, "long", ["MACD cắt lên", "Pullback EMA21 + nến bật"], 0, 0)
assert s_mom == s_one, (s_mom, s_one)             # MACD + EMA = chỉ 1 trigger
assert s_mix == s_one + 1.5, (s_mix, s_one)       # động lượng + cấu trúc = 2 trigger
print(f"✓ trigger: MACD+EMA = {s_mom} (bằng 1 trigger), MACD+Pullback = {s_mix}")

# 4b) v3.2: volume cao trào & xu hướng 1h đã chạy lâu bị TRỪ điểm (không cộng)
r_cl = NS(**{**vars(r), "vol_ratio": cfg.CLIMAX_VOL})
s_cl, why_cl = S._score(NS(row=lambda i: r_cl), hf, "long", ["MACD cắt lên"], 0, 0)
assert s_cl == s_one - 1 and any("cao trào" in w for w in why_cl), (s_cl, s_one)
h_late = NS(**{**vars(h), "adx": cfg.LATE_TREND_ADX})
s_late, why_late = S._score(fr, NS(row=lambda i: h_late), "long", ["MACD cắt lên"], 0, 0)
assert s_late == s_one - 1 and any("chạy lâu" in w for w in why_late), (s_late, s_one)
print("✓ v3.2: volume cao trào -1, ADX 1h ≥ 35 -1")

# 4c) v3.2: cổng "ngược nhịp 1h của coin"
assert "ngược nhịp 1h" in S._gates(row(), "long", 1, None, chg1h=-cfg.CHASE_1H_PCT)
assert S._gates(row(), "long", 1, None, chg1h=-cfg.CHASE_1H_PCT + 0.1) == ""
sh = row(close=99, open=100, ema21=99.5, rsi=40, close_pos=0.2)
assert "ngược nhịp 1h" in S._gates(sh, "short", -1, None, chg1h=cfg.CHASE_1H_PCT)
assert S._gates(sh, "short", -1, None, chg1h=-1.0) == ""
assert S._gates(sh, "short", -1, {"btc_chg_1h": cfg.BTC_GATE_CHG + 0.01}) == "BTC đang xu hướng tăng"
print("✓ v3.2: cổng ngược nhịp 1h; cổng BTC %.1f%%" % cfg.BTC_GATE_CHG)

# 5) điểm dòng tiền
def sig(side, **ctx):
    return S.Signal("X/USDT:USDT", side, 5.3, 100, 1, 98, 104, [], ctx)
a = sig("long", oi_chg_1h=2.0, px_chg_1h=1.0); assert S.flow_adjust(a)[0] == 0.5
assert S.apply_flow(a) == "" and a.score == 5.8          # 5.3 + 0.5 ≥ 5.5 → đạt
b = sig("long", oi_chg_1h=-2.0, px_chg_1h=1.0); assert S.flow_adjust(b)[0] == -1.0
assert S.apply_flow(b).startswith("điểm thấp")
c = sig("short", oi_chg_1h=2.0, px_chg_1h=1.0); assert S.flow_adjust(c)[0] == 0   # giá ngược chiều lệnh
d = sig("long", funding=0.002); assert S.flow_adjust(d)[0] == -1.0
print("✓ điểm dòng tiền OI/funding")

# 6) v4.0 – tin tức: điểm cộng/trừ theo hướng lệnh × trọng số tin, luật tin tức, quyết định không AI
def nsig(side, score=5.0, **ctx):
    return S.Signal("X/USDT:USDT", side, score, 100, 1, 98 if side == "long" else 102, 104 if side == "long" else 96, [], ctx)
L0 = cfg.NEWS_SCORE_MAX
d, why = S.news_adjust(nsig("long", news_bias=0.6, news_n=3, news_head="[CoinDesk] X soars"))
assert abs(d - round(L0 * 0.6, 2)) < 1e-9 and "ủng hộ" in why[0] and "X soars" in why[0], (d, why)
assert S.news_adjust(nsig("short", news_bias=0.6, news_n=3))[0] == -round(L0 * 0.6, 2)      # tin tốt → short bị trừ
assert S.news_adjust(nsig("long", news_bias=0.1, news_n=3))[0] == 0                        # dưới NEWS_MIN_BIAS
assert S.news_adjust(nsig("long", news_bias=0.9, news_n=0))[0] == 0                        # không có bài nào
S.LEARNED["news_w"] = 0.0; assert S.news_adjust(nsig("long", news_bias=0.9, news_n=5))[0] == 0   # trọng số 0 → bỏ qua tin
S.LEARNED["news_w"] = 2.0; assert S.news_adjust(nsig("long", news_bias=1.0, news_n=5))[0] == 2 * L0
S.LEARNED["news_w"] = None
g = nsig("long", score=cfg.MIN_SCORE - 0.4, news_bias=0.5, news_n=2)
assert S.apply_context(g) == "" and g.score >= cfg.MIN_SCORE                                 # tin tốt đẩy qua ngưỡng
b2 = nsig("long", score=cfg.MIN_SCORE + 0.3, news_bias=-0.6, news_n=4)
assert S.apply_context(b2).startswith("điểm thấp")                                          # tin xấu kéo xuống dưới ngưỡng
# luật tin tức
R_ = lambda side, **c: set(S.matching_rules(side, c))
assert "news_delist" in R_("short", news_events=["delist"]) and "news_delist" in R_("long", news_events=["delist"])
assert "news_hack_long" in R_("long", news_events=["hack"]) and "news_hack_long" not in R_("short", news_events=["hack"])
assert "news_listing_short" in R_("short", news_events=["listing"]) and "news_listing_short" not in R_("long", news_events=["listing"])
assert "news_against" in R_("long", news_bias=-0.4, news_n=2) and "news_against" not in R_("short", news_bias=-0.4, news_n=2)
assert "fng_greed_long" in R_("long", fng=80) and "fng_fear_short" in R_("short", fng=20)
assert not ({"fng_greed_long", "fng_fear_short"} & (R_("long", fng=50) | R_("short", fng=50) | R_("long")))   # thiếu dữ liệu → không khớp
assert "mkt_news_against" in R_("short", mkt_news=0.3) and "mkt_news_against" not in R_("long", mkt_news=0.3)
assert {"news_delist", "news_hack_long", "news_listing_short"} <= S.active_blocks()            # chặn sẵn
hk = nsig("long", score=6, news_events=["hack"]); assert "hack" in S.blocked_by(hk)
# quyết định (thay AI)
ok = nsig("long", score=cfg.MIN_SCORE + 1, news_bias=0.4, news_n=2, fng=55)
dec = S.decide(ok)
assert dec["decision"] == "LONG" and dec["confidence"] == 60 and dec["news"] == 0.4 and "F&G 55" in dec["reason"], dec
assert S.decide(hk)["decision"] == "SKIP" and S.decide(nsig("long", score=cfg.MIN_SCORE - 1))["decision"] == "SKIP"
print("✓ v4.0: điểm tin tức theo hướng lệnh × trọng số, luật tin tức chặn sẵn, quyết định không AI")

# 7) luật chặn sẵn & gỡ chặn
from bot.learner import Learner
S.LEARNED.update({"blocks": [], "unblocked": []})
assert {"afternoon_session", "setup_range", "night_session", "climax_volume", "news_delist"} <= S.active_blocks()   # mặc định
S.LEARNED["blocks"] = ["short_side", "weak_adx"]
assert "short_side" not in S.active_blocks() and "weak_adx" in S.active_blocks()   # không bao giờ chặn cả phía
S.LEARNED["blocks"] = []
_saved = cfg.DEFAULT_BLOCKS; cfg.DEFAULT_BLOCKS = ["afternoon_session", "setup_range"]
assert "afternoon_session" in S.active_blocks()
sg = S.Signal("X/USDT:USDT", "long", 6, 100, 1, 98, 104, [], {"hour": 15})
assert "13h–19h" in S.blocked_by(sg)
sg.context["hour"] = 21; assert S.blocked_by(sg) == ""
Learner._apply(NS(store=NS(set=lambda *a: None, get=lambda *a: {}), _touch=lambda k: None),
               {"kind": "unblock", "key": "afternoon_session", "new": False})
assert "afternoon_session" not in S.active_blocks() and "afternoon_session" in S.LEARNED["unblocked"]
S.LEARNED.update({"blocks": [], "unblocked": []}); cfg.DEFAULT_BLOCKS = _saved
print("✓ luật chặn sẵn (phiên 13h–19h, setup range) + bộ tự học gỡ được")

# 8) setup range: TP riêng → thoát fixed tại dải giữa
from bot.engine import plan_exit
rs = S.Signal("X/USDT:USDT", "long", 5, 100, 1, 99, 101.5, [], {"setup": "range"})
assert plan_exit(rs, 100) == ("fixed", 101.5, None)
assert S.min_rr_for(rs) == cfg.RANGE_MIN_RR and S.min_score_for(rs) == cfg.RANGE_MIN_SCORE
ts_ = S.Signal("X/USDT:USDT", "long", 5, 100, 1, 98, 104, [], {"setup": "trend"})
m, tp, tp1 = plan_exit(ts_, 100)
assert tp1 is None or abs(tp1 - (100 + 2 * __import__("bot.exits", fromlist=["x"]).current_tp1_r())) < 1e-9
print("✓ setup range thoát fixed tại dải giữa; trend dùng TP1 tự học")
print("TẤT CẢ OK")
