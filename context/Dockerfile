FROM docker.io/library/node@sha256:c190e697545bdb4fb32b29c0f47bf742f3c3d974965b825f1437aa127ee7b866
USER root
ENV PNPM_CONFIG_IGNORE_SCRIPTS=true PNPM_CONFIG_IGNORE_PNPMFILE=true
RUN node -e 'if(process.versions.node!=="22.20.0") process.exit(1)' && npm install --global --ignore-scripts --no-audit --no-fund pnpm@10.11.0 && test "$(pnpm --version)" = "10.11.0"
COPY --chmod=600 dependency-input/ /opt/cirujano/dependency-input/
COPY --chmod=600 harness.mjs recipe.json build-manifest.mjs /opt/cirujano/
WORKDIR /opt/cirujano/dependency-input
RUN pnpm fetch --store-dir /opt/cirujano/store --ignore-scripts --ignore-pnpmfile
RUN node /opt/cirujano/build-manifest.mjs
RUN find /opt/cirujano -type f -exec chmod 0444 {} + && find /opt/cirujano -type d -exec chmod 0555 {} +
RUN mkdir -p /workspace && chown 65534:65534 /workspace && chmod 700 /workspace
WORKDIR /workspace
RUN mkdir -p /home/runner/setup-pnpm/node_modules/.bin && ln -s /usr/local/bin/pnpm /home/runner/setup-pnpm/node_modules/.bin/pnpm && chmod 0555 /home/runner /home/runner/setup-pnpm /home/runner/setup-pnpm/node_modules /home/runner/setup-pnpm/node_modules/.bin
