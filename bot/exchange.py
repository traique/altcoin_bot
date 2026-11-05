"""Kết nối OKX qua ccxt – dữ liệu thị trường (public) + giao dịch (private)."""
import logging
import os
import time
import ccxt
from .config import cfg

log = logging.getLogger("exchange")


class OKX:
    def __init__(self):
        params = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if cfg.OKX_API_KEY:
            params.update(apiKey=cfg.OKX_API_KEY, secret=cfg.OKX_API_SECRET, password=cfg.OKX_PASSPHRASE)
        self.ex = ccxt.okx(params)
        if os.getenv("HTTPS_PROXY") or os.getenv("REQUESTS_CA_BUNDLE"):
            # tôn trọng proxy / CA bundle của hệ thống (ccxt mặc định bỏ qua)
            self.ex.session.trust_env = True
        if cfg.OKX_DEMO:
            self.ex.set_sandbox_mode(True)
        self._markets = None
        self._markets_ts = 0

    # ------------------------------------------------------------ public
    def markets(self, force=False):
        if force or self._markets is None or time.time() - self._markets_ts > 3600:
            self._markets = self.ex.load_markets(True)
            self._markets_ts = time.time()
        return self._markets

    def market(self, symbol):
        return self.markets()[symbol]

    @staticmethod
    def is_crypto(m):
        """Hợp đồng crypto thường. OKX còn niêm yết cổ phiếu / hàng hoá token hoá dạng USDT-SWAP (instCategory 3 = cổ phiếu,
        4 = hàng hoá) và hợp đồng tiền niêm yết (ruleType pre_market) – không phải altcoin: giờ giao dịch, khoảng trống giá,
        tách cổ phiếu làm chỉ báo sai. 05/11/2026: 236/525 hợp đồng USDT-SWAP là loại này, 15/50 cặp volume lớn nhất.
        Hợp đồng đã có lịch gỡ (expTime) cũng loại – sắp bị huỷ niêm yết."""
        info = m.get("info") or {}
        if str(info.get("instCategory") or "1") != "1":
            return False
        if str(info.get("ruleType") or "normal") != "normal":
            return False
        if m.get("swap") and str(info.get("expTime") or "").strip():
            return False
        return True

    def crypto_bases(self):
        """Mã gốc của mọi hợp đồng USDT-SWAP crypto đang giao dịch (để module tin tức nhận diện coin)."""
        return {m["base"] for m in self.markets().values()
                if m.get("swap") and m.get("quote") == "USDT" and m.get("active", True)
                and (not cfg.CRYPTO_ONLY or self.is_crypto(m))}

    def top_altcoins(self, n=25):
        """Lấy n cặp USDT-SWAP crypto có volume 24h (USD) cao nhất, loại BTC/ETH/stable và cổ phiếu/hàng hoá token hoá."""
        mk = self.markets()
        tickers = None
        for attempt in range(3):
            try:
                tickers = self.ex.fetch_tickers(params={"instType": "SWAP"})
                break
            except Exception as e:                      # mạng chập chờn: thử lại, rồi dùng danh sách lần trước
                log.warning("OKX tickers lỗi mạng (lần %d/3): %s", attempt + 1, str(e)[:120])
                time.sleep(2 * (attempt + 1))
        if tickers is None:
            if getattr(self, "_top_cache", None):
                log.warning("Dùng tạm danh sách coin của lượt quét trước")
                return self._top_cache[:n]
            raise RuntimeError("không lấy được danh sách coin từ OKX (mạng)")
        rows = []
        for sym, t in tickers.items():
            m = mk.get(sym)
            if not m or not m.get("swap") or m.get("quote") != "USDT" or not m.get("active", True):
                continue
            if m["base"].upper() in cfg.EXCLUDE or (cfg.CRYPTO_ONLY and not self.is_crypto(m)):
                continue
            info = t.get("info", {})
            try:
                vol_usd = float(info.get("volCcy24h", 0)) * float(t.get("last") or 0)
            except (TypeError, ValueError):
                vol_usd = 0
            if not vol_usd and t.get("quoteVolume"):
                vol_usd = float(t["quoteVolume"])
            if vol_usd <= 0:
                continue
            rows.append((sym, vol_usd, t.get("percentage") or 0))
        rows.sort(key=lambda r: r[1], reverse=True)
        self._top_cache = rows
        return rows[:n]

    def ohlcv(self, symbol, timeframe, limit=200):
        return self.ex.fetch_ohlcv(symbol, timeframe, limit=limit)

    def price(self, symbol):
        t = self.ex.fetch_ticker(symbol)
        return float(t["last"])

    def prices(self, symbols):
        if not symbols:
            return {}
        t = self.ex.fetch_tickers(symbols)
        return {s: float(v["last"]) for s, v in t.items() if v.get("last")}

    def funding_rate(self, symbol):
        try:
            fr = self.ex.fetch_funding_rate(symbol)
            return float(fr.get("fundingRate") or 0)
        except Exception:
            return 0.0

    # ------------------------------------------------------------ private
    def balance_usdt(self):
        b = self.ex.fetch_balance(params={"type": "swap"})
        usdt = b.get("USDT", {})
        return float(usdt.get("total") or 0), float(usdt.get("free") or 0)

    def set_leverage(self, symbol, lev):
        try:
            self.ex.set_leverage(lev, symbol, params={"mgnMode": "isolated"})
        except Exception as e:
            log.warning("set_leverage %s: %s", symbol, e)

    def contracts_for_notional(self, symbol, notional_usdt, price):
        """Đổi giá trị USDT -> số hợp đồng hợp lệ theo lot size của OKX."""
        m = self.market(symbol)
        ct_val = float(m.get("contractSize") or 1)
        lot = float(m["limits"]["amount"].get("min") or 1)
        step = float(m.get("precision", {}).get("amount") or lot)
        raw = notional_usdt / (price * ct_val)
        contracts = int(raw / step) * step
        if contracts < lot:
            return 0.0, lot * ct_val * price  # trả về min notional cần có
        return float(self.ex.amount_to_precision(symbol, contracts)), 0.0

    def open_position(self, symbol, side, contracts, sl, tp):
        """Mở lệnh market + SL/TP (OCO) trên OKX. side: long|short."""
        self.set_leverage(symbol, cfg.LEVERAGE)
        order_side = "buy" if side == "long" else "sell"
        params = {
            "tdMode": "isolated",
            "posSide": "net",
            "attachAlgoOrds": [{
                "tpTriggerPx": self.ex.price_to_precision(symbol, tp),
                "tpOrdPx": "-1",
                "slTriggerPx": self.ex.price_to_precision(symbol, sl),
                "slOrdPx": "-1",
            }],
        }
        order = self.ex.create_order(symbol, "market", order_side, contracts, params=params)
        time.sleep(1)
        try:
            o = self.ex.fetch_order(order["id"], symbol)
            fill = float(o.get("average") or o.get("price") or 0)
        except Exception:
            fill = 0.0
        return order["id"], fill

    def close_position(self, symbol, side, contracts):
        order_side = "sell" if side == "long" else "buy"
        params = {"tdMode": "isolated", "posSide": "net", "reduceOnly": True}
        o = self.ex.create_order(symbol, "market", order_side, contracts, params=params)
        # huỷ các lệnh algo (SL/TP) còn treo
        try:
            algos = self.ex.fetch_open_orders(symbol, params={"ordType": "conditional"})
            for a in algos:
                self.ex.cancel_order(a["id"], symbol, params={"stop": True})
        except Exception:
            pass
        return o

    def close_fill_price(self, symbol, since_ts, side):
        """Giá khớp trung bình của các lệnh ĐÓNG vị thế (sell với long, buy với short) kể từ since_ts.
        Dùng khi sàn tự khớp SL/TP để ghi PnL thật thay vì ước lượng. None nếu không lấy được."""
        try:
            rows = self.ex.fetch_my_trades(symbol, since=int(since_ts * 1000), limit=50)
        except Exception as e:
            log.warning("fetch_my_trades %s: %s", symbol, e)
            return None
        want = "sell" if side == "long" else "buy"
        fills = [(float(x.get("price") or 0), float(x.get("amount") or 0)) for x in rows if x.get("side") == want]
        fills = [(p, a) for p, a in fills if p > 0 and a > 0]
        qty = sum(a for _, a in fills)
        return sum(p * a for p, a in fills) / qty if qty else None

    def fetch_positions(self):
        try:
            pos = self.ex.fetch_positions(params={"instType": "SWAP"})
            return [p for p in pos if float(p.get("contracts") or 0) > 0]
        except Exception as e:
            log.warning("fetch_positions: %s", e)
            return []
