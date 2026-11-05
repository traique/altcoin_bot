"""Kiểm tra bộ tự học với dữ liệu giả: mô phỏng kết quả bóng, chặn luật, trọng số trigger, ngưỡng điểm,
trọng số tin tức (v4.0), kiểm soát nhiều phép thử, nâng cấp tham số bản cũ, báo cáo ngày."""
import os, shutil, json, time, random
os.environ.update(MODE="paper", DATA_DIR="/tmp/okx-learn-test", LEARN_MODE="auto", DATABASE_URL="", LEARN_MIN_SAMPLES="12")   # dữ liệu giả 14–16 mẫu/nhóm
shutil.rmtree("/tmp/okx-learn-test", ignore_errors=True)
from bot.storage import Store
from bot.learner import Learner
from bot import learner as LM
from bot.strategy import Signal, LEARNED
from bot import strategy

# 1) mô phỏng kết quả từ nến
from bot import exits
from bot.config import cfg
c = lambda t, h, l, cl: [t * 1000, 100, h, l, cl, 1]
atr = 2 / 1.5
o, r = exits.simulate("long", 100, 98, atr, "fixed", 1000, [c(1000, 101, 99, 100), c(1300, 104.5, 99.5, 104)], 0.00125)
assert o == "TP" and 1.9 < r < 2.0, (o, r)
assert exits.simulate("long", 100, 98, atr, "fixed", 1000, [c(1000, 101, 97.9, 98)], 0.00125)[0] == "SL"
assert exits.simulate("long", 100, 98, atr, "fixed", 1000, [c(1000, 105, 97, 100)], 0.00125)[0] == "SL"   # cùng nến → SL
# hybrid: chốt 50% ở TP1 (2R = 104), sau đó sóng chạy tới 112 (6R) rồi quay đầu → trailing chốt phần còn lại
cs = [c(1000, 101, 99, 100), c(1300, 104.5, 100, 104), c(1600, 108, 103.5, 108), c(1900, 112, 107, 111.5), c(2200, 111.6, 104, 104.5)]
o, r = exits.simulate("long", 100, 98, atr, "hybrid", 1000, cs, 0.00125, tp1_r=2.0)
assert o == "TRAIL" and r > 3.0, (o, r)
o1, r1 = exits.simulate("long", 100, 98, atr, "hybrid", 1000, cs, 0.00125, tp1_r=1.0)
assert o1 == "TRAIL" and 2.5 < r1 < r, (o1, r1)        # TP1 1R chốt sớm hơn → ít hơn TP1 2R trên sóng dài
of, rf = exits.simulate("long", 100, 98, atr, "fixed", 1000, cs, 0.00125)
assert rf < r, "ăn sóng phải hơn TP cố định trên sóng dài"
print(f"✓ mô phỏng đúng: sóng 6R → TP cố định {rf:+.2f}R, ăn sóng {r:+.2f}R")

# 2) dữ liệu giả: short khi RSI 1h < 32 luôn thua; pullback thắng; breakout thua; suýt đạt điểm 4.5 lại thắng
st = Store(); notes = []
lr = Learner(st, None, notes.append)
assert not [r for r in st.learn_log(50) if r["kind"] == "migrate"], "cài mới không cần ghi nâng cấp"
random.seed(1)


def add(side, htf_rsi, trig, score, R, source, **ctx):
    sig = Signal("X/USDT:USDT", side, score, 100, 1, 98 if side == "long" else 102, 104 if side == "long" else 96, [],
                 {"htf_rsi": htf_rsi, "bb_pos": 0.5, "adx": 30, "change24h": 0, "hour": 15, **ctx}, triggers=[trig])
    st.log_signal(sig, None, source == "taken", source=source)
    sid = st.db.run("SELECT sid FROM signals ORDER BY rowid DESC LIMIT 1", fetch=True)[0]["sid"]
    st.set_outcome(sid, "TP" if R > 0 else "SL", R)


for i in range(15): add("short", 25, "ema_cross", 6, -1.05, "not_taken")
for i in range(15): add("long", 55, "pullback", 6, random.choice([1.9, 1.9, -1.05]), "taken")
for i in range(14): add("long", 55, "breakout", 5.5, ([-1.05] * 12 + [1.9, 1.9])[i], "not_sent")   # nguồn cũ (trước v4) vẫn được học
for i in range(14): add("long", 55, "pullback", 4.5, random.choice([1.9, 1.9, -1.05]), "below_score")
props = lr.learn()
for p in props: print(" →", p["reason"])
assert "short_htf_oversold" in LEARNED["blocks"], LEARNED
assert LEARNED["trigger_w"].get("pullback", 1) > 1 and LEARNED["trigger_w"].get("breakout", 1) < 1
assert LEARNED["min_score"] == cfg.MIN_SCORE - 0.5, (LEARNED["min_score"], cfg.MIN_SCORE)   # mặc định 5.0 → 4.5
assert "ai_veto_conf" not in LEARNED and not any(p["kind"] == "ai_veto_conf" for p in props)   # v4.0: không còn AI
fdr = lr.last_stats["fdr"]
assert fdr["tested"] >= 3 and "rule:short_htf_oversold" in fdr["passed"], fdr
print(f"✓ học đúng: chặn short quá bán, tăng trọng số pullback, giảm breakout, hạ ngưỡng điểm "
      f"(qua lọc FDR: {len(fdr['passed'])}/{fdr['tested']} nhóm)")

# 3) giới hạn: chạy lại ngay → không đổi tiếp (cooldown)
assert lr.learn() == [], "phải có cooldown"
print("✓ cooldown hoạt động")

# 3b) v3.2: không bao giờ chặn cả một phía dù nhóm đó thua rõ
st.set("learn_last", {})
for i in range(40): add("short", 55, "pullback", 6, -1.05, "not_taken")
props2 = lr.learn()
assert not any(p["key"] in ("short_side", "long_side") for p in props2), props2
assert "short_side" not in LEARNED["blocks"]
print("✓ không chặn cả phía short dù 55 short thua")

# 4) khôi phục mặc định
lr.reset()
assert LEARNED["blocks"] == [] and LEARNED["min_score"] is None and LEARNED["news_w"] is None
assert LEARNED["schema"] == Learner.LEARNED_SCHEMA
print("✓ khôi phục mặc định")

# 4b) tham số bản cũ (schema 1, có AI) → v3.2 đưa về mặc định, v4.0 xoá ngưỡng phủ quyết AI, giữ TP1, thêm trọng số tin
st.set("learned", {"min_score": 5.5, "trigger_w": {"pullback": 1.2}, "blocks": ["short_side", "weak_adx"],
                   "unblocked": [], "exit_mode": "trail", "ai_veto_conf": 55, "tp1_r": 1.6})
st.set("learn_last", {"rule:short_side": time.time(), "exit_mode": time.time(), "ai_veto_conf": time.time()})
LEARNED.clear(); LEARNED.update({"min_score": None, "trigger_w": {}, "blocks": [], "unblocked": [], "exit_mode": None,
                                 "tp1_r": None, "news_w": None})
lr2 = Learner(st, None, notes.append)
assert LEARNED["blocks"] == [] and LEARNED["exit_mode"] is None and LEARNED["min_score"] is None and LEARNED["trigger_w"] == {}
assert "ai_veto_conf" not in LEARNED and LEARNED["tp1_r"] == 1.6 and LEARNED["news_w"] is None
assert LEARNED["schema"] == Learner.LEARNED_SCHEMA == 3
assert "exit_mode" not in st.get("learn_last") and "ai_veto_conf" not in st.get("learn_last")
mig = [r["k"] for r in st.learn_log(50) if r["kind"] == "migrate"]
assert mig == ["v4.0", "v3.2"], mig
lr3 = Learner(st, None, notes.append)
assert len([r for r in st.learn_log(50) if r["kind"] == "migrate"]) == 2      # chỉ chạy 1 lần
print("✓ nâng cấp tham số bản cũ: v3.2 về mặc định, v4.0 bỏ ai_veto_conf (giữ TP1) – đúng 1 lần")

# 5) chế độ suggest: tạo đề xuất chờ duyệt, áp dụng qua apply_pending
lr.reset()
st.set("learn_last", {}); lr.mode = "suggest"
lr.learn()
pend = [r for r in st.learn_log() if r["status"] == "pending"]
assert pend and LEARNED["blocks"] == [], "suggest không được tự áp dụng"
n = lr.apply_pending(); assert n == len(pend) and "short_htf_oversold" in LEARNED["blocks"]
print(f"✓ chế độ chờ duyệt: {len(pend)} đề xuất, áp dụng thủ công OK")

# 6) v4.0 – trọng số tin tức: tín hiệu tin CÙNG chiều thắng, tin NGƯỢC chiều thua → tăng trọng số tin
lr.mode = "auto"; lr.reset(); st.db.run("DELETE FROM signals")
for i in range(16): add("long", 55, "macd_cross", 6, [1.9, 1.9, 1.9, -1.05][i % 4], "taken", news_bias=0.6, news_n=3)
for i in range(16): add("long", 55, "macd_cross", 6, [-1.05, -1.05, -1.05, 1.9][i % 4], "below_score", news_bias=-0.5, news_n=2)
props = lr.learn()
ne = lr.last_stats["news_effect"]
assert ne["n_aligned"] == 16 and ne["n_against"] == 16 and ne["diff"] > 1 and ne["t"] >= 2, ne
assert any(p["kind"] == "news_w" for p in props) and LEARNED["news_w"] == 1.25, (props, LEARNED["news_w"])
assert {"aligned", "against"} <= set(lr.last_stats["by_news"])
assert not any(p["kind"] == "news_w" for p in lr.learn())          # cooldown
print(f"✓ v4.0: tin cùng chiều {ne['exp_aligned']:+.2f}R vs ngược chiều {ne['exp_against']:+.2f}R "
      f"(t={ne['t']}) → trọng số tin 1.0 → 1.25")

# 6b) tin "dự báo ngược" → giảm trọng số, không xuống dưới 0
LEARNED["news_w"] = 0.1; st.set("learn_last", {}); st.db.run("DELETE FROM signals")
for i in range(16): add("short", 55, "macd_cross", 6, -1.05 if i % 4 else 1.9, "taken", news_bias=-0.7, news_n=4)  # short + tin xấu = cùng chiều
for i in range(16): add("short", 55, "macd_cross", 6, 1.9 if i % 4 else -1.05, "not_taken", news_bias=0.7, news_n=4)
lr.learn()
assert LEARNED["news_w"] == 0.0, LEARNED["news_w"]
assert strategy.news_weight() == 0.0
print("✓ v4.0: tin dự báo ngược → trọng số tin giảm, kẹp ở 0 (bot bỏ qua tin)")

# 7) Benjamini–Hochberg: nhóm t=2.1 lẫn trong 30 nhóm nhiễu không được coi là phát hiện; nhóm rất mạnh thì được
pv = {f"g{i}": 0.5 for i in range(29)}; pv["weak"] = LM._pval(2.1); pv["strong"] = LM._pval(5)
d = LM._bh(pv, 0.10)
assert "strong" in d and "weak" not in d, d
assert LM._bh({"a": 0.04}, 0.10) == {"a"} and LM._bh(pv, 0) == set(pv)
print("✓ kiểm soát nhiều phép thử (FDR): nhóm t=2.1 giữa 30 nhóm bị loại, nhóm t=5 được giữ")

# 8) báo cáo ngày (số liệu, không AI)
rep = lr.daily_summary(force=True)
assert rep and "24h qua" in rep["summary"] and st.get("learn_daily")["ts"] == rep["ts"]
assert notes[-1].startswith("📈 TỰ HỌC")
print("✓ báo cáo ngày:", rep["summary"][:100], "…")
lr.reset()
print("TẤT CẢ OK")
