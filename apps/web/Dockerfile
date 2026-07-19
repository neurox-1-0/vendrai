FROM node:22.17.0-bookworm-slim AS build
WORKDIR /srv/web
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_AUTH_MODE
ARG NEXT_PUBLIC_KEYCLOAK_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE NEXT_PUBLIC_KEYCLOAK_URL=$NEXT_PUBLIC_KEYCLOAK_URL
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM node:22.17.0-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /srv/web
RUN groupadd --system neurox && useradd --system --gid neurox neurox
COPY --from=build --chown=neurox:neurox /srv/web ./
USER neurox
EXPOSE 3000
CMD ["npm", "run", "start"]

