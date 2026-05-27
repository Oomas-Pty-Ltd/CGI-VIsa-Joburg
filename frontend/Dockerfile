# syntax=docker/dockerfile:1
#
# Frontend image: build the CRA app + embeddable widget, serve the static
# output (and reverse-proxy /api) from nginx.

############################  build  ############################
FROM node:20-bookworm-slim AS build

WORKDIR /app

# REACT_APP_* is inlined at BUILD time by CRA. This single value drives both
# the SPA and the embeddable widget (seva-widget.js). It MUST be your public
# API origin (e.g. https://app.example.com) — not empty — otherwise the widget,
# when embedded on a customer's site, would call the customer's origin instead
# of yours. The SPA tolerates the absolute URL fine (same domain in prod).
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .

# Build the widget FIRST so the freshly built seva-widget.js lands in public/
# before craco copies public/ into build/. (The package.json `build:all`
# script runs them in the opposite order, which ships a stale widget.)
RUN yarn build:widget && yarn build

############################  serve  ############################
FROM nginx:1.27-alpine AS serve

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
