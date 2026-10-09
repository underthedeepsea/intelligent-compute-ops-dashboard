#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
registry= version= platform= push=false
usage() { echo "Usage: $0 --registry HOST/NAMESPACE --version VERSION --platform linux/amd64 [--push]"; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --registry|--version|--platform)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$1" in --registry) registry=$2;; --version) version=$2;; --platform) platform=$2;; esac
      shift 2;;
    --push) push=true; shift;;
    --help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done
[ -n "$registry" ] && [ -n "$version" ] && [ -n "$platform" ] || { usage >&2; exit 2; }
case "$registry" in *[!a-zA-Z0-9._:/-]*|/*|*/|*://*) echo 'Invalid registry namespace' >&2; exit 2;; esac
case "$version" in latest|*[!a-zA-Z0-9_.-]*|.*|-*) echo 'Use an explicit valid version tag, not latest' >&2; exit 2;; esac
[ "${#version}" -le 128 ] || { echo 'Version tag is too long' >&2; exit 2; }
case "$platform" in *[!a-zA-Z0-9_/,.-]*) echo 'Invalid platform' >&2; exit 2;; esac
if [ "$push" = true ]; then output=--push; else
  case "$platform" in *,*) echo 'Multi-platform builds require --push' >&2; exit 2;; esac
  output=--load
fi
for target in api web; do
  docker buildx build --file "$project_root/deploy/Dockerfile" --target "$target" \
    --platform "$platform" --tag "$registry/control-$target:$version" "$output" "$project_root"
done
