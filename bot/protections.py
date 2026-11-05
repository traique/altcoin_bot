"""Lớp bảo vệ kiểu freqtrade (StoplossGuard, CooldownPeriod/LowProfitPairs, AgeFilter) – tách khỏi tín hiệu.

Bộ tự học cần vài ngày đến vài tuần mới đủ mẫu để đổi tham số; lớp bảo vệ phản ứng trong vài giờ khi thị trường
đổi chiều (v3.2: 3 ngày liền short thua vì bot vẫn đánh theo chế độ cũ).

1. Khoá một phía (long hoặc short) PROTECT_LOCK_HOURS giờ khi:
   a) ≥ PROTECT_SIDE_LOSSES lệnh THẬT cùng phía đóng lỗ trong PROTECT_SIDE_HOURS giờ (StoplossGuard), hoặc
   b) tín hiệu cùng phía trong PROTECT_SHADOW_HOURS giờ gần nhất (đạt bộ lọc, kể cả không vào lệnh; mỗi coin tính
      1 lần) chạm SL (−1R) TRƯỚC +1R với tỉ lệ ≥ PROTECT_SHADOW_SL_SHARE trên ≥ PROTECT_SHADOW_MIN coin.
      Đo "chạm rào nào trước" chứ không đo kết quả cuối: lệnh thua chạm SL nhanh còn lệnh thắng bám sóng tới 24h mới
      xong, nên nhìn "kết quả vừa có" luôn thấy toàn thua. Hai rào ±1R đối xứng → không thiên lệch thời gian.
   Chỉ tính sự kiện xảy ra SAU lần khoá trước của phía đó (không khoá nối tiếp vô hạn vì cùng 1 đợt thua).
2. Khoá coin: lệnh gần nhất của coin đóng lỗ trong PROTECT_PAIR_LOSS_HOURS giờ → nghỉ; thua ≥ 2 lần trong
   PROTECT_PAIR_REPEAT_HOURS giờ → nghỉ tới hết khoảng đó.
3. Tuổi niêm yết: bỏ hợp đồng niêm yết chưa đủ PROTECT_MIN_AGE_DAYS ngày (listTime của OKX) – giá mới niêm yết
   bị thao túng, chỉ báo chưa đủ dữ liệu.
Tín hiệu bị khoá (1, 2) vẫn được theo dõi bóng với nguồn 'protected' → biết lớp bảo vệ đang cứu hay đang làm mất lãi.
"""
import logging
import time

from .config import cfg

log = logging.getLogger("protect")

WOULD_TRADE = ("taken", "unfilled", "not_taken", "protected")    # tín hiệu đạt mọi bộ lọc (sẽ được vào nếu còn chỗ)


class Protections:
    def __init__(self, store, notify=None):
        self.store = store
        self.notify = notify or (lambda *_: None)

    # ------------------------------------------------------------ khoá một phía
    def side_reason(self, side, now=None):
        """Lý do cần khoá phía `side` lúc này ('' nếu không)."""
        now = now or time.time()
        last = (self.store.get("protect_last") or {}).get(side, 0)
        if cfg.PROTECT_SIDE_LOSSES > 0:
            t0 = max(now - cfg.PROTECT_SIDE_HOURS * 3600, last)
            losses = [t for t in self.store.closed_trades_since(t0) if t["side"] == side and (t["pnl"] or 0) < 0]
            if len(losses) >= cfg.PROTECT_SIDE_LOSSES:
                return f"{len(losses)} lệnh {side.upper()} đóng lỗ trong {cfg.PROTECT_SIDE_HOURS:g}h"
        if cfg.PROTECT_SHADOW_MIN > 0:
            t0 = max(now - cfg.PROTECT_SHADOW_HOURS * 3600, last)
            latest = {}
            for r in self.store.signals_since(t0):          # cũ → mới: mỗi coin giữ tín hiệu mới nhất đã biết rào
                if r["side"] == side and r["source"] in WOULD_TRADE and r.get("first_hit") in ("SL", "TP1"):
                    latest[r["symbol"]] = r["first_hit"]
            n = len(latest)
            if n >= cfg.PROTECT_SHADOW_MIN:
                share = sum(1 for h in latest.values() if h == "SL") / n
                if share >= cfg.PROTECT_SHADOW_SL_SHARE:
                    return (f"{round(share * 100)}% tín hiệu {side.upper()} ({n} coin, {cfg.PROTECT_SHADOW_HOURS:g}h) "
                            f"chạm SL trước khi lời 1R")
        return ""

    def refresh(self, now=None):
        """Cập nhật khoá phía (gọi mỗi lượt quét). Trả về {side: {"until", "why", "since"}} đang hiệu lực."""
        if not cfg.PROTECT_ENABLED:
            return {}
        now = now or time.time()
        locks = {k: v for k, v in (self.store.get("protect_locks") or {}).items() if v.get("until", 0) > now}
        changed = False
        for side in ("long", "short"):
            if side in locks:
                continue
            why = self.side_reason(side, now)
            if why:
                locks[side] = {"until": now + cfg.PROTECT_LOCK_HOURS * 3600, "why": why, "since": now}
                last = self.store.get("protect_last") or {}
                last[side] = now
                self.store.set("protect_last", last)
                changed = True
                log.warning("Bảo vệ: khoá %s %gh – %s", side.upper(), cfg.PROTECT_LOCK_HOURS, why)
                self.notify(f"🛡️ BẢO VỆ: tạm khoá {side.upper()} {cfg.PROTECT_LOCK_HOURS:g} giờ – {why}. "
                            f"Tín hiệu bị khoá vẫn được theo dõi bóng.")
        if changed or locks != (self.store.get("protect_locks") or {}):
            self.store.set("protect_locks", locks)
        return locks

    # ------------------------------------------------------------ khoá coin
    def pair_locks(self, now=None):
        """{symbol: (đến lúc, lý do)} các coin đang nghỉ sau khi thua."""
        if not cfg.PROTECT_ENABLED or cfg.PROTECT_PAIR_LOSS_HOURS <= 0:
            return {}
        now = now or time.time()
        span = max(cfg.PROTECT_PAIR_LOSS_HOURS, cfg.PROTECT_PAIR_REPEAT_HOURS)
        by_sym = {}
        for t in self.store.closed_trades_since(now - span * 3600):
            by_sym.setdefault(t["symbol"], []).append(t)
        out = {}
        for sym, rows in by_sym.items():
            rows.sort(key=lambda t: t["closed_at"] or 0)
            losses = [t for t in rows if (t["pnl"] or 0) < 0]
            if len(losses) >= 2 and cfg.PROTECT_PAIR_REPEAT_HOURS > 0:
                until = losses[-2]["closed_at"] + cfg.PROTECT_PAIR_REPEAT_HOURS * 3600
                if until > now:
                    out[sym] = (until, f"thua {len(losses)} lần trong {cfg.PROTECT_PAIR_REPEAT_HOURS:g}h")
                    continue
            last = rows[-1]
            if (last["pnl"] or 0) < 0:
                until = (last["closed_at"] or 0) + cfg.PROTECT_PAIR_LOSS_HOURS * 3600
                if until > now:
                    out[sym] = (until, f"vừa thua lệnh gần nhất")
        return out

    # ------------------------------------------------------------ áp cho 1 tín hiệu
    @staticmethod
    def blocks(sig, side_locks, pair_locks):
        """Lý do lớp bảo vệ chặn tín hiệu ('' nếu không)."""
        lk = (side_locks or {}).get(sig.side)
        if lk:
            return f"khoá {sig.side.upper()} đến {time.strftime('%H:%M', time.localtime(lk['until']))} ({lk['why']})"
        pl = (pair_locks or {}).get(sig.symbol)
        if pl:
            return f"coin nghỉ đến {time.strftime('%H:%M', time.localtime(pl[0]))} ({pl[1]})"
        return ""

    @staticmethod
    def too_new(market, now=None):
        """Hợp đồng niêm yết chưa đủ PROTECT_MIN_AGE_DAYS ngày (listTime của OKX, mili giây)."""
        if not cfg.PROTECT_ENABLED or cfg.PROTECT_MIN_AGE_DAYS <= 0:
            return False
        try:
            lt = float(((market or {}).get("info") or {}).get("listTime") or 0) / 1000
        except (TypeError, ValueError):
            return False
        return bool(lt) and ((now or time.time()) - lt) < cfg.PROTECT_MIN_AGE_DAYS * 86400

    def public(self, now=None):
        now = now or time.time()
        locks = {k: v for k, v in (self.store.get("protect_locks") or {}).items() if v.get("until", 0) > now}
        return {"enabled": cfg.PROTECT_ENABLED, "sides": locks,
                "pairs": {s: {"until": u, "why": w} for s, (u, w) in self.pair_locks(now).items()},
                "params": {"side_losses": cfg.PROTECT_SIDE_LOSSES, "side_hours": cfg.PROTECT_SIDE_HOURS,
                           "shadow_min": cfg.PROTECT_SHADOW_MIN, "shadow_sl_share": cfg.PROTECT_SHADOW_SL_SHARE,
                           "shadow_hours": cfg.PROTECT_SHADOW_HOURS, "lock_hours": cfg.PROTECT_LOCK_HOURS,
                           "pair_loss_hours": cfg.PROTECT_PAIR_LOSS_HOURS, "min_age_days": cfg.PROTECT_MIN_AGE_DAYS}}


def first_barrier(side, entry, sl, ts, candles):
    """Rào nào bị chạm trước sau thời điểm tín hiệu: 'SL' (−1R) hay 'TP1' (+1R). Cùng 1 nến chạm cả hai → SL (thận trọng).
    candles: [[ts_ms, o, h, l, c, v], …] (5m). Trả về (nhãn, ts) hoặc (None, None) nếu chưa chạm."""
    risk = abs(entry - sl)
    if not risk:
        return None, None
    up = entry + risk if side == "long" else entry - risk
    for c in candles:
        t = c[0] / 1000
        if t + 300 <= ts:                 # nến kết thúc trước lúc có tín hiệu
            continue
        hi, lo = float(c[2]), float(c[3])
        if (side == "long" and lo <= sl) or (side == "short" and hi >= sl):
            return "SL", t + 300
        if (side == "long" and hi >= up) or (side == "short" and lo <= up):
            return "TP1", t + 300
    return None, None
