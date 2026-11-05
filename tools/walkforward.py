"""Tối ưu walk-forward trên nến lịch sử OKX – chạy trên máy tính / VPS, KHÔNG chạy trên Botkeep.

Mục đích: thử nhiều bộ ngưỡng cổng lọc / ngưỡng điểm / cách thoát lệnh trên dữ liệu quá khứ, nhưng CHỈ tin bộ tham số nào
vẫn thắng trên đoạn dữ liệu CHƯA dùng để chọn nó (out-of-sample). Dùng lại đúng code chấm tín hiệu (bot/strategy.py) và
thoát lệnh (bot/exits.py) của bot để kết quả khớp cách bot giao dịch.

    python tools/walkforward.py fetch    --days 90 --coins 40 --data tools/wf_data      # tải nến (≈ 45 phút)
    python tools/walkforward.py events   --data tools/wf_data                             # tín hiệu ứng viên + mô phỏng thoát
    python tools/walkforward.py optimize --data tools/wf_data --out tools/wf_out          # lưới tham số + walk-forward

Giới hạn (ghi rõ trong báo cáo): không có tin tức và dòng tiền (OI/funding/long-short) lịch sử → chỉ tối ưu phần kỹ thuật;
danh sách coin là top volume HIỆN TẠI (thiên lệch sống sót); EMA200 tính trên toàn chuỗi (bot thật tính trên 220 nến).
"""
import argparse
import gzip
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TF_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000}


# ============================================================ 1. tải nến
def _okx():
    import ccxt
    ex = ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    if os.getenv("HTTPS_PROXY") or os.getenv("REQUESTS_CA_BUNDLE"):
        ex.session.trust_env = True
    return ex


def _path(data, sym, tf):
    return os.path.join(data, f"{sym.split('/')[0]}_{tf}.json.gz")


def load(data, sym, tf):
    with gzip.open(_path(data, sym, tf), "rt") as fh:
        return json.load(fh)


def fetch_series(ex, sym, tf, since_ms, until_ms):
    out, cur = [], since_ms
    while cur < until_ms:
        for attempt in range(5):
            try:
                rows = ex.fetch_ohlcv(sym, tf, since=cur, limit=300)
                break
            except Exception as e:                       # mạng chập chờn / giới hạn tần suất → chờ rồi thử lại
                print(f"  {sym} {tf}: {str(e)[:80]} – thử lại", flush=True)
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"không tải được {sym} {tf}")
        if not rows:
            break
        rows = [r for r in rows if r[0] >= cur]
        if not rows:
            break
        out.extend(rows)
        cur = rows[-1][0] + TF_MS[tf]
    seen, clean = set(), []
    for r in out:                                         # bỏ trùng, chỉ nến đã đóng
        if r[0] not in seen and r[0] + TF_MS[tf] <= until_ms:
            seen.add(r[0])
            clean.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0)])
    return sorted(clean)


def cmd_fetch(a):
    from bot.exchange import OKX
    os.makedirs(a.data, exist_ok=True)
    okx = OKX()
    coins = [s for s, _, _ in okx.top_altcoins(a.coins)]          # đúng bộ lọc của bot: crypto thật, bỏ BTC/ETH/stable
    syms = ["BTC/USDT:USDT"] + coins
    until = int(time.time() // 3600 * 3600 * 1000)                 # tròn giờ → mọi khung cùng mốc kết thúc
    since = until - a.days * 86_400_000
    meta = {"since": since, "until": until, "days": a.days, "coins": coins, "fetched": time.time()}
    t0 = time.time()
    for i, s in enumerate(syms):
        for tf in ("1h", "15m", "5m"):
            p = _path(a.data, s, tf)
            if os.path.exists(p) and not a.force:
                continue
            # nến 1h cần thêm 10 ngày đầu để chỉ báo khung lớn "ấm máy" (EMA50, ADX)
            rows = fetch_series(okx.ex, s, tf, since - (10 * 86_400_000 if tf == "1h" else 2 * 86_400_000), until)
            with gzip.open(p, "wt") as fh:
                json.dump(rows, fh)
        print(f"[{i + 1}/{len(syms)}] {s} xong – {time.time() - t0:.0f}s", flush=True)
    with open(os.path.join(a.data, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("Tải xong:", len(syms), "mã,", a.days, "ngày")


# ============================================================ 2. tín hiệu ứng viên (dùng đúng code của bot)
VN = 7 * 3600                       # giờ Việt Nam – bot ghi "hour" theo TIMEZONE=Asia/Ho_Chi_Minh
TP1S = (1.0, 1.3, 1.6, 2.0, 2.5)
EXITS = ("fixed",) + tuple(f"hybrid:{v:g}" for v in TP1S) + ("trail",)
# Ngưỡng lỏng nhất trong lưới tối ưu: tín hiệu không qua nổi mức này thì không bộ tham số nào dùng → khỏi mô phỏng
LOOSE = dict(min_adx=16, min_atr_pct=0.25, min_vol_ratio=0.5, max_ext_atr=1.5, chase_1h_pct=1.2, btc_gate_chg=0.8,
             rsi_floor=40, rsi_cap=80, wick_close_pos=0.5, max_sl_atr=4.0, min_score=4.0)


class Col:
    """Cửa sổ chỉ đọc trên 1 cột chỉ báo đã tính (không sao chép). Chỉ số dương tính từ đầu cửa sổ, âm từ cuối."""
    __slots__ = ("a", "s", "n")

    def __init__(self, a, s, e):
        self.a, self.s, self.n = a, s, e - s

    def __len__(self):
        return self.n

    def __getitem__(self, k):
        if isinstance(k, slice):
            i, j, st = k.indices(self.n)
            return self.a[self.s + i:self.s + j:st]
        if k < 0:
            k += self.n
        if not 0 <= k < self.n:
            raise IndexError(k)
        return self.a[self.s + k]


class View:
    """Khung "tới nến end-1" trên chuỗi đã tính chỉ báo – thay cho enrich(to_frame(...)) mỗi lần quét của bot."""

    def __init__(self, f, end, size=220):
        self.f, self.s, self.e = f, max(0, end - size), end
        self.n = self.e - self.s

    def __getattr__(self, name):
        arr = getattr(self.f, name)
        return Col(arr, self.s, self.e) if isinstance(arr, list) else arr

    def row(self, i):
        from types import SimpleNamespace
        k = self.e + i if i < 0 else self.s + i
        return SimpleNamespace(**{c: a[k] for c, a in self.f.__dict__.items() if isinstance(a, list)})


def _btc_context(data):
    """{giờ đóng nến 15m (ms): bối cảnh BTC như market.btc_context() lúc bot quét ngay sau khi nến đóng}."""
    from bot.indicators import to_frame, enrich
    b15 = load(data, "BTC/USDT:USDT", "15m")
    h = enrich(to_frame(load(data, "BTC/USDT:USDT", "1h")))
    ts, cl = [r[0] for r in b15], [r[4] for r in b15]
    out, j = {}, -1
    for k in range(16, len(ts)):
        tc = ts[k] + TF_MS["15m"]
        while j + 1 < h.n and h.ts[j + 1] + TF_MS["1h"] <= tc:
            j += 1
        if j < 60:
            continue
        # bot lấy 40 nến 15m gồm cả nến đang chạy: giá hiện tại ≈ close[k], closes[-5] = close[k-3], closes[-17] = close[k-15]
        e21, e50, c1 = h.ema21[j], h.ema50[j], h.close[j]
        trend = 1 if (e21 > e50 and c1 > e21) else -1 if (e21 < e50 and c1 < e21) else 0
        out[tc] = {"btc_price": round(cl[k], 1), "btc_chg_1h": round(100 * (cl[k] / cl[k - 3] - 1), 2),
                   "btc_chg_4h": round(100 * (cl[k] / cl[k - 15] - 1), 2), "btc_trend_1h": trend,
                   "btc_rsi_1h": round(h.rsi[j], 1), "btc_adx_1h": round(h.adx[j], 1)}
    return out


def _coin_events(job):
    """Mọi nến 15m của 1 coin mà bot (với cổng nới tối đa) coi là tín hiệu xu hướng → sự kiện kèm giá trị từng cổng
    và kết quả R theo từng cách thoát (mô phỏng bằng nến 5m sau tín hiệu, y như bộ tự học)."""
    import bisect
    data, sym, since, until, btc = job
    from bot.config import cfg
    from bot import strategy as S, exits
    from bot.indicators import to_frame, enrich
    cfg.RANGE_ENABLED = False                               # setup range đang bị chặn sẵn – chỉ tối ưu setup xu hướng
    S.LEARNED.update(min_score=-99.0, trigger_w={}, gates={
        k: (-1e9 if g[1] == "min" else 1e9) for k, g in S.GATES.items()})
    try:
        F = enrich(to_frame(load(data, sym, "15m")))
        H = enrich(to_frame(load(data, sym, "1h")))
        m5 = load(data, sym, "5m")
    except FileNotFoundError:
        return []
    m5ts = [r[0] for r in m5]
    cost = 2 * cfg.TAKER_FEE + cfg.SLIPPAGE
    out, j = [], -1
    for i in range(F.n):
        tc = F.ts[i] + TF_MS["15m"]
        while j + 1 < H.n and H.ts[j + 1] + TF_MS["1h"] <= tc:
            j += 1
        if i < 250 or j < 120 or tc < since or tc > until - 25 * 3_600_000:
            continue
        mk = btc.get(tc)
        if mk is None:
            continue
        hour = int(((tc // 1000 + VN) // 3600) % 24)
        chg24 = (F.close[i] / F.close[i - 96] - 1) * 100
        sig, why, _ = S.evaluate(sym, View(F, i + 1), View(H, j + 1, 120), 0.0, chg24, mk, hour=hour)
        if sig is None or why or sig.context.get("setup") != "trend":
            continue
        want = 1 if sig.side == "long" else -1
        r = F.row(i)
        a = r.atr
        ev = {"sym": sym, "ts": tc // 1000, "side": sig.side, "score": sig.score, "hour": hour,
              "trig": ",".join(sig.triggers), "price": sig.price, "sl": sig.sl, "atr": a,
              "adx": r.adx, "atr_pct": r.atr_pct, "vol_ratio": r.vol_ratio,
              "ext_atr": abs(r.close - r.ema21) / a if a else 0.0,
              "chase": -want * (r.close / F.close[i - 4] - 1) * 100,
              "btc_v": -want * mk["btc_chg_1h"],
              "rsi_m": r.rsi if sig.side == "long" else 100 - r.rsi,
              "wick": r.close_pos if sig.side == "long" else 1 - r.close_pos,
              "sl_atr": abs(sig.price - sig.sl) / a if a else 0.0,
              "rules": ",".join(S.matching_rules(sig.side, sig.context))}
        if not (ev["adx"] >= LOOSE["min_adx"] and ev["atr_pct"] >= LOOSE["min_atr_pct"]
                and ev["vol_ratio"] >= LOOSE["min_vol_ratio"] and ev["ext_atr"] <= LOOSE["max_ext_atr"]
                and ev["chase"] < LOOSE["chase_1h_pct"] and ev["btc_v"] <= LOOSE["btc_gate_chg"]
                and LOOSE["rsi_floor"] <= ev["rsi_m"] <= LOOSE["rsi_cap"] and ev["wick"] >= LOOSE["wick_close_pos"]
                and ev["sl_atr"] <= LOOSE["max_sl_atr"] and ev["score"] >= LOOSE["min_score"]):
            continue
        k0 = bisect.bisect_left(m5ts, tc - TF_MS["5m"])
        cs = m5[k0:k0 + 12 * 27]                                  # 27h nến 5m sau tín hiệu (lệnh bám sóng tối đa 24h)
        t0 = tc / 1000
        for ex in EXITS:
            mode, _, v = ex.partition(":")
            lab, R, tx = exits.simulate(sig.side, sig.price, sig.sl, a, mode, t0, cs, cost,
                                        tp1_r=float(v) if v else None, with_time=True)
            if lab is None:                                       # thiếu dữ liệu → đóng theo giá cuối (như bộ tự học)
                last = cs[-1][4] if cs else sig.price
                risk = abs(sig.price - sig.sl)
                R = round(want * (last - sig.price) / risk - cost * sig.price / risk, 3)
                lab, tx = "TIMEOUT", (cs[-1][0] / 1000 + 300) if cs else t0
            ev["R_" + ex], ev["X_" + ex] = R, tx
        out.append(ev)
    return out


def cmd_events(a):
    from multiprocessing import Pool
    meta = json.load(open(os.path.join(a.data, "meta.json")))
    btc = _btc_context(a.data)
    jobs = [(a.data, s, meta["since"], meta["until"], btc) for s in meta["coins"]]
    t0 = time.time()
    events = []
    with Pool(a.procs) as pool:
        for k, evs in enumerate(pool.imap_unordered(_coin_events, jobs), 1):
            events.extend(evs)
            print(f"[{k}/{len(jobs)}] {len(evs)} tín hiệu – tổng {len(events)} – {time.time() - t0:.0f}s", flush=True)
    events.sort(key=lambda e: (e["ts"], e["sym"]))
    with gzip.open(os.path.join(a.data, "events.json.gz"), "wt") as fh:
        json.dump(events, fh)
    print("Xong:", len(events), "tín hiệu ứng viên")


# ============================================================ 3. tối ưu + walk-forward
GRID = {
    "min_adx": [16, 18, 20, 22, 24, 26],
    "min_atr_pct": [0.25, 0.35, 0.45, 0.6],
    "min_vol_ratio": [0.5, 0.7, 0.9, 1.1],
    "max_ext_atr": [0.5, 0.75, 1.0, 1.25, 1.5],
    "chase_1h_pct": [0.3, 0.5, 0.8, 1.2],
    "btc_gate_chg": [0.2, 0.3, 0.5, 0.8],
    "rsi_floor": [40, 45, 50],
    "rsi_cap": [65, 70, 75, 80],
    "wick_close_pos": [0.5, 0.6, 0.7],
    "max_sl_atr": [2.5, 3.0, 3.5, 4.0],
    "min_score": [4.0, 4.5, 5.0, 5.5, 6.0, 6.5],
    "block_sessions": [1, 0],          # luật chặn sẵn night_session (0–7h) + afternoon_session (13–19h) giờ VN
    "block_climax": [1, 0],            # luật chặn sẵn climax_volume (volume ≥ 1.5× TB20)
    "exit": list(EXITS),
}
NAMES = {"min_adx": "ADX 15m tối thiểu", "min_atr_pct": "ATR% tối thiểu", "min_vol_ratio": "Volume tối thiểu (×TB20)",
         "max_ext_atr": "Cách EMA21 tối đa (ATR)", "chase_1h_pct": "Nhịp 1h ngược tối đa (%)",
         "btc_gate_chg": "BTC ngược tối đa (%/1h)", "rsi_floor": "RSI tối thiểu (theo hướng)",
         "rsi_cap": "RSI tối đa (theo hướng)", "wick_close_pos": "Vị trí đóng nến tối thiểu",
         "max_sl_atr": "SL cấu trúc tối đa (ATR)", "min_score": "Điểm tối thiểu", "block_sessions": "Chặn phiên 0–7h & 13–19h",
         "block_climax": "Chặn nến volume cao trào", "exit": "Cách thoát lệnh"}


def defaults():
    from bot.config import cfg
    return {"min_adx": cfg.MIN_ADX, "min_atr_pct": cfg.MIN_ATR_PCT, "min_vol_ratio": cfg.MIN_VOL_RATIO,
            "max_ext_atr": cfg.MAX_EXT_ATR, "chase_1h_pct": cfg.CHASE_1H_PCT, "btc_gate_chg": cfg.BTC_GATE_CHG,
            "rsi_floor": cfg.RSI_LONG_MIN, "rsi_cap": cfg.RSI_LONG_MAX, "wick_close_pos": cfg.WICK_CLOSE_POS,
            "max_sl_atr": cfg.MAX_SL_ATR, "min_score": cfg.MIN_SCORE, "block_sessions": 1, "block_climax": 1,
            "exit": f"hybrid:{cfg.TP1_R:g}"}


class Book:
    """Sự kiện dạng mảng numpy để lọc nhanh hàng nghìn bộ tham số."""

    def __init__(self, events):
        import numpy as np
        from bot.config import cfg
        self.np, self.ev = np, events
        col = lambda k: np.array([e[k] for e in events], dtype=float)
        self.ts = col("ts")
        for k in ("adx", "atr_pct", "vol_ratio", "ext_atr", "chase", "btc_v", "rsi_m", "wick", "sl_atr", "score", "hour"):
            setattr(self, k, col(k))
        self.R = {x: col("R_" + x) for x in EXITS}
        self.X = {x: col("X_" + x) for x in EXITS}
        self.session = (self.hour < 7) | ((self.hour >= 13) & (self.hour < 19))
        self.climax = self.vol_ratio >= cfg.CLIMAX_VOL
        syms = sorted({e["sym"] for e in events})
        sid = {s: i for i, s in enumerate(syms)}
        self.key = np.array([sid[e["sym"]] * 2 + (e["side"] == "short") for e in events])
        self.sym = [e["sym"] for e in events]

    def mask(self, p, t0, t1):
        m = (self.ts >= t0) & (self.ts < t1)
        m &= (self.adx >= p["min_adx"]) & (self.atr_pct >= p["min_atr_pct"]) & (self.vol_ratio >= p["min_vol_ratio"])
        m &= (self.ext_atr <= p["max_ext_atr"]) & (self.chase < p["chase_1h_pct"]) & (self.btc_v <= p["btc_gate_chg"])
        m &= (self.rsi_m >= p["rsi_floor"]) & (self.rsi_m <= p["rsi_cap"]) & (self.wick >= p["wick_close_pos"])
        m &= (self.sl_atr <= p["max_sl_atr"]) & (self.score >= p["min_score"])
        if p["block_sessions"]:
            m &= ~self.session
        if p["block_climax"]:
            m &= ~self.climax
        return m

    def dedup(self, m, gap=3600):
        """Mỗi (coin, hướng) tối đa 1 tín hiệu/giờ – giống cách bot ghi tín hiệu bóng (trigger kéo dài 3 nến)."""
        last, keep = {}, []
        for i in self.np.flatnonzero(m):
            k = self.key[i]
            if self.ts[i] - last.get(k, -1e18) >= gap:
                last[k] = self.ts[i]
                keep.append(i)
        return keep

    def stats(self, idx, exit_):
        np = self.np
        r = self.R[exit_][idx] if len(idx) else np.array([])
        n = len(r)
        if not n:
            return {"n": 0, "exp_r": 0.0, "sum_r": 0.0, "winrate": 0.0, "t": 0.0}
        sd = float(r.std(ddof=1)) if n > 1 else 0.0
        return {"n": n, "exp_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 2),
                "winrate": round(100 * float((r > 0).mean()), 1),
                "t": round(float(r.mean() / (sd / n ** 0.5)), 2) if sd > 0 else 0.0}

    def portfolio(self, m, exit_, max_open=2, cooldown=7200):
        """Mô phỏng danh mục như bot: tối đa `max_open` lệnh mở, mỗi coin chờ 2h sau khi vào, chọn điểm cao nhất,
        mỗi lệnh rủi ro 1R. Trả về danh sách lệnh (ts vào, coin, hướng, điểm, R, ts ra)."""
        idx = self.np.flatnonzero(m)
        by_t = {}
        for i in idx:
            by_t.setdefault(self.ts[i], []).append(i)
        open_, last_in, trades = [], {}, []
        for t in sorted(by_t):
            open_ = [o for o in open_ if o[0] > t]
            slots = max_open - len(open_)
            if slots <= 0:
                continue
            busy = {o[1] for o in open_}
            for i in sorted(by_t[t], key=lambda i: -self.score[i]):
                s = self.sym[i]
                if slots <= 0:
                    break
                if s in busy or t - last_in.get(s, -1e18) < cooldown:
                    continue
                x = self.X[exit_][i]
                open_.append((x, s))
                busy.add(s)
                last_in[s] = t
                slots -= 1
                trades.append((int(t), s, self.ev[i]["side"], float(self.score[i]), float(self.R[exit_][i]), int(x)))
        return trades


def pstats(trades, days):
    eq, peak, dd, streak, worst = 0.0, 0.0, 0.0, 0, 0
    for tr in trades:
        eq += tr[4]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        streak = streak + 1 if tr[4] <= 0 else 0
        worst = max(worst, streak)
    n = len(trades)
    return {"trades": n, "sum_r": round(eq, 2), "exp_r": round(eq / n, 3) if n else 0.0,
            "winrate": round(100 * sum(1 for t in trades if t[4] > 0) / n, 1) if n else 0.0,
            "max_dd_r": round(dd, 2), "r_per_day": round(eq / days, 3) if days else 0.0, "worst_streak": worst}


def objective(s, min_n):
    """Chọn bộ tham số trên đoạn huấn luyện: t-thống kê của kỳ vọng R (lãi đều, đủ mẫu) – không chọn theo tổng lãi
    (dễ chọn bộ quá lỏng nhiều lệnh) hay kỳ vọng thuần (dễ chọn bộ quá chặt vài lệnh may mắn)."""
    return s["t"] if s["n"] >= min_n else -1e9


def cmd_optimize(a):
    import csv
    import random
    meta = json.load(open(os.path.join(a.data, "meta.json")))
    with gzip.open(os.path.join(a.data, "events.json.gz"), "rt") as fh:
        events = json.load(fh)
    os.makedirs(a.out, exist_ok=True)
    B = Book(events)
    D = defaults()
    day = 86400
    t_start = meta["since"] / 1000
    t_end = meta["until"] / 1000 - 25 * 3600
    span = (t_end - t_start) / day
    rng = random.Random(a.seed)
    combos = [dict(D)]
    for k, vals in GRID.items():                          # đổi 1 tham số quanh mặc định
        for v in vals:
            if v != D[k]:
                combos.append({**D, k: v})
    while len(combos) < a.samples:
        combos.append({k: rng.choice(v) for k, v in GRID.items()})
    print(f"{len(events)} tín hiệu ứng viên, {span:.0f} ngày, {len(combos)} bộ tham số", flush=True)

    def evaluate(p, t0, t1):
        return B.stats(B.dedup(B.mask(p, t0, t1)), p["exit"])

    # ---- 3a. độ nhạy từng tham số (toàn kỳ – mô tả, CHƯA phải kiểm tra ngoài mẫu)
    half = t_start + span / 2 * day
    rows = []
    for k, vals in GRID.items():
        for v in vals:
            p = {**D, k: v}
            full, h1, h2 = evaluate(p, t_start, t_end), evaluate(p, t_start, half), evaluate(p, half, t_end)
            rows.append({"tham_so": k, "ten": NAMES[k], "gia_tri": v, "mac_dinh": int(v == D[k]),
                         "n": full["n"], "ky_vong_R": full["exp_r"], "tong_R": full["sum_r"], "thang_%": full["winrate"],
                         "t": full["t"], "nua_dau_R": h1["exp_r"], "nua_dau_n": h1["n"], "nua_sau_R": h2["exp_r"],
                         "nua_sau_n": h2["n"]})
    _csv(os.path.join(a.out, "do_nhay_tham_so.csv"), rows)

    # ---- 3b. walk-forward: huấn luyện a.train ngày → kiểm tra a.test ngày tiếp theo, trượt a.test ngày
    folds, oos_wf, oos_def = [], [], []
    oos_days = 0.0
    k = 0
    while True:
        tr0 = t_start + k * a.test * day
        tr1, te1 = tr0 + a.train * day, min(tr0 + (a.train + a.test) * day, t_end)
        if te1 - tr1 < 3 * day:                          # lượt cuối còn < 3 ngày kiểm tra → dừng
            break
        oos_days += (te1 - tr1) / day
        scored = sorted(((objective(evaluate(p, tr0, tr1), a.min_n), i) for i, p in enumerate(combos)), reverse=True)
        best = combos[scored[0][1]]
        tr_b, te_b, te_d = evaluate(best, tr0, tr1), evaluate(best, tr1, te1), evaluate(D, tr1, te1)
        pw = B.portfolio(B.mask(best, tr1, te1), best["exit"])
        pd = B.portfolio(B.mask(D, tr1, te1), D["exit"])
        oos_wf += pw
        oos_def += pd
        folds.append({"fold": k + 1, "huan_luyen": f"{_d(tr0)}→{_d(tr1)}", "kiem_tra": f"{_d(tr1)}→{_d(te1)}",
                      **{f"chon_{p}": best[p] for p in GRID},
                      "hl_n": tr_b["n"], "hl_R": tr_b["exp_r"], "hl_t": tr_b["t"],
                      "kt_n": te_b["n"], "kt_R": te_b["exp_r"], "kt_tong_R": te_b["sum_r"],
                      "macdinh_kt_n": te_d["n"], "macdinh_kt_R": te_d["exp_r"], "macdinh_kt_tong_R": te_d["sum_r"],
                      "dm_lenh": len(pw), "dm_tong_R": pstats(pw, a.test)["sum_r"],
                      "dm_macdinh_lenh": len(pd), "dm_macdinh_tong_R": pstats(pd, a.test)["sum_r"]})
        print(f"fold {k + 1}: huấn luyện t={tr_b['t']} ({tr_b['n']}) → kiểm tra {te_b['exp_r']:+.3f}R×{te_b['n']} "
              f"| mặc định {te_d['exp_r']:+.3f}R×{te_d['n']}", flush=True)
        k += 1
    _csv(os.path.join(a.out, "walk_forward_folds.csv"), folds)
    oos_days = round(oos_days, 1)
    first_test = t_start + a.train * day

    # ---- 3c. tổng hợp ngoài mẫu + bộ "tốt nhất nhìn lại" (quá khớp – để so)
    best_all = combos[max(range(len(combos)), key=lambda i: objective(evaluate(combos[i], t_start, t_end), a.min_n))]
    hind = B.portfolio(B.mask(best_all, first_test, t_end), best_all["exit"])
    summary = {"events": len(events), "coins": len(meta["coins"]), "days": round(span, 1), "combos": len(combos),
               "train_days": a.train, "test_days": a.test, "folds": len(folds), "oos_days": oos_days,
               "defaults": D, "best_hindsight": best_all,
               "oos_default_portfolio": pstats(oos_def, oos_days), "oos_walkforward_portfolio": pstats(oos_wf, oos_days),
               "hindsight_portfolio_same_period": pstats(hind, oos_days),
               "default_signals_full": evaluate(D, t_start, t_end),
               "default_signals_oos": evaluate(D, first_test, t_end),
               # mọi tín hiệu ứng viên (ngưỡng lỏng nhất, không chặn phiên) – mức nền để biết bộ lọc có thêm giá trị không
               "loose_signals_full": evaluate({**LOOSE, "block_sessions": 0, "block_climax": 0, "exit": D["exit"]},
                                              t_start, t_end),
               "best_hindsight_signals_full": evaluate(best_all, t_start, t_end),
               "best_hindsight_signals_oos": evaluate(best_all, first_test, t_end)}
    with open(os.path.join(a.out, "tong_hop.json"), "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    _csv(os.path.join(a.out, "lenh_ngoai_mau_walkforward.csv"), _trows(oos_wf))
    _csv(os.path.join(a.out, "lenh_ngoai_mau_macdinh.csv"), _trows(oos_def))

    # ---- 3d. phân tích mô tả với tham số mặc định (toàn kỳ): theo hướng, trigger, giờ, điểm, cách thoát, luật
    idx = B.dedup(B.mask({**D, "block_sessions": 0, "block_climax": 0}, t_start, t_end))    # bỏ chặn để đo cả nhóm bị chặn
    rows = []

    def grp(dim, key_fn):
        g = {}
        for i in idx:
            for kk in key_fn(i):
                g.setdefault(kk, []).append(i)
        for kk, ii in sorted(g.items(), key=lambda x: str(x[0])):
            s = B.stats(ii, D["exit"])
            rows.append({"nhom": dim, "gia_tri": kk, "n": s["n"], "ky_vong_R": s["exp_r"], "tong_R": s["sum_r"],
                         "thang_%": s["winrate"], "t": s["t"]})

    grp("huong", lambda i: [B.ev[i]["side"]])
    grp("tuan", lambda i: [_week(B.ts[i])])
    grp("huong_x_tuan", lambda i: [B.ev[i]["side"] + " " + _week(B.ts[i])])
    grp("trigger", lambda i: B.ev[i]["trig"].split(","))
    grp("gio_VN", lambda i: [f"{int(B.hour[i]) // 2 * 2:02d}–{int(B.hour[i]) // 2 * 2 + 2:02d}h"])
    grp("diem", lambda i: [f"{int(B.score[i] * 2) / 2:.1f}"])
    grp("luat_khop", lambda i: [r for r in B.ev[i]["rules"].split(",") if r] or ["(không khớp luật nào)"])
    grp("coin", lambda i: [B.ev[i]["sym"].split("/")[0]])
    for ex in EXITS:
        s = B.stats(idx, ex)
        rows.append({"nhom": "cach_thoat", "gia_tri": ex, "n": s["n"], "ky_vong_R": s["exp_r"], "tong_R": s["sum_r"],
                     "thang_%": s["winrate"], "t": s["t"]})
    _csv(os.path.join(a.out, "phan_tich_mac_dinh.csv"), rows)

    # ---- 3e. toàn bộ tín hiệu ứng viên (để anh tự lọc trên Excel / Google Sheets)
    with gzip.open(os.path.join(a.out, "tin_hieu_ung_vien.csv.gz"), "wt", newline="") as fh:
        cols = ["time_vn", "sym", "side", "score", "trig", "hour", "adx", "atr_pct", "vol_ratio", "ext_atr", "chase",
                "btc_v", "rsi_m", "wick", "sl_atr", "rules"] + ["R_" + x for x in EXITS]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for e in events:
            w.writerow({**{c: (round(v, 4) if isinstance(v, float) else v) for c, v in e.items()},
                        "time_vn": time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["ts"] + VN))})
    print(json.dumps({k: summary[k] for k in ("oos_default_portfolio", "oos_walkforward_portfolio",
                                              "hindsight_portfolio_same_period")}, ensure_ascii=False, indent=1))


def _week(t):
    """Ngày thứ Hai đầu tuần (giờ VN) – 05/01/1970 là thứ Hai."""
    v = t + VN
    return time.strftime("%Y-%m-%d", time.gmtime(v - (v - 4 * 86400) % (7 * 86400)))


def _d(t):
    return time.strftime("%d/%m", time.gmtime(t + VN))


def _trows(trades):
    return [{"vao_vn": time.strftime("%Y-%m-%d %H:%M", time.gmtime(t + VN)), "coin": s.split("/")[0], "huong": side,
             "diem": sc, "R": R, "ra_vn": time.strftime("%Y-%m-%d %H:%M", time.gmtime(x + VN))}
            for t, s, side, sc, R, x in trades]


def _csv(path, rows):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:          # utf-8-sig: Excel đọc đúng tiếng Việt
        if not rows:
            return
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--days", type=int, default=90)
    f.add_argument("--coins", type=int, default=40)
    f.add_argument("--data", default=os.path.join(ROOT, "tools", "wf_data"))
    f.add_argument("--force", action="store_true")
    e = sub.add_parser("events")
    e.add_argument("--data", default=os.path.join(ROOT, "tools", "wf_data"))
    e.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 0))
    o = sub.add_parser("optimize")
    o.add_argument("--data", default=os.path.join(ROOT, "tools", "wf_data"))
    o.add_argument("--out", default=os.path.join(ROOT, "tools", "wf_out"))
    o.add_argument("--train", type=int, default=30, help="số ngày huấn luyện mỗi lượt")
    o.add_argument("--test", type=int, default=10, help="số ngày kiểm tra ngoài mẫu mỗi lượt")
    o.add_argument("--samples", type=int, default=3000, help="số bộ tham số thử")
    o.add_argument("--min-n", dest="min_n", type=int, default=40, help="số tín hiệu tối thiểu trên đoạn huấn luyện")
    o.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    {"fetch": cmd_fetch, "events": cmd_events, "optimize": cmd_optimize}[a.cmd](a)


if __name__ == "__main__":
    main()
