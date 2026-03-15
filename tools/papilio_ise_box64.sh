#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  tools/papilio_ise_box64.sh --ise-root <path> <tool> [args...]
  tools/papilio_ise_box64.sh --ise-root <path> --check

Run Xilinx ISE 14.7 x86_64 command-line tools under Box64 on the Raspberry Pi.

Options:
  --ise-root <path>   Root of the ISE installation tree
  --check             Validate that Box64, amd64 runtime paths, and common ISE tools exist
  --verbose           Print extra diagnostics
  -h, --help          Show this help

Examples:
  tools/papilio_ise_box64.sh --ise-root /opt/Xilinx/14.7/ISE_DS --check
  tools/papilio_ise_box64.sh --ise-root /opt/Xilinx/14.7/ISE_DS xst -h
  tools/papilio_ise_box64.sh --ise-root /opt/Xilinx/14.7/ISE_DS bitgen design.ncd design.bit
EOF
}

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

verbose=0
check_only=0
ise_root=""

while (($#)); do
    case "$1" in
        --ise-root)
            (($# >= 2)) || die "missing value for --ise-root"
            ise_root="$2"
            shift 2
            ;;
        --check)
            check_only=1
            shift
            ;;
        --verbose)
            verbose=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            die "unknown option: $1"
            ;;
        *)
            break
            ;;
    esac
done

[[ -n "$ise_root" ]] || die "missing: --ise-root <path>"
[[ -d "$ise_root" ]] || die "missing: ISE root directory not found: $ise_root"

command -v box64 >/dev/null 2>&1 || die "missing: box64"

amd64_lib1="/usr/x86_64-linux-gnu/lib"
amd64_lib2="/usr/x86_64-linux-gnu/lib64"
[[ -d "$amd64_lib1" ]] || die "missing: $amd64_lib1"
[[ -d "$amd64_lib2" ]] || die "missing: $amd64_lib2"

common_bin="$ise_root/ISE/bin/lin64"
xst_bin="$common_bin/xst"
ngdbuild_bin="$common_bin/ngdbuild"
map_bin="$common_bin/map"
par_bin="$common_bin/par"
bitgen_bin="$common_bin/bitgen"

if ((check_only)); then
    printf 'box64: %s\n' "$(command -v box64)"
    printf 'amd64 runtime: %s\n' "$amd64_lib1"
    printf 'amd64 runtime: %s\n' "$amd64_lib2"
    printf 'ISE root: %s\n' "$ise_root"
    for tool in "$xst_bin" "$ngdbuild_bin" "$map_bin" "$par_bin" "$bitgen_bin"; do
        if [[ -x "$tool" ]]; then
            printf 'found: %s\n' "$tool"
        else
            printf 'missing: %s\n' "$tool"
        fi
    done
    exit 0
fi

(($# >= 1)) || die "missing: <tool> [args...]"

tool_name="$1"
shift

tool_path="$common_bin/$tool_name"
[[ -x "$tool_path" ]] || die "missing: executable tool not found: $tool_path"

export BOX64_LD_LIBRARY_PATH="$amd64_lib1:$amd64_lib2"

if ((verbose)); then
    printf 'using box64: %s\n' "$(command -v box64)"
    printf 'using ISE root: %s\n' "$ise_root"
    printf 'using tool: %s\n' "$tool_path"
    printf 'BOX64_LD_LIBRARY_PATH=%s\n' "$BOX64_LD_LIBRARY_PATH"
fi

exec box64 "$tool_path" "$@"
