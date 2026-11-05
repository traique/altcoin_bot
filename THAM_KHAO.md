# Repo tham khảo trên GitHub (khảo sát 05/11/2026)

Mục tiêu khảo sát: tìm các dự án mã nguồn mở gần với bot này – giao dịch futures altcoin bằng **phân tích kỹ thuật + tin tức, không dùng AI/LLM để quyết định**, có **tự tối ưu tham số**. Số sao, ngày cập nhật (lần push cuối), giấy phép và ngôn ngữ lấy từ GitHub API ngày 05/11/2026; tính năng đọc từ README/tài liệu/mã nguồn (không chạy thử code của họ).

> **Giấy phép:** freqtrade, OctoBot, NostalgiaForInfinity là **GPL-3.0** – chỉ học thiết kế, không chép code vào bot này. Repo không có giấy phép (`none`) = giữ mọi quyền, chỉ tham khảo ý tưởng.

## 1. Bot / framework phân tích kỹ thuật lớn

| Repo | ★ | Cập nhật | Giấy phép | OKX futures | Đáng học |
|---|---|---|---|---|---|
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 56.465 | 05/11/2026 | GPL-3.0 | Có (isolated) | Bảo vệ rủi ro tách khỏi tín hiệu, lọc cặp, gắn nhãn tín hiệu, hyperopt |
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 31.249 | 05/11/2026 | LGPL-3.0 | Có | Cùng một code chạy backtest và live; tin tức là sự kiện có dấu thời gian |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | 20.946 | 04/11/2026 | Apache-2.0 | Có | "Triple barrier" (SL, TP, thời gian, trailing) dùng chung cho lệnh thật và mô phỏng |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | 8.769 | 03/11/2026 | MIT | **Không** | Kiểm định ý nghĩa luật bằng bootstrap, Monte Carlo |
| [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | 6.892 | 02/11/2026 | GPL-3.0 | Có | **Bot duy nhất còn bảo trì gộp TA + tin tức vào 1 điểm** không cần LLM |
| [iterativv/NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity) | 3.514 | 05/11/2026 | GPL-3.0 | Có (chiến lược freqtrade) | Danh sách loại trừ theo sàn, **mỗi mục có lý do** |
| [enarjord/passivbot](https://github.com/enarjord/passivbot) | 2.158 | 04/11/2026 | Unlicense | Có | Chọn thị trường theo volume + biến động; tối ưu đa mục tiêu có ràng buộc |

**freqtrade** – tham khảo chính:
- Bảo vệ rủi ro độc lập với tín hiệu: `StoplossGuard` (vd 4 lần SL trong 24 nến → khoá 4 nến, có tuỳ chọn chỉ khoá **một phía**), `MaxDrawdown`, `LowProfitPairs` (khoá riêng cặp lỗ), `CooldownPeriod`.
- Lọc cặp trước khi phân tích: `VolumePairList`, `AgeFilter` (mặc định niêm yết ≥ 10 ngày), `VolatilityFilter`, `SpreadFilter`, `DelistFilter` (**không hỗ trợ OKX**).
- Mỗi tín hiệu có `enter_tag`/`exit_tag`, báo cáo lãi theo tag, theo cặp × tag và cả **tín hiệu bị từ chối** – bot này làm tương tự bằng "kết quả bóng" của mọi tín hiệu.
- `lookahead-analysis`/`recursive-analysis`: phát hiện chỉ báo "nhìn trước tương lai" và EMA200 thiếu dữ liệu khởi động.

**OctoBot** – cách gộp tin tức không cần LLM:
- Mỗi bộ đánh giá (TA, tin tức/mạng xã hội) cho điểm trong [−1, 1]; chiến lược lấy **trung bình** rồi so ngưỡng.
- Điểm tin tức **hết hạn** sau 1 giờ; tin mới kích hoạt đánh giá TA lại chứ không tự đặt lệnh → **tin là bộ điều chỉnh, TA mới là trigger** (đúng như bot v4.0).
- `TwitterNewsEvaluator` chỉ hành động khi |điểm| > 0,6 và thời gian sống tỉ lệ với độ mạnh; `FearAndGreedIndexEvaluator` dùng Fear & Greed theo kiểu **ngược đám đông**.

**NostalgiaForInfinity**: `configs/blacklist-okx.json` loại token hoá cổ phiếu (chia tách cổ phiếu trông như cú sập −67% với chỉ báo), hợp đồng cổ phiếu đòn bẩy 2x/3x, coin bị Binance gắn "Monitoring Tag" (dấu hiệu sắp huỷ niêm yết).

## 2. Bot tin tức / cảm xúc không dùng LLM

| Repo | ★ | Cập nhật | Giấy phép | Ghi chú |
|---|---|---|---|---|
| [CyberPunkMetalHead/Binance-News-Sentiment-Bot](https://github.com/CyberPunkMetalHead/Binance-News-Sentiment-Bot) | 1.654 | 16/03/2022 | MIT | ~100 RSS + NLTK VADER; ngưỡng 0, chỉ cần 1 bài → **bài học cần tránh** |
| [CyberPunkMetalHead/gateio-crypto-trading-bot-binance-announcements-new-coins](https://github.com/CyberPunkMetalHead/gateio-crypto-trading-bot-binance-announcements-new-coins) | 1.236 | 08/02/2022 | MIT | Đọc thông báo niêm yết Binance (catalog 48), lấy mã bằng regex `\((...)\)` |
| [CyberPunkMetalHead/binance-trading-bot-new-coins](https://github.com/CyberPunkMetalHead/binance-trading-bot-new-coins) | 1.502 | 21/10/2021 | MIT | Phát hiện coin mới bằng so sánh danh sách ticker |
| [cjhutto/vaderSentiment](https://github.com/cjhutto/vaderSentiment) | 5.090 | 02/03/2026 | MIT | Thư viện từ điển + luật (Python thuần), có thể mở rộng từ điển crypto |
| [soheilrahsaz/cryptoNewsDataset](https://github.com/soheilrahsaz/cryptoNewsDataset) | 77 | 04/12/2025 | CC0-1.0 | 248 nghìn bài CryptoPanic 2017–2025 kèm phiếu bầu cộng đồng – dùng hiệu chỉnh từ điển offline |
| [lowweihong/crypto_exchange_news_crawler](https://github.com/lowweihong/crypto_exchange_news_crawler) | 29 | 03/05/2026 | none | Thu thập thông báo 13 sàn (OKX, Binance, Bybit…) |
| [binance/ai-trading-prototype-backtester](https://github.com/binance/ai-trading-prototype-backtester) | 65 | 16/04/2026 | MIT | Lưu cả giờ đăng và **giờ thu thập** tin → backtest không nhìn trước |

Ý tưởng lạ (repo nhỏ, chỉ để tham khảo giả thuyết): mua coin có cảm xúc Reddit **thấp** (ngược đám đông – [Cryptocurrency-Sentiment-Bot](https://github.com/CyberPunkMetalHead/Cryptocurrency-Sentiment-Bot)); giao dịch khi cảm xúc và xu hướng giá **lệch nhau** ([cryptocontrol/sentiment-trading-bot](https://github.com/cryptocontrol/sentiment-trading-bot), đã bỏ).

## 3. Tự tối ưu / thích nghi

| Repo | ★ | Cập nhật | Giấy phép | Đáng học |
|---|---|---|---|---|
| [imsatoshi/GeneTrader](https://github.com/imsatoshi/GeneTrader) | 204 | 29/07/2026 | MIT | Walk-forward, "thanh chọn lọc" chống chọn nhầm chiến lược may mắn (Python thuần), kiểm tra độ bền khi đổi tham số ±10% |
| [optuna/optuna](https://github.com/optuna/optuna) | 15.010 | 04/11/2026 | MIT | Tối ưu tham số (cần numpy → chạy riêng, xuất JSON cho bot) |
| [hummingbot/quants-lab](https://github.com/hummingbot/quants-lab) | 302 | 04/11/2025 | Apache-2.0 | Tối ưu offline rồi nạp tham số |
| [DaruFinance/deflated-sharpe](https://github.com/DaruFinance/deflated-sharpe) | 0 | 25/09/2026 | MIT | Deflated/Probabilistic Sharpe Python thuần (repo mới – cần tự kiểm tra) |
| [tschm/jsharpe](https://github.com/tschm/jsharpe) | 25 | 03/11/2026 | MIT | Kiểm soát FDR khi sàng lọc nhiều chiến lược |
| [eslazarev/purged-cross-validation](https://github.com/eslazarev/purged-cross-validation) | 57 | 04/11/2026 | MIT | Kiểm định chéo có "purge/embargo" cho tín hiệu chồng thời gian |

Chưa có repo trưởng thành nào cho "bandit chọn trigger" hay nhận diện chế độ thị trường không dùng ML – tự viết (~50 dòng Python) nếu cần.

**Danh sách tổng hợp**: [awesome-quant](https://github.com/wilsonfreitas/awesome-quant) (30.484★), [paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) (15.174★), [botcrypto-io/awesome-crypto-trading-bots](https://github.com/botcrypto-io/awesome-crypto-trading-bots) (2.550★).

## 4. Nguồn tin miễn phí không cần LLM (kiểm tra 05/11/2026)

| Nguồn | Cần key? | Trạng thái | Bot v4.0 |
|---|---|---|---|
| RSS: CoinDesk, Cointelegraph, The Block, Decrypt, CryptoSlate, Bitcoinist, CryptoPotato, U.Today, NewsBTC, BeInCrypto | Không | 200 | **Đang dùng** |
| OKX `/api/v5/support/announcements` (niêm yết, huỷ niêm yết) | Không | 200 (nội dung có thể khác theo vùng) | **Đang dùng** |
| Binance CMS – catalog 48 (niêm yết), 161 (huỷ niêm yết) | Không | 200 (API không chính thức) | **Đang dùng** |
| alternative.me Fear & Greed | Không | 200 | **Đang dùng** |
| OKX `/api/v5/public/instruments` (`instCategory`, `ruleType`, `expTime`, `listTime`) | Không | 200 | **Đang dùng** để chỉ quét crypto thật |
| DefiLlama `/hacks` | Không | 200 | Lịch sử hack, không thời gian thực – chưa dùng |
| GDELT DOC 2.0 | Không | 200 | Tin tổng hợp, không chuyên crypto – chưa dùng |
| CryptoPanic API | **Có (trả phí)** | Gói miễn phí đã ngừng (theo thông báo lỗi của API) | Không dùng |
| CoinDesk Data API (CryptoCompare cũ) | **Có** | 401 khi không có key | Không dùng |

## 5. Bot đã áp dụng gì trong v4.0

1. **Tin tức là bộ điều chỉnh, không phải trigger** (như OctoBot): cộng/trừ điểm có giới hạn, co giãn rủi ro, luật chặn; TA vẫn quyết định thời điểm vào.
2. **Không tin vào 1 bài báo** (tránh lỗi của Binance-News-Sentiment-Bot): co về 0 khi ít bài, giảm dần theo độ mới (half-life 6h), mỗi sự kiện có hạn hiệu lực riêng (hack 48h, huỷ niêm yết 7 ngày).
3. **Sự kiện từ chính sàn trước** (OKX + Binance), gán sự kiện theo khoảng cách từ trong tiêu đề, có xử lý phủ định.
4. **Chỉ quét crypto thật** theo phân loại OKX (`instCategory=1`, `ruleType=normal`, không có `expTime`) – đúng cảnh báo của NFI: ngày khảo sát có 236/525 hợp đồng USDT-SWAP là cổ phiếu/hàng hoá/tiền niêm yết, và 15/50 cặp bot cũ quét là loại này.
5. **Tự học chặt hơn**: kiểm soát nhiều phép thử Benjamini–Hochberg (ý tưởng từ jsharpe/GeneTrader), học trọng số tin bằng kiểm định Welch, vẫn giữ ≥ 30 mẫu, t ≥ 2, 48h/lần đổi.
6. **Đóng lệnh theo tin mới** chỉ dựa trên giờ bot *biết* tin (tương tự cách lưu "giờ thu thập" của binance/ai-trading-prototype-backtester).

## 6. Đã làm trong v4.1

- **Lớp bảo vệ kiểu freqtrade** (`bot/protections.py`): khoá **một phía** sau 3 lệnh thua/12h hoặc khi ≥ 80% tín hiệu cùng phía chạm SL trước +1R (StoplossGuard theo phía), coin vừa thua nghỉ 6h / thua 2 lần nghỉ 24h (CooldownPeriod/LowProfitPairs), bỏ coin niêm yết < 10 ngày theo `listTime` (AgeFilter).
- **Tự chỉnh ngưỡng cổng lọc**: theo dõi bóng tín hiệu trượt đúng 1 cổng sát ngưỡng (tương tự `--rejected-signals` của freqtrade) để bộ tự học nới/siết từng cổng.
- **Tối ưu walk-forward trên nến lịch sử** (`tools/walkforward.py`, ý tưởng từ freqtrade hyperopt / GeneTrader): chỉ tin bộ tham số thắng ở đoạn dữ liệu chưa dùng để chọn nó. Kết quả chạy 90 ngày: xem `tools/wf_results/`.

## 7. Có thể làm tiếp (chưa làm)

- Đọc `upcChg`/`expTime` của OKX để biết trước hợp đồng sắp gỡ (đã loại khỏi danh sách quét; chưa dùng để đóng lệnh đang mở).
- Hiệu chỉnh từ điển và half-life offline bằng [cryptoNewsDataset](https://github.com/soheilrahsaz/cryptoNewsDataset) (event study lợi nhuận 1h/4h/24h sau tin).
- Bootstrap p-value kiểu Jesse (xử lý tự tương quan của tín hiệu chồng thời gian).
- Trọng số trigger theo multiplicative weights / Thompson sampling có chiết khấu thay cho bước ±0,2 hiện tại.
