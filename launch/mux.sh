#!/bin/zsh
# Frames + beat → launch/out/hallmonitor-launch.mp4 (H.264 High, AAC 320k).
set -euo pipefail
cd "${0:A:h}/out"
ffmpeg -hide_banner -loglevel error -y \
  -framerate 30 -i frames/%04d.png -i beat.wav \
  -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -profile:v high -movflags +faststart \
  -c:a aac -b:a 320k -shortest \
  hallmonitor-launch.mp4
ls -la hallmonitor-launch*.mp4
