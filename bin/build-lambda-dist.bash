#!/usr/bin/env bash

set -euxo pipefail

CIRRUS_LAMBDA_ZIP="./cirrus-lambda-dist.zip"


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
    local venv
    venv="${1:?'provide path to directory for venv'}"
    uv venv "${venv}"
    source "${venv}/bin/activate"
    uv sync --locked --no-dev --active --no-editable
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


main() {
    find_this "${BASH_SOURCE[0]}"

    local zipfile venv handler lambda_name tmp_zip

    zipfile="$(mktemp -u)"
    (
        trap "rm -f '${zipfile}'" EXIT

        venv="$(mktemp -d)"
        (
            trap "rm -rf '${venv}'" EXIT

            setup_venv "${venv}"
            make_zip_base "${venv}" "${zipfile}"
            get_lambda_handlers "${venv}" | while IFS= read -r handler; do
                (
                    cd "$(dirname "${handler}")"
                    zip "${zipfile}" "$(basename "${handler}")"
                )
            done
        )

        mv "${zipfile}" "${CIRRUS_LAMBDA_ZIP}"
        trap "" EXIT
    )
}


main
