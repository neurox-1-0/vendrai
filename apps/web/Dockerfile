FROM node:22.23.1-bookworm-slim AS build
WORKDIR /srv/web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_AUTH_MODE=keycloak
ARG NEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8080
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE NEXT_PUBLIC_KEYCLOAK_URL=$NEXT_PUBLIC_KEYCLOAK_URL
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM node:22.23.1-bookworm-slim AS runtime
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /srv/web
RUN groupadd --system neurox && useradd --system --gid neurox neurox
# The standalone Next.js runtime only needs the Node binary. Remove bundled
# package managers from the production image so their unused dependency trees
# cannot expand the runtime attack surface.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg
COPY --from=build --chown=neurox:neurox /srv/web/public ./public
COPY --from=build --chown=neurox:neurox /srv/web/.next/standalone ./
COPY --from=build --chown=neurox:neurox /srv/web/.next/static ./.next/static
USER neurox
EXPOSE 3000
CMD ["node", "server.js"]
