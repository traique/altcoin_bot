"""Kiểm tra PaperEngine: mở lệnh giả, ép chạm TP/SL, kiểm tra số dư cập nhật đúng."""
import os, shutil
os.environ["MODE"] = "paper"; os.environ["DATA_DIR"] = "/tmp/okx-engine-test"; os.environ["DATABASE_URL"] = ""
shutil.rmtree("/tmp/okx-engine-test", ignore_errors=True)
from bot.storage import Store
from bot.engine import PaperEngine
from bot.strategy import Signal
from bot.config import cfg

class FakeOKX:
    def market(self, s): return {"contractSize": 1000, "limits": {"amount": {"min": 0.01}}, "precision": {"amount": 0.01}}
    def contracts_for_notional(self, s, notional, price):
        c = int(notional / (price * 1000) / 0.01) * 0.01
        return (round(c, 2), 0.0) if c >= 0.01 else (0.0, 0.01 * 1000 * price)

msgs = []
st = Store(); eng = PaperEngine(FakeOKX(), st, msgs.append)
sig = Signal("DOGE/USDT:USDT", "long", 4.0, 0.10, 0.002, 0.097, 0.106, ["test"], {})
t = eng.open(sig, {"decision": "LONG", "confidence": 80, "reason": "điểm 4.0", "news": 0.0})
assert t and t["notional"] <= 10 * cfg.LEVERAGE * 0.9, t
print("Mở:", t["notional"], "USDT, ký quỹ", round(t["margin"], 3))
eng.close(t, 0.106, "Chạm TP")
bal = eng.balance()
print("Sau TP, số dư:", round(bal, 4))
assert bal > 10
sig2 = Signal("DOGE/USDT:USDT", "short", 4.0, 0.10, 0.002, 0.103, 0.094, ["test"], {})
t2 = eng.open(sig2, None); eng.close(t2, 0.103, "Chạm SL")
print("Sau SL, số dư:", round(eng.balance(), 4), "| lỗ lệnh ≈", round(bal - eng.balance(), 4), "(mục tiêu ≈", round(bal * cfg.RISK_PER_TRADE, 4), ")")
print("Stats:", st.stats())
print("\n".join(msgs))

# LiveEngine: lệnh đóng trên sàn lỗi → KHÔNG ghi đóng trong DB (vị thế vẫn còn trên sàn), báo lỗi lên để lượt sau thử lại
from bot.engine import LiveEngine


class FakeLiveOKX(FakeOKX):
    def __init__(self):
        self.fail, self.closed = True, []

    def close_position(self, s, side, contracts):
        if self.fail:
            raise RuntimeError("51000 sàn từ chối lệnh")
        self.closed.append(s)

    def balance_usdt(self):
        return 10.0, 10.0


t3 = eng.open(sig, None)
live = LiveEngine(FakeLiveOKX(), st, msgs.append)
try:
    live.close(t3, 0.101, "Sóng đuối – thoát")
    raise AssertionError("đóng lỗi trên sàn phải báo lỗi lên trên")
except RuntimeError:
    pass
assert [x["id"] for x in st.open_trades()] == [t3["id"]], "đóng lỗi trên sàn → lệnh vẫn mở trong DB để thử lại"
live.okx.fail = False
live.close(t3, 0.101, "Sóng đuối – thoát")
assert st.open_trades() == [] and live.okx.closed == ["DOGE/USDT:USDT"]
print("✓ LiveEngine: đóng lỗi trên sàn → giữ lệnh, thử lại; đóng được → mới ghi đóng")
