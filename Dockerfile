FROM rust:1.85-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4 AS engine
WORKDIR /source
ADD --checksum=sha256:a0befa90bba40f017d2a75e1644bbfcb38f4348d780cd3a2310341e23adb1e9c https://codeload.github.com/seanebones-lang/deadbolt/tar.gz/14804f2d512ce814a11de80daa8ca858b1dc7598 /source/engine.tar.gz
RUN tar -xzf engine.tar.gz --strip-components=1 && rm engine.tar.gz
RUN cargo build --locked --release --bin deadbolt

FROM node:22.23.4-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
LABEL org.opencontainers.image.title="DeadBolt MCP" \
      org.opencontainers.image.version="2.0.0" \
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
