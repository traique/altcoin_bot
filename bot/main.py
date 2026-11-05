"""Vòng lặp chính của bot – v4.0: quyết định thuần kỹ thuật + tin tức, KHÔNG dùng AI."""
import logging
import os
import signal
import sys
import threading
import time
import datetime as dt
import traceback
from collections import Counter

from .config import cfg, ENV_FILE_INFO
from .version import VERSION, BUILD
from . import version as ver
from .channels import Switches
from .exchange import OKX
from .storage import Store
from .engine import PaperEngine, LiveEngine
from .risk import CircuitBreaker
from .strategy import diagnose
from .telegram import Telegram
from .notify import Notifier, Zoom
from .dashboard import start_dashboard
from .learner import Learner
from .news import NewsHub, EVENT_NAMES
from .review import review_trade
from .protections import Protections
from . import eventlog
from . import market as mkt
from . import news as newsmod
from . import strategy as strat

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")

SRC_SHORT = {"taken": "✅ vào lệnh", "unfilled": "⛔ sàn/ngân sách từ chối", "not_taken": "xếp sau",
             "blocked": "🚫 luật chặn", "below_score": "suýt đạt", "gate_near": "suýt qua cổng",
             "protected": "🛡️ lớp bảo vệ",
             # dữ liệu trước v4.0
             "ai_rejected": "AI từ chối (cũ)", "ai_weak": "AI chưa chắc (cũ)", "ai_override": "vượt AI (cũ)",
             "ai_error": "AI lỗi (cũ)", "not_sent": "không gửi AI (cũ)"}


def _ago(ts):
    if not ts:
        return "chưa"
    m = int((time.time() - float(ts)) / 60)
    return "vừa xong" if m < 1 else f"{m} phút trước" if m < 60 else f"{m // 60} giờ trước"


class Bot:
    def __init__(self):
        self.started_at = time.time()
        self.booting = True
        self.store = Store()
        self.switches = Switches(self.store)
        eventlog.install(self.store)   # mọi log INFO trở lên được ghi vào DB → xem trên web, tải về
        self.learner = None
        self.news = None
        self.is_leader = False
        self.instance = cfg.INSTANCE_NAME
        self.last_prices = {}
        start_dashboard(self)          # mở cổng web ngay lập tức để host không báo "not responding"
        self.okx = OKX()
        self.tg = Telegram(self)
        self.zoom = Zoom(self)
        self.notify = Notifier(self)
        self.notify.add(self.tg)
        self.notify.add(self.zoom)
        self.news = NewsHub(self.store)
        self._sync_universe()
        engine_cls = LiveEngine if cfg.MODE == "live" else PaperEngine
        self.engine = engine_cls(self.okx, self.store, self.notify.send)
        self.engine.on_close = self._on_trade_closed
        self.learner = Learner(self.store, self.okx, self.notify.send)
        self.protect = Protections(self.store, self.notify.send)
        self.shadow_seen = {}   # (symbol, side) -> ts: tránh ghi trùng tín hiệu bóng
        self.last_btc = {}
        self.last_market = {}
        self.breaker = CircuitBreaker(self.store)
        self.paused = bool(self.store.get("paused", False))
        self.last_scan = 0
        self.last_scan_summary = self.store.get("last_scan")
        self.cooldown = {}   # symbol -> time cho phép vào lại
        self._news_exit_done = set()
        self.start_equity = self.store.get("start_equity")
        if self.start_equity is None:
            self.start_equity = self.engine.equity()
            self.store.set("start_equity", self.start_equity)
            self.store.set("peak_equity", self.start_equity)
        self.booting = False

    def _sync_universe(self):
        """Danh sách mã có hợp đồng USDT-SWAP trên OKX → module tin tức nhận diện coin trong bài báo."""
        try:
            self.news.set_universe(self.okx.crypto_bases())
        except Exception as e:
            log.warning("Tin tức: chưa lấy được danh sách coin OKX (%s)", str(e)[:120])

    # ------------------------------------------------------------ tổng kết lệnh (theo quy tắc, không AI)
    def _on_trade_closed(self, t, exit_, pnl, pnl_pct, reason):
        if not cfg.TRADE_REVIEW:
            return
        try:
            now = None
            if self.news and self.news.enabled:
                ctx = self.news.coin(t["symbol"].split("/")[0])
                if ctx.get("news_n"):
                    now = strat.news_align(t["side"], ctx)
            rev = review_trade(t, exit_, pnl, pnl_pct, reason, news_now=now)
            self.store.add_review(t, pnl, rev)
            self.notify.send(f"🧾 TỔNG KẾT {t['side'].upper()} {t['symbol']} [{rev['verdict']}]\n{rev['lesson']}\n#"
                             + " #".join(rev.get("tags") or []))
        except Exception as e:
            log.warning("Tổng kết lệnh lỗi: %s", e)

    # ------------------------------------------------------------ text cho Telegram / Zoom
    def status_text(self):
        eq = self.engine.equity(self.last_prices)
        s = self.store.stats()
        opens = self.store.open_trades()
        peers = ", ".join(f"{i['instance']}={i['role']}" + ("" if time.time() - i['ts'] < cfg.LEADER_TTL else "(mất liên lạc)")
                          for i in self.store.instances())
        lines = [f"📊 v{VERSION} ({ver.build()}) · {cfg.MODE.upper()} | {'TẠM DỪNG' if self.paused else 'ĐANG CHẠY'} | leader: {self.store.lock_owner('trader') or '-'}",
                 f"Instances: {peers}",
                 f"Vốn: {eq:.4f} USDT (bắt đầu {self.start_equity:.2f}, {100*(eq-self.start_equity)/self.start_equity:+.1f}%)",
                 f"Lệnh: {s['trades']} | Win {s['winrate']}% | PF {s['profit_factor']}",
                 "📰 " + ((newsmod.describe(self.news.market()) or "chưa có tin") + f" · cập nhật {_ago(self.news.last_refresh)}"
                         if self.news and self.news.enabled else "Tin tức: tắt")]
        ls = self.last_scan_summary
        if getattr(self, "last_btc", None):
            lines.append("₿ " + mkt.describe(self.last_btc))
        if ls:
            lines.append(f"Quét cuối {dt.datetime.fromtimestamp(ls['ts']).strftime('%H:%M')}: {ls['scanned']} coin, {ls['passed']} đạt | "
                         + ", ".join(f"{k} {v}" for k, v in list(ls['reasons'].items())[:4]))
        pr = self.protect.public() if getattr(self, "protect", None) else {}
        for side, lk in (pr.get("sides") or {}).items():
            lines.append(f"🛡️ Khoá {side.upper()} đến {dt.datetime.fromtimestamp(lk['until']).strftime('%H:%M')}: {lk['why']}")
        if pr.get("pairs"):
            lines.append("🛡️ Coin đang nghỉ: " + ", ".join(f"{s.split('/')[0]} ({v['why']})" for s, v in pr["pairs"].items()))
        for t in opens:
            p = self.last_prices.get(t["symbol"])
            upnl = self.engine._pnl(t["side"], t["entry"], p, t["notional"])[0] if p else 0
            lines.append(f"• {t['side'].upper()} {t['symbol']} @ {t['entry']:.6g} SL {t['sl']:.6g} TP {t['tp']:.6g} uPnL {upnl:+.4f}")
        return "\n".join(lines)

    def trades_text(self):
        rows = [t for t in self.store.trades(10) if t["status"] == "closed"]
        if not rows:
            return "Chưa có lệnh nào đóng."
        return "\n".join(f"{'✅' if t['pnl']>0 else '❌'} {t['side'].upper()} {t['symbol']} {t['pnl']:+.4f} ({t['pnl_pct']:+.0f}%) – {t['reason_close']}" for t in rows)

    def signals_text(self):
        rows = self.store.recent_signals(10)
        if not rows:
            return "Chưa có tín hiệu."
        out = []
        for r in rows:
            res = ""
            if r.get("outcome") and r["outcome"] not in ("PENDING", "NODATA") and r.get("outcome_r") is not None:
                res = f" | kết quả {r['outcome']} {r['outcome_r']:+.2f}R"
            out.append(f"{dt.datetime.fromtimestamp(r['ts']).strftime('%d/%m %H:%M')} {r['symbol'].split('/')[0]} {r['side']} "
                       f"điểm {r['score']} → {SRC_SHORT.get(r.get('source'), r.get('source') or '-')}{res}")
        return "\n".join(out)

    def news_text(self):
        if not self.news or not self.news.enabled:
            return "Tin tức đang tắt (NEWS_ENABLED=false)."
        st = self.news.public()
        bad = [k for k, v in (st.get("status") or {}).items() if not v.get("ok")]
        lines = [f"📰 TIN TỨC | {newsmod.describe(st['market']) or 'chưa có dữ liệu'}",
                 f"Kho {st['n']} bài · cập nhật {_ago(st['ts'])} · nguồn lỗi: {', '.join(bad) or 'không'}"]
        if st.get("hot"):
            lines.append("Coin được nhắc nhiều (24h): " + ", ".join(f"{c} {k} bài ({b:+.2f})" for c, k, b in st["hot"][:8]))
        for h in st.get("headlines", [])[:8]:
            ev = f" [{', '.join(EVENT_NAMES.get(e, e) for e in h['events'])}]" if h.get("events") else ""
            coins = f" ({', '.join(h['coins'])})" if h.get("coins") else ""
            lines.append(f"• {h['score']:+.2f} [{h['src']}] {h['title'][:100]}{coins}{ev}")
        return "\n".join(lines)

    def reviews_text(self):
        rows = self.store.reviews(8)
        if not rows:
            return "Chưa có tổng kết nào."
        return "\n\n".join(f"{'✅' if r['pnl']>0 else '❌'} {r['side'].upper()} {r['symbol']} [{r['verdict']}]\n{r['lesson']}" for r in rows)

    HELP = ("Lệnh (Telegram gõ /lenh, Zoom gõ /okxbot lenh):\n"
            "status – vốn, lệnh mở, quét gần nhất\ntrades – 10 lệnh gần nhất\nsignals – tín hiệu & kết quả\n"
            "news (tintuc) – tâm lý thị trường, coin được nhắc nhiều, tin mới\nlearn – trạng thái tự học\n"
            "apply – duyệt đề xuất tự học\ntongket – tổng kết các lệnh gần nhất\nbtc – bối cảnh BTC\n"
            "pause / resume – tạm dừng / tiếp tục\nclose – đóng tất cả lệnh\n"
            "phienban – phiên bản & lịch sử cập nhật\nzoomtest – gửi thử thông báo Zoom\n"
            "zoompair <jid> / zoomxoa / zoomstatus – ghép đôi Zoom (chỉ trên Telegram)")

    def handle_command(self, text, source="Telegram"):
        """Xử lý lệnh chung cho mọi kênh. Trả về chuỗi trả lời."""
        cmd = (text.strip().split() or [""])[0].lower().lstrip("/").split("@")[0]
        if cmd == "status":
            return self.status_text()
        if cmd == "pause":
            self.paused = True
            self.store.set("paused", True)
            return f"⏸ Bot tạm dừng mở lệnh mới (lệnh đang mở vẫn được quản lý). – qua {source}"
        if cmd == "resume":
            self.paused = False
            self.store.set("paused", False)
            self.store.set("halted", False)
            return f"▶️ Bot tiếp tục giao dịch. – qua {source}"
        if cmd == "trades":
            return self.trades_text()
        if cmd == "close":
            return f"Đã đóng {self.close_all(f'Đóng thủ công qua {source}')} lệnh."
        if cmd == "signals":
            return self.signals_text()
        if cmd in ("news", "tintuc"):
            return self.news_text()
        if cmd == "ai":
            return "Từ v4.0 bot không dùng AI để quyết định – chỉ kỹ thuật + tin tức.\n\n" + self.news_text()
        if cmd == "learn":
            return self.learn_text()
        if cmd == "apply":
            n = self.learner.apply_pending()
            return f"Đã áp dụng {n} đề xuất tự học." if n else "Không có đề xuất nào đang chờ."
        if cmd in ("tongket", "reviews", "lessons"):
            return self.reviews_text()
        if cmd in ("zoompair", "zoomxoa", "zoomstatus"):
            if source == "Zoom":
                return "Lệnh ghép đôi Zoom chỉ dùng được từ Telegram."
            z = self.zoom
            if not z.chatbot_on:
                return "Chưa cấu hình Zoom chatbot (ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET / ZOOM_BOT_JID)."
            if cmd == "zoomstatus":
                p = z.pairing()
                return f"Zoom đang ghép đôi: {p.get('name') or ''} {p['jid']}" if p.get("jid") else "Chưa ghép đôi JID Zoom nào."
            if cmd == "zoomxoa":
                z.unpair()
                return "Đã gỡ ghép đôi Zoom."
            parts = text.strip().split(maxsplit=2)
            if len(parts) < 2:
                return "Cú pháp: /zoompair <jid> [tên]. JID lấy từ tin báo khi anh nhắn bot trên Zoom lần đầu."
            p = z.pair(parts[1], parts[2] if len(parts) > 2 else "")
            return f"✅ Đã ghép đôi Zoom: {p['jid']}. Từ giờ anh gõ lệnh và nhận thông báo trên Zoom."
        if cmd in ("phienban", "version"):
            return ver.text()
        if cmd == "zoomtest":
            ok, tried = self.zoom.test_send()
            return ("✅ Zoom nhận thông báo thử. " if ok else "❌ Zoom chưa nhận thông báo. ") + "Đã thử: " + "; ".join(tried)
        if cmd == "btc":
            return "₿ " + (mkt.describe(self.last_btc) or "Chưa có dữ liệu BTC (chờ lượt quét đầu).")
        return self.HELP

    def close_all(self, reason):
        n = 0
        for t in self.store.open_trades():
            try:
                self.engine.close(t, self.okx.price(t["symbol"]), reason)
                n += 1
            except Exception as e:
                log.error("close_all %s: %s", t["symbol"], e)
        return n

    def snapshot(self):
        if self.booting or self.learner is None:
            return {"mode": cfg.MODE, "paused": False, "halted": False, "instance": self.instance, "is_leader": False,
                    "leader": None, "instances": [], "shared_db": self.store.pg, "equity": 0, "start": 0,
                    "stats": self.store.stats(), "curve": [], "open": [], "trades": [], "signals": [],
                    "news": {"enabled": False}, "reviews": [], "tz": cfg.TIMEZONE, "ts": time.time(), "booting": True,
                    "learn": None, "last_scan": None, "version": VERSION, "build": BUILD}
        opens = self.store.open_trades()
        for t in opens:
            p = self.last_prices.get(t["symbol"])
            t["price"] = p
            t["upnl"] = self.engine._pnl(t["side"], t["entry"], p, t["notional"])[0] if p else None
        return {
            "mode": cfg.MODE, "paused": self.paused, "halted": bool(self.store.get("halted")),
            "instance": self.instance, "is_leader": self.is_leader, "leader": self.store.lock_owner("trader"),
            "instances": self.store.instances(), "shared_db": self.store.pg,
            "equity": self.engine.equity(self.last_prices), "start": self.start_equity,
            "stats": self.store.stats(), "curve": self.store.equity_curve(),
            "open": opens, "trades": self.store.trades(100), "signals": self.store.recent_signals(40),
            "news": self.news.public() if self.news else {"enabled": False},
            "protect": self.protect.public() if getattr(self, "protect", None) else {"enabled": False},
            "reviews": self.store.reviews(30), "tz": cfg.TIMEZONE, "ts": time.time(),
            "last_scan": self.last_scan_summary,
            "learn": self.learner.public_state() if self.learner else None,
            "btc": getattr(self, "last_btc", {}),
            "version": VERSION, "build": BUILD, "started": self.started_at, "ver": ver.info(),
            "switches": self.switches.all(),
        }

    # ------------------------------------------------------------ logic
    def _day_key(self):
        return dt.datetime.now().strftime("%Y-%m-%d")

    def _risk_ok(self, equity):
        day = self._day_key()
        if self.store.get("day_key") != day:
            self.store.set("day_key", day)
            self.store.set("day_start_equity", equity)
            self.store.set("halted", False)
            self._daily_report()
        peak = max(float(self.store.get("peak_equity") or equity), equity)
        self.store.set("peak_equity", peak)
        ok, why = self.breaker.check(equity, float(self.store.get("day_start_equity") or equity), peak)
        if not ok and not self.store.get("halted"):
            self.store.set("halted", True)
            self.notify.send(f"🛑 DỪNG GIAO DỊCH: {why}. Gõ /resume để chạy lại.")
        return ok and not self.store.get("halted")

    def _daily_report(self):
        since = time.time() - 86400
        rows = self.store.closed_trades_since(since)
        if not rows:
            return
        pnl = sum(r["pnl"] for r in rows)
        wins = sum(1 for r in rows if r["pnl"] > 0)
        self.notify.send(f"📅 BÁO CÁO NGÀY\nLệnh: {len(rows)} | Thắng: {wins} | PnL: {pnl:+.4f} USDT\n"
                         f"Vốn: {self.engine.equity(self.last_prices):.4f} USDT")

    def _add_context(self, sig, sym):
        """Gắn tin tức của coin (trong bộ nhớ, không gọi mạng) rồi – nếu còn khả năng đạt ngưỡng – dòng tiền
        (OI / long-short / funding: 4 request), cộng điểm và xét lại ngưỡng. Trả về lý do loại ('' nếu đạt)."""
        if self.news and self.news.enabled:
            sig.context.update(self.news.coin(sym.split("/")[0]))
        nd, _ = strat.news_adjust(sig)
        if sig.score + nd + 1.0 >= strat.min_score_for(sig):          # dòng tiền cộng tối đa +1.0
            sig.context.update(mkt.symbol_context(self.okx, sym))
        return strat.apply_context(sig)

    def scan(self):
        opens = self.store.open_trades()
        if len(opens) >= cfg.MAX_OPEN_POSITIONS:
            return
        open_syms = {t["symbol"] for t in opens}
        coins = self.okx.top_altcoins(cfg.TOP_N_COINS)
        btc = mkt.btc_context(self.okx)
        self.last_btc = btc
        self._sync_universe()
        market = dict(btc)
        if self.news and self.news.enabled:
            market.update(self.news.market())          # tâm lý tin tức toàn thị trường + Fear & Greed
        self.last_market = market
        log.info("Quét %d coin... %s%s", len(coins), mkt.describe(btc),
                 (" | " + newsmod.describe(market)) if self.news and self.news.enabled else "")
        candidates, reasons, near = [], Counter(), []
        side_locks = self.protect.refresh()                 # v4.1: lớp bảo vệ (khoá phía / coin)
        pair_locks = self.protect.pair_locks()
        for sym, vol, chg in coins:
            if sym in open_syms or self.cooldown.get(sym, 0) > time.time():
                continue
            try:
                if self.protect.too_new(self.okx.market(sym)):
                    reasons["mới niêm yết"] += 1
                    continue
                ltf = self.okx.ohlcv(sym, cfg.TIMEFRAME, 220)
                htf = self.okx.ohlcv(sym, cfg.HTF_TIMEFRAME, 120)
                sig, why, info = diagnose(sym, ltf, htf, funding=0.0, change24h=float(chg or 0), market=market)
                if sig is not None and why.startswith(strat.NEAR_PREFIX):
                    # v4.1: trượt đúng 1 cổng, sát ngưỡng → theo dõi bóng để bộ tự học biết có nên nới cổng
                    self._shadow(sig, "gate_near")
                    reasons[why[len(strat.NEAR_PREFIX):].split("(")[0].strip()] += 1
                    continue
                if sig is not None and (not why or why.startswith("điểm thấp")):
                    # qua cổng + có trigger → cộng điểm dòng tiền + tin tức TRƯỚC khi xét ngưỡng & xếp hạng
                    why = self._add_context(sig, sym)
                    info["score"] = sig.score
                if sig and not why:
                    blk = strat.blocked_by(sig)
                    if blk:
                        sig.rejected = f"luật chặn: {blk}"
                        reasons["luật chặn"] += 1
                        log.info("%s %s bị luật chặn: %s", sym, sig.side, blk)
                        self._shadow(sig, "blocked")
                        continue
                    pblk = self.protect.blocks(sig, side_locks, pair_locks)
                    if pblk:
                        sig.rejected = f"lớp bảo vệ: {pblk}"
                        reasons["lớp bảo vệ"] += 1
                        log.info("%s %s bị lớp bảo vệ chặn: %s", sym, sig.side, pblk)
                        self._shadow(sig, "protected")
                        continue
                    candidates.append(sig)
                else:
                    if sig is not None:   # suýt đạt (điểm thấp) → ghi lại để theo dõi kết quả bóng
                        self._shadow(sig, "below_score")
                    reasons[why.split("(")[0].strip()] += 1
                    if "trigger" in why or "điểm thấp" in why or "RR thấp" in why:
                        near.append(f"{sym.split('/')[0]} ({why[:30]})")
            except Exception as e:
                log.warning("phân tích %s lỗi: %s", sym, e)
        candidates.sort(key=lambda s: s.score, reverse=True)
        summary = ", ".join(f"{k} {v}" for k, v in reasons.most_common(6))
        log.info("Kết quả quét: %d đạt | loại vì: %s%s", len(candidates), summary,
                 (" | suýt đạt: " + ", ".join(near[:4])) if near else "")
        if candidates:
            log.info("Tín hiệu: %s", ", ".join(f"{s.symbol} {s.side} {s.score}" for s in candidates[:5]))
        self.last_scan_summary = {"ts": time.time(), "scanned": len(coins), "passed": len(candidates),
                                  "reasons": dict(reasons.most_common(8)), "near": near[:6],
                                  "top": [f"{s.symbol.split('/')[0]} {s.side} {s.score}" for s in candidates[:3]]}
        self.store.set("last_scan", self.last_scan_summary)
        try:
            self.store.add_scan(self.last_scan_summary)
        except Exception as e:
            log.debug("add_scan: %s", e)
        k = max(1, cfg.ENTRY_CANDIDATES)
        for sig in candidates[k:]:          # đạt nhưng xếp sau → không vào, vẫn theo dõi kết quả bóng
            self._shadow(sig, "not_taken")
        for i, sig in enumerate(candidates[:k]):
            dec = strat.decide(sig)
            if dec["decision"] == "SKIP":     # không xảy ra nếu các bước trên đúng – phòng hờ
                self._shadow(sig, "not_taken")
                continue
            log.info("Vào lệnh %s %s điểm %s | %s", sig.symbol, sig.side, sig.score, dec["reason"])
            t = self.engine.open(sig, dec)
            taken = t is not None
            self.store.log_signal(sig, dec, taken, source="taken" if taken else "unfilled")
            self.shadow_seen[(sig.symbol, sig.side)] = time.time()
            if taken:
                self.cooldown[sig.symbol] = time.time() + 7200
                for rest in candidates[i + 1:k]:
                    self._shadow(rest, "not_taken")
                break
            self.cooldown[sig.symbol] = time.time() + 1800     # sàn / ngân sách rủi ro từ chối → thử lại sau 30 phút

    def _shadow(self, sig, source):
        key = (sig.symbol, sig.side)
        if time.time() - self.shadow_seen.get(key, 0) < 3600:
            return
        self.shadow_seen[key] = time.time()
        if "oi_chg_1h" not in sig.context and "ls_ratio" not in sig.context:
            try:
                sig.context.update(mkt.symbol_context(self.okx, sig.symbol))
            except Exception:
                pass
        if "news_n" not in sig.context and self.news and self.news.enabled:
            sig.context.update(self.news.coin(sig.symbol.split("/")[0]))
        try:
            self.store.log_signal(sig, None, False, source=source)
        except Exception as e:
            log.debug("shadow log: %s", e)

    def _news_guard(self):
        """Lệnh đang mở gặp tin xấu MỚI (đăng sau lúc vào lệnh): long – huỷ niêm yết / hack; short – niêm yết sàn lớn
        → đóng ngay (NEWS_EXIT_EVENTS). Mỗi lệnh × sự kiện chỉ xử lý 1 lần."""
        if not cfg.NEWS_EXIT_EVENTS or not self.news or not self.news.enabled:
            return
        for t in self.store.open_trades():
            bad = self.news.adverse_events(t["symbol"].split("/")[0], t["side"], float(t["opened_at"]), cfg.NEWS_EXIT_EVENTS)
            if not bad:
                continue
            ev, _, title = bad[0]
            key = f"{t['id']}:{ev}"
            if key in self._news_exit_done:
                continue
            self._news_exit_done.add(key)
            try:
                price = self.okx.price(t["symbol"])
                log.warning("%s %s: tin %s mới – đóng lệnh. %s", t["side"].upper(), t["symbol"], EVENT_NAMES.get(ev, ev), title)
                self.engine.close(t, price, f"Tin xấu: {EVENT_NAMES.get(ev, ev)}")
                self.notify.send(f"📰 Đã đóng {t['side'].upper()} {t['symbol']} vì tin {EVENT_NAMES.get(ev, ev)}:\n{title}")
            except Exception as e:
                log.error("Đóng lệnh theo tin %s lỗi: %s", t["symbol"], e)

    def learn_text(self):
        st = self.learner.public_state()
        p, s = st["params"], st.get("stats") or {}
        lines = [f"🧬 TỰ HỌC | chế độ {st['mode']} | cần ≥{st['min_samples']} mẫu",
                 f"Ngưỡng điểm: {p['min_score']} (mặc định {p['min_score_default']}) | trọng số tin tức: {p['news_w']} "
                 f"(mặc định {p['news_w_default']})",
                 "Luật đang chặn: " + (", ".join(st['rules'][b] for b in p['blocks']) or "không"),
                 "Trọng số trigger: " + (", ".join(f"{st['trigger_names'].get(k,k)} {v}" for k, v in p['trigger_w'].items()) or "mặc định")]
        if s:
            t = s.get("tech", {})
            lines.append(f"Đã có kết quả {s['total']['n']} tín hiệu, đang chờ {s.get('pending', 0)} | tín hiệu kỹ thuật: kỳ vọng {t.get('exp_r', 0):+.2f}R, thắng {t.get('winrate', 0)}%")
            ne = s.get("news_effect") or {}
            if ne.get("n_aligned") or ne.get("n_against"):
                lines.append(f"Tin cùng chiều {ne.get('exp_aligned', 0):+.2f}R ({ne.get('n_aligned', 0)} mẫu) vs ngược chiều "
                             f"{ne.get('exp_against', 0):+.2f}R ({ne.get('n_against', 0)} mẫu), t = {ne.get('t', 0)}")
        pend = [r for r in st["log"] if r["status"] == "pending"]
        if pend:
            lines.append(f"⏳ {len(pend)} đề xuất chờ duyệt – gõ /apply để áp dụng tất cả")
        return "\n".join(lines)

    # ------------------------------------------------------------ nhiều instance
    def _keepalive(self):
        """Ping chéo để Render free không bị ngủ (và để biết máy kia còn sống)."""
        urls = [u for u in (cfg.SELF_URL, cfg.PEER_URL) if u]
        if not urls:
            return
        import requests
        while True:
            for u in urls:
                try:
                    requests.get(u.rstrip("/") + "/health", timeout=20)
                except Exception as e:
                    log.debug("keepalive %s: %s", u, e)
            time.sleep(cfg.KEEPALIVE_INTERVAL)

    def _elect(self):
        """Giành/gia hạn khoá leader. Trả về True nếu instance này được phép giao dịch."""
        was = self.is_leader
        self.is_leader = self.store.try_lock("trader", self.instance, cfg.LEADER_TTL)
        self.store.heartbeat(self.instance, "leader" if self.is_leader else "standby",
                             f"v{VERSION} b{ver.build()} paper={cfg.MODE=='paper'} host={os.uname().nodename}")
        if self.is_leader and not was:
            log.info("[%s] trở thành LEADER", self.instance)
            if self.learner:   # nạp lại tham số tự học mới nhất (có thể do instance khác vừa cập nhật)
                strat.LEARNED.update(self.store.get("learned") or {})
            self.notify.send(f"👑 {self.instance} tiếp quản vai trò giao dịch (chế độ {cfg.MODE.upper()}).")
        elif was and not self.is_leader:
            log.warning("[%s] mất khoá leader -> chuyển sang standby", self.instance)
        return self.is_leader

    def run(self):
        self.tg.start()
        self.news.start(is_leader=lambda: self.is_leader)
        threading.Thread(target=self._keepalive, daemon=True, name="keepalive").start()
        fi = ENV_FILE_INFO
        if fi.get("path"):
            log.info("Đã nạp %d biến từ file %s (bỏ qua %d dòng trống/chưa điền) – ưu tiên hơn biến trên panel",
                     fi["loaded"], fi["path"], fi["skipped"])
        if fi.get("error"):
            log.warning("File cấu hình lỗi, không nạp được: %s", fi["error"])
        L = strat.LEARNED
        from . import exits as _ex
        # giá trị THỰC đang dùng (tự học ghi đè mặc định)
        log.info("Thông số đang dùng: MIN_SCORE=%s MIN_ADX=%s HTF_MIN_ADX=%s MAX_EXT_ATR=%s BTC_GATE=%s%% CHASE_1H=%s%% "
                 "CLIMAX_VOL=%s LATE_ADX=%s(trừ %s) SL=%s–%sATR TP1_R=%s "
                 "RISK=%.1f%% (×%.2f–%.2f theo tin tức, trần tổng %.0f%%, tối đa %d lệnh) TOP_N=%s "
                 "TIN: %s, trọng số %s × ±%s điểm, làm mới %s phút, đóng lệnh khi tin [%s] | HỌC≥%s mẫu,t≥%s CHẶN=%s",
                 L.get("min_score") or cfg.MIN_SCORE, cfg.MIN_ADX, cfg.HTF_MIN_ADX,
                 cfg.MAX_EXT_ATR, cfg.BTC_GATE_CHG, cfg.CHASE_1H_PCT, cfg.CLIMAX_VOL, cfg.LATE_TREND_ADX, cfg.LATE_TREND_PENALTY,
                 cfg.ATR_SL_MULT, cfg.MAX_SL_ATR, _ex.current_tp1_r(), cfg.RISK_PER_TRADE * 100,
                 cfg.RISK_MIN_MULT, cfg.RISK_MAX_MULT, cfg.MAX_TOTAL_RISK * 100, cfg.MAX_OPEN_POSITIONS, cfg.TOP_N_COINS,
                 "bật" if cfg.NEWS_ENABLED else "TẮT", strat.news_weight(), cfg.NEWS_SCORE_MAX, cfg.NEWS_REFRESH_MIN,
                 ",".join(cfg.NEWS_EXIT_EVENTS) or "-", cfg.LEARN_MIN_SAMPLES, cfg.LEARN_MIN_T,
                 ",".join(sorted(strat.active_blocks())) or "-")
        log.info("Tự học đã đổi so với mặc định: %s",
                 ", ".join(f"{k}={v}" for k, v in L.items() if k != "schema" and v not in (None, [], {})) or "chưa có")
        log.info("Phiên bản %s · bản dựng %s · %s | Instance %s | storage %s | leader TTL %ss", VERSION, ver.build(),
                 ver.status_line(), self.instance, "Postgres" if self.store.pg else "SQLite", cfg.LEADER_TTL)
        last_eq_log = 0
        announced = False
        while True:
            try:
                if not self._elect():
                    time.sleep(cfg.MONITOR_INTERVAL)
                    continue
                if not announced:
                    announced = True
                    try:
                        cur = f"{VERSION} {ver.build()}"
                        msg = ver.update_notice(self.store.get("last_version") or "")
                        if msg:
                            self.notify.send(msg)
                        self.store.set("last_version", cur)
                    except Exception as e:
                        log.debug("update notice: %s", e)
                    self.notify.send(f"🚀 Bot v{VERSION} khởi động – chế độ {cfg.MODE.upper()} | vốn {self.engine.equity():.2f} USDT | x{cfg.LEVERAGE} | "
                                     f"rủi ro {cfg.RISK_PER_TRADE*100:.1f}%/lệnh (co giãn theo tin tức), tối đa {cfg.MAX_TOTAL_RISK*100:.0f}% tổng | "
                                     f"quyết định: kỹ thuật + tin tức (không AI)")
                self.paused = bool(self.store.get("paused", False))
                # 1. quản lý lệnh đang mở (SL/TP/trailing) + đóng lệnh khi có tin xấu mới
                self.engine.monitor()
                self._news_guard()
                opens = self.store.open_trades()
                if opens:
                    self.last_prices.update(self.okx.prices([t["symbol"] for t in opens]))
                equity = self.engine.equity(self.last_prices)
                self.store.set("last_equity", equity)
                if time.time() - last_eq_log > 300:
                    self.store.log_equity(equity)
                    last_eq_log = time.time()
                # 2. kiểm tra rủi ro + quét tín hiệu
                if self._risk_ok(equity) and not self.paused and time.time() - self.last_scan > cfg.SCAN_INTERVAL:
                    self.last_scan = time.time()
                    self.scan()
                # 3. tự học: cập nhật kết quả bóng, điều chỉnh tham số, báo cáo ngày
                self.learner.tick()
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                if _is_network_error(e):
                    log.warning("Lỗi mạng tạm thời (%s) – thử lại ở vòng sau", str(e)[:160])
                else:
                    log.error("Lỗi vòng lặp:\n%s", traceback.format_exc())
                time.sleep(10)
            try:
                time.sleep(cfg.MONITOR_INTERVAL)
            except (KeyboardInterrupt, SystemExit):
                break
        # dọn dẹp: bỏ qua tín hiệu dừng lặp lại để không in traceback khi Botkeep restart
        try:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except Exception:
            pass
        try:
            if self.is_leader:
                self.store.release_lock("trader", self.instance)
            log.info("Bot dừng (instance %s).", self.instance)
        except BaseException:
            pass


def _is_network_error(e):
    try:
        import ccxt
        if isinstance(e, (ccxt.NetworkError,)):
            return True
    except Exception:
        pass
    import requests
    return isinstance(e, (requests.RequestException, ConnectionError, TimeoutError)) or "mạng" in str(e)


def main():
    if cfg.MODE == "live" and not cfg.OKX_API_KEY:
        log.error("MODE=live nhưng thiếu OKX_API_KEY")
        sys.exit(1)
    if cfg.MODE == "live" and os.getenv("I_UNDERSTAND_THE_RISK", "").lower() != "yes":
        log.error("MODE=live cần đặt I_UNDERSTAND_THE_RISK=yes trong .env để xác nhận")
        sys.exit(1)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    Bot().run()


if __name__ == "__main__":
    main()
