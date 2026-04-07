#!/bin/sh
set -eu

FFMPEG_BIN="${CAMERA_FFMPEG_PATH:-ffmpeg}"
DEVICE_PATH="${CAMERA_DEVICE_PATH:-/dev/video0}"
INPUT_FORMAT="${CAMERA_INPUT_FORMAT:-mjpeg}"
STREAM_PATH="${CAMERA_STREAM_PATH:-camera}"
RTSP_PORT="${CAMERA_RTSP_PORT:-8554}"
WIDTH="${CAMERA_WIDTH:-1280}"
HEIGHT="${CAMERA_HEIGHT:-720}"
FPS="${CAMERA_FPS:-15}"
BITRATE="${CAMERA_VIDEO_BITRATE:-3000000}"

if ! command -v "$FFMPEG_BIN" >/dev/null 2>&1; then
  echo "ffmpeg not found: $FFMPEG_BIN" >&2
  exit 1
fi

if [ ! -e "$DEVICE_PATH" ]; then
  echo "camera device not found: $DEVICE_PATH" >&2
  exit 1
fi

case "$FPS" in
  ''|*[!0-9]*)
    FPS=15
    ;;
esac

case "$WIDTH" in
  ''|*[!0-9]*)
    WIDTH=1280
    ;;
esac

case "$HEIGHT" in
  ''|*[!0-9]*)
    HEIGHT=720
    ;;
esac

case "$BITRATE" in
  ''|*[!0-9]*)
    BITRATE=3000000
    ;;
esac

GOP_SIZE=$((FPS * 2))
if [ "$GOP_SIZE" -le 0 ]; then
  GOP_SIZE=30
fi
BUFFER_SIZE=$((BITRATE * 2))
if [ "$BUFFER_SIZE" -le 0 ]; then
  BUFFER_SIZE=6000000
fi

set -- \
  -hide_banner \
  -loglevel error \
  -fflags nobuffer \
  -flags low_delay \
  -thread_queue_size 1024 \
  -f video4linux2

if [ -n "$INPUT_FORMAT" ]; then
  set -- "$@" -input_format "$INPUT_FORMAT"
fi

set -- "$@" -framerate "$FPS"

if [ "$WIDTH" -gt 0 ] && [ "$HEIGHT" -gt 0 ]; then
  set -- "$@" -video_size "${WIDTH}x${HEIGHT}"
fi

set -- "$@" \
  -i "$DEVICE_PATH" \
  -an \
  -pix_fmt yuv420p \
  -r "$FPS"

TARGET_URL="rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}"

if "$FFMPEG_BIN" -hide_banner -encoders 2>/dev/null | grep -q 'h264_v4l2m2m'; then
  exec "$FFMPEG_BIN" "$@" \
    -c:v h264_v4l2m2m \
    -b:v "$BITRATE" \
    -maxrate "$BITRATE" \
    -bufsize "$BUFFER_SIZE" \
    -g "$GOP_SIZE" \
    -bf 0 \
    -f rtsp \
    -rtsp_transport tcp \
    "$TARGET_URL"
fi

exec "$FFMPEG_BIN" "$@" \
  -c:v libx264 \
  -preset ultrafast \
  -tune zerolatency \
  -b:v "$BITRATE" \
  -maxrate "$BITRATE" \
  -bufsize "$BUFFER_SIZE" \
  -g "$GOP_SIZE" \
  -keyint_min "$GOP_SIZE" \
  -sc_threshold 0 \
  -bf 0 \
  -f rtsp \
  -rtsp_transport tcp \
  "$TARGET_URL"
