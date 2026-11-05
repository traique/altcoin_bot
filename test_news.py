"""Kiểm tra module tin tức (v4.0, không AI) với dữ liệu mẫu offline: đọc RSS/Atom, nhận diện coin, chấm điểm từ điển,
gán sự kiện, tổng hợp theo coin (độ mới, co về 0), tâm lý thị trường, sự kiện bất lợi cho lệnh đang mở, lưu/nạp DB,
thông báo sàn, lọc hợp đồng không phải crypto, tổng kết lệnh theo quy tắc."""
import os, shutil, time
os.environ.update(MODE="paper", DATA_DIR="/tmp/okx-news-test", DATABASE_URL="", NEWS_ENABLED="true")
shutil.rmtree("/tmp/okx-news-test", ignore_errors=True)
from bot.config import cfg
from bot import news as N
from bot.storage import Store

U = {"SOL", "XRP", "ZEC", "NEAR", "POL", "AAVE", "SUI", "CETUS", "SPELL", "DORA", "ICX", "PTB", "MITO", "UNI", "ONE",
     "TRUMP", "ARB", "DOGE"}

# 1) đọc RSS 2.0 + Atom, làm sạch HTML / câu quảng cáo, giờ đăng
RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Feed</title>
<item><title><![CDATA[Solana (SOL) soars 12% as ETF inflows hit record]]></title><link>https://x.test/a</link>
<pubDate>Thu, 05 Nov 2026 08:00:00 +0000</pubDate>
<description><![CDATA[<p>Big <b>rally</b> &amp; more.</p> The post Solana soars appeared first on X.]]></description></item>
<item><title>No date here</title><link>https://x.test/b</link></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>A</title>
<entry><title>Cetus Protocol hacked for $223M</title><link href="https://y.test/c"/><updated>2026-11-05T07:30:00Z</updated>
<summary>Attackers drained pools.</summary></entry></feed>"""
items = N.parse_feed(RSS, "R")
assert len(items) == 2 and items[0]["title"].startswith("Solana (SOL) soars") and items[0]["url"] == "https://x.test/a"
assert items[0]["desc"] == "Big rally & more.", items[0]["desc"]
assert items[0]["ts"] == N.parse_time("Thu, 05 Nov 2026 08:00:00 +0000") and items[1]["ts"] is None
at = N.parse_feed(ATOM, "A")
assert at[0]["url"] == "https://y.test/c" and abs(at[0]["ts"] - N.parse_time("2026-11-05T07:30:00+00:00")) < 1
assert N.parse_time("2026-11-05 07:30:00") == N.parse_time("2026-11-05T07:30:00Z")   # không múi giờ → UTC
print("✓ đọc RSS/Atom, làm sạch HTML, giờ đăng")

# 2) nhận diện coin
dc = lambda t, strict=True: N.detect_coins(t, U, strict=strict)
assert dc("Solana (SOL), Near Protocol (NEAR) and Zcash (ZEC) price analysis") == {"SOL", "NEAR", "ZEC"}
assert dc("XRP jumps while $doge lags") == {"XRP", "DOGE"}
assert dc("Harmony ONE network update") == set()            # ONE trùng từ thông dụng → cần $ONE / (ONE)
assert dc("Harmony (ONE) network update") == {"ONE"}
assert dc("Polygon hard fork announced") == {"POL"} and dc("SEC approves ETF") == set()
assert N.detect_coins("Solana and $ABC", set()) == {"SOL", "ABC"}   # chưa biết danh sách coin → chỉ tên riêng / $MÃ
assert dc("TRUMP token rallies") == set() and dc("Official Trump (TRUMP) drops") == {"TRUMP"}
print("✓ nhận diện coin: mã, $mã, (mã), tên riêng, từ trùng nghĩa")

# 3) chấm điểm từ điển + phủ định
s_pos, _ = N.score_article("Solana soars to all-time high as inflows surge")
s_neg, _ = N.score_article("Protocol hacked, $50M drained in exploit")
s_negated, _ = N.score_article("Uniswap not hacked, team denies exploit rumors")
s_flat, _ = N.score_article("Ripple executive speaks at conference")
assert s_pos > 0.7 and s_neg < -0.8 and s_negated > 0 and s_flat == 0, (s_pos, s_neg, s_negated, s_flat)
assert N.score_article("Official Trump (TRUMP) Drops to a 3-Month Low")[0] < -0.5
print(f"✓ chấm điểm: tốt {s_pos:+.2f}, hack {s_neg:+.2f}, phủ định {s_negated:+.2f}, trung tính {s_flat:+.2f}")

# 4) sự kiện: chỉ gán cho coin đứng gần từ khoá, không gán khi bị phủ định / coin là "tang vật"
ec = lambda t: N.event_coins(t, dc(t), N.detect_events(t))
assert ec("Binance hackers move 81% of stolen Solana") == {}
assert ec("Aave and Lido lose $1.7B in massive DeFi capital drop after the Binance hack") == {}
assert ec("Hackers drain $8M from Abracadabra (SPELL)") == {"SPELL": ["hack"]}
assert ec("Uniswap not hacked, team denies exploit rumors") == {}
assert ec("Cetus Protocol hacked for $223M")["CETUS"] == ["hack"]
assert N.event_coins("OKX to delist DORA, ICX and ELF spot trading pairs", {"DORA", "ICX"}, ["delist"], structured=True) \
    == {"DORA": ["delist"], "ICX": ["delist"]}
assert N._announcement_tickers("Binance Futures Will Delist PTBUSDT and MITOUSDT USDⓈ-M Perpetual Contracts") == {"PTB", "MITO"}
assert N._announcement_tickers("OKX will launch GRVT/USD for spot trading") == {"GRVT"}
assert N.detect_events("Binance Will List Predict (PREDICT)") == ["listing"]
assert "listing" not in N.detect_events("OKX to delist ABC") and N.detect_events("OKX to delist ABC") == ["delist"]
print("✓ sự kiện: gán đúng coin, bỏ 'stolen Solana' / 'not hacked', đọc mã trong thông báo sàn")

# 5) kho tin: tổng hợp theo coin (độ mới, co về 0), sự kiện còn hiệu lực, thị trường, lưu/nạp DB
st = Store()
hub = N.NewsHub(st)
hub.set_universe(U)
now = time.time()
H = 3600
hub.ingest([
    {"src": "A", "kind": "news", "title": "Solana (SOL) soars 12% as ETF inflows hit record", "desc": "", "url": "u1", "ts": now - 0.5 * H},
    {"src": "B", "kind": "news", "title": "Solana rallies after major partnership", "desc": "", "url": "u2", "ts": now - 2 * H},
    {"src": "C", "kind": "news", "title": "SOL price slips", "desc": "", "url": "u3", "ts": now - 30 * H},   # ngoài 24h
    {"src": "A", "kind": "news", "title": "Hackers drain $8M from Abracadabra (SPELL)", "desc": "", "url": "u4", "ts": now - 1 * H},
    {"src": "B", "kind": "news", "title": "Bitcoin crashes as liquidations surge", "desc": "", "url": "u5", "ts": now - 1 * H},
    {"src": "OKX", "kind": "ann", "title": "OKX to delist DORA and ICX spot trading pairs", "desc": "", "url": "u6",
     "ts": now - 100 * H, "ann_type": "announcements-delistings"},
    {"src": "B", "kind": "news", "title": "Old story", "desc": "", "url": "u7", "ts": now - 60 * H},          # quá cũ → bỏ
], now=now)
assert len(hub.articles) == 6, len(hub.articles)
assert hub.ingest([{"src": "A", "kind": "news", "title": "dup", "url": "u1", "ts": now}], now=now) == 0   # trùng id
sol = hub.coin("SOL", now)
assert sol["news_n"] == 2 and 0.3 < sol["news_bias"] < 1 and sol["news_head"].startswith("[A] Solana (SOL) soars"), sol
assert hub.coin("SPELL", now)["news_events"] == ["hack"] and hub.coin("SPELL", now)["news_bias"] < 0
assert hub.coin("DORA", now)["news_events"] == ["delist"]                 # thông báo sàn 100h trước: còn hiệu lực 7 ngày
assert hub.coin("DORA", now + 80 * H)["news_events"] == []                  # hết hạn sau 168h
assert hub.coin("XRP", now) == {"news_bias": 0.0, "news_n": 0, "news_events": []}
one = N.NewsHub(None); one.set_universe(U)
one.ingest([{"src": "A", "kind": "news", "title": "Solana soars", "url": "z", "ts": now}], now=now)
assert one.coin("SOL", now)["news_bias"] <= 0.5 * 0.8, one.coin("SOL", now)  # 1 bài lẻ bị co về 0 (NEWS_SHRINK)
m = hub.market(now)
assert m["mkt_news_n"] == 4 and "fng" not in m                              # thông báo sàn không tính vào tâm lý chung
hub.fng = {"value": 22, "cls": "Extreme Fear", "ts": now}
assert hub.market(now)["fng"] == 22 and "F&G 22" in N.describe(hub.market(now))
hub.last_refresh = now
hub._save()
hub2 = N.NewsHub(st); hub2.set_universe(U)
assert hub2.coin("SOL", now) == sol and hub2.fng["value"] == 22 and hub2.last_refresh == now
hot = hub.hot(now=now)
assert hot[0][0] == "SOL" and hot[0][1] == 2
assert hub.public()["headlines"][0]["title"]
print(f"✓ kho tin: SOL {sol['news_bias']:+.2f} ({sol['news_n']} bài), SPELL hack, DORA huỷ niêm yết 7 ngày, "
      f"thị trường {m['mkt_news']:+.2f}, lưu/nạp DB")

# 6) sự kiện bất lợi cho lệnh đang mở: chỉ tin bot biết SAU lúc vào lệnh, đăng không quá sớm trước lúc vào
opened = now - 600
h3 = N.NewsHub(None); h3.set_universe(U)
h3.ingest([{"src": "A", "kind": "news", "title": "Cetus Protocol hacked for $223M", "url": "h", "ts": now - 60}], now=now)
assert h3.adverse_events("CETUS", "long", opened, ["hack"])[0][0] == "hack"
assert h3.adverse_events("CETUS", "short", opened, ["hack", "delist", "listing"]) == []    # hack không hại lệnh short
assert h3.adverse_events("CETUS", "long", opened, []) == []                                 # NEWS_EXIT_EVENTS trống = tắt
h4 = N.NewsHub(None); h4.set_universe(U)                                                      # khởi động lại, kho trống
h4.ingest([{"src": "A", "kind": "news", "title": "Cetus Protocol hacked", "url": "h", "ts": now - 2 * 86400}], now=now)
assert h4.adverse_events("CETUS", "long", now - 86400, ["hack"]) == []                       # tin cũ không đóng lệnh
h4.ingest([{"src": "A", "kind": "news", "title": "Cetus exploit: attackers drain more", "url": "h2", "ts": now - 120}], now=now)
assert len(h4.adverse_events("CETUS", "long", now - 300, ["hack"])) == 1                     # đăng 2 phút trước, biết sau khi vào
print("✓ đóng lệnh theo tin: chỉ tin mới, đúng hướng bất lợi, bỏ qua tin cũ sau khi khởi động lại")

# 7) lọc hợp đồng không phải crypto (OKX niêm yết cổ phiếu / hàng hoá dạng USDT-SWAP)
from bot.exchange import OKX
crypto = {"swap": True, "info": {"instCategory": "1", "ruleType": "normal", "expTime": ""}}
assert OKX.is_crypto(crypto) and OKX.is_crypto({"swap": True, "info": {}})                  # thiếu trường → coi là crypto
assert not OKX.is_crypto({"swap": True, "info": {"instCategory": "3", "ruleType": "normal"}})   # cổ phiếu
assert not OKX.is_crypto({"swap": True, "info": {"instCategory": "4"}})                          # hàng hoá
assert not OKX.is_crypto({"swap": True, "info": {"instCategory": "1", "ruleType": "pre_market"}})
assert not OKX.is_crypto({"swap": True, "info": {"instCategory": "1", "expTime": "1793000000000"}})  # có lịch gỡ
print("✓ chỉ quét hợp đồng crypto thường (loại cổ phiếu, hàng hoá, tiền niêm yết, sắp gỡ)")

# 8) tổng kết lệnh theo quy tắc (thay AI)
from bot.review import review_trade
base = dict(symbol="X/USDT:USDT", side="long", entry=100.0, sl=98.0, sl0=98.0, tp=110.0, atr=1.0, notional=100.0,
            notional0=100.0, opened_at=time.time() - 3600, tp1_done=0, news=0.5)
risk_usdt = 100.0 * 2 / 100
r1 = review_trade({**base, "peak": 100.2}, 98.0, -risk_usdt, -20, "Chạm SL")
assert r1["verdict"] == "SAI HƯỚNG NGAY" and "ĐIỂM VÀO" in r1["lesson"] and "tin_ủng_hộ" in r1["tags"], r1
r2 = review_trade({**base, "peak": 103.0}, 98.0, -risk_usdt, -20, "Chạm SL", news_now=-0.4)
assert r2["verdict"] == "THUA SAU KHI ĐÃ LỜI" and "đổi chiều" in r2["lesson"] and "tin_đổi_chiều" in r2["tags"], r2
r3 = review_trade({**base, "peak": 101.2}, 98.0, -risk_usdt, -20, "Chạm SL")
assert r3["verdict"] == "THUA TRONG KẾ HOẠCH" and r3["facts"]["sl_atr"] == 2.0
r4 = review_trade({**base, "peak": 112.0, "tp1_done": 1}, 104.0, 2 * risk_usdt, 40, "Trailing stop")
assert r4["verdict"] == "THẮNG – TRẢ LẠI NHIỀU" and r4["facts"]["mfe_r"] == 6.0 and r4["facts"]["r"] == 2.0, r4
r5 = review_trade({**base, "peak": 104.5, "tp1_done": 1}, 104.0, 2 * risk_usdt, 40, "Chạm TP")
assert r5["verdict"] == "THẮNG ĐÚNG KẾ HOẠCH" and r5["model"] == "quy-tắc"
print("✓ tổng kết lệnh theo quy tắc: sai hướng / thua sau khi lời / thua trong kế hoạch / thắng trả lại / thắng")
print("TẤT CẢ OK")
