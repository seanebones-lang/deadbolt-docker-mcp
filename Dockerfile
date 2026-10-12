FROM rust:1.85-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4 AS engine
WORKDIR /source
ADD --checksum=sha256:bbfe4f285a9dfe1489cc8c3dbac51425e5cc13c7a2d2886ce4891dfa02841e9f https://codeload.github.com/seanebones-lang/deadbolt/tar.gz/d166c7b039800bbd6d8acb1bc5c66f9add472f5f /source/engine.tar.gz
RUN tar -xzf engine.tar.gz --strip-components=1 && rm engine.tar.gz
RUN cargo build --locked --release --bin deadbolt

FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
LABEL org.opencontainers.image.title="DeadBolt MCP" \
      org.opencontainers.image.version="2.0.0-rc.2" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/seanebones-lang/deadbolt-docker-mcp"
WORKDIR /opt/deadbolt
COPY --from=engine /source/target/release/deadbolt /usr/local/bin/deadbolt
COPY server ./server
COPY build ./build
COPY manifest.json SOURCE.json LICENSE NOTICE THIRD-PARTY.md THIRD-PARTY-NOTICES.txt ./
COPY --from=engine /source/third-party ./third-party
RUN node build/metadata.cjs && \
    useradd --uid 10001 --create-home --shell /usr/sbin/nologin deadbolt && \
    chmod -R a-w /opt/deadbolt && chmod a-w /usr/local/bin/deadbolt
USER 10001:10001
ENTRYPOINT ["node", "/opt/deadbolt/server/entry.cjs"]
