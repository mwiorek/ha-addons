# Atlas Frame: renders the maps and pushes them to The Frame. Build context is this folder after
# prep.sh has filled app/ (code, the built-in maps, grids, places, fonts).
FROM python:3.12-slim-bookworm
ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=dev
LABEL io.hass.type="addon" \
      io.hass.name="Atlas Frame" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/mwiorek/ha-addons" \
      org.opencontainers.image.licenses="MIT AND CC-BY-NC-4.0"
ENV PYTHONUNBUFFERED=1 \
    ATLAS_MAPS=/app/maps ATLAS_GRIDS=/app/grids ATLAS_PLACES=/app/places ATLAS_FONTS=/app/fonts \
    ATLAS_MOON=/app/moon.png ATLAS_OWN=/config/maps
RUN pip install --no-cache-dir numpy==2.1.3 Pillow==11.0.0 "samsungframetv>=4.0,<5"
COPY app/ /app/
WORKDIR /app
CMD ["python", "-m", "artmode.service"]
