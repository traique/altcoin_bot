"""Kiểm tra luồng chính v4.0 (không AI) với sàn giả, không cần mạng:
quét → cộng điểm dòng tiền + tin tức → luật chặn → quyết định → vào lệnh → tin xấu mới → tự đóng lệnh → tổng kết;
lệnh Telegram/Zoom, dữ liệu web (snapshot) và các trang dashboard."""
import os, shutil, time, json
os.environ.update(MODE="paper", DATA_DIR="/tmp/okx-flow-test", DATABASE_URL="", NEWS_ENABLED="true",
                  DASHBOARD_USER="", DASHBOARD_PASS="")
shutil.rmtree("/tmp/okx-flow-test", ignore_errors=True)
from types import SimpleNamespace as NS
from bot.config import cfg
from bot import main as M
from bot.storage import Store
from bot.engine import PaperEngine
from bot.news import NewsHub
from bot.channels import Switches
from bot.strategy import Signal
from bot import strategy as S


class FakeOKX:
    prices_ = {"AAA/USDT:USDT": 10.0, "BBB/USDT:USDT": 20.0, "CCC/USDT:USDT": 5.0}

    def top_altcoins(self, n):
        return [("AAA/USDT:USDT", 9e8, 3.0), ("BBB/USDT:USDT", 8e8, 2.0), ("CCC/USDT:USDT", 7e8, 1.0)]

    def ohlcv(self, *a, **k):
        return []

    def crypto_bases(self):
        return {"AAA", "BBB", "CCC"}

    def market(self, s):
        return {"contractSize": 1, "limits": {"amount": {"min": 0.001}}, "precision": {"amount": 0.001}}

    def contracts_for_notional(self, s, notional, price):
        c = int(notional / price / 0.001) * 0.001
        return (round(c, 6), 0.0) if c >= 0.001 else (0.0, 0.001 * price)

    def price(self, s):
        return self.prices_[s]

    def prices(self, syms):
        return {s: self.prices_[s] for s in syms}


def fake_diagnose(sym, ltf, htf, funding=0.0, change24h=0.0, market=None):
    """Cả 3 coin đều có setup long kỹ thuật; điểm khác nhau."""
    score = {"AAA/USDT:USDT": 5.2, "BBB/USDT:USDT": 6.0, "CCC/USDT:USDT": 5.3}[sym]
    p = FakeOKX.prices_[sym]
    ctx = {"setup": "trend", "hour": 21, "adx": 28, "htf_rsi": 55, "atr_pct": 1.0, "vol_ratio": 1.1, **(market or {})}
    sig = Signal(sym, "long", score, p, p * 0.01, p * 0.98, p * 1.04, ["Pullback EMA21 + nến bật"], ctx, triggers=["pullback"])
    return sig, "", {"score": score}


M.diagnose = fake_diagnose
M.mkt.btc_context = lambda okx: {"btc_chg_1h": 0.1, "btc_chg_4h": 0.5, "btc_trend_1h": 1, "btc_price": 80000.0}
M.mkt.symbol_context = lambda okx, sym: {"oi_chg_1h": 0.2, "px_chg_1h": 0.3, "funding": 0.0001, "ls_ratio": 1.1}

st = Store()
msgs = []
b = M.Bot.__new__(M.Bot)
b.__dict__.update(started_at=time.time(), booting=False, store=st, switches=Switches(st), okx=FakeOKX(), is_leader=True,
                  instance="test", last_prices={}, learner=None, shadow_seen={}, last_btc={}, last_market={},
                  paused=False, last_scan=0, last_scan_summary=None, cooldown={}, _news_exit_done=set(),
                  start_equity=10.0, notify=NS(send=msgs.append), tg=NS(enabled=False), zoom=None)
b.news = NewsHub(st)
b.news.set_universe(b.okx.crypto_bases())
now = time.time()
b.news.ingest([
    # AAA: nhiều tin tốt → +điểm, đẩy 5.2 lên trên ngưỡng 5.0 và vượt BBB/CCC khi xếp hạng
    {"src": "CoinDesk", "kind": "news", "title": "AAA soars 20% after major exchange partnership", "url": "a1", "ts": now - 1800},
    {"src": "Decrypt", "kind": "news", "title": "AAA rallies to record high as inflows surge", "url": "a2", "ts": now - 3600},
    # BBB: hack → luật chặn sẵn news_hack_long
    {"src": "The Block", "kind": "news", "title": "BBB protocol hacked, $30M drained", "url": "b1", "ts": now - 3600},
    # CCC: tin xấu → trừ điểm, rơi xuống dưới ngưỡng ("suýt đạt")
    {"src": "CoinDesk", "kind": "news", "title": "CCC plunges as team faces fraud lawsuit", "url": "c1", "ts": now - 1800},
    {"src": "Cointelegraph", "kind": "news", "title": "CCC tumbles, investors fear collapse", "url": "c2", "ts": now - 2400},
], now=now)
b.engine = PaperEngine(b.okx, st, msgs.append)
b.engine.on_close = b._on_trade_closed
st.set("paper_balance", 10.0)

# 1) quét → AAA vào lệnh, BBB bị luật tin tức chặn, CCC suýt đạt
b.scan()
sig_rows = {r["symbol"].split("/")[0]: r for r in st.recent_signals(10)}
assert sig_rows["AAA"]["source"] == "taken" and sig_rows["AAA"]["decision"] == "LONG", sig_rows["AAA"]
assert "tin coin +" in sig_rows["AAA"]["reason"] and sig_rows["AAA"]["ai_decision"] is None
assert sig_rows["BBB"]["source"] == "blocked" and json.loads(sig_rows["BBB"]["features"])["news_events"] == ["hack"]
assert sig_rows["CCC"]["source"] == "below_score" and json.loads(sig_rows["CCC"]["features"])["news_bias"] < 0
t = st.open_trades()
assert len(t) == 1 and t[0]["symbol"] == "AAA/USDT:USDT" and t[0]["news"] > 0 and t[0]["conf"] >= 50, t
assert t[0]["risk_mult"] > 1.0                      # tin ủng hộ → rủi ro nhỉnh hơn cơ bản
assert "Tin tức ủng hộ" in t[0]["reason_open"] and "Quyết định:" in t[0]["reason_open"]
assert any(m.startswith("🟢 MỞ LỆNH LONG AAA") for m in msgs)
assert b.last_scan_summary["passed"] == 1 and b.last_scan_summary["reasons"].get("luật chặn") == 1
print(f"✓ quét: AAA vào lệnh (điểm {sig_rows['AAA']['score']}, tin {t[0]['news']:+.2f}, rủi ro ×{t[0]['risk_mult']}), "
      f"BBB bị chặn vì hack, CCC suýt đạt vì tin xấu")

# 2) tin hack MỚI về AAA sau khi đã vào lệnh → bot tự đóng lệnh + tổng kết theo quy tắc
time.sleep(0.01)
b.news.ingest([{"src": "The Block", "kind": "news", "title": "AAA exploit: attackers drain $12M from bridge", "url": "a3",
                "ts": time.time()}])
b.okx.prices_["AAA/USDT:USDT"] = 9.95
b._news_guard()
assert st.open_trades() == [], "lệnh phải được đóng vì tin hack mới"
closed = [x for x in st.trades(5) if x["status"] == "closed"][0]
assert closed["reason_close"].startswith("Tin xấu: hack"), closed["reason_close"]
rev = st.reviews(1)[0]
assert rev["model"] == "quy-tắc" and rev["verdict"] == "ĐÓNG VÌ TIN XẤU" and "tin_xấu" in rev["tags"], rev
assert any(m.startswith("📰 Đã đóng LONG AAA") for m in msgs) and any(m.startswith("🧾 TỔNG KẾT") for m in msgs)
b._news_guard()                                      # chạy lại: không xử lý trùng
assert sum(1 for m in msgs if m.startswith("📰 Đã đóng")) == 1
print(f"✓ tin hack mới → tự đóng lệnh ({closed['reason_close']}), tổng kết [{rev['verdict']}] #{rev['tags']}")

# 3) lệnh Telegram/Zoom
assert "TIN TỨC" in b.handle_command("/news") and "TIN TỨC" in b.handle_command("tintuc")
assert b.handle_command("ai").startswith("Từ v4.0 bot không dùng AI")
assert "AAA" in b.handle_command("signals") and "vào lệnh" in b.handle_command("signals")
assert "[" in b.handle_command("tongket") and b.handle_command("lessons") == b.handle_command("tongket")
assert "news (tintuc)" in b.handle_command("help") and "📰" in b.status_text()
print("✓ lệnh: news/tintuc, ai (báo đã bỏ AI), signals, tongket, status")

# 4) dữ liệu web + các trang
from bot.learner import Learner
b.learner = Learner(st, b.okx, msgs.append)
snap = b.snapshot()
json.dumps(snap, default=str)
assert snap["news"]["enabled"] and snap["news"]["headlines"] and "ai" not in snap and "ai_model" not in snap
from bot import dashboard as D
html = D._news_body() + D._home_body() + D._settings_body(b)
assert "Tin tức" in html and "Bộ lọc AI" not in html and "Trọng số tin tức" in html
try:
    from fastapi.testclient import TestClient
    c = TestClient(D.build_app(b))
    assert c.get("/tintuc").status_code == 200 and "Tin tức & Tự học" in c.get("/tintuc").text
    r = c.get("/ai", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("tintuc")
    assert c.get("/api/state").json()["news"]["n"] >= 5 and c.get("/health").json()["ok"]
    assert c.get("/caidat").status_code == 200 and c.get("/").status_code == 200
    print("✓ trang web: /, /tintuc, /ai → /tintuc, /caidat, /api/state, /health")
except ImportError as e:
    print(f"(bỏ qua kiểm tra HTTP – thiếu thư viện: {e})")
print("TẤT CẢ OK")
