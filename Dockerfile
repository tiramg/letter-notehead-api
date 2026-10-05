FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    AUDIVERIS_BIN=/opt/audiveris/bin/Audiveris \
    MUSESCORE_BIN=/opt/musescore/squashfs-root/AppRun \
    DISPLAY=:99 \
    QT_QPA_PLATFORM=xcb

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 python3-pil poppler-utils xvfb xauth \
    libasound2t64 libegl1 libgl1 libglib2.0-0 libgtk-3-0t64 libnss3 libopengl0 \
    libx11-xcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
    libxkbcommon-x11-0 libxrender1 tesseract-ocr fonts-dejavu-core fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

ARG AUDIVERIS_VERSION=5.11.0
# Audiveris' Debian post-install script registers a desktop launcher. Minimal
# containers do not create the XDG system menu directories by default.
RUN mkdir -p /etc/xdg/menus/applications-merged \
    /usr/share/applications \
    /usr/share/desktop-directories
RUN python3 - <<'PY' > /tmp/audiveris-url
import json, os, urllib.request
tag=os.environ.get('AUDIVERIS_VERSION','5.11.0')
data=json.load(urllib.request.urlopen(f'https://api.github.com/repos/Audiveris/audiveris/releases/tags/{tag}'))
assets=[a['browser_download_url'] for a in data['assets'] if a['name'].endswith('ubuntu24.04-x86_64.deb')]
assert assets, 'Audiveris Ubuntu 24.04 installer not found'
print(assets[0])
PY
RUN curl -fL "$(cat /tmp/audiveris-url)" -o /tmp/audiveris.deb \
    && apt-get update && apt-get install -y /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/audiveris.deb /tmp/audiveris-url

RUN mkdir -p /opt/musescore && python3 - <<'PY' > /tmp/musescore-url
import json, urllib.request
data=json.load(urllib.request.urlopen('https://api.github.com/repos/musescore/MuseScore/releases/latest'))
assets=[a['browser_download_url'] for a in data['assets'] if a['name'].endswith('x86_64.AppImage')]
assert assets, 'MuseScore x86_64 AppImage not found'
print(assets[0])
PY
RUN curl -fL "$(cat /tmp/musescore-url)" -o /tmp/musescore.AppImage \
    && chmod +x /tmp/musescore.AppImage \
    && cd /opt/musescore && /tmp/musescore.AppImage --appimage-extract >/dev/null \
    && rm /tmp/musescore.AppImage /tmp/musescore-url

WORKDIR /app
COPY server.py engrave.py render.py photo_prep.py review.html review.css review.js start-cloud.sh ./
RUN chmod +x start-cloud.sh

EXPOSE 10000
CMD ["./start-cloud.sh"]
