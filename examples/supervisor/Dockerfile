ARG DEADBOLT_IMAGE=n11-deadbolt-docker:local
FROM ${DEADBOLT_IMAGE} AS engine
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=engine /usr/local/bin/deadbolt /usr/local/bin/deadbolt
COPY --from=engine /opt/deadbolt/LICENSE /opt/deadbolt/NOTICE /opt/deadbolt/THIRD-PARTY.md /opt/deadbolt/THIRD-PARTY-NOTICES.txt /opt/deadbolt/
COPY --from=engine /opt/deadbolt/third-party /opt/deadbolt/third-party
ADD --checksum=sha256:ce2c04cc68b4f19bf79e7aa63bed5864896ec7d8cb52ecee6f03f5aac8c7e9ac https://github.com/seanebones-lang/deadbolt/releases/download/v2.0.0-rc.2/n11_deadbolt_client-2.0.0rc2-py3-none-any.whl /tmp/n11_deadbolt_client-2.0.0rc2-py3-none-any.whl
RUN python -m pip install --no-cache-dir --no-deps /tmp/n11_deadbolt_client-2.0.0rc2-py3-none-any.whl && \
    rm /tmp/n11_deadbolt_client-2.0.0rc2-py3-none-any.whl && \
    useradd --uid 10001 --create-home --shell /usr/sbin/nologin deadbolt
COPY entry.py /opt/deadbolt-operator/entry.py
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 DEADBOLT_DB=/state/deadbolt.db DEADBOLT_EVENTS=/state/events.jsonl DEADBOLT_SOCK=/control/deadbolt.sock
ENTRYPOINT ["python", "/opt/deadbolt-operator/entry.py"]
