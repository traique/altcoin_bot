# Tối ưu walk-forward trên nến lịch sử OKX – 05/11/2026

**Dữ liệu:** 40 coin USDT-SWAP crypto có volume lớn nhất trên OKX (lọc đúng như bot v4.1), nến 1h / 15m / 5m từ 07/08 đến 05/11/2026; tín hiệu được chấm từ 07/08 đến 04/11 (89 ngày). Công cụ: `tools/walkforward.py`. Nó dùng **đúng** `strategy.evaluate()` để chấm tín hiệu và **đúng** `exits.simulate()` để thoát lệnh trên nến 5m, nên kết quả khớp cách bot thật giao dịch. Phí và trượt giá đã trừ (0,05% × 2 + 0,05%).

**Cách làm:**
- Cho mọi nến 15m, bot chấm tín hiệu xu hướng với cổng lọc nới tối đa. Ra 11.255 tín hiệu ứng viên, mỗi tín hiệu kèm giá trị của từng cổng và kết quả R theo 7 cách thoát.
- Lọc lại các tín hiệu đó theo 3.000 bộ tham số. Mỗi coin và mỗi hướng chỉ tính tối đa 1 tín hiệu/giờ, giống cách bot ghi tín hiệu bóng.
- **Walk-forward:** chọn bộ tốt nhất trên 30 ngày, rồi chấm nó trên 10 ngày **kế tiếp** chưa dùng để chọn. Trượt 10 ngày một lần, được 6 lượt, phủ khoảng 59 ngày ngoài mẫu.
- **Mô phỏng danh mục:** như bot thật. Mỗi lệnh rủi ro 1R, tối đa 2 lệnh mở, mỗi coin chờ 2 giờ sau khi vào, chọn tín hiệu điểm cao nhất.

## 1. Kết luận chính

1. **Tối ưu tham số KHÔNG thắng tham số mặc định ngoài mẫu.** Trên 59 ngày ngoài mẫu: walk-forward **−4,5R** (217 lệnh), mặc định **+1,6R** (238 lệnh). Bộ tham số "tốt nhất nhìn lại" (chọn bằng cả 89 ngày, tức quá khớp) cho **−25,3R** trên cùng giai đoạn. Ở đoạn huấn luyện, các bộ được chọn có t = 2,5–7,8, nhưng sang đoạn kiểm tra thì không giữ được. Đây là dấu hiệu điển hình của quá khớp.
2. **Phần kỹ thuật gần như hoà vốn:** +0,011R mỗi tín hiệu (t = 0,26, 736 tín hiệu). Bộ lọc vẫn có ích: mọi tín hiệu ứng viên chưa qua lọc là **−0,054R** (t = −4,3, 7.673 tín hiệu), lọc kéo về khoảng 0. Nhưng lọc chưa tạo ra lãi.
3. **Chế độ thị trường quyết định, không phải tham số.** Đổi bất kỳ tham số nào quanh mặc định đều cho cùng một kiểu: nửa đầu (08–09) lãi, nửa sau (10–11) lỗ. Nhiều tuần **một phía thắng, phía kia thua** (bảng ở mục 5).
4. **Lớp bảo vệ v4.1 có ích**, cụ thể là khoá phía sau 3 lệnh thua trong 12 giờ. Tham số này được đặt **trước** khi có dữ liệu, vậy mà vẫn dương ở **cả hai nửa** (mục 3).
5. **Nhiều kết luận rút từ vài ngày dữ liệu bị đảo dấu khi xét 89 ngày** (mục 4). Điều này cho thấy các ngưỡng thống kê chặt của bộ tự học (≥ 30 mẫu, t ≥ 2, kiểm soát FDR, 48 giờ/lần) là cần thiết.

## 2. Walk-forward từng lượt

| Lượt | Huấn luyện | Kiểm tra | Bộ được chọn (khác mặc định) | Tín hiệu ngoài mẫu: chọn / mặc định | Danh mục ngoài mẫu: chọn / mặc định |
|---|---|---|---|---|---|
| 1 | 07/08→06/09 | 06/09→16/09 | ADX 26, ATR 0,6, vol 0,5, EMA21 1,5, nhịp 1h 0,8, BTC 0,5, RSI 40, nến 0,5, SL 3,5, điểm 4, không chặn phiên, TP1 2,5R | −0,053R×208 / −0,001R×104 | +7,3R / −4,2R |
| 2 | 17/08→16/09 | 16/09→26/09 | ADX 26, ATR 0,25, vol 0,5, nhịp 0,8, BTC 0,8, RSI 40–65, nến 0,5, SL 4, điểm 4, không chặn, TP1 2R | +0,113R×303 / −0,167R×98 | +1,7R / −1,9R |
| 3 | 27/08→26/09 | 26/09→06/10 | ADX 16, EMA21 1,25, nhịp 1,2, RSI 50, SL 4, không chặn, TP1 2,5R | −0,404R×235 / +0,086R×63 | −11,3R / 0,0R |
| 4 | 06/09→06/10 | 06/10→16/10 | ADX 18, ATR 0,25, EMA21 0,5, nhịp 1,2, RSI 50–80, nến 0,7, SL 4, điểm 5,5, không chặn nến cao trào, TP1 2,5R | −0,014R×36 / +0,153R×65 | +1,6R / +12,4R |
| 5 | 16/09→16/10 | 16/10→26/10 | ADX 16, vol 1,1, EMA21 0,75, nhịp 1,2, BTC 0,2, RSI 50–80, nến 0,7, SL 4, điểm 6, không chặn, TP1 2,5R | +0,341R×25 / +0,110R×112 | +5,5R / +4,9R |
| 6 | 26/09→26/10 | 26/10→04/11 | mặc định, chỉ ATR 0,6 | −0,405R×33 / −0,291R×66 | −9,3R / −9,5R |
| **Tổng** | | | | | **−4,5R (217 lệnh) / +1,6R (238 lệnh)** |

Bộ được chọn nhảy lung tung giữa các lượt (ADX 26 → 16 → 18, chặn phiên lúc bật lúc tắt). Đó là dấu hiệu tối ưu đang khớp theo nhiễu chứ không phải tìm ra quy luật.

## 3. Lớp bảo vệ (bot/protections.py) trên danh mục, tham số mặc định

| Biến thể | Toàn kỳ (89 ngày) | Ngoài mẫu (từ ngày 30) | Tín hiệu bị chặn, nếu vào thì sẽ có |
|---|---|---|---|
| Không bảo vệ | +2,7R, 347 lệnh, sụt tối đa −13,7R | +2,7R | – |
| **Đủ lớp bảo vệ v4.1** | **+10,6R**, 328 lệnh, sụt −12,7R | **+7,9R** | 37 tín hiệu, **−0,34R** (ngoài mẫu −0,58R) |
| Chỉ khoá phía theo lệnh thua (≥ 3 lệnh/12h) | +13,6R | +10,9R | 33 tín hiệu, −0,42R |
| Chỉ khoá phía theo tín hiệu bóng (≥ 80%, ≥ 10 coin) | +2,7R (chưa kích hoạt lần nào) | +2,7R | 0 |
| Chỉ khoá coin vừa thua | +0,8R | +0,8R | 8 tín hiệu, +0,07R (quá ít để kết luận) |
| Khoá phía 12h thay vì 6h | +1,9R | +5,0R | 58 tín hiệu, −0,14R |

Độ nhạy theo hai nửa thời gian (danh mục; khi không bảo vệ: nửa đầu −0,8R, nửa sau +3,5R):
- **≥ 3 lệnh thua / 12h (mặc định): nửa đầu +6,3R, nửa sau +7,3R.** Đây là thiết lập duy nhất dương ở cả hai nửa.
- ≥ 2 lệnh thua / 12h: +10,1R rồi −6,0R. ≥ 2 lệnh / 24h: +10,1R rồi −12,0R. Cả hai đều không ổn định.
- Quy tắc theo tín hiệu bóng: không có ngưỡng nào ổn định ở cả hai nửa (thử 3–8 coin, 70–100%, cửa sổ 12/24h). Mặc định ≥ 10 coin nên giữ như lưới an toàn cho ngày cực đoan.

## 4. Các kết luận cũ, xét lại trên 89 ngày (mỗi nửa ~45 ngày)

| Nhóm | Nửa đầu (08–09) | Nửa sau (10–11) | Nhận xét |
|---|---|---|---|
| Phiên 13h–19h VN (đang chặn sẵn từ v3.2) | **+0,22R** (n=180, t=+2,7) | −0,14R (n=200, t=−2,0) | Đảo dấu theo giai đoạn |
| Xu hướng 1h đã chạy lâu (ADX 1h ≥ 35, đang trừ 1 điểm) | **+0,33R** (n=218, t=+4,3) | −0,20R (n=181, t=−2,7) | Đảo dấu |
| Long khi RSI 1h > 68 | +0,44R (n=71, t=+3,1) | −0,05R (n=36) | Đảo dấu |
| Phiên 0h–7h VN (đang chặn) | −0,03R | −0,04R | Hơi âm ở cả hai nửa, giữ chặn là hợp lý |
| Điểm hợp lưu | Không liên quan tới kết quả (5,0 → 8,0 đều quanh 0) | | Khớp kết luận v3.2 |

- **Bỏ điểm trừ "xu hướng 1h đã chạy lâu":** tốt hơn ở **cả hai nửa** (+0,153R / −0,030R so với +0,070R / −0,048R). Trên toàn kỳ được 912 tín hiệu +0,061R, danh mục **+8,5R** so với +2,7R.
- **Điểm trừ "volume cao trào":** không có tác dụng, vì luật `climax_volume` đã chặn những tín hiệu đó rồi.
- **Cách thoát:** TP1 2,5R có kỳ vọng cao nhất trên toàn kỳ (+0,066R so với +0,011R của TP1 1R). Nhưng ở nửa sau nó kém hơn (−0,086R so với −0,048R), nên không ổn định.
- **Cổng "cách EMA21 ≤ 1 ATR" và "ATR ≥ 0,35%":** nới ra (1,25–1,5 ATR; ATR 0,25%) làm kết quả **xấu hơn ở cả hai nửa**. Mức hiện tại đúng.

## 5. Long / short theo tuần (tham số mặc định)

| Tuần (thứ Hai) | LONG | SHORT |
|---|---|---|
| 10/08 | −0,51R (n=20) | −0,26R (n=55) |
| 17/08 | +0,22R (n=85) | −0,86R (n=6) |
| 31/08 | **+0,34R** (n=98, t=+2,9) | **−0,32R** (n=50, t=−2,7) |
| 07/09 | +0,01R (n=17) | +0,20R (n=113) |
| 14/09 | **+0,41R** (n=85, t=+3,0) | **−0,35R** (n=51, t=−2,9) |
| 21/09 | −0,17R (n=94) | −0,45R (n=42, t=−3,6) |
| 05/10 | −0,06R (n=44) | **+0,41R** (n=53, t=+2,7) |
| 19/10 | −0,20R (n=39) | +0,20R (n=111) |
| 26/10 | −0,27R (n=45) | **−0,46R** (n=64, t=−4,5) |

Thua thường dồn vào **một phía** trong vài ngày. Lớp bảo vệ khoá phía được làm để xử lý đúng trường hợp này.

## 6. Khuyến nghị

1. **Giữ tham số cổng lọc và cách thoát mặc định.** Tối ưu theo từng tháng là khớp nhiễu. Bộ tự học v4.1 chỉ đổi khi có bằng chứng mạnh (≥ 30 mẫu, t ≥ 2, kiểm soát FDR); cách đó an toàn hơn tối ưu hàng loạt.
2. **Giữ lớp bảo vệ v4.1**, nhất là khoá phía theo lệnh thua: đã được kiểm chứng trên 89 ngày.
3. **Nên xem xét** bỏ điểm trừ "xu hướng 1h đã chạy lâu" của v3.2 (tốt hơn ở cả hai nửa). Luật `late_trend` vẫn nằm trong danh mục để bộ tự học tự chặn khi nhóm này lỗ rõ. *Chưa áp dụng, chờ anh quyết.*
4. **Chưa nên chạy tiền thật.** Phần kỹ thuật đang hoà vốn; lãi phải đến từ lớp bảo vệ, quản lý rủi ro và tin tức. Riêng phần tin tức chưa kiểm được trên lịch sử: chạy ảo 2–4 tuần để bộ tự học đo trọng số tin.

## 7. Giới hạn

- Không có tin tức và dòng tiền (OI, funding, long/short) lịch sử → chỉ đánh giá được phần kỹ thuật.
- 40 coin là top volume **hiện tại** (thiên lệch sống sót); chỉ có 1 giai đoạn 89 ngày (08–11/2026).
- EMA200 tính trên toàn chuỗi, trong khi bot tính trên 220 nến (chỉ ảnh hưởng điểm cộng "đúng phía EMA200", +0,5).
- Danh mục mỗi lệnh 1R, chưa tính co giãn rủi ro theo tin tức và co sau chuỗi thua. Nến 5m chạm cả SL lẫn TP trong cùng một nến thì tính là SL (thận trọng).

## 8. Các file

| File | Nội dung |
|---|---|
| `tong_hop.json` | Số liệu tổng hợp (ngoài mẫu, mốc nền, bộ "tốt nhất nhìn lại", lớp bảo vệ) |
| `walk_forward_folds.csv` | Từng lượt: bộ được chọn, kết quả huấn luyện / ngoài mẫu so với mặc định |
| `do_nhay_tham_so.csv` | Đổi từng tham số quanh mặc định, chia 2 nửa thời gian |
| `phan_tich_mac_dinh.csv` | Tham số mặc định theo hướng, tuần, hướng×tuần, trigger, giờ, điểm, luật, coin, cách thoát |
| `lop_bao_ve.csv` | Danh mục với các biến thể lớp bảo vệ |
| `lenh_ngoai_mau_macdinh.csv`, `lenh_ngoai_mau_walkforward.csv` | Từng lệnh mô phỏng ngoài mẫu |
| `tin_hieu_ung_vien.csv.gz` | 11.255 tín hiệu ứng viên: giờ VN, coin, hướng, điểm, trigger, giá trị từng cổng, rào ±1R chạm trước, R theo 7 cách thoát (mở bằng Excel / Google Sheets sau khi giải nén) |
| `du_lieu_meta.json` | Danh sách coin, mốc thời gian |
