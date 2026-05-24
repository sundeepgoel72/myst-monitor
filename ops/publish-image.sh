#!/usr/bin/env bash
set -euo pipefail

image="${MYSTMON_IMAGE:-}"
if [[ -z "$image" ]]; then
  echo "Set MYSTMON_IMAGE, for example docker.io/sundeep/mystmon:0.72" >&2
  exit 1
fi

docker build -t "$image" .
docker push "$image"
echo "Published $image"
