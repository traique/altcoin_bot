"""Kiểm tra v4.1: cổng lọc có ngưỡng học được + tín hiệu "suýt qua cổng" + bộ tự học nới/siết cổng,
và lớp bảo vệ kiểu freqtrade (khoá phía, khoá coin, tuổi niêm yết, rào ±1R chạm trước)."""
import os, shutil, time, json
os.environ.update(MODE="paper", DATA_DIR="/tmp/okx-gates-test", DATABASE_URL="", LEARN_MODE="auto",
                  LEARN_MIN_SAMPLES="12")
shutil.rmtree("/tmp/okx-gates-test", ignore_errors=True)
from types import SimpleNamespace as NS
from bot.config import cfg
from bot import strategy as S
from bot.storage import Store
from bot.learner import Learner
from bot.protections import Protections, first_barrier

# 1) ngưỡng cổng: mặc định từ config, bộ tự học ghi đè; RSI tính theo hướng lệnh
assert S.gv("min_adx") == cfg.MIN_ADX and S.gv("rsi_floor", "short") == 100 - cfg.RSI_SHORT_MAX
S.LEARNED["gates"] = {"min_adx": 18, "rsi_floor": 42.5}
assert S.gv("min_adx") == 18 and S.gv("rsi_floor", "short") == 42.5
S.LEARNED["gates"] = {}
ctx = {"adx": 21, "chg1h": -0.4, "btc_chg_1h": 0.2, "rsi": 40, "close_pos": 0.3, "ext_atr": 0.8, "sl_atr": 2.1}
assert S.gate_value("chase_1h_pct", "long", ctx) == 0.4 and S.gate_value("chase_1h_pct", "short", ctx) == -0.4
assert S.gate_value("btc_gate_chg", "short", ctx) == 0.2 and S.gate_value("rsi_floor", "short", ctx) == 60
assert abs(S.gate_value("wick_close_pos", "short", ctx) - 0.7) < 1e-9
assert S.gate_near("min_adx", 17, 20) and not S.gate_near("min_adx", 15, 20)
assert S.gate_near("max_ext_atr", 1.4, 1.0) and not S.gate_near("max_ext_atr", 1.6, 1.0)
print("✓ ngưỡng cổng: mặc định, ghi đè của bộ tự học, giá trị theo hướng lệnh, vùng suýt qua")


# 2) gate_fails: đủ mọi cổng hỏng, đúng thứ tự cũ; _gates trả lý do đầu tiên như trước
def row(**k):
    base = dict(adx=30, atr_pct=1.0, vol_ratio=1.2, close=101, open=100, ema21=100.5, atr=1.0, rsi=60, close_pos=0.8)
    base.update(k)
    return NS(**base)


f = S.gate_fails(row(adx=18, vol_ratio=0.6), "long", 1, None)
assert [x["key"] for x in f] == ["min_adx", "min_vol_ratio"] and S._gates(row(adx=18, vol_ratio=0.6), "long", 1) == f[0]["why"]
f = S.gate_fails(row(close=99, open=100, ema21=99.5, rsi=40, close_pos=0.2), "short", -1, {"btc_trend_1h": 1})
assert f[0]["key"] is None and f[0]["why"] == "BTC đang xu hướng tăng"
assert S.gate_fails(row(), "long", 1, {"btc_chg_1h": -0.5})[0]["key"] == "btc_gate_chg"
print("✓ kiểm tra đủ mọi cổng, thứ tự & lý do như bản cũ")


# 3) evaluate(): trượt ĐÚNG 1 cổng sát ngưỡng → tín hiệu "suýt qua cổng" (không vào lệnh), 2 cổng hoặc trượt xa → loại
class FakeFrame:
    def __init__(self, **k):
        base = dict(close=101.0, open=100.0, high=101.2, low=99.9, ema9=100.8, ema21=100.5, ema50=100.0, ema200=99.0,
                    vwap=100.4, macd_hist=0.1, adx=30.0, atr=1.0, atr_pct=1.0, vol_ratio=1.2, rsi=60.0, close_pos=0.8,
                    bb_lo=98.0, bb_up=103.0, bb_mid=100.5, hh20=102.0, ll20=98.0, di_plus=25.0, di_minus=15.0, body_pct=0.6)
        base.update(k)
        self.r = NS(**base)
        self.n = 200
        self.close = [100.9] * 200

    def row(self, i):
        return self.r


S._htf_trend = lambda htf: 1                                   # 1h xu hướng tăng
S._triggers = lambda df, side: ["MACD cắt lên"]
S._levels = lambda df, side, price, a: (price - 2 * a, price + 4 * a)
htf = FakeFrame()
sig, why, _ = S.evaluate("X/USDT:USDT", FakeFrame(), htf)
assert sig is not None and why == "" and sig.context["ext_atr"] == 0.5 and sig.context["sl_atr"] == 2.0
sig, why, _ = S.evaluate("X/USDT:USDT", FakeFrame(adx=17.0), htf)             # ADX 17 < 20, trong vùng 4
assert sig is not None and why.startswith(S.NEAR_PREFIX + "ADX thấp") and sig.context["gate_near"] == "min_adx"
assert sig.context["gate_val"] == 17.0
assert S.evaluate("X/USDT:USDT", FakeFrame(adx=14.0), htf)[0] is None                   # trượt xa
assert S.evaluate("X/USDT:USDT", FakeFrame(adx=17.0, vol_ratio=0.6), htf)[0] is None     # trượt 2 cổng
sig, why, _ = S.evaluate("X/USDT:USDT", FakeFrame(close=101.6), htf)           # cách EMA21 1.1 ATR > 1.0
assert sig.context["gate_near"] == "max_ext_atr"
S._levels = lambda df, side, price, a: (price - 3.4 * a, price + 6 * a)        # SL cấu trúc 3.4 ATR > 3.0
sig, why, _ = S.evaluate("X/USDT:USDT", FakeFrame(), htf)
assert sig.context["gate_near"] == "max_sl_atr" and why.startswith(S.NEAR_PREFIX + "SL theo cấu trúc quá xa")
S.LEARNED["gates"] = {"min_adx": 16}                                            # bộ tự học đã nới ADX → 17 qua cổng
S._levels = lambda df, side, price, a: (price - 2 * a, price + 4 * a)
assert S.evaluate("X/USDT:USDT", FakeFrame(adx=17.0), htf)[1] == ""
S.LEARNED["gates"] = {}
print("✓ evaluate: tín hiệu suýt qua cổng (ADX, cách EMA21, SL xa), trượt xa/2 cổng thì loại, ngưỡng học được có hiệu lực")

# 4) bộ tự học: tín hiệu suýt qua cổng ADX thắng rõ → nới; tín hiệu qua cổng sát ngưỡng thua rõ → siết
st = Store()
notes = []
lr = Learner(st, None, notes.append)


def add(source, R, **ctx):
    c = {"setup": "trend", "hour": 21, "adx": 30, "atr_pct": 1.0, "vol_ratio": 1.1, "rsi": 60, "close_pos": 0.8,
         "ext_atr": 0.4, "chg1h": 0.1, "btc_chg_1h": 0.0, "sl_atr": 2.0, **ctx}
    sig = S.Signal("X/USDT:USDT", "long", 6, 100, 1, 98, 104, [], c, triggers=["macd_cross"])
    st.log_signal(sig, None, source == "taken", source=source)
    sid = st.db.run("SELECT sid FROM signals ORDER BY rowid DESC LIMIT 1", fetch=True)[0]["sid"]
    st.set_outcome(sid, "TP" if R > 0 else "SL", R, R, R, R)


for i in range(16):
    add("gate_near", [1.9, 1.9, 1.9, -1.05][i % 4], adx=17.5, gate_near="min_adx", gate_val=17.5)
for i in range(16):
    add("taken", [1.9, -1.05][i % 2], adx=35)                      # nhóm tham chiếu xa ngưỡng
props = lr.learn()
g = lr.last_stats["by_gate"]["min_adx"]
assert g["out"]["n"] == 16 and g["out"]["exp_r"] > 1, g
assert S.LEARNED["gates"].get("min_adx") == cfg.MIN_ADX - 2, (S.LEARNED.get("gates"), props)
assert any(p["kind"] == "gate" and p["key"] == "min_adx" for p in props)
print(f"✓ tự học: {g['out']['n']} tín hiệu suýt qua cổng ADX thắng {g['out']['exp_r']:+.2f}R → nới ADX {cfg.MIN_ADX} → "
      f"{S.LEARNED['gates']['min_adx']:g}")
lr.reset(); st.db.run("DELETE FROM signals")
for i in range(16):
    add("taken", -1.05 if i < 14 else 1.9, ext_atr=0.8)             # qua cổng nhưng cách EMA21 0.8 ATR (sát 1.0): thua rõ
for i in range(16):
    add("not_taken", [1.9, -1.05][i % 2], ext_atr=0.1)
lr.learn()
gi = lr.last_stats["by_gate"]["max_ext_atr"]["in"]
assert gi["n"] == 16 and gi["t"] <= -2 and S.LEARNED["gates"].get("max_ext_atr") == cfg.MAX_EXT_ATR - 0.25, (gi, S.LEARNED.get("gates"))
print(f"✓ tự học: tín hiệu qua cổng sát ngưỡng (cách EMA21 0.5–1.0 ATR) thua {gi['exp_r']:+.2f}R → siết "
      f"{cfg.MAX_EXT_ATR} → {S.LEARNED['gates']['max_ext_atr']:g}")
lr.reset()
assert S.LEARNED["gates"] == {} and S.gv("max_ext_atr") == cfg.MAX_EXT_ATR

# 5) rào ±1R chạm trước (đo không thiên lệch cho lớp bảo vệ)
c5 = lambda t, h, l: [t * 1000, 100, h, l, 100, 1]
assert first_barrier("long", 100, 98, 1000, [c5(400, 99, 97), c5(1000, 101, 99), c5(1300, 102.5, 99.5)]) == ("TP1", 1600)
assert first_barrier("long", 100, 98, 1000, [c5(1000, 102.5, 97.5)])[0] == "SL"                   # cùng nến → SL
assert first_barrier("short", 100, 102, 1000, [c5(1000, 101, 97.9)])[0] == "TP1"
assert first_barrier("long", 100, 98, 1000, [c5(1000, 101, 99)]) == (None, None)
print("✓ rào ±1R chạm trước: TP1 / SL / cùng nến → SL / chưa chạm")

# 6) lớp bảo vệ
pr = Protections(st, notes.append)
now = time.time()


def trade(sym, side, pnl, closed):
    tid = st.open_trade(dict(mode="paper", symbol=sym, side=side, entry=100, sl=98, tp=104, notional=10, margin=1,
                             contracts=1, pnl=0, pnl_pct=0, fee=0, opened_at=closed - 3600, status="open"))
    st.db.run("UPDATE trades SET status='closed', pnl=?, closed_at=? WHERE id=?", (pnl, closed, tid))


trade("A/USDT:USDT", "short", -0.3, now - 3 * 3600)
trade("B/USDT:USDT", "short", -0.3, now - 2 * 3600)
assert pr.refresh(now) == {}
trade("C/USDT:USDT", "short", -0.3, now - 3600)
lk = pr.refresh(now)
assert "short" in lk and "long" not in lk and "3 lệnh SHORT" in lk["short"]["why"] and notes[-1].startswith("🛡️ BẢO VỆ")
assert pr.refresh(now + 6 * 3600 + 60) == {}                     # hết 6h → mở; 3 lệnh thua cũ không khoá lại
sg = S.Signal("D/USDT:USDT", "short", 6, 100, 1, 102, 96, [], {})
assert "khoá SHORT" in Protections.blocks(sg, lk, {}) and Protections.blocks(sg, {}, {}) == ""
pl = pr.pair_locks(now)
assert set(pl) == {"A/USDT:USDT", "B/USDT:USDT", "C/USDT:USDT"} and "vừa thua" in pl["C/USDT:USDT"][1]
assert "A/USDT:USDT" not in pr.pair_locks(now + 7 * 3600)        # 6h sau khi đóng → hết nghỉ
trade("A/USDT:USDT", "long", -0.2, now - 600)                      # thua lần 2 trong 24h → nghỉ tới hết 24h
assert "thua 2 lần" in pr.pair_locks(now + 7 * 3600)["A/USDT:USDT"][1]
# khoá theo tín hiệu bóng: ≥ 10 coin long, ≥ 80% chạm SL trước +1R
for i in range(10):
    sgl = S.Signal(f"L{i}/USDT:USDT", "long", 6, 100, 1, 98, 104, [], {})
    st.log_signal(sgl, None, False, source="not_taken")
    sid = st.db.run("SELECT sid FROM signals ORDER BY rowid DESC LIMIT 1", fetch=True)[0]["sid"]
    st.set_first_hit(sid, "SL" if i < 8 else "TP1", time.time())
lk2 = pr.refresh(time.time())
assert "long" in lk2 and "80%" in lk2["long"]["why"], lk2
assert Protections.too_new({"info": {"listTime": str(int((now - 3 * 86400) * 1000))}}, now)
assert not Protections.too_new({"info": {"listTime": str(int((now - 30 * 86400) * 1000))}}, now)
assert not Protections.too_new({"info": {}}, now)
pub = pr.public(time.time())
assert "long" in pub["sides"] and pub["params"]["lock_hours"] == cfg.PROTECT_LOCK_HOURS
print("✓ lớp bảo vệ: khoá phía (3 lệnh thua / 80% tín hiệu chạm SL trước), không khoá lặp, khoá coin, tuổi niêm yết")

# 7) theo dõi bóng ghi rào chạm trước
class FakeEx:
    def fetch_ohlcv(self, sym, tf, since=None, limit=300):
        t0 = since // 1000
        return [[(t0 + 300 * k) * 1000, 100, 100.5, 99.5, 100, 1] for k in range(3)] + \
               [[(t0 + 900) * 1000, 100, 101, 97.5, 98, 1]]


lr2 = Learner(st, NS(ex=FakeEx()), notes.append)
st.db.run("DELETE FROM signals")
sg = S.Signal("Z/USDT:USDT", "long", 6, 100, 1, 98, 104, [], {"atr_pct": 1.0})
st.log_signal(sg, None, False, source="not_taken")
st.db.run("UPDATE signals SET ts = ts - 600")
lr2.resolve_pending()
r = st.db.run("SELECT first_hit, outcome FROM signals", fetch=True)[0]
assert r["first_hit"] == "SL", r
print("✓ theo dõi bóng ghi rào chạm trước (first_hit) ngay khi biết, trước khi lệnh bóng kết thúc")
print("TẤT CẢ OK")
