"""Quản lý rủi ro & tính khối lượng lệnh.

Mỗi lệnh có hệ số rủi ro = hệ số tin tức × chuỗi thua gần đây, kẹp trong [RISK_MIN_MULT, RISK_MAX_MULT].
Tổng rủi ro mọi lệnh đang mở không vượt MAX_TOTAL_RISK vốn.
v4.0: bỏ hệ số theo AI. Điểm kỹ thuật vẫn KHÔNG làm tăng rủi ro (v3.2: điểm ≥ 7 thua nặng nhất – điểm cao = xu hướng
đã rõ với mọi người = vào muộn); chỉ tin tức (đã nhân trọng số tin bộ tự học đo được) và chuỗi thua điều tiết.
"""
from .config import cfg
from . import strategy


def quality_mult(sig, dec=None):
    """Hệ số rủi ro theo tin tức (1.0 = không có tin riêng / tin trung tính).
    Tin cùng chiều lệnh → tăng tối đa +25% × trọng số tin; ngược chiều → giảm tương ứng. Trọng số tin (news_w, 0–2) do
    bộ tự học chỉnh theo kết quả thật: tin không giúp ích → trọng số về 0 → hệ số luôn 1.0."""
    c = getattr(sig, "context", None) or {}
    if not (c.get("news_n") or 0):
        return 1.0
    al = strategy.news_align(sig.side, c)
    if abs(al) < cfg.NEWS_MIN_BIAS:
        return 1.0
    return max(0.5, min(1.5, 1.0 + 0.25 * strategy.news_weight() * al))


def streak_mult(closed_recent):
    """Giảm rủi ro sau chuỗi thua: từ lệnh thua liên tiếp thứ LOSS_STREAK_FROM trở đi nhân LOSS_STREAK_CUT mỗi lệnh.
    closed_recent: các lệnh đã đóng, MỚI NHẤT TRƯỚC."""
    streak = 0
    for t in closed_recent or []:
        if (t.get("pnl") or 0) <= 0:
            streak += 1
        else:
            break
    return cfg.LOSS_STREAK_CUT ** max(0, streak - (cfg.LOSS_STREAK_FROM - 1))


def risk_mult(sig, dec=None, closed_recent=None):
    m = quality_mult(sig, dec) * streak_mult(closed_recent)
    return max(cfg.RISK_MIN_MULT, min(cfg.RISK_MAX_MULT, m))


def open_risk_usdt(open_trades):
    """USDT sẽ mất (gồm phí + trượt giá) nếu mọi lệnh đang mở chạm SL hiện tại (SL đã dời về hoà vốn → chỉ còn phí)."""
    total = 0.0
    for t in open_trades or []:
        entry, sl, notional = t.get("entry") or 0, t.get("sl") or 0, t.get("notional") or 0
        if not entry:
            continue
        loss = (entry - sl) if t.get("side") == "long" else (sl - entry)
        total += (max(0.0, loss / entry) + 2 * cfg.TAKER_FEE + cfg.SLIPPAGE) * notional
    return total


def risk_budget(equity, open_trades):
    """USDT còn được phép rủi ro thêm (trần MAX_TOTAL_RISK trừ rủi ro đang mở)."""
    return equity * cfg.MAX_TOTAL_RISK - open_risk_usdt(open_trades)


def position_notional(equity, entry, sl, mult=1.0, budget=None):
    """Giá trị lệnh (USDT) sao cho nếu chạm SL thì mất RISK_PER_TRADE * mult * equity,
    không vượt ngân sách rủi ro còn lại (budget) và ký quỹ tối đa (equity * leverage * 0.9)."""
    risk_usdt = equity * cfg.RISK_PER_TRADE * mult
    if budget is not None:
        if budget < 0.4 * risk_usdt:         # còn quá ít chỗ → không mở thêm
            return 0.0
        risk_usdt = min(risk_usdt, budget)
    sl_dist = abs(entry - sl) / entry
    if sl_dist <= 0:
        return 0.0
    # trừ phí vào/ra + trượt giá vào tổng rủi ro
    cost = 2 * cfg.TAKER_FEE + cfg.SLIPPAGE
    notional = risk_usdt / (sl_dist + cost)
    max_notional = equity * cfg.LEVERAGE * 0.9
    return max(0.0, min(notional, max_notional))


def risk_of(notional, entry, sl):
    """USDT mất nếu lệnh `notional` chạm SL (gồm phí + trượt giá)."""
    return notional * (abs(entry - sl) / entry + 2 * cfg.TAKER_FEE + cfg.SLIPPAGE) if entry else 0.0


def margin_for(notional):
    return notional / cfg.LEVERAGE


class CircuitBreaker:
    """Dừng giao dịch khi lỗ ngày / drawdown vượt ngưỡng."""

    def __init__(self, state):
        self.state = state

    def check(self, equity, today_start_equity, peak_equity):
        if today_start_equity > 0 and (today_start_equity - equity) / today_start_equity >= cfg.MAX_DAILY_LOSS:
            return False, f"Chạm giới hạn lỗ ngày ({cfg.MAX_DAILY_LOSS*100:.0f}%)"
        if peak_equity > 0 and (peak_equity - equity) / peak_equity >= cfg.MAX_DRAWDOWN:
            return False, f"Chạm giới hạn drawdown ({cfg.MAX_DRAWDOWN*100:.0f}%)"
        return True, ""
