"""Trusted operator container only. No tokens in argv, Docker env or output."""
import json
import os
import stat
import sys


def private_secret(filename):
    # Open without following symlinks; reject devices and shared permissions.
    descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("credential file must be a private regular file")
        secret = source.read(4097).strip()
    if not secret or len(secret) > 4096:
        raise ValueError("invalid credential file")
    return secret


def main():
    mode, *args = sys.argv[1:]
    # The image is never the downstream image. Still refuse inherited role
    # credentials so renewal cannot fall back to operator/admission authority.
    os.environ.pop("DEADBOLT_TOKEN", None)
    os.environ.pop("DEADBOLT_ADMISSION_TOKEN", None)
    if mode == "engine":
        if "serve" in args:
            os.environ["DEADBOLT_TOKEN"] = private_secret("/credentials/operator-token")
        os.execv("/usr/local/bin/deadbolt", ["deadbolt", *args])
    elif mode == "heartbeat":
        from deadbolt_supervisor import heartbeat_cli
        sys.argv = ["deadbolt-supervisor-heartbeat", *args]
        return heartbeat_cli()
    elif mode == "status" and len(args) == 1:
        import deadbolt_client
        os.environ["DEADBOLT_TOKEN"] = private_secret("/credentials/operator-token")
        result = deadbolt_client.status(args[0])
        print(json.dumps(result))
        return 0 if result.get("agents") else 1
    elif mode == "renew" and len(args) == 2:
        import deadbolt_client
        result = deadbolt_client.renew_supervised(args[0], private_secret(args[1]))
        print(json.dumps(result))
        return 0 if result == {"ok": True} else 1
    else:
        raise ValueError("expected engine, heartbeat, status AGENT or renew AGENT FILE")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError):
        print("operator setup unavailable; check private files and arguments", file=sys.stderr)
        sys.exit(1)
