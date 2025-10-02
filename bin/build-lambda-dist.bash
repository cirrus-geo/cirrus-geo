#!/usr/bin/env bash

set -euxo pipefail

LAMBDA_ARCHITECTURES="arm64 x86_64"
LAMBDA_PYTHON_VERSIONS="3.12 3.13"
CIRRUS_LAMBDA_ZIP_DIR="${CIRRUS_LAMBDA_ZIP_DIR:-.}"


find_this () {
    THIS="${1:?'must provide script path, like "${BASH_SOURCE[0]}" or "$0"'}"
    trap "echo >&2 'FATAL: could not resolve parent directory of ${THIS}'" EXIT
    [ "${THIS:0:1}"  == "/" ] || THIS="$(pwd -P)/${THIS}"
    THIS_DIR="$(dirname -- "${THIS}")"
    THIS_DIR="$(cd -P -- "${THIS_DIR}" && pwd)"
    THIS="${THIS_DIR}/$(basename -- "${THIS}")"
    trap "" EXIT
}


setup_venv() {
    local lambda_architecture lambda_python_version lambda_platform
    lambda_architecture="${1:?'provide architecture (arm64 or x86_64)'}"
    lambda_python_version="${2:?'provide python version (e.g. 3.12)'}"

    if [[ "$lambda_architecture" == "arm64" ]]; then
        lambda_platform="aarch64-manylinux2014"
    elif [[ "$lambda_architecture" == "x86_64" ]]; then
        lambda_platform="x86_64-manylinux2014"
    else
        echo >&2 "ERROR: LAMBDA_ARCHITECTURE must be 'arm64' or 'x86_64', got: ${lambda_architecture}"
        exit 1
    fi

    local venv
    venv="${3:?'provide path to directory for venv'}"
    uv venv --python "${lambda_python_version}" "${venv}"
    source "${venv}/bin/activate"
    uv sync --python-platform "${lambda_platform}" --locked --no-dev --active --no-editable
}


make_zip_base() {
    local venv dest _python site_packages
    venv="${1:?'provide path to virtual env with cirrus installed'}"
    dest="${2:?'provide path to output zip file'}"
    _python="${venv}/bin/python"
    site_packages="$("${_python}" -c "import sysconfig as s; print(s.get_path('purelib'))")"
    (
        cd "${site_packages}"
        zip -r "${dest}" .
        # we don't need or want pip cluttering up our lambda zip (if it exists)
        zip --delete "${dest}" 'pip/*' ||:
    )
}


get_lambda_handlers() {
    local venv
    venv="${1:?'provide path to virtual env with cirrus installed'}"
    "${venv}/bin/python" <<EOP
from pathlib import Path
from cirrus import lambda_functions

reader = lambda_functions.__loader__.get_resource_reader()

for path in map(lambda x: reader.path / Path(x), reader.contents()):
    if path.suffix not in ('.py', '.pyc'):
        continue
    if path.stem == '__init__':
        continue

    print(path)
EOP
}


build_for_config() {
    local lambda_architecture lambda_python_version zipfile venv handler output_zip
    lambda_architecture="${1:?'provide architecture'}"
    lambda_python_version="${2:?'provide python version'}"

    # Create output filename with architecture and python version
    output_zip="${CIRRUS_LAMBDA_ZIP_DIR}/cirrus-lambda-dist-py${lambda_python_version}-${lambda_architecture}.zip"

    zipfile="$(mktemp -u)"
    (
        trap "rm -f '${zipfile}'" EXIT

        venv="$(mktemp -d)"
        (
            trap "rm -rf '${venv}'" EXIT

            setup_venv "${lambda_architecture}" "${lambda_python_version}" "${venv}"
            make_zip_base "${venv}" "${zipfile}"
            get_lambda_handlers "${venv}" | while IFS= read -r handler; do
                (
                    cd "$(dirname "${handler}")"
                    zip "${zipfile}" "$(basename "${handler}")"
                )
            done
        )

        mv "${zipfile}" "${output_zip}"
        trap "" EXIT
    )
}


main() {
    find_this "${BASH_SOURCE[0]}"

    for lambda_python_version in ${LAMBDA_PYTHON_VERSIONS}; do
        for lambda_architecture in ${LAMBDA_ARCHITECTURES}; do
            echo "Building for Python ${lambda_python_version} on ${lambda_architecture}"
            build_for_config "${lambda_architecture}" "${lambda_python_version}"
        done
    done
}


main
