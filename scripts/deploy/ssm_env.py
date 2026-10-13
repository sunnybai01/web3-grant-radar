"""Keep production settings in SSM Parameter Store and render them into .env.

    # laptop, with the deploy IAM user: upload a filled-in copy of .env.example
    python3 scripts/deploy/ssm_env.py push .env.prod

    # EC2 host, with the instance role (deploy.sh does this)
    python3 scripts/deploy/ssm_env.py pull .env

Every non-empty KEY=value becomes the SecureString parameter <prefix>KEY
(default prefix /grant-radar/prod/). `pull` writes all parameters under the
prefix back as KEY=value with mode 0600, and adds AWS_REGION and COMPOSE_FILE
so plain `docker compose` commands on the host use the production overlay.
Values are never printed. Needs only the standard library and the AWS CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_PREFIX = "/grant-radar/prod/"
COMPOSE_FILE = "docker-compose.yml:docker-compose.prod.yml"
# chat-api refuses to start without the key, and Postgres would otherwise be
# initialised with the default password from docker-compose.yml.
REQUIRED_KEYS = ("POSTGRES_PASSWORD", "CHAT_API_INTERNAL_KEY")

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Written unquoted; anything else is single-quoted, which both docker compose
# and python-dotenv read literally (no ${VAR} interpolation, no escapes).
_UNQUOTED_SAFE = re.compile(r"^[A-Za-z0-9_./:,@+=-]*$")


def parse_env(text: str) -> dict[str, str]:
    """Parse KEY=value lines the way the .env files in this repo are written."""
    values: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _KEY.match(key):
            raise ValueError(f"line {lineno}: expected KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0]
        values[key] = value
    return values


def format_env(values: dict[str, str]) -> str:
    lines = []
    for key in sorted(values):
        value = values[key]
        if not _KEY.match(key):
            raise ValueError(f"{key!r} is not a valid variable name")
        if _UNQUOTED_SAFE.match(value):
            lines.append(f"{key}={value}")
        elif "'" not in value and "\n" not in value:
            lines.append(f"{key}='{value}'")
        else:
            raise ValueError(f"{key}: values with single quotes or newlines are not supported")
    return "\n".join(lines) + "\n"


def missing_required(values: dict[str, str]) -> list[str]:
    return [key for key in REQUIRED_KEYS if not values.get(key)]


def _imds_region() -> str:
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        token = urllib.request.urlopen(token_req, timeout=2).read().decode()
        region_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/placement/region",
            headers={"X-aws-ec2-metadata-token": token},
        )
        return urllib.request.urlopen(region_req, timeout=2).read().decode().strip()
    except OSError:
        return ""


def resolve_region(explicit: str | None) -> str:
    region = explicit or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        configured = subprocess.run(
            ["aws", "configure", "get", "region"], capture_output=True, text=True
        )
        region = configured.stdout.strip()
    region = region or _imds_region()
    if not region:
        sys.exit("Cannot determine the AWS region; pass --region.")
    return region


def _aws(region: str, *args: str) -> dict:
    result = subprocess.run(
        ["aws", "--region", region, "--output", "json", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"aws {args[0]} {args[1]} failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "{}")


def push(env_file: Path, prefix: str, region: str) -> None:
    values = {k: v for k, v in parse_env(env_file.read_text()).items() if v}
    missing = missing_required(values)
    if missing:
        sys.exit(f"{env_file} is missing required values: {', '.join(missing)}")
    for key, value in sorted(values.items()):
        # --cli-input-json keeps the CLI from fetching values that look like URLs.
        request = {"Name": prefix + key, "Value": value, "Type": "SecureString", "Overwrite": True}
        _aws(region, "ssm", "put-parameter", "--cli-input-json", json.dumps(request))
        print(f"put {prefix}{key}")
    print(f"{len(values)} parameters written under {prefix} in {region}.")


def pull(env_file: Path, prefix: str, region: str) -> None:
    response = _aws(
        region, "ssm", "get-parameters-by-path",
        "--path", prefix, "--recursive", "--with-decryption",
    )
    values = {p["Name"].rsplit("/", 1)[-1]: p["Value"] for p in response.get("Parameters", [])}
    missing = missing_required(values)
    if missing:
        sys.exit(f"SSM {prefix} is missing required parameters: {', '.join(missing)}")
    values.setdefault("AWS_REGION", region)
    values.setdefault("COMPOSE_FILE", COMPOSE_FILE)

    body = (
        f"# Generated by scripts/deploy/ssm_env.py from SSM {prefix} ({region}).\n"
        "# Change the parameters and redeploy instead of editing this file.\n"
        + format_env(values)
    )
    env_file = env_file.resolve()
    fd, tmp = tempfile.mkstemp(dir=env_file.parent, prefix=".env.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, 0o600)
        os.replace(tmp, env_file)
    except BaseException:
        os.unlink(tmp)
        raise
    print(f"Wrote {len(values)} variables to {env_file}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("push", "pull"))
    parser.add_argument("env_file", type=Path)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--region")
    args = parser.parse_args()

    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    region = resolve_region(args.region)
    if args.command == "push":
        push(args.env_file, prefix, region)
    else:
        pull(args.env_file, prefix, region)


if __name__ == "__main__":
    main()
