"""Phiên bản bot – một chỗ duy nhất, hiện ở web (đầu trang, cuối trang, trang /phienban),
Telegram/Zoom (lệnh `phienban`, `status`), /health, và tự báo khi bot được cập nhật.

- VERSION / RELEASED: bản phát hành; NOTES: lịch sử (mới nhất ở trên).
- build(): mã 7 ký tự tính từ toàn bộ file .py của bot (trừ file này). Cùng code → cùng mã trên mọi máy,
  nên biết server có chạy ĐÚNG và ĐỦ bản phát hành không (RELEASE_BUILD) hay upload thiếu / lẫn file cũ.
- Phát hành bản mới: tăng VERSION, thêm NOTES, rồi chạy `python -m bot.version --stamp` để ghi RELEASE_BUILD.
Chỉ dùng thư viện chuẩn.
"""
import hashlib
import platform
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

VERSION = "4.2.2"
RELEASED = "2026-11-05"
RELEASE_BUILD = "b0bcfb6"          # ghi bởi `python -m bot.version --stamp`
BUILD = RELEASED                   # tương thích các chỗ cũ dùng BUILD

# Mới nhất ở trên: (phiên bản, ngày, các thay đổi – câu ngắn, đọc tốt trên điện thoại)
NOTES = (
    ("4.2.2", "2026-11-05", (
        "Chạy thật: lệnh đóng trên sàn bị lỗi thì KHÔNG ghi là đã đóng nữa – lệnh vẫn được theo dõi và lượt sau thử đóng lại (bản cũ ghi đóng dù vị thế còn trên sàn)",
        "Đóng lệnh vì tin xấu bị lỗi (mất giá, sàn từ chối) → thử lại sau 2 phút thay vì bỏ qua luôn",
    )),
    ("4.2.1", "2026-11-05", (
        "Deploy thẳng từ GitHub như repo Stockvn: GitHub Actions chạy test, tạo gói rồi đẩy lên nhánh 'botkeep' – Botkeep trỏ vào nhánh này",
        "RESET_DATA=<mã>: xoá toàn bộ dữ liệu một lần khi khởi động để bắt đầu lại từ đầu (không xoá khi chạy thật còn lệnh mở)",
    )),
    ("4.2.0", "2026-11-05", (
        "Bỏ điểm trừ 'xu hướng 1h đã chạy lâu' (ADX 1h ≥ 35) của v3.2 – rút từ 5 ngày; kiểm chứng 89 ngày × 40 coin: kỳ vọng mỗi tín hiệu tốt hơn ở cả hai nửa (+0,15/−0,03R so với +0,07/−0,05R)",
        "Luật late_trend vẫn trong danh mục để bộ tự học tự chặn khi nhóm này lỗ rõ; LATE_TREND_PENALTY=1 để trừ điểm lại như cũ",
    )),
    ("4.1.0", "2026-11-05", (
        "Bộ tự học chỉnh được ngưỡng 10 cổng lọc (ADX, ATR, volume, cách EMA21, nhịp 1h, BTC, RSI, nến, SL): theo dõi bóng cả tín hiệu trượt đúng 1 cổng sát ngưỡng – trước đây tín hiệu bị loại ở cổng không được ghi",
        "Lớp bảo vệ kiểu freqtrade: khoá 1 phía 6h sau 3 lệnh thua/12h hoặc khi ≥80% tín hiệu cùng phía chạm SL trước khi lời 1R; coin vừa thua nghỉ 6h; bỏ coin niêm yết < 10 ngày",
        "Tín hiệu bị lớp bảo vệ chặn vẫn được theo dõi bóng → báo cáo ngày cho biết bảo vệ đang cứu hay làm mất lãi",
        "Công cụ tối ưu walk-forward trên nến lịch sử OKX (tools/walkforward.py) dùng đúng code chấm tín hiệu và thoát lệnh của bot",
    )),
    ("4.0.0", "2026-11-05", (
        "Bỏ hoàn toàn AI khỏi quyết định mua bán: vào lệnh thuần kỹ thuật + dòng tiền + tin tức, không cần key 9Router/OpenRouter",
        "Tin tức miễn phí, không cần key: 10 trang RSS crypto, thông báo niêm yết/huỷ niêm yết OKX & Binance, Fear & Greed – chấm bằng từ điển + luật sự kiện",
        "Tin của coin cộng/trừ tối đa ±1,5 điểm × trọng số tin; chặn sẵn: coin bị huỷ niêm yết, long khi có tin hack, short khi vừa niêm yết sàn lớn",
        "Lệnh đang mở gặp tin hack / huỷ niêm yết MỚI (short: tin niêm yết) → tự đóng và báo",
        "Rủi ro co giãn theo tin tức (0,5–1,5× tuỳ trọng số tin) thay cho hệ số AI",
        "Bộ tự học tự nâng cấp: đo tin cùng/ngược chiều (kiểm định Welch) để chỉnh trọng số tin 0–2, thống kê theo tin & Fear/Greed, chống học nhiễu khi thử ~30 nhóm (Benjamini–Hochberg)",
        "Chỉ quét crypto thật: loại cổ phiếu/hàng hoá token hoá theo phân loại OKX (trước đây 15/50 cặp được quét là cổ phiếu, dầu)",
        "Tổng kết lệnh & báo cáo ngày theo số liệu (không AI); web có trang Tin tức & Tự học; lệnh news/tintuc, tongket",
    )),
    ("3.2.0", "2026-10-28", (
        "Rút từ 211 tín hiệu bóng 23–27/10: cổng mới không đánh ngược nhịp 1h của coin (short khi vừa tăng ≥0.5%/1h: -0.72R, thắng 18%)",
        "Volume cao trào ≥1.5× và ADX 1h ≥35 bị TRỪ điểm thay vì cộng; chặn sẵn phiên 13h–19h VN và nến cao trào; cổng BTC 0.3%",
        "Rủi ro không tăng theo điểm hợp lưu (điểm ≥7 thua nặng nhất); co rủi ro từ lệnh thua thứ 3 thay vì thứ 2",
        "Bộ tự học: cần t ≥ 2.0 (trước 1.3), không bao giờ chặn cả một phía, đổi cách thoát cần ≥60 cặp, thống kê nhóm theo mốc hybrid cố định",
        "Tham số bộ tự học của bản cũ (chặn short, exit trail, MIN_SCORE 5.5, trọng số trigger) tự về mặc định 1 lần khi khởi động",
        "Bảo mật: che token/khoá/mật khẩu DB trong mọi dòng log và file sao lưu (bản cũ lộ token Telegram khi lỗi mạng) – hãy đổi token Telegram",
    )),
    ("3.1.0", "2026-10-23", (
        "Rủi ro 3%/lệnh × hệ số chất lượng (điểm KT, AI, chuỗi thua), tối đa 2 lệnh – tổng rủi ro ≤ 5%, cầu dao 12%/ngày, 30% DD",
        "Bắt nhạy hơn: điểm tối thiểu 5.0, volume 0.7, quét 50 coin, hỏi AI 3 ứng viên, trigger bật tại VWAP",
        "AI đồng ý nhưng chưa chắc (50–59%) vẫn vào với nửa rủi ro thay vì bỏ; chặn sẵn phiên 0h–7h",
        "Bộ tự học cần ≥30 mẫu và có ý nghĩa thống kê (t ≥ 1.3), 48h/lần đổi – hết nhảy qua lại",
        "AI tổng kết nhận số liệu tính sẵn (SL/ATR, R, MFE) – không bịa số",
        "Live: dời SL đặt mới trước rồi huỷ cũ (không trống SL); ghi giá khớp thật khi sàn tự đóng",
        "Log thông số in giá trị thực đang dùng",
    )),
    ("3.0.2", "2026-10-22", (
        "Zoom: gửi thông báo bằng account_id Zoom gửi kèm tin nhắn (ZOOM_ACCOUNT_ID điền nhầm Account No. gây lỗi 7004)",
        "Nhận đúng chat 1:1 để lưu địa chỉ trả lời thành công cho thông báo",
        "Cài đặt hiện account_id Zoom gửi tới và báo nếu khác biến ZOOM_ACCOUNT_ID",
    )),
    ("3.0.1", "2026-10-22", (
        "Zoom: dùng đúng Bot JID mà Zoom gửi kèm mỗi tin nhắn (sai Bot JID là nguyên nhân hay gặp của lỗi 7004)",
        "Cài đặt hiện Bot JID Zoom gửi tới và báo nếu khác biến ZOOM_BOT_JID",
        "Bỏ cách gửi không kèm user_jid (Zoom báo 7001)",
    )),
    ("3.0.0", "2026-10-22", (
        "Giao diện web mới: điều hướng Tổng quan · AI & Tự học · Cài đặt · Phiên bản",
        "Công tắc bật/tắt thông báo và trả lời lệnh cho Telegram, Zoom",
        "Nút gửi thử thông báo Zoom, tự thử nhiều cách gửi khi Zoom báo lỗi 7004",
        "Trang lịch sử phiên bản, mã bản dựng kiểm tra upload đủ file, bot tự báo khi được cập nhật",
    )),
    ("2.9.7", "2026-10-22", (
        "SL tối thiểu 2 ATR (bỏ tín hiệu nếu cấu trúc xa hơn 3 ATR)",
        "Bộ tự học cần ít nhất 20 mẫu mới điều chỉnh",
        "Zoom gửi thông báo theo đúng địa chỉ đã trả lời thành công",
    )),
    ("2.9.6", "2026-10-20", (
        "Thông số giao dịch tự cập nhật theo bản (không cần khai trên panel)",
        "Biến để trống không làm bot dừng; log in thông số đang dùng",
    )),
    ("2.9.5", "2026-10-20", ("Đọc file .env của Botkeep, ưu tiên hơn biến môi trường",)),
    ("2.9.4", "2026-10-20", ("Điểm tối thiểu 5.5 theo kết quả dò lại bộ lọc 10 ngày",)),
    ("2.9.3", "2026-10-20", ("Rủi ro mặc định 10%/lệnh",)),
    ("2.9.2", "2026-10-20", ("Bỏ chặn mặc định phiên 13h–19h (bộ tự học tự chặn lại nếu lỗ)",)),
    ("2.9.1", "2026-10-20", ("Zoom tự cập nhật account_id; lỗi mạng OKX tự thử lại",)),
    ("2.9.0", "2026-10-20", (
        "Tối ưu lợi nhuận kỳ vọng: TP1 tự học, chống đuổi giá 1 ATR, quét 40 coin",
        "Hỏi AI tới 2 ứng viên mỗi lượt; setup range theo dõi bóng",
    )),
    ("2.8.0", "2026-10-20", ("Cổng BTC, chống râu nến, SL theo cấu trúc, điểm dòng tiền OI/funding",)),
    ("2.7.0", "2026-10-20", ("Hiện phiên bản trên web; AI phản đối yếu không chặn tín hiệu mạnh",)),
)

ROOT = Path(__file__).resolve().parents[1]
STARTED = time.time()
_VN = timezone(timedelta(hours=7))


def _code_files():
    files = sorted(p for p in (ROOT / "bot").rglob("*.py") if "__pycache__" not in p.parts)
    run = ROOT / "run.py"
    out = files + ([run] if run.exists() else [])
    return [p for p in out if p.resolve() != Path(__file__).resolve()]


@lru_cache(maxsize=1)
def build():
    """7 ký tự hex: dấu vân tay của code đang chạy (đường dẫn + nội dung, bỏ khác biệt xuống dòng)."""
    h = hashlib.sha256()
    for p in _code_files():
        try:
            data = p.read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            data = b"<unreadable>"
        h.update(p.relative_to(ROOT).as_posix().encode() + b"\0" + data + b"\0")
    return h.hexdigest()[:7]


def is_release():
    return build() == RELEASE_BUILD


def ddmmyyyy(day):
    return f"{day[8:10]}/{day[5:7]}/{day[:4]}" if len(day) >= 10 else day


def label():
    mark = "" if is_release() else " (khác bản phát hành)"
    return f"v{VERSION} · {ddmmyyyy(RELEASED)} · bản dựng {build()}{mark}"


def uptime(now=None):
    s = max(int((now or time.time()) - STARTED), 0)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    return (f"{d} ngày " if d else "") + (f"{h} giờ " if d or h else "") + f"{s // 60} phút"


def started_text():
    return datetime.fromtimestamp(STARTED, _VN).strftime("%d/%m %H:%M")


def status_line():
    if is_release():
        return "✅ đúng bản phát hành"
    return f"⚠️ khác bản phát hành v{VERSION} ({RELEASE_BUILD}): upload thiếu file hoặc lẫn file cũ"


def info():
    return {"version": VERSION, "released": RELEASED, "build": build(), "release_build": RELEASE_BUILD,
            "release": is_release(), "started": int(STARTED), "uptime": uptime(),
            "notes": [{"version": v, "day": d, "notes": list(n)} for v, d, n in NOTES]}


def text(history=3):
    """Lệnh `phienban` trên Telegram/Zoom."""
    lines = [f"🏷️ OKX Altcoin Bot v{VERSION} (phát hành {ddmmyyyy(RELEASED)})",
             f"Bản dựng {build()} · {status_line()}",
             f"Chạy từ {started_text()} ({uptime()}) · Python {platform.python_version()}"]
    for v, day, notes in NOTES[:history]:
        lines += ["", f"{'Có gì mới ở ' if v == VERSION else ''}v{v} ({ddmmyyyy(day)}):"] + [f"• {n}" for n in notes]
    lines += ["", "Trên web: trang Phiên bản"]
    return "\n".join(lines)


def changes_since(previous):
    names = [v for v, _, _ in NOTES]
    if previous in names:
        return list(NOTES[:names.index(previous)])
    return list(NOTES[:1])


def update_notice(last):
    """Tin báo lúc khởi động khi phiên bản/bản dựng đổi so với lần chạy trước (`last` = "phiên_bản bản_dựng")."""
    prev_v, prev_b = ((last or "").split() + ["", ""])[:2]
    if prev_v == VERSION and prev_b == build():
        return None
    if prev_v == VERSION:
        return (f"⚠️ Code của bot vừa đổi nhưng vẫn ghi v{VERSION}: bản dựng {prev_b} → {build()}\n"
                f"Bản dựng {build()} · {status_line()}")
    head = f"🆕 Bot đã cập nhật: v{prev_v} → v{VERSION}" if prev_v else f"🏷️ Bot đang chạy v{VERSION}"
    lines = [head, f"Bản dựng {build()} · {status_line()}"]
    for v, day, notes in changes_since(prev_v):
        lines += ["", f"v{v} ({ddmmyyyy(day)}):"] + [f"• {n}" for n in notes]
    return "\n".join(lines)


def stamp():
    build.cache_clear()
    value = build()
    path = Path(__file__)
    src = path.read_text(encoding="utf-8")
    new, n = re.subn(r'^RELEASE_BUILD = "[0-9a-f]*"', f'RELEASE_BUILD = "{value}"', src, count=1, flags=re.M)
    if n != 1:
        raise RuntimeError("không tìm thấy dòng RELEASE_BUILD")
    path.write_text(new, encoding="utf-8")
    return value


if __name__ == "__main__":
    if "--stamp" in sys.argv[1:]:
        print(f"v{VERSION}: RELEASE_BUILD = {stamp()}")
    else:
        print(text())
