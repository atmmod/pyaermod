# build_common.sh — helpers shared by scripts/build_*.sh (sourced, not run)
#
# Two things every build script needs:
#
#   * Where the binaries go. With no override every build lands in
#     <repo>/bin, so a second build (a diagnostic variant of the same
#     source, a different compiler, a study that must not touch the
#     checkout's bin/) could only be made by overwriting the first.
#     resolve_bin_dir honours a BIN_DIR override and makes it absolute,
#     because the scripts cd into scratch directories before linking and
#     a relative path would then land somewhere else.
#
#   * What was built. A run manifest that records a binary's SHA-256 is
#     only useful if the build said which hash it produced, with which
#     compiler and which flags. report_binary prints that record right
#     after each link. The flags are the ones actually passed to the
#     compiler, which is not always $FFLAGS (AERMET and the AERSURFACE
#     link use their own).
#
#     The hash identifies the binary, not the recipe. gfortran writes the
#     absolute path of each source file into the binary (its runtime
#     error messages quote it), so the same source built from another
#     directory hashes differently, and so does every build from a
#     downloaded archive, which is unpacked into a fresh temporary
#     directory. Two AERMOD 26135 builds from the same AERMOD_SRC_DIR with
#     the same compiler and flags gave the same hash; two BPIP builds
#     from the same archive did not.
#
# The callers set FC before calling report_binary.

# resolve_bin_dir <repo_root>
#   Sets BIN_DIR to $BIN_DIR when that is set and non-empty, otherwise
#   to <repo_root>/bin; creates it and makes it absolute.
resolve_bin_dir() {
    BIN_DIR="${BIN_DIR:-$1/bin}"
    mkdir -p "$BIN_DIR"
    BIN_DIR="$(cd "$BIN_DIR" && pwd)"
}

# sha256_of <file>  — hex digest; sha256sum on Linux, shasum on macOS.
sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "unavailable (no sha256sum or shasum)"
    fi
}

# aermod_banner_version <aermod binary>
#   The five-digit version AERMOD prints in its usage banner
#   ("Usage: AERMOD 26135  takes either no or one or two parameters."),
#   probed with --help in a throw-away directory because AERMOD drops a
#   --help_ERRMSG.TMP file where it runs. Empty when there is none.
aermod_banner_version() {
    local probe out
    probe="$(mktemp -d)"
    out="$( (cd "$probe" && "$1" --help) 2>&1 || true)"
    rm -rf "$probe"
    printf '%s\n' "$out" | grep -oE 'AERMOD +[0-9]{5}' | head -1 | grep -oE '[0-9]{5}' || true
}

# report_binary <binary> <compile flags> <link flags> [<version>]
#   Prints the build record of one binary.
report_binary() {
    local bin="$1" cflags="$2" lflags="$3" version="${4:-}"
    echo "  Build record: $(basename "$bin")"
    echo "    path:     $bin"
    echo "    sha256:   $(sha256_of "$bin")"
    [ -n "$version" ] && echo "    version:  $version"
    echo "    compiler: $FC ($("$FC" --version 2>&1 | head -1))"
    echo "    compile:  $cflags"
    echo "    link:     $lflags"
    return 0
}
