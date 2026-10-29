#!/usr/bin/env bash
# Convert videos to play smoothly on the GPi Case 2W (640x480 screen).
# Run on your computer (much faster than on the Pi):
#   bash pitato/convert_videos.sh /path/to/videos     (from the Pietato folder)
# Uses settings that are cheap for the Pi to decode (fastdecode, 24 fps, 640x480).
# Output goes to a "pietato" folder inside it: drop those files on the web page
# (http://<your Pi's name>.local:5432), or copy them to ~/Videos on the Pi.

src="${1:-.}"
out="$src/pietato"
mkdir -p "$out"

for f in "$src"/*.{mp4,mkv,avi,mov,webm,m4v,MP4,MKV,MOV}; do
  [ -e "$f" ] || continue
  name="$(basename "${f%.*}")"
  echo "converting: $name"
  ffmpeg -nostdin -y -i "$f" \
    -vf "scale=640:480:force_original_aspect_ratio=decrease,pad=640:480:(ow-iw)/2:(oh-ih)/2,fps=24" \
    -c:v libx264 -profile:v baseline -preset veryfast -tune fastdecode -crf 25 \
    -c:a aac -b:a 128k -ac 2 -ar 48000 \
    "$out/$name.mp4"
done
echo "done -> $out"
