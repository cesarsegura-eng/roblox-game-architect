#!/bin/sh
# Put the pinned Luau toolchain on PATH, ahead of Rokit's shims.
#
#     . tools/dev-env.sh
#
# Rokit installs shims in .tools/rokit-root/bin that fail with "The system cannot
# find the path specified (os error 3)" from some shells unless ROKIT_ROOT points
# at the toolchain directory. The failure is quiet: eighteen Lute tests fail with
# no indication of why. This puts the real binaries first instead, and refuses to
# finish unless each one reports the version aftman.toml pins, so it cannot drift
# away from the pins without saying so.
#
# Source it, do not run it: it changes PATH in your shell.

rga_self=${BASH_SOURCE:-$0}
rga_root=$(cd "$(dirname "$rga_self")/.." 2>/dev/null && pwd)
[ -f "$rga_root/aftman.toml" ] || rga_root=$PWD

if [ ! -f "$rga_root/aftman.toml" ]; then
    echo "dev-env: run this from the repository root." >&2
    unset rga_self rga_root
    return 1 2>/dev/null || exit 1
fi

rga_storage="$rga_root/.tools/rokit-root/tool-storage"
if [ ! -d "$rga_storage" ]; then
    echo "dev-env: no toolchain under .tools/. Run 'rokit install --no-trust-check'." >&2
    unset rga_self rga_root rga_storage
    return 1 2>/dev/null || exit 1
fi

# One line per tool: "name owner/repo@version", read from the pins themselves.
rga_pins=$(
    awk -F'"' '/^(rojo|selene|stylua|lute) *=/ { split($0, k, " ="); print k[1] ":" $2 }' \
        "$rga_root/aftman.toml"
)
if [ -z "$rga_pins" ]; then
    echo "dev-env: could not read the [tools] pins from aftman.toml." >&2
    unset rga_self rga_root rga_storage rga_pins
    return 1 2>/dev/null || exit 1
fi

# Rokit stores a tool under a lower-cased owner/repo.
rga_prefix=""
for rga_entry in $rga_pins; do
    rga_spec=${rga_entry#*:}
    rga_slug=$(echo "${rga_spec%@*}" | tr '[:upper:]' '[:lower:]')
    rga_dir="$rga_storage/$rga_slug/${rga_spec#*@}"
    if [ ! -d "$rga_dir" ]; then
        echo "dev-env: ${rga_entry%%:*} is not installed at $rga_dir." >&2
        echo "dev-env: run 'rokit install --no-trust-check'." >&2
        unset rga_self rga_root rga_storage rga_pins rga_prefix
        unset rga_entry rga_spec rga_slug rga_dir
        return 1 2>/dev/null || exit 1
    fi
    rga_prefix="$rga_dir:$rga_prefix"
done

PATH="$rga_prefix$PATH"
export PATH

# Prove it rather than assume it.
rga_failed=""
for rga_entry in $rga_pins; do
    rga_name=${rga_entry%%:*}
    rga_version=${rga_entry#*@}
    rga_reported=$("$rga_name" --version 2>&1) || rga_reported="(did not run)"
    case "$rga_reported" in
        *"$rga_version"*) echo "dev-env: $rga_name $rga_version" ;;
        *)
            echo "dev-env: $rga_name reported '$rga_reported', expected $rga_version" >&2
            rga_failed="yes"
            ;;
    esac
done

unset rga_self rga_root rga_storage rga_pins rga_prefix
unset rga_entry rga_spec rga_slug rga_dir rga_name rga_version rga_reported

if [ -n "$rga_failed" ]; then
    unset rga_failed
    return 1 2>/dev/null || exit 1
fi
unset rga_failed
