FROM rust:1.89-bookworm@sha256:948f9b08a66e7fe01b03a98ef1c7568292e07ec2e4fe90d88c07bb14563c84ff AS engine
WORKDIR /source
ADD --checksum=sha256:7dc28b3f45c77b7c4d901d9fb5066b194e3d56b7934ee75ba0efaafc089ff900 https://codeload.github.com/seanebones-lang/deadbolt/tar.gz/7d130e882d03b9ba82556fb072f646d4191bbe8a /source/engine.tar.gz
RUN tar -xzf engine.tar.gz --strip-components=1 && rm engine.tar.gz
RUN cargo build --locked --release --bin deadbolt

FROM node:22.23.4-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da
LABEL org.opencontainers.image.title="DeadBolt MCP" \
      org.opencontainers.image.version="2.0.2" \
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
