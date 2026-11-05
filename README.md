# OKX Altcoin Futures Bot – Kỹ thuật + Tin tức (không AI)

Bot giao dịch hợp đồng tương lai (USDT-SWAP) altcoin trên OKX, đánh cả Long lẫn Short. **Từ v4.0 bot không dùng AI để quyết định mua bán**: mọi quyết định đến từ phân tích kỹ thuật, dòng tiền (OI, funding, long/short) và **phân tích tin tức theo quy tắc** (từ điển + luật sự kiện, không LLM). Bộ tự học đo kết quả thật của mọi tín hiệu và **tự nâng cấp** tham số (luật chặn, trọng số trigger, ngưỡng điểm, cách thoát, TP1, trọng số tin tức) có kiểm định thống kê. Có chế độ **chạy ảo (paper)**, Telegram, Zoom, dashboard web. Chạy được trên **Botkeep.cloud** với runtime Python (không cần Docker), không cần API key nào ngoài Telegram (và OKX khi chạy thật).

> ⚠️ Future đòn bẩy với vốn nhỏ rủi ro rất cao, có thể mất toàn bộ vốn. Đây là công cụ, không phải lời khuyên đầu tư. Chỉ bật `live` sau khi đã xem kết quả 2 tuần chạy ảo.

## 1. Cách bot ra quyết định

**Bước 1 – Quét**: mỗi 5 phút lấy top 50 cặp USDT-SWAP **crypto** có volume 24h lớn nhất trên OKX. v4.0 lọc theo phân loại của chính OKX (`instCategory=1`, `ruleType=normal`, chưa có lịch gỡ) – OKX đang niêm yết hơn 200 hợp đồng cổ phiếu/hàng hoá token hoá dạng USDT-SWAP, bản cũ quét nhầm 15/50 cặp là cổ phiếu, dầu. Loại thêm BTC, ETH, stablecoin (`EXCLUDE`).

**Bước 2 – Cổng bắt buộc** (thiếu một cái là loại ngay, chỉ dùng nến đã đóng):

| Cổng | Điều kiện |
|---|---|
| Xu hướng khung 1h | EMA21 so với EMA50, giá so với EMA21, ADX 1h ≥ 18. Chỉ đánh **cùng chiều** khung 1h |
| Thị trường có xu hướng | ADX 15m ≥ 20 (lọc sideway) |
| Đủ biến động | ATR ≥ 0.35% giá |
| Có volume | Volume nến tín hiệu ≥ 70% trung bình 20 nến |
| Không đuổi giá | Giá cách EMA21 không quá 1 ATR |
| Không ngược nhịp 1h | Short khi coin vừa tăng ≥ 0.5% trong 1h (long: vừa giảm) → loại |
| Cổng BTC | BTC đang tăng/giảm ≥ 0.3%/1h hoặc xu hướng 1h ngược → cấm short/long altcoin |
| RSI hợp lý | Long: 45–70, Short: 30–55 |
| Nến tín hiệu đúng màu, không râu dài | Long phải là nến tăng đóng ≥ 60% biên độ (short ngược lại) |

**Bước 3 – Trigger** (ít nhất 1 sự kiện trong 3 nến gần nhất): MACD cắt, EMA9 cắt EMA21, breakout đỉnh/đáy 20 nến kèm volume ×1.5, pullback về EMA21/VWAP rồi bật, nến nhấn chìm.

**Bước 4 – Chấm điểm** = hợp lưu kỹ thuật (EMA 9/21/50, EMA200, VWAP, ADX, MACD+RSI 1h, nến đóng dứt khoát; trừ điểm volume cao trào, coin đã chạy > 20%/24h; v4.2 bỏ điểm trừ "xu hướng 1h đã chạy lâu" theo kiểm chứng 89 ngày – xem mục 13) **+ dòng tiền** (OI tăng cùng giá +0.5, tiền rút −1, funding) **+ tin tức** (xem mục 1b): độ lệch tin của coin × 1.5 điểm × trọng số tin. Cần ≥ `MIN_SCORE` = 5 điểm và tỉ lệ lời/lỗ ≥ 1.5.

**Bước 5 – Luật chặn**: danh mục luật cố định (phiên giờ, BTC, OI, đám đông, funding, tin tức, Fear & Greed). Một số chặn sẵn, còn lại để bộ tự học bật/tắt theo kết quả thật. Tín hiệu bị chặn vẫn được theo dõi "bóng" để bộ tự học biết luật đó có đáng giữ không.

**Bước 5b – Lớp bảo vệ (v4.1, kiểu freqtrade)** – phản ứng trong vài giờ, không phải chờ bộ tự học đủ mẫu:
- **Khoá một phía** 6h khi 3 lệnh thật cùng phía đóng lỗ trong 12h, *hoặc* ≥ 10 coin có tín hiệu cùng phía trong 12h mà ≥ 80% chạm SL (−1R) trước khi lời +1R. Đo "rào nào chạm trước" chứ không đo kết quả cuối – vì lệnh thua chạm SL nhanh còn lệnh thắng bám sóng tới 24h mới xong, nhìn "kết quả vừa có" lúc nào cũng thấy toàn thua.
- **Khoá coin**: coin vừa đóng lỗ nghỉ 6h; thua 2 lần trong 24h nghỉ tới hết 24h.
- **Tuổi niêm yết**: bỏ hợp đồng niêm yết chưa đủ 10 ngày.
- Tín hiệu bị khoá vẫn được theo dõi bóng (nguồn "Lớp bảo vệ") → báo cáo ngày cho biết bảo vệ đang cứu hay đang làm mất lãi. Khoá đang hiệu lực hiện ở `/status` và trang chủ.

**Bước 6 – Quyết định & vào lệnh (không AI)**: ứng viên qua hết các bước trên được xếp theo điểm; bot vào **ứng viên tốt nhất** (sàn / ngân sách rủi ro từ chối thì thử #2, #3 – `ENTRY_CANDIDATES`), tối đa 1 lệnh mới mỗi lượt quét. SL theo cấu trúc (đáy/đỉnh 6 nến ± 0.15 ATR, tối thiểu 2 ATR; xa hơn 3 ATR thì bỏ). Khối lượng để chạm SL mất `RISK_PER_TRADE` = **3% vốn × hệ số tin tức × chuỗi thua** (đã gồm phí + trượt giá): tin cùng chiều mạnh → tối đa ×1.25 (×1.5 nếu bộ tự học tăng trọng số tin), tin ngược chiều → giảm tương ứng, từ lệnh thua liên tiếp thứ 3 nhân 0.7; kẹp 0.35–1.5×. Điểm kỹ thuật **không** làm tăng rủi ro (dữ liệu v3.2: điểm cao thua nặng nhất). x10 isolated, tối đa 2 lệnh, tổng rủi ro đang mở ≤ `MAX_TOTAL_RISK` = 5% vốn.

**Bước 7 – Quản lý lệnh**: hybrid (chốt 50% ở TP1 do bộ tự học chọn, phần còn lại bám sóng) hoặc cách khác bộ tự học chọn (mục 9). **Lệnh đang mở gặp tin MỚI bất lợi** (long: hack/exploit, huỷ niêm yết; short: niêm yết sàn lớn – `NEWS_EXIT_EVENTS`) → đóng ngay và báo Telegram/Zoom.

**Bước 8 – Tổng kết lệnh (theo số liệu)**: khi lệnh đóng, bot xếp lệnh vào nhóm *thắng đúng kế hoạch / thắng nhưng trả lại nhiều / thua trong kế hoạch / thua sau khi đã lời (lỗi quản lý lệnh) / sai hướng ngay (lỗi điểm vào) / đóng vì tin xấu*, kèm R, MFE, SL theo ATR, tin tức lúc vào và lúc đóng. Xem bằng `/tongket` hoặc trên dashboard.

**Cầu dao**: lỗ 12% vốn trong ngày → nghỉ đến ngày mai; drawdown 30% từ đỉnh → dừng hẳn, chờ `/resume`.

### 1b. Phân tích tin tức (không AI, không cần API key)

| Nguồn | Dùng để |
|---|---|
| RSS 10 trang tin crypto: CoinDesk, Cointelegraph, The Block, Decrypt, CryptoSlate, Bitcoinist, CryptoPotato, U.Today, NewsBTC, BeInCrypto (`NEWS_FEEDS`) | Điểm tin của từng coin, tâm lý tin tức toàn thị trường |
| Thông báo OKX (`/api/v5/support/announcements`: niêm yết, huỷ niêm yết) và Binance (New Cryptocurrency Listing, Delisting) | Sự kiện niêm yết / huỷ niêm yết (nặng gấp đôi bài báo) |
| Fear & Greed Index (alternative.me) | Tâm lý chung (luật để bộ tự học thống kê) |

Làm mới mỗi 10 phút trên luồng nền (chỉ máy leader tải tin, máy dự phòng đọc bản lưu trong DB), mỗi nguồn tối đa 15 giây – nguồn lỗi bị bỏ qua, không ảnh hưởng giao dịch.

- **Nhận diện coin**: `$SOL`, `(SOL)`, `SOL` viết hoa, tên dự án = mã (`Pendle`, `Kaito`) hoặc tên riêng (`Solana`, `Polygon`) – chỉ mã đang có hợp đồng trên OKX. Mã trùng từ thông dụng (`NEAR`, `LINK`, `MOVE`, `ONE`…) chỉ nhận khi viết dạng `$MÃ`/`(MÃ)`.
- **Điểm cảm xúc** −1..+1: từ điển crypto (surge/rally/listing/partnership… dương; hack/exploit/delist/plunge/lawsuit… âm), đảo dấu khi có phủ định ngay trước (`not hacked`, `denies exploit`).
- **Sự kiện** (chỉ gán cho coin đứng gần từ khoá trong tiêu đề – "hackers move stolen Solana" không phải Solana bị hack): `delist` (hiệu lực 7 ngày), `hack` (48h), `listing` (48h), `unlock`, `lawsuit`, `etf`, `partnership`, `upgrade`.
- **Độ lệch tin của coin** (`news_bias`): trung bình có trọng số theo độ mới (bài 6h trước nặng bằng nửa), chỉ bài trong 24h, **co về 0 khi ít bài** (1 bài lẻ không đủ kéo mạnh).
- **Cách dùng**: tin là *bộ điều chỉnh*, không phải trigger. Cộng/trừ điểm, co giãn rủi ro, 3 luật chặn sẵn (`news_delist`, `news_hack_long`, `news_listing_short`), 6 luật để bộ tự học thống kê (`news_against`, `news_hype`, `news_unlock_long`, `mkt_news_against`, `fng_greed_long`, `fng_fear_short`), và đóng lệnh khi có tin xấu mới.
- **Trọng số tin** (`news_w`, mặc định 1.0): bộ tự học so tín hiệu có tin **cùng chiều** với tín hiệu tin **ngược chiều** (kiểm định Welch). Tin giúp chọn lệnh tốt hơn rõ rệt → tăng (tối đa 2.0); tin dự báo ngược → giảm (tối thiểu 0 = bỏ qua tin). Không ai phải tin vào từ điển: dữ liệu quyết định.

## 2. Chuẩn bị

| Cần gì | Lấy ở đâu |
|---|---|
| Telegram bot token | Chat `@BotFather` → `/newbot` |
| Telegram chat id | Chat `@userinfobot` |
| OKX API key (chỉ khi `live`) | OKX → Profile → API → tạo key quyền **Trade** (không bật Withdraw). Bật Futures, nạp ≥ 10 USDT vào Trading account |

Nhớ nhắn `/start` cho bot Telegram một lần để bot gửi được tin.

## 3. Deploy lên Botkeep.cloud (runtime Python, không Docker)

> **Ổ đĩa Botkeep có hạn (1 GB ở gói free).** Bản này đã bỏ pandas/numpy, cài pip không cache và tự dọn cache → tổng thư viện ~170 MB. Nếu server từng bị báo `disk I/O error` / `readonly database`: vào File Manager của Botkeep xoá thư mục `.cache` (nếu còn) và `data/`, rồi Start lại. Khuyên dùng `DATABASE_URL` Supabase cả trên Botkeep để dữ liệu không nằm trên ổ đĩa server.

Botkeep chạy app theo runtime, nhận code qua **GitHub** (khuyên dùng) hoặc **ZIP upload**, biến môi trường nhập ở mục **Secrets** của panel.

### Deploy từ GitHub: nhánh `botkeep` (giống repo Stockvn)

Không trỏ Botkeep vào `main` (có test, công cụ, dữ liệu walk-forward… không cần trên server). Mỗi lần `main` đổi, GitHub Actions (`.github/workflows/botkeep-branch.yml`) chạy bộ kiểm thử offline, tạo gói bằng `scripts/build_botkeep_bundle.py` (chỉ `run.py`, `requirements.txt`, `.env.example`, `README.md`, `bot/*.py`; kiểm giới hạn Botkeep 250 mục / 4 MB, biên dịch, mã bản dựng đúng bản phát hành) rồi đẩy **đúng nội dung gói** lên nhánh **`botkeep`** (kèm `.gitignore` cho `data/` và `.env`). Test hỏng, gói vượt giới hạn hoặc sai mã bản dựng thì lượt chạy báo đỏ và nhánh giữ bản cũ. File zip của mỗi lượt cũng nằm ở mục **Artifacts** trên trang Actions để upload tay khi cần.

1. Trên Botkeep: nguồn **GitHub**, repo `traique/altcoin_bot`, nhánh **`botkeep`**, start command `python run.py`, Python 3.13. Repo riêng tư thì cấp cho Botkeep quyền đọc repo trên GitHub.
2. Bắt đầu lại từ đầu: đặt `RESET_DATA=<mã bất kỳ>` (vd `2026-11-05`) trong Secrets → lần khởi động đầu tiên bot xoá **toàn bộ** dữ liệu (vốn ảo về `PAPER_START_BALANCE`, lệnh, tín hiệu, tham số tự học, nhật ký – kể cả DB dùng chung nếu có `DATABASE_URL`) rồi báo Telegram "🧹 Đã xoá toàn bộ dữ liệu cũ". Khởi động lại với cùng mã thì không xoá nữa; đổi mã để xoá lần nữa. Chạy thật còn lệnh mở thì bot không xoá.
3. Chạy tay (khi Actions tắt): `python scripts/build_botkeep_bundle.py && scripts/publish_botkeep_branch.sh dist/botkeep`.

### Tạo server

1. Tạo server mới → chọn profile **Python** (phiên bản 3.10 trở lên; Botkeep hiện chạy 3.13).
2. Nguồn code: GitHub nhánh `botkeep` như trên (hoặc upload file zip từ mục Artifacts của Actions / `python scripts/build_botkeep_bundle.py`).
3. **Start command**: `python run.py` (file này tự cài thư viện trong `requirements.txt` rồi chạy bot, tự khởi động lại nếu bot crash).
4. **Secrets**: nhập các biến trong `.env.example` mà anh cần (tối thiểu: `MODE=paper`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `DASHBOARD_PASS`). Không cần key AI nào. Nếu panel còn biến `AI_*`, `NINEROUTER_*`, `OPENROUTER_*` của bản cũ thì xoá (để lại bot cũng bỏ qua). Hoặc tạo file `.env` trong ZIP – nhưng để key trong Secrets an toàn hơn.
5. Bấm Start, xem console: dòng `🚀 Bot khởi động – chế độ PAPER` là chạy được.
   **Nâng cấp từ v3.x lên v4.x bằng upload zip**: upload zip đè, rồi xoá file `bot/ai.py` cũ nếu còn (trang Phiên bản báo "khác bản phát hành" khi còn sót file cũ); giữ thư mục `data/` hoặc `DATABASE_URL` để giữ lịch sử – bot tự nâng cấp tham số tự học 1 lần (bỏ ngưỡng phủ quyết AI, giữ TP1/trọng số đã học). Deploy từ nhánh `botkeep` thì không có file cũ sót lại.
6. Dashboard: bot mở cổng theo biến `PORT` / `SERVER_PORT` / `APP_PORT` nếu Botkeep cấp, không thì `DASHBOARD_PORT` (8080). Trong console lúc khởi động có dòng `Dashboard: http://0.0.0.0:<cổng>` – đó là cổng cần mở/expose trong panel Botkeep (mục Network/Ports nếu có). Truy cập `http://<ip-server>:<cổng>/` – có trang đăng nhập (`DASHBOARD_USER`/`DASHBOARD_PASS`, nhớ 30 ngày); để trống `DASHBOARD_PASS` nếu không muốn hỏi. Cổng web được mở ngay trong 1–2 giây đầu, trước khi bot tải dữ liệu OKX, để host không báo "not responding". Nếu Botkeep vẫn báo vậy: so sánh **assigned port** trong panel với số cổng trong dòng log `Dashboard: cổng …` – nếu khác, đặt Secret `PORT=<assigned port>`. Thử `http://<ip>:<cổng>/health` trước: trả `{"ok":true}` nghĩa là server đã chạy, chỉ còn vấn đề cổng/đường dẫn. File `botkeep.env` có sẵn danh sách biến. **Khuyên dùng:** trên panel chỉ khai các bí mật (token Telegram, Zoom, mật khẩu dashboard) cùng `MODE`, `INSTANCE_NAME`, `PUBLIC_URL`. Mọi thông số khác đã có mặc định tốt nhất trong code và tự cập nhật theo từng bản; nếu panel còn khai biến thông số thì giá trị cũ đó sẽ thắng, nên hãy xoá chúng. Trong khung `.env` của Botkeep, dòng `__BOTKEEP_KEEP_SECRET_…__` giữ nguyên để giữ giá trị; không dán dòng `<...>`. Lúc khởi động, log in dòng `Thông số đang dùng: …` để kiểm tra.

Bot dùng ~200 MB RAM; v4.0 không cần chạy thêm 9Router hay dịch vụ AI nào. Server cần ra được Internet tới OKX, các trang RSS, binance.com và api.alternative.me (tin tức).

## 3b. Chạy song song trên Render free + Botkeep (dự phòng lẫn nhau)

Hai máy chạy cùng lúc nhưng **chỉ một máy giao dịch** (leader), máy kia đứng chờ (standby). Chúng dùng chung một cơ sở dữ liệu Postgres nên thấy cùng số dư, lệnh, lịch sử, tổng kết lệnh, tham số tự học, bộ nhớ đệm tin tức. Leader gia hạn "khoá" mỗi 20 giây; nếu leader chết/ngủ quá `LEADER_TTL` (90 giây) thì standby tự tiếp quản và báo Telegram. Hai máy ping `/health` của nhau mỗi 4 phút để Render free không bị ngủ (Render tắt web service free sau 15 phút không có request).

**Bước 1 – Tạo Postgres dùng chung trên Supabase (free)**

1. Vào supabase.com → New project → đặt tên, **Database password** (ghi lại; nên đặt chỉ gồm chữ + số để khỏi phải mã hoá URL), region gần Render nhất (Singapore nếu Render chọn Singapore).
2. Trong project bấm nút **Connect** (góc trên) → tab **Connection string** → chọn **Session pooler** (KHÔNG chọn "Direct connection": kết nối trực tiếp chỉ có IPv6, Render free không ra được IPv6 nên sẽ báo lỗi mạng).
3. Chuỗi có dạng:
   `postgresql://postgres.abcdefghijklmnop:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
   Thay `[YOUR-PASSWORD]` bằng mật khẩu. Nếu mật khẩu có ký tự đặc biệt phải mã hoá URL (`@`→`%40`, `#`→`%23`, `/`→`%2F`, `:`→`%3A`).
4. Dán vào `DATABASE_URL` của **cả Render lẫn Botkeep**. Bot tự thêm `sslmode=require` và tự tắt prepared statement (bắt buộc với pooler của Supabase).
5. Kiểm tra trước khi deploy: `python check_db.py` (đọc `.env`) → phải in `✅ Kết nối OK`.
6. Bot tự tạo bảng khi chạy lần đầu, không cần làm gì trong SQL Editor. Dữ liệu xem được ở Supabase → Table Editor (bảng `trades`, `signals`, `reviews`, `locks`, `heartbeats`).

Lưu ý Supabase free: project bị **tạm dừng (pause) sau 7 ngày không có truy vấn** – bot chạy liên tục thì không bị; nếu anh tắt cả hai bot hơn 1 tuần thì vào dashboard Supabase bấm Restore rồi chạy lại. Giới hạn 500 MB dữ liệu là dư thừa (bot ghi vài MB/tháng). Nếu Render của anh ở region khác, chọn region Supabase tương ứng để giảm độ trễ (mỗi truy vấn vẫn chỉ vài chục ms, không ảnh hưởng giao dịch).

**Bước 2 – Render**: New → Web Service → kết nối repo GitHub (hoặc dùng file `render.yaml` qua New → Blueprint). Runtime Python, Build command `pip install -r requirements.txt`, Start command `python run.py`, plan Free. Environment: `DATABASE_URL` (chuỗi Supabase ở trên), `INSTANCE_NAME=render`, `MODE=paper`, Telegram, `PEER_URL=<URL public của Botkeep>` nếu có. Render tự cấp `PORT` và `RENDER_EXTERNAL_URL`, bot tự dùng.

**Bước 3 – Botkeep**: như mục 3, thêm Secrets `DATABASE_URL` (cùng chuỗi), `INSTANCE_NAME=botkeep`, `PEER_URL=https://<tên-service>.onrender.com`.

**Bước 4 – Kiểm tra**: mở dashboard của cả hai, góc trên hiển thị `render · LEADER` / `botkeep · STANDBY` và danh sách instance. Hoặc gõ `/status` trên Telegram. Tắt thử máy leader, sau ~1.5 phút máy kia sẽ nhắn "👑 … tiếp quản".

Lưu ý: Render free cho 750 giờ/tháng – đủ chạy 1 service 24/7; ổ đĩa Render bị xoá mỗi lần deploy nên **bắt buộc** dùng `DATABASE_URL` (Supabase) khi chạy trên Render. Không dùng Postgres free của Render (hết hạn sau 30 ngày). Telegram chỉ cho một máy nhận lệnh, bot đã xử lý: chỉ leader nhận và gửi tin.

### Chạy trên VPS/máy thường

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
python run.py
```

## 4. Lệnh Telegram

`/status` vốn, PnL, lệnh mở, tâm lý tin tức · `/trades` 10 lệnh gần nhất · `/signals` tín hiệu & kết quả bóng · `/news` (`/tintuc`) Fear & Greed, tâm lý tin 12h, coin được nhắc nhiều, tin mới kèm điểm · `/tongket` tổng kết các lệnh gần nhất · `/learn` `/apply` tự học · `/btc` · `/pause` `/resume` · `/close` đóng tất cả. Bot tự gửi báo cáo ngày lúc 0h và báo cáo tự học lúc 7h theo `TIMEZONE` (mặc định giờ Việt Nam).

## 5. Quy trình 2 tuần ảo → thật

1. `MODE=paper` 14 ngày, không đổi tham số giữa chừng.
2. Cần ≥ 30 lệnh để đánh giá: winrate, profit factor > 1.3, drawdown chịu được. Với bộ lọc khắt khe, có thể mất 2–3 tuần mới đủ 30 lệnh – đó là bình thường.
3. (Nên) chạy thêm vài ngày `OKX_DEMO=true` với API key demo của OKX để kiểm tra đặt lệnh thật trên sàn ảo.
4. Chuyển thật: `MODE=live`, điền API key OKX, `I_UNDERSTAND_THE_RISK=yes`, xoá thư mục `data/` để reset thống kê, khởi động lại.

## 6. Tinh chỉnh

- Ít tín hiệu quá → hạ `MIN_SCORE` 5 → 4.5, `MIN_ADX` 20 → 18. Nhiều lệnh thua → tăng lên.
- `NEWS_SCORE_MAX` (1.5): điểm tin tối đa (× trọng số tin bộ tự học đo được). Muốn tin tức nặng/nhẹ hơn từ đầu: đổi `NEWS_WEIGHT` (0–2); `NEWS_ENABLED=false` để chạy thuần kỹ thuật so sánh.
- `NEWS_EXIT_EVENTS` (`delist,hack,listing`): sự kiện mới khiến bot đóng lệnh đang mở; để trống để tắt.
- `NEWS_FEEDS`: thêm/bớt RSS (`tên|url,tên|url`). `NEWS_REFRESH_MIN` (10), `NEWS_HALF_LIFE_H` (6), `NEWS_SHRINK` (1.0).
- `DEFAULT_BLOCKS`: luật chặn sẵn. Nếu panel còn `DEFAULT_BLOCKS` của bản cũ, 3 luật tin tức chặn sẵn của v4.0 sẽ mất – hãy xoá biến đó trên panel.
- `RISK_PER_TRADE`, `LEVERAGE`: hạ nếu thấy chuỗi thua dài. Bot đã tự co rủi ro sau chuỗi thua (`LOSS_STREAK_CUT`) và theo tin tức (`RISK_MIN_MULT`–`RISK_MAX_MULT`); `MAX_TOTAL_RISK` là trần cho mọi lệnh đang mở.
- `CRYPTO_ONLY=false` chỉ khi muốn quét cả hợp đồng cổ phiếu/hàng hoá token hoá (không khuyên).
- Lớp bảo vệ: `PROTECT_ENABLED=false` để tắt; nới/siết bằng `PROTECT_SIDE_LOSSES`, `PROTECT_SHADOW_SL_SHARE`, `PROTECT_LOCK_HOURS`, `PROTECT_PAIR_LOSS_HOURS`, `PROTECT_MIN_AGE_DAYS`.
- Phiên bản đang chạy hiện ở góc tiêu đề dashboard, `/health`, lệnh `status` và tin nhắn khởi động. Nếu Render và Botkeep chạy khác bản, nhãn phiên bản chuyển màu đỏ.


## 8. Ghi nhận dữ liệu & tự học

**Trên web** (cuộn xuống dưới dashboard):
- Tab **Hoạt động**: toàn bộ log của bot (giống console Botkeep), lọc theo mức INFO/WARNING/ERROR và tìm kiếm. Lưu 14 ngày.
- Tab **Lịch sử quét**: mỗi lượt quét bao nhiêu coin đạt, loại vì lý do gì. Lưu 30 ngày.
- Tab **Tín hiệu**: mỗi tín hiệu kèm nguồn (đã vào lệnh / xếp sau / sàn-ngân sách từ chối / suýt đạt / bị luật chặn), tin tức của coin lúc đó và **kết quả thật** sau đó (TP / SL / hết giờ, tính bằng R).
- Tab **Tổng kết lệnh** và trang **Tin tức & Tự học** (tâm lý thị trường, coin được nhắc nhiều, tin mới kèm điểm và sự kiện, nguồn lỗi).
- Thẻ **Tải dữ liệu**: tải CSV (mở được bằng Excel / Google Sheets, đúng tiếng Việt) hoặc sao lưu toàn bộ JSON.

**Tự học hoạt động thế nào:**
1. Mọi tín hiệu đã qua bộ lọc kỹ thuật, kể cả tín hiệu không vào lệnh, đều được theo dõi "bóng": bot xem nến 5 phút sau đó để biết nếu vào thì sẽ chạm TP hay SL trước. Kết quả tính bằng R (1R = khoảng cách tới SL), đã trừ phí.
2. Mỗi giờ bot thống kê theo nhóm: nguồn tín hiệu, loại trigger, luật lọc, khung giờ, điểm số, **tin tức (cùng/ngược chiều/không có tin), Fear & Greed**. Khi một nhóm có đủ mẫu (mặc định 30) **và** kết quả khác 0 có ý nghĩa thống kê (|kỳ vọng| / sai số chuẩn ≥ `LEARN_MIN_T` = 1.3; so sánh cách thoát / mức TP1 theo từng cặp trên cùng tín hiệu, TP1 cần ≥ 40 mẫu), bot điều chỉnh:
   - bật/tắt luật chặn trong danh mục cố định (vd. "short khi RSI 1h < 32") – chặn ở bộ lọc thì không tốn lượt AI;
   - trọng số từng trigger (0,6 – 1,4);
   - ngưỡng điểm MIN_SCORE (4,0 – 7,0, mỗi lần ±0,5);
   - **trọng số tin tức** (0 – 2, mỗi lần ±0,25) – v4.0, so tin cùng chiều vs ngược chiều bằng kiểm định Welch.
   - **ngưỡng 10 cổng lọc** (v4.1): ADX 15m, ATR%, volume, cách EMA21, nhịp 1h ngược, BTC ngược, RSI sàn/trần, vị trí đóng nến, SL cấu trúc. Bot theo dõi bóng cả tín hiệu **trượt đúng 1 cổng, sát ngưỡng** (vd ADX 16–20 khi ngưỡng 20) – trước đây tín hiệu bị loại ở cổng không được ghi nên bộ tự học "mù" với các ngưỡng quan trọng nhất. Nhóm suýt qua có lãi rõ → nới cổng 1 bước; nhóm đã qua nhưng sát ngưỡng lỗ rõ → siết 1 bước (mỗi cổng có giới hạn thấp/cao, 48h/lần).
   v4.0: mỗi giờ bot thử ~30 nhóm luật + trigger + cổng cùng lúc → **kiểm soát tỉ lệ phát hiện sai Benjamini–Hochberg** (`LEARN_FDR_Q` = 0,10): một nhóm "đạt" t ≥ 2 do may rủi giữa nhiều nhóm sẽ không được đổi tham số.
   Mỗi tham số chỉ đổi tối đa 1 lần/48h (`LEARN_COOLDOWN_H`). v3.2: `LEARN_MIN_T` = 2,0; không bao giờ chặn cả một phía (long_side/short_side chỉ để thống kê); cách thoát lệnh cần ≥ `LEARN_EXIT_MIN_SAMPLES` = 60 cặp. Luật đã chặn vẫn được theo dõi bóng, nên nếu nhóm đó tốt lên bot sẽ tự bỏ chặn. (v3.1: trước đây 13–20 mẫu đã đổi, trọng số trigger nhảy qua lại trong 1 ngày – nay không còn.)
3. Mỗi sáng (7h) bot gửi **báo cáo tự học** bằng số liệu (không AI): kết quả 24h, nhóm tốt/xấu nhất đủ mẫu, tác động tin tức, cách thoát tốt nhất, đề xuất chờ duyệt.
4. Chạy ảo: tự áp dụng. Chạy thật: chỉ đề xuất, anh duyệt trên web hoặc gõ `/apply` trên Telegram. Nút "Khôi phục mặc định" đưa mọi thứ về ban đầu.

Bot **không bao giờ tự sửa code** – chỉ chỉnh các tham số trong danh mục, có giới hạn và có lịch sử. Telegram: `/learn` xem trạng thái, `/apply` duyệt đề xuất.


## 9. Cách thoát lệnh – "ăn sóng" altcoin

Ba cách, chọn bằng `EXIT_MODE` (mặc định `auto` = bộ tự học chọn, khởi đầu là hybrid):

| Cách | Mô tả | Hợp với |
|---|---|---|
| `fixed` | TP cố định 3 ATR; lời 1,5R thì kéo SL về hoà vốn | Thị trường giật, sóng ngắn |
| `hybrid` | Chốt 50% khi lời 2R (khoá lợi nhuận, SL về hoà vốn); 50% còn lại **bám sóng**: SL = đỉnh/đáy kể từ khi vào ∓ 2,5 ATR, siết còn 1,5 ATR khi lời ≥ 4R; thoát nếu 4h không lập đỉnh mới | Sóng mạnh kéo dài |
| `trail` | Toàn bộ vị thế bám sóng, không chốt trước | Xu hướng rất mạnh, chấp nhận trả lại lãi |

Bot mô phỏng **song song cả 3 cách** trên mọi tín hiệu (bằng nến 5 phút thật sau tín hiệu), hiển thị so sánh trong thẻ "Tự học" → "So sánh cách thoát lệnh". Với `EXIT_MODE=auto`, khi có ≥ 20 tín hiệu và một cách hơn cách đang dùng ≥ 0,25R/tín hiệu thì bot tự chuyển (tối đa 1 lần/24h, có lịch sử, khôi phục được).

Lưu ý thật lòng: không cách nào "ăn trọn" sóng. Trailing đổi tỉ lệ thắng lấy những lệnh thắng lớn; gặp sóng giật mạnh rồi mới chạy tiếp (như STRK ngày 17/10: hồi về EMA21 rồi mới giảm thêm 3R) thì trailing vẫn bị chốt sớm. Vì vậy hãy để dữ liệu quyết định thay vì tin cảm giác.


## 10. Kênh Zoom Team Chat

Kênh Zoom làm theo đúng mô hình đã chạy thực tế trong repo **lananh** (`channels/zoom.py`): chatbot app, xác thực chữ ký HMAC, ghép đôi đúng 1 JID, trả lời đúng JID (chat 1:1 trả về người gửi, kênh nhóm trả về kênh), chuyển markdown sang kiểu Zoom, cắt tin dài, thử lại 3 lần. Mọi thông báo gửi đồng thời Telegram + Zoom; lệnh gõ ở đâu cũng được (chỉ máy leader gửi).

**Trang phục vụ Zoom (có sẵn trong bot, theo cách repo lananh làm):**

| Trang | Dùng cho ô nào trên Marketplace |
|---|---|
| `/zoom/oauth/callback` | OAuth Redirect URL + OAuth Allow List |
| `/webhook/zoom` | Bot endpoint URL, Event notification endpoint, Deauthorization endpoint |
| `/privacy` | Privacy Policy URL |
| `/terms` | Terms of Use URL |
| `/support` | Support URL |
| `/docs` | Documentation URL / Home URL |
| `/data-deletion` | Hướng dẫn xoá dữ liệu |
| `/zoom/install` | Nút "Thêm vào Zoom" |
| `/zoom` | Trang cấu hình (cần đăng nhập dashboard): liệt kê đúng các URL theo domain của anh, nút chép, kiểm tra biến môi trường, trạng thái cài đặt/ghép đôi |

Với Botkeep đã có HTTPS (vd `https://okx.bot-keep.xyz`), chatbot Zoom chạy được ngay trên Botkeep, không cần Render.

**Cài đặt (Local Test):**
1. Secrets: `PUBLIC_URL=https://okx.bot-keep.xyz`, `SUPPORT_EMAIL=...`, rồi Redeploy.
2. Đăng nhập dashboard → mở `https://okx.bot-keep.xyz/zoom` → làm theo 7 bước và bấm "Chép" từng URL dán vào marketplace.zoom.us (General App → bật Team Chat → Chatbot).
3. Điền `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` (Development), `ZOOM_BOT_JID`, `ZOOM_SECRET_TOKEN`, `ZOOM_ACCOUNT_ID`, Redeploy, bấm **Validate** endpoint trên Marketplace.
4. Local Test → **Add App Now** → Allow → về trang callback báo "Đã cài thành công".
5. Zoom → Team Chat → Apps → nhắn `status` → Telegram báo JID → gõ `/zoompair <JID>`. `/zoomstatus` xem, `/zoomxoa` gỡ. Gỡ app khỏi Zoom thì bot tự xoá ghép đôi.

**Lưu ý:** mỗi Zoom app chỉ có 1 endpoint. Nếu anh đã dùng app Zoom cho bot lananh thì tạo **app thứ hai** cho bot trading (cùng cách làm), không dùng chung.

**Chỉ chạy trên Botkeep (không có HTTPS):** dùng Incoming Webhook để nhận thông báo vào 1 kênh Zoom – cài app "Incoming Webhook", trong kênh gõ `/inc connect okxbot`, dán Endpoint + Token vào `ZOOM_WEBHOOK_URL`, `ZOOM_WEBHOOK_TOKEN`. Khi đó lệnh vẫn gõ qua Telegram hoặc dashboard.

Lệnh dùng chung: `status, trades, signals, news (tintuc), learn, apply, tongket, btc, pause, resume, close, phienban` (Telegram thêm `/`, Zoom gõ trực tiếp hoặc `/okxbot <lệnh>`).

## 11. Bối cảnh BTC, Open Interest, tỉ lệ long/short

Mỗi lượt quét bot lấy BTC 15m/1h (xu hướng, % thay đổi 1h/4h). Với mỗi tín hiệu đã qua bộ lọc kỹ thuật, bot lấy thêm Open Interest thay đổi 1h, tỉ lệ tài khoản long/short và funding của coin đó. Các dữ liệu này:
- cộng/trừ điểm (OI, funding) trước khi xét ngưỡng & xếp hạng;
- được lưu cùng tín hiệu (tải được trong signals.csv);
- tạo thành các **luật ứng viên** cho bộ tự học: long khi BTC 1h giảm, short khi BTC tăng, ngược xu hướng BTC, BTC biến động mạnh, giá tăng nhưng OI giảm, OI tăng đột biến, đám đông long/short quá đông, funding cực đoan.

Bot **không chặn sẵn** luật nào. Mỗi luật được theo dõi kết quả bóng; chỉ khi một nhóm có đủ mẫu và thua rõ rệt (kỳ vọng < −0,25R) thì mới bị chặn – xem bảng "Theo luật lọc" trong thẻ Tự học.

## 7. Cấu trúc

```
run.py            – start command cho Botkeep/Render: tự cài thư viện, chạy & tự khởi động lại bot
scripts/          – build_botkeep_bundle.py (tạo & kiểm tra gói Botkeep), publish_botkeep_branch.sh (đẩy nhánh botkeep)
.github/workflows/botkeep-branch.yml – mỗi lần main đổi: test → gói → nhánh botkeep (Botkeep deploy từ nhánh này)
render.yaml       – blueprint tạo Web Service free trên Render
bot/config.py     – đọc biến môi trường / .env
bot/exchange.py   – OKX qua ccxt
bot/indicators.py – EMA/RSI/ATR/MACD/BB/ADX/VWAP
bot/strategy.py   – cổng bắt buộc + trigger + chấm điểm (kỹ thuật + dòng tiền + tin tức) + luật chặn + quyết định
bot/news.py       – tin tức không AI: RSS, thông báo OKX/Binance, Fear & Greed, từ điển, sự kiện, điểm theo coin
bot/review.py     – tổng kết lệnh theo số liệu (thay AI tổng kết)
bot/protections.py – lớp bảo vệ: khoá phía, khoá coin, tuổi niêm yết, rào ±1R chạm trước
tools/walkforward.py – tối ưu walk-forward trên nến lịch sử OKX (chạy trên máy tính, không chạy trên Botkeep)
bot/risk.py       – khối lượng lệnh, cầu dao
bot/engine.py     – PaperEngine & LiveEngine
bot/storage.py    – SQLite (1 máy) hoặc Postgres dùng chung (nhiều máy) + khoá leader
bot/exits.py      – logic thoát lệnh (fixed/hybrid/trail) dùng chung cho engine & mô phỏng
bot/learner.py    – tự học: kết quả bóng, điều chỉnh tham số có kiểm định (t, Welch, Benjamini–Hochberg), báo cáo ngày
bot/market.py     – bối cảnh BTC, Open Interest, long/short, funding
bot/notify.py     – gửi thông báo đa kênh (Telegram, Zoom webhook/chatbot), nhận lệnh Zoom
bot/eventlog.py   – ghi log hoạt động vào DB để xem trên web
bot/telegram.py, bot/dashboard.py, bot/main.py
test_smoke.py     – quét thật OKX, in tín hiệu (không cần key)
test_engine.py    – kiểm tra toán PnL paper
test_news.py      – tin tức (RSS/Atom, nhận diện coin, từ điển, sự kiện, tổng hợp, đóng lệnh theo tin), tổng kết lệnh
test_flow.py      – luồng chính với sàn giả: quét → tin tức → luật chặn → vào lệnh → đóng vì tin xấu → tổng kết, web
test_gates_protect.py – cổng lọc học được, tín hiệu suýt qua cổng, nới/siết cổng, lớp bảo vệ
test_strategy.py, test_risk.py, test_learner.py, test_web.py – bộ lọc, rủi ro, tự học, giao diện
botkeep.env       – các biến cần khai trên panel Botkeep (chỉ bí mật + thông tin riêng)
check_db.py       – kiểm tra kết nối Supabase trước khi deploy
```

## 12. Repo tham khảo trên GitHub

Danh sách repo tương tự (bot TA, bot tin tức không dùng LLM, tự tối ưu tham số) đã kiểm chứng sao/ngày cập nhật/giấy phép, và những gì bot này đã/có thể học từ chúng: xem [THAM_KHAO.md](THAM_KHAO.md).

## 13. Kiểm chứng trên 90 ngày lịch sử (walk-forward)

`tools/walkforward.py` chấm lại 40 coin × 89 ngày (08–11/2026) bằng đúng code của bot. Kết quả: [tools/wf_results/2026-11-05/BAO_CAO.md](tools/wf_results/2026-11-05/BAO_CAO.md).
Tóm tắt: tối ưu tham số **không** thắng mặc định ngoài mẫu (−4,5R so với +1,6R trong 59 ngày); phần kỹ thuật ≈ hoà vốn; nhiều kết luận rút từ vài ngày (phiên 13–19h, xu hướng 1h đã chạy lâu) đảo dấu khi xét 89 ngày → v4.2 bỏ điểm trừ "xu hướng 1h đã chạy lâu" (kỳ vọng mỗi tín hiệu tốt hơn ở cả hai nửa). Lớp bảo vệ: với điểm số v4.1 có lợi ở cả hai nửa, nhưng với điểm số v4.2 thì nửa sau chặn nhầm lệnh thắng – **chưa đủ bằng chứng**; mọi chênh lệch cấp danh mục (vài R) đều nằm trong biên nhiễu ±15–20R. Bot ghi bóng tín hiệu bị bảo vệ chặn, báo cáo ngày sẽ cho biết bảo vệ đang cứu hay làm mất lãi.

---

# Lịch sử các bản trước

Các mục dưới đây mô tả các bản v2.9–v3.2 (còn dùng AI) – giữ lại để biết lý do của từng thông số.

## Tối ưu lợi nhuận kỳ vọng (v2.9)
Mục tiêu là **lợi nhuận kỳ vọng** = tỉ lệ thắng × lãi trung bình − tỉ lệ thua × lỗ trung bình, không chỉ tỉ lệ thắng.
- **Cổng BTC, chống râu nến, SL theo cấu trúc, trigger không cộng trùng, điểm dòng tiền trước xếp hạng**: giữ từ v2.8.
- **Không đuổi giá**: giá cách EMA21 quá `MAX_EXT_ATR` = 1 ATR thì bỏ. Backtest 10 ngày: nhóm cách hơn 1 ATR lỗ ở cả hai nửa dữ liệu.
- **Phiên 13h–19h (giờ VN)**: backtest thấy lỗ ở cả 4 giai đoạn nhưng mặc định KHÔNG chặn (v2.9.2). Bộ tự học theo dõi và tự chặn nếu thực tế lỗ (kỳ vọng < −0.25R trên đủ mẫu). Muốn chặn ngay: thêm `afternoon_session` vào `DEFAULT_BLOCKS`.
- **TP1 tự học**: mỗi tín hiệu được mô phỏng với TP1 = 1 / 1.3 / 1.6 / 2 / 2.5R; bot chọn mức có kỳ vọng cao nhất. Mặc định `TP1_R=1.0`.
- **Nhiều cơ hội hơn**: quét `TOP_N_COINS=50`; AI từ chối ứng viên #1 thì hỏi #2, #3 (`AI_CANDIDATES_PER_SCAN=3`).
- **Setup range** (đảo chiều tại biên Bollinger khi 1h đi ngang, TP = dải giữa): đã có, nhưng chặn sẵn (`setup_range`) vì chưa đủ dữ liệu chứng minh có lãi; bộ tự học gỡ khi có lãi.
- **AI**: đánh giá theo lợi nhuận kỳ vọng; `confidence` khi đồng ý = điểm chất lượng (50 = trung bình), duyệt khi ≥ `AI_MIN_CONFIDENCE` = 60.

## Học từ 5 ngày chạy ảo (v3.2)
Rút từ 211 tín hiệu bóng có kết quả (23–27/10/2026, v3.1): kỳ vọng chung −0,24R, thắng 38%; 190 short / 21 long; lệnh thật +9,3%
chỉ nhờ 2 ngày giảm mạnh đầu tiên, 3 ngày sau short thua 24%. Những gì dữ liệu nói rõ (n ≥ 27, khoảng tin cậy 90% không chứa 0):
- **Short khi coin vừa tăng ≥ 0.5%/1h** (bắt đỉnh nhịp hồi): −0,72R, thắng 18% (n=56); nhóm còn lại −0,13R → **cổng mới `CHASE_1H_PCT`**.
- **Volume nến tín hiệu 1,5–2,5×**: −0,68R, thắng 16% (n=31); dưới 1,5×: −0,16R → **trừ điểm + luật `climax_volume` chặn sẵn** (trước đây được CỘNG điểm).
- **ADX 1h ≥ 35** (xu hướng đã chạy lâu): short −0,44R (n=76) so với −0,22R → **trừ 1 điểm** (trước đây "ADX mạnh" được cộng).
- **Short khi BTC đang +0,3%/1h trở lên**: −0,60R (n=27) → **`BTC_GATE_CHG` 0,6 → 0,3**.
- **13h–19h VN** (06–12 UTC) lỗ ở mọi khung 2h; **21h–23h VN** (Mỹ mở cửa) là khung duy nhất lãi rõ (+0,42R, n=27) → **chặn sẵn `afternoon_session`**.
- **Điểm hợp lưu ngược dự báo**: điểm ≥ 7 thua nặng nhất (−0,33R, thắng 25%, n=20), điểm < 5 gần hoà → **rủi ro không còn tăng theo điểm** (`risk.quality_mult` chỉ theo AI).
- **Bộ tự học tự thắt cổ bot**: với t ≥ 1,3 nó đổi trọng số trigger rồi đảo ngược sau 48h, chuyển hybrid→trail trên 31 mẫu (trên 211 mẫu hybrid vẫn hơn), rồi **chặn toàn bộ short** sau 2 ngày xấu → bot đứng im 2,5 ngày. Nay: `LEARN_MIN_T` 2,0, không bao giờ chặn cả một phía, đổi cách thoát cần ≥ 60 cặp, thống kê nhóm theo mốc hybrid cố định. Tham số học bằng ngưỡng cũ được **đưa về mặc định một lần** khi khởi động bản 3.2 (giữ ngưỡng phủ quyết AI).
- **Chuỗi thua**: co rủi ro từ lệnh thua thứ 3 thay vì thứ 2 (4 lệnh thua liên tiếp là bình thường với tỉ lệ thắng 40%; co sớm làm bot vào 0,35× đúng lúc thị trường đổi chiều).

Áp lại 4 bộ lọc mới lên chính 173 tín hiệu trend đó (R theo hybrid): còn 78 tín hiệu, +0,36R/tín hiệu, thắng 72%; 95 tín hiệu bị loại
có −0,58R. Đây là kết quả **trên cùng dữ liệu dùng để chọn lọc** nên lạc quan hơn thực tế; nửa sau (25–27/10) chỉ từ −0,50R
lên −0,13R. Cần chạy ảo thêm ≥ 2 tuần (≥ 150 tín hiệu bóng) trước khi tin.

**Bảo mật**: bản cũ in nguyên URL Telegram (có token) khi lỗi mạng và file "sao lưu toàn bộ" kèm log đó. v3.2 che token / khoá API /
mật khẩu DB trong mọi dòng log. Nếu anh đã chia sẻ file sao lưu của bản cũ: **đổi token qua @BotFather (`/revoke`)**.

**Giới hạn vốn**: với 10 USDT, rủi ro 3%/lệnh là 0,30 USDT; kỳ vọng +0,3R và 1,5 lệnh/ngày cho ~4 USDT/tháng dù bot chạy đúng.
Vốn 10 USDT chỉ để kiểm tra hệ thống, không để đo "hiệu quả đầu tư".

## Nhạy hơn nhưng ít rủi ro hơn (v3.1)
Rút từ 2,8 ngày chạy ảo (80 tín hiệu bóng có kết quả, 4 lệnh đóng): điểm hợp lưu gần như không dự báo kết quả (điểm 6.x thua điểm 4.x), AI từ chối 90% nhưng không chọn tốt hơn ngẫu nhiên, phiên 0–7h thắng 1/14, bộ tự học đổi tham số trên 13–20 mẫu rồi đổi ngược lại.
- **Chất lượng → khối lượng, không → chặn cứng**: `MIN_SCORE` 5.5 → 5.0, volume 0.8 → 0.7; mỗi lệnh có hệ số rủi ro theo điểm KT, AI, chuỗi thua (xem Bước 6). Lệnh "vừa đủ" vào nhỏ, lệnh đẹp vào lớn hơn.
- **Rủi ro cơ bản 3%/lệnh** thay vì 10%, cầu dao 12%/ngày và 30% drawdown, tối đa 2 lệnh với trần tổng 5%.
- **AI điều tiết thay vì phủ quyết**: đồng ý 50–59% vẫn vào nửa rủi ro (nguồn `ai_weak`, bộ tự học theo dõi riêng).
- **Trigger mới**: hồi về VWAP rồi bật (tính chung nhóm với pullback EMA21, không cộng trùng).
- **Chặn sẵn phiên 0h–7h** (`night_session`); bộ tự học gỡ nếu bóng có lãi.
- **Bộ tự học cần ý nghĩa thống kê** (t ≥ 1.3, ≥ 30 mẫu, TP1 ≥ 40 mẫu so theo cặp, 48h/lần đổi).
- **AI tổng kết nhận số liệu tính sẵn** (SL theo ATR, kết quả R, MFE) – trước đây bịa "SL 0,35 ATR" trong khi thật là 1,56 ATR rồi đưa bài học sai vào prompt sau.
- **Live an toàn hơn**: dời SL trên sàn = đặt lệnh mới trước rồi mới huỷ lệnh cũ (bản cũ huỷ trước – đặt lỗi là trống SL); sàn tự khớp SL/TP → ghi giá khớp thật từ lịch sử giao dịch thay vì ước lượng.
- Log `Thông số đang dùng` in giá trị **thực** (sau khi tự học ghi đè), không in mặc định nữa.

## Giao diện web & phiên bản (v3.0)
- **Trang**: Tổng quan (vốn, lệnh mở, đường vốn, nhật ký) · AI & Tự học · Cài đặt · Phiên bản. Đổi sáng/tối bằng nút trên đầu trang; tối ưu điện thoại.
- **Cài đặt → Thông báo & tin nhắn**: 4 công tắc – Telegram thông báo, Telegram trả lời lệnh, Zoom thông báo, Zoom trả lời lệnh. Lưu trong DB, khởi động lại vẫn giữ. Tắt chỉ làm im kênh, không xoá cấu hình.
- **Cài đặt → Zoom → Gửi thử thông báo** (hoặc lệnh `zoomtest`): bot thử lần lượt các cách gửi (địa chỉ lần trả lời thành công, `ZOOM_TO_JID`, JID đã ghép đôi có/không kèm `user_jid`…), nhớ cách Zoom nhận và dùng cách đó cho mọi thông báo sau.
- **Phiên bản**: số phiên bản, mã bản dựng (dấu vân tay toàn bộ code) và lịch sử. Mã bản dựng khác bản phát hành nghĩa là upload thiếu file hoặc lẫn file cũ. Khi lên bản mới bot tự nhắn "Bot đã cập nhật" kèm danh sách thay đổi; lệnh `phienban` xem trên Telegram/Zoom.
- Biến tuỳ chọn mới: `ZOOM_TO_JID` – JID nhận thông báo cố định (khi cần ép một địa chỉ).
- Phát hành bản mới (cho người sửa code): tăng `VERSION`, thêm `NOTES` trong `bot/version.py`, rồi `python -m bot.version --stamp`.
