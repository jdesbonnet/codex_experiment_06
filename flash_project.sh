#!/usr/bin/env bash
set -euo pipefail

RUST_PROFILE=${RUST_PROFILE:-release}
targets=("lpc1114" "ch32v003" "tm4c123gxl")

target_projects() {
  local target=$1

  if [ "${target}" = "lpc1114" ]; then
    find projects -mindepth 2 -maxdepth 2 -type d \
      \( -name "lpc1114_*" -o -name c -o -name rust \) -printf '%P\n' \
      | cut -d/ -f1 \
      | sort -u
    return
  fi

  find projects -mindepth 2 -maxdepth 2 -type d -name "${target}_*" -printf '%P\n' \
    | cut -d/ -f1 \
    | sort -u
}

project_supports_lang() {
  local project=$1
  local target=$2
  local lang=$3

  case "${lang}" in
    c)
      if [ "${target}" = "lpc1114" ]; then
        [[ -d "projects/${project}/${target}_c" || -d "projects/${project}/c" ]]
      else
        [[ -d "projects/${project}/${target}_c" ]]
      fi
      ;;
    rust)
      if [ "${target}" = "lpc1114" ]; then
        [[ -d "projects/${project}/${target}_rust" || -d "projects/${project}/rust" ]]
      else
        [[ -d "projects/${project}/${target}_rust" || -d "projects/${project}/${target}_rust_shim" ]]
      fi
      ;;
    *)
      return 1
      ;;
  esac
}

usage() {
  echo "usage: $0 [project] [lang] [target]" >&2
  echo "  target: ${targets[*]} (default: lpc1114 for positional usage)" >&2
  echo "  project: target-specific project name" >&2
  echo "  lang: c|rust (default: c)" >&2
  echo "  env: RUST_PROFILE=release|debug" >&2
}

project=""
lang="c"
target=""

if [ $# -ge 1 ]; then
  project=$1
fi
if [ $# -ge 2 ]; then
  lang=$2
fi
if [ $# -ge 3 ]; then
  target=$3
fi

if [ -n "${target}" ]; then
  found=0
  for t in "${targets[@]}"; do
    if [ "${target}" = "${t}" ]; then
      found=1
      break
    fi
  done
  if [ ${found} -ne 1 ]; then
    echo "Unknown target: ${target}" >&2
    usage
    exit 2
  fi
fi

if [ "${lang}" != "c" ] && [ "${lang}" != "rust" ]; then
  echo "Unknown language: ${lang}" >&2
  usage
  exit 2
fi

if [ -z "${target}" ]; then
  if [ -z "${project}" ]; then
    select target in "${targets[@]}"; do
      if [ -n "${target}" ]; then
        echo "Selected target: ${target}"
        break
      fi
      echo "Invalid selection."
    done
  else
    target="lpc1114"
  fi
fi

if [ -z "${project}" ]; then
  mapfile -t projects < <(target_projects "${target}")
  if [ ${#projects[@]} -eq 0 ]; then
    echo "No projects found for target: ${target}" >&2
    exit 2
  fi

  select project in "${projects[@]}"; do
    if [ -n "${project}" ]; then
      echo "Selected project: ${project}"
      break
    fi
    echo "Invalid selection."
  done
fi

if ! project_supports_lang "${project}" "${target}" "${lang}"; then
  echo "Project '${project}' does not have a ${target} ${lang} implementation." >&2
  exit 2
fi

echo "Selected target: ${target}"
echo "Selected project: ${project} (${lang})"

./tools/flash.sh --target "${target}" --lang "${lang}" --project "${project}" --profile "${RUST_PROFILE}"
