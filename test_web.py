"""Kiểm tra v3.0: công tắc kênh, thông báo cập nhật phiên bản, khung trang web."""
import os
import shutil
import sys

D = "/tmp/okx_test_web"
shutil.rmtree(D, ignore_errors=True)
os.environ.update(DATA_DIR=D, MODE="paper", DASHBOARD_USER="", DASHBOARD_PASS="", DATABASE_URL="")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from types import SimpleNamespace as NS
from bot.storage import Store
from bot.channels import Switches
from bot.notify import Notifier
from bot import version as ver, ui

st = Store()
sw = Switches(st)
got = []


class Ch:
    def __init__(self, key):
        self.switch_key, self.enabled = key, True

    def send(self, t):
        got.append((self.switch_key, t))


bot = NS(is_leader=True, switches=sw)
n = Notifier(bot)
n.add(Ch("telegram_notify"))
n.add(Ch("zoom_notify"))
n.send("a")
assert [k for k, _ in got] == ["telegram_notify", "zoom_notify"]
sw.set("zoom_notify", False)
got.clear()
n.send("b")
assert [k for k, _ in got] == ["telegram_notify"]
assert sw.all()["zoom_notify"] is False and Switches(st).on("zoom_notify") is False   # lưu bền
try:
    sw.set("khong_co", True)
    raise SystemExit("phải báo lỗi")
except ValueError:
    pass
print("✓ công tắc kênh")

assert ver.update_notice(f"{ver.VERSION} {ver.build()}") is None
assert ver.update_notice("2.9.7 abc1234").startswith("🆕 Bot đã cập nhật: v2.9.7 → v" + ver.VERSION)
assert "vừa đổi" in ver.update_notice(f"{ver.VERSION} 0000000")
assert len(ver.build()) == 7 and ver.NOTES[0][0] == ver.VERSION
print("✓ phiên bản & thông báo cập nhật:", ver.label())

html = ui.page("Thử", ui.hero("Tiêu đề", "mô tả", eyebrow="Nhóm"), active="home")
assert "aria-current=page" in html and "Phiên bản" in html and html.count("<h1>") == 1
assert 'role="switch"' in ui.switch_form("zoom_cmd", True, "Zoom – lệnh")
print("✓ khung trang")

# RESET_DATA: xoá toàn bộ dữ liệu đúng 1 lần cho mỗi mã; chạy thật còn lệnh mở thì không xoá
from bot.config import cfg
st.set("paper_balance", 5.0)
st.add_events([(1.0, "INFO", "x", "dữ liệu cũ")])
os.environ["RESET_DATA"] = "lan-1"
s2 = Store()
assert s2.reset_done == "lan-1" and s2.get("paper_balance") is None and not s2.events() and s2.get("reset_token") == "lan-1"
s2.set("paper_balance", 7.0)
s3 = Store()
assert s3.reset_done == "" and s3.get("paper_balance") == 7.0          # cùng mã → khởi động lại không xoá nữa
s3.open_trade(dict(mode="live", symbol="X/USDT:USDT", side="long", entry=1, sl=0.9, tp=1.2, notional=10, margin=1,
                   contracts=1, pnl=0, pnl_pct=0, fee=0, opened_at=1.0, status="open"))
os.environ["RESET_DATA"] = "lan-2"
cfg.MODE = "live"
s4 = Store()
assert s4.reset_done == "" and len(s4.open_trades()) == 1                # chạy thật còn lệnh mở → không xoá
cfg.MODE = "paper"
s5 = Store()
assert s5.reset_done == "lan-2" and s5.open_trades() == [] and s5.get("paper_balance") is None
os.environ["RESET_DATA"] = ""
assert Store().reset_done == ""
print("✓ RESET_DATA: xoá đúng 1 lần mỗi mã, đổi mã xoá lại, chạy thật còn lệnh mở thì không xoá")
print("TẤT CẢ OK")
