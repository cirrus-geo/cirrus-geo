#!/usr/bin/env bash

set -euo pipefail


find_this () {
    THIS="${1:?'must provide script path, like "${BASH_SOURCE[0]}" or "$0"'}"
    trap "echo >&2 'FATAL: could not resolve parent directory of ${THIS}'" EXIT
    [ "${THIS:0:1}"  == "/" ] || THIS="$(pwd -P)/${THIS}"
    THIS_DIR="$(dirname -- "${THIS}")"
    THIS_DIR="$(cd -P -- "${THIS_DIR}" && pwd)"
    THIS="${THIS_DIR}/$(basename -- "${THIS}")"
    trap "" EXIT
}


maybe_print_help() {
    for arg in "$@"; do
        case "$arg" in
            -h|--help)
                local help
                help="$(pip-compile --help | tail -n +2)"
                echo >&2 "Usage: $CUSTOM_COMPILE_COMMAND [OPTIONS] [SRC_FILES]..."
                echo >&2 ""
                echo >&2 "This is a script wrapping pip-compile."
                echo >&2 "The following is the pip-compile usage."
                echo >&2 "$help"
                exit
                ;;
        esac
    done
}


main () {
    export CUSTOM_COMPILE_COMMAND="$0"
    find_this "${BASH_SOURCE[0]}"

    maybe_print_help "$@"

    cd "${THIS_DIR}/.."

    local compile="pip-compile --strip-extras --allow-unsafe"

    $compile pyproject.toml "$@"

    local infile
    for infile in *.in; do
        [ "$infile" == 'MANIFEST.in' ] && continue
        $compile -o "${infile%.*}.txt" "${infile}" "$@"
    done
}


main "$@"
