# syntax=docker/dockerfile:1.7
FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85 AS build
WORKDIR /src
ARG VITE_API_BASE_URL=
ARG VITE_KEYCLOAK_URL=http://localhost:8081
ARG VITE_KEYCLOAK_REALM=boa-sme-mvp
ARG VITE_KEYCLOAK_CLIENT_ID=boa-sme-spa
ARG VITE_AUTH_DISABLED=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL \
    VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID \
    VITE_AUTH_DISABLED=$VITE_AUTH_DISABLED
COPY frontend/ /src/
RUN mkdir -p /out \
    && if [ -f package.json ]; then \
         if [ -f package-lock.json ]; then npm ci && npm run build; \
         else npm install --no-audit --no-fund && npm run build; fi; \
         if [ -d dist ]; then cp -R dist/. /out/; elif [ -d build ]; then cp -R build/. /out/; else echo 'Frontend build produced no dist/ or build/ directory' >&2; exit 1; fi; \
       else \
         printf '%s\n' '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Frontend non installé</title><body><h1>Frontend non installé</h1><p>L’infrastructure est prête; ajoutez le frontend React dans /frontend puis reconstruisez l’image.</p></body></html>' > /out/index.html; \
       fi

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:daa17b944bac2b578e962da4c61ad72a59233b3c63abea17113acaf4e6b9aea4
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out/ /usr/share/nginx/html/
EXPOSE 8080
