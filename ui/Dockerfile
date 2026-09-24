# Builds ui/dist (the React NOW screen) without needing node >= 22 on the host (the herald-ui conda env, or
# scripts/setup.sh, are the non-Docker way to get the same result).
#
# Runs as the invoking host user (UID/GID passed at build time), not root, so files written into the bind-mounted
# ui/dist and ui/node_modules stay owned by you and `rm -rf ui/dist` from the host works normally afterwards.
FROM node:22-slim
ARG UID=1000
ARG GID=1000
RUN if ! getent group "$GID" >/dev/null; then groupadd -g "$GID" builder; fi \
    && if ! getent passwd "$UID" >/dev/null; then useradd -m -u "$UID" -g "$GID" builder; fi
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN chown -R "$UID:$GID" /app
USER $UID:$GID
CMD ["npm", "run", "build"]
