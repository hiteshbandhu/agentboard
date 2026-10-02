#!/bin/zsh
# Film frames + drive.wav -> two encodes in launch/out:
#   hallmonitor-film.mp4      master, H.264 High, CRF 14 (X, YouTube, release)
#   hallmonitor-film-gh.mp4   under 10 MB, two-pass, for GitHub's inline player
set -euo pipefail
cd "${0:A:h}/out"
in=(-framerate 30 -i film_frames/%04d.png -i drive.wav)
ffmpeg -hide_banner -loglevel error -y $in \
  -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -profile:v high -movflags +faststart \
  -c:a aac -b:a 320k -shortest hallmonitor-film.mp4
for pass in 1 2; do
  ffmpeg -hide_banner -loglevel error -y $in \
    -c:v libx264 -preset slow -b:v 2300k -maxrate 3500k -bufsize 4600k -pass $pass -passlogfile /tmp/hm2pass \
    -pix_fmt yuv420p -profile:v high -movflags +faststart \
    -c:a aac -b:a 160k -shortest $([[ $pass == 1 ]] && echo "-an -f mp4 /dev/null" || echo hallmonitor-film-gh.mp4)
done
ls -la hallmonitor-film*.mp4
