# Công cụ phân tích (không phải code của bot)

Các script ở đây **không** được bot import và **không** nằm trong bản dựng (`bot/version.py` chỉ tính `bot/*.py` và `run.py`).
Chạy trên máy tính hoặc VPS, không chạy trên Botkeep.

## Tối ưu walk-forward trên nến lịch sử (`walkforward.py`)

Thử hàng nghìn bộ ngưỡng (10 cổng lọc, điểm tối thiểu, chặn phiên, chặn nến cao trào, cách thoát/TP1) trên nến OKX quá khứ,
nhưng **chỉ tin kết quả ngoài mẫu**: mỗi lượt chọn bộ tốt nhất trên 30 ngày rồi chấm trên 10 ngày *tiếp theo* chưa dùng để
chọn, trượt dần tới hết dữ liệu. Dùng đúng `strategy.evaluate()` và `exits.simulate()` của bot (chỉ báo tính sẵn 1 lần cho
cả chuỗi để nhanh). Cần `numpy` (chỉ cho công cụ này, bot không cần).

```bash
pip install numpy
python tools/walkforward.py fetch    --days 90 --coins 40 --data tools/wf_data   # ≈ 25 phút (nến 1h, 15m, 5m)
python tools/walkforward.py events   --data tools/wf_data                          # ≈ 1 phút, 4 nhân
python tools/walkforward.py optimize --data tools/wf_data --out tools/wf_out       # ≈ vài phút
```

Kết quả (`--out`): `tong_hop.json` (tổng hợp), `walk_forward_folds.csv` (từng lượt: bộ được chọn, kết quả huấn luyện và
ngoài mẫu so với mặc định), `do_nhay_tham_so.csv` (đổi từng tham số quanh mặc định, chia 2 nửa thời gian),
`phan_tich_mac_dinh.csv` (tham số mặc định theo hướng, tuần, trigger, giờ, điểm, luật, coin, cách thoát),
`lenh_ngoai_mau_*.csv` (lệnh mô phỏng danh mục ngoài mẫu), `tin_hieu_ung_vien.csv.gz` (mọi tín hiệu ứng viên kèm giá trị
từng cổng và R theo từng cách thoát – tự lọc trên Excel/Google Sheets).

Giới hạn: không có tin tức và dòng tiền (OI, funding, long/short) lịch sử → chỉ tối ưu phần kỹ thuật; danh sách coin là top
volume hiện tại (thiên lệch sống sót); EMA200 tính trên toàn chuỗi (bot tính trên 220 nến); mô phỏng danh mục dùng 1R/lệnh,
tối đa 2 lệnh mở, mỗi coin chờ 2h sau khi vào.

## Đánh giá Kronos trên tín hiệu của bot

[Kronos](https://github.com/shiyu-coder/Kronos) là mô hình nền tảng dự báo nến (MIT). Hai script này kiểm tra xem nó có
dự báo được kết quả các tín hiệu bot đã tạo ra hay không, trước khi tính chuyện tích hợp.

**Cách làm**: với mỗi tín hiệu đã có kết quả bóng, lấy 400 nến 15m đã đóng *trước* thời điểm tín hiệu (không nhìn tương lai),
cho Kronos sinh 24 kịch bản 16 nến (4h), tính xác suất chạm +1R trước SL (`p_tp1`, `p_sl`) và kỳ vọng di chuyển theo R,
rồi so với `outcome_r` thật: tương quan Spearman + kiểm định hoán vị, chia nhóm, so với quyết định AI, hiệu chuẩn.

### Chạy

```bash
git clone https://github.com/shiyu-coder/Kronos.git ../Kronos
python -m venv kvenv && source kvenv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r tools/requirements-kronos.txt

# file JSON: dashboard → Tải dữ liệu → sao lưu toàn bộ
python tools/kronos_eval.py --kronos ../Kronos --data okxbot-all.json --out res_mini.json \
    --model NeoQuasar/Kronos-mini --tok NeoQuasar/Kronos-Tokenizer-2k --ctx 2048
python tools/kronos_analyze.py res_mini.json

# Kronos-small (chậm ~5×) – chia 2 tiến trình song song rồi gộp
for i in 0 1; do python tools/kronos_eval.py --kronos ../Kronos --data okxbot-all.json --shard $i/2 \
    --out res_small_$i.json --model NeoQuasar/Kronos-small --tok NeoQuasar/Kronos-Tokenizer-base --ctx 512 & done; wait
python tools/kronos_analyze.py res_small_0.json res_small_1.json
```

Cần mạng tới OKX (nến lịch sử, API công khai) và HuggingFace (tải model lần đầu).

### Kết quả lần 1 (24/10/2026 – 80 tín hiệu từ 20–23/10, bot v2.9.6–v3.0.2)

| | Kronos-mini | Kronos-small |
|---|---|---|
| Spearman(p_tp1 − p_sl, kết quả) | −0,08 (p = 0,46) | +0,08 (p = 0,51) |
| Kronos ủng hộ | −0,25R/lệnh (n = 26) | +0,06R/lệnh (n = 25) |
| Kronos phản đối | −0,05R/lệnh (n = 54) | −0,19R/lệnh (n = 55) |
| Thời gian / tín hiệu (1 luồng CPU) | 20 s | 96 s |
| RAM đỉnh | 719 MB | ~1 GB |

**Kết luận**: không có giá trị dự báo (hai bản ngược dấu, đều xa ý nghĩa thống kê); xác suất dự báo lệch thực tế
(dự báo thắng < 35% nhưng thực tế ~40%). 80 mẫu chỉ đủ phát hiện chênh lệch lớn (~0,6R) → **chưa tích hợp vào bot**.
Chạy lại khi có 200–300 tín hiệu mới của v3.1; chỉ tính chế độ bóng nếu tương quan có ý nghĩa (p < 0,05).
