"""Tổng kết lệnh sau khi đóng – theo quy tắc, từ số liệu thật (v4.0 thay cho AI tổng kết).

Không phán đoán cảm tính: chỉ dùng số đã tính sẵn (kết quả theo R, giá đi thuận tối đa MFE, khoảng cách SL theo ATR,
tin tức lúc vào và lúc đóng) để xếp lệnh vào 1 trong các nhóm và nói rõ vấn đề nằm ở ĐIỂM VÀO hay QUẢN LÝ LỆNH.
Bài học dạng số liệu; việc chỉnh tham số là của bộ tự học (learner.py) dựa trên hàng trăm tín hiệu bóng, không dựa trên 1 lệnh.
"""
import time

from .config import cfg


def facts(t, exit_price, pnl):
    """Số liệu của lệnh: kết quả R (đã gồm phí), MFE theo R, SL theo ATR, thời gian giữ."""
    entry = float(t["entry"])
    sl0 = float(t.get("sl0") or t["sl"])
    risk0 = abs(entry - sl0)
    sign = 1 if t["side"] == "long" else -1
    notional0 = float(t.get("notional0") or t.get("notional") or 0)
    risk_usdt = notional0 * risk0 / entry if entry else 0
    atr = float(t.get("atr") or 0)
    peak = t.get("peak")
    return {
        "r": round(pnl / risk_usdt, 2) if risk_usdt else None,
        "mfe_r": round(sign * (float(peak) - entry) / risk0, 2) if (peak is not None and risk0) else None,
        "sl_atr": round(risk0 / atr, 2) if atr else None,
        "exit_r": round(sign * (float(exit_price) - entry) / risk0, 2) if risk0 else None,
        "hold_h": round((time.time() - float(t.get("opened_at") or time.time())) / 3600, 1),
        "tp1_hit": bool(t.get("tp1_done")),
    }


def review_trade(t, exit_price, pnl, pnl_pct, reason, news_now=None):
    """Trả về {verdict, lesson, tags, model, facts}. news_now: độ lệch tin tức theo hướng lệnh lúc đóng (hoặc None)."""
    f = facts(t, exit_price, pnl)
    r, mfe = f["r"], f["mfe_r"]
    r_txt = f"{r:+.2f}R" if r is not None else f"{pnl:+.4f} USDT"
    mfe_txt = f"{mfe:.1f}R" if mfe is not None else "?"
    tags = []
    if str(reason).startswith("Tin xấu"):              # main._news_guard đóng lệnh vì tin bất lợi mới
        verdict = "ĐÓNG VÌ TIN XẤU"
        lesson = (f"Đóng sớm ({reason}) với kết quả {r_txt}, giá từng thuận {mfe_txt}. Tin bất lợi xuất hiện SAU lúc vào "
                  "lệnh – không phải lỗi điểm vào. Các luật tin tức (news_*) vẫn được theo dõi bóng để biết chặn/đóng theo "
                  "tin có đáng hay không.")
        tags.append("tin_xấu")
    elif pnl > 0:
        if mfe is not None and r is not None and mfe - r >= 1.5:
            verdict = "THẮNG – TRẢ LẠI NHIỀU"
            lesson = (f"Lãi {r_txt} nhưng giá từng đi thuận {mfe_txt}: phần bám sóng trả lại {mfe - r:.1f}R. "
                      "Bộ tự học đang so sánh các cách thoát và mức TP1 trên dữ liệu bóng để chọn cách giữ lãi tốt hơn.")
            tags.append("trả_lại_lãi")
        else:
            verdict = "THẮNG ĐÚNG KẾ HOẠCH"
            lesson = f"Lãi {r_txt} ({reason}); giá đi thuận tối đa {mfe_txt}" + (", đã chốt TP1." if f["tp1_hit"] else ".")
            tags.append("đúng_kế_hoạch")
    else:
        if mfe is not None and mfe >= 1.0:
            verdict = "THUA SAU KHI ĐÃ LỜI"
            lesson = (f"Đã lời {mfe_txt} rồi quay về {r_txt}: vấn đề ở QUẢN LÝ LỆNH (mức TP1 / thời điểm dời SL), "
                      "không phải điểm vào. Bộ tự học so TP1 1–2,5R trên mọi tín hiệu bóng và tự chọn mức lời nhất.")
            tags.append("quản_lý_lệnh")
        elif mfe is not None and mfe < 0.3:
            verdict = "SAI HƯỚNG NGAY"
            lesson = (f"Giá đi ngược gần như ngay sau khi vào (thuận tối đa {mfe_txt}, kết quả {r_txt}): vấn đề ở ĐIỂM VÀO. "
                      "Xem lại trigger, bối cảnh BTC và tin tức lúc vào trong lý do mở lệnh.")
            tags.append("điểm_vào")
        else:
            sl = f" (SL {f['sl_atr']:.1f} ATR)" if f["sl_atr"] else ""
            verdict = "THUA TRONG KẾ HOẠCH"
            lesson = (f"Lỗ {r_txt} đúng mức dự tính{sl}, giá từng thuận {mfe_txt}. "
                      "Thua kiểu này là bình thường khi tỉ lệ thắng ~40% – không đổi gì vì 1 lệnh.")
            tags.append("bình_thường")
    n0 = t.get("news")
    if n0 is not None and abs(float(n0)) >= cfg.NEWS_MIN_BIAS:
        tags.append("tin_ủng_hộ" if float(n0) > 0 else "tin_ngược")
    if news_now is not None and n0 is not None:
        a, b = float(n0), float(news_now)
        if (a >= cfg.NEWS_MIN_BIAS and b <= -cfg.NEWS_MIN_BIAS) or (a <= -cfg.NEWS_MIN_BIAS and b >= cfg.NEWS_MIN_BIAS) \
                or (abs(a) < cfg.NEWS_MIN_BIAS and b <= -0.3):
            lesson += f" Tin tức về coin đổi chiều trong lúc giữ lệnh ({a:+.2f} → {b:+.2f})."
            tags.append("tin_đổi_chiều")
    return {"verdict": verdict, "lesson": lesson, "tags": tags[:3], "model": "quy-tắc", "facts": f}
