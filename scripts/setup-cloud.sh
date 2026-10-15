#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if command -v sudo >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y ffmpeg
  elif [ "$(id -u)" -eq 0 ]; then
    apt-get update
    apt-get install -y ffmpeg
  else
    echo "Cần cài FFmpeg/ffprobe hoặc chạy trong Codespace có sudo" >&2
    exit 1
  fi
fi

if ! command -v python3 >/dev/null; then
  echo "Cần Python 3.10+" >&2
  exit 1
fi
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo "Cần Node.js 20+ và npm" >&2
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
npm install --no-audit --no-fund
npm install --no-save --no-audit --no-fund @openai/codex

echo "Cài đặt xong. Đăng nhập Codex CLI hoặc cấu hình OPENAI_API_KEY, rồi đặt một video vào input/."


