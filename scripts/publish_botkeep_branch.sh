#!/usr/bin/env bash
# Đẩy nội dung gói Botkeep (thư mục botkeep/ do scripts/build_botkeep_bundle.py tạo) lên một nhánh riêng
# (mặc định "botkeep") để Botkeep deploy thẳng từ GitHub – cách làm giống repo Stockvn. Nhánh chỉ chứa đúng
# các file của gói, cộng một .gitignore cho data/ và .env.
#
#   scripts/publish_botkeep_branch.sh dist/botkeep [remote] [nhánh]
#
# Chạy trong repo (commit nguồn = HEAD). Mỗi lần chạy thêm một commit lên nhánh nếu gói đổi, không bao giờ
# ép ghi đè lịch sử. GitHub Actions (.github/workflows/botkeep-branch.yml) gọi script này sau mỗi lần main đổi.
set -euo pipefail

SRC=$(cd "${1:?cần thư mục gói, ví dụ dist/botkeep}" && pwd)
REMOTE=${2:-origin}
BRANCH=${3:-botkeep}
SHA=$(git rev-parse --short HEAD)
FROM=$(git rev-parse --abbrev-ref HEAD)              # "main" khi GitHub Actions chạy; tên nhánh khi chạy tay
[ -f "$SRC/run.py" ] || { echo "Không thấy $SRC/run.py: chưa tạo gói?" >&2; exit 1; }

WT=$(mktemp -d)
cleanup() {
  git worktree remove --force "$WT" >/dev/null 2>&1 || true
  rm -rf "$WT"
  git branch -D "$BRANCH-moi" >/dev/null 2>&1 || true      # nhánh mồi khi tạo nhánh lần đầu – không để lại trong repo
}
trap cleanup EXIT

if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
  git fetch -q --depth 1 "$REMOTE" "$BRANCH"
  git worktree add -q --detach "$WT" FETCH_HEAD
else
  git worktree add -q --detach "$WT" HEAD
  git -C "$WT" checkout -q --orphan "$BRANCH-moi"
fi

find "$WT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$SRC"/. "$WT"/
cat > "$WT/.gitignore" <<'EOF'
# Dữ liệu và bí mật nằm trên server, không bao giờ vào nhánh này
.env
bot.env
data/
__pycache__/
*.pyc
EOF

git -C "$WT" add -A
if git -C "$WT" diff --cached --quiet; then
  echo "Nhánh $BRANCH đã đúng gói của $SHA, không đổi."
  exit 0
fi
INFO=""
if [ -f "$SRC/../botkeep.json" ]; then
  INFO=$(python3 - "$SRC/../botkeep.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
b = d["builds"]["altcoin"]
size = f"{d['bytes']:,}".replace(",", ".")
print(f"Altcoin {b['version']} ({b['build']}); {d['files']} file, {d['dirs']} thư mục, {size} B")
PY
)
fi
# BOTKEEP_COMMIT_NOTE (tuỳ chọn): đoạn thêm vào cuối thông điệp commit, vd ghi chú người/nguồn chạy tay
git -C "$WT" commit -q -m "Gói Botkeep từ $FROM $SHA" ${INFO:+-m "$INFO"} ${BOTKEEP_COMMIT_NOTE:+-m "$BOTKEEP_COMMIT_NOTE"}
git -C "$WT" push -q "$REMOTE" "HEAD:refs/heads/$BRANCH"
echo "Đã cập nhật nhánh $BRANCH: gói của $FROM $SHA${INFO:+ – $INFO}"
