#!/usr/bin/env bash

set -euo pipefail

export AWS_ENDPOINT_URL='http://localhost:4566'
export AWS_ACCESS_KEY_ID="testing"
export AWS_SECRET_ACCESS_KEY="testing"
export AWS_SECURITY_TOKEN="testing"
export AWS_SESSION_TOKEN="testing"
export AWS_REGION='us-east-1'

DATA_BUCKET_KEY="CirrusDataBucket"
PAYLOAD_BUCKET_KEY="CirrusPayloadBucket"
ARTIFACT_BUCKET_KEY="CirrusDeploymentArtifactsBucket"


ercho () {
    local msg="${1:?message to echo is required}"
    echo -e >&2 "${msg}"
    [ -z "${2:-}" ] || exit "${2}"
}


find_this () {
    THIS="${1:?'must provide script path, like "${BASH_SOURCE[0]}" or "$0"'}"
    trap "ercho 'FATAL: could not resolve parent directory of ${THIS}'" EXIT
    [ "${THIS:0:1}"  == "/" ] || THIS="$(pwd -P)/${THIS}"
    THIS_DIR="$(dirname -- "${THIS}")"
    THIS_DIR="$(cd -P -- "${THIS_DIR}" && pwd)"
    THIS="${THIS_DIR}/$(basename -- "${THIS}")"
    trap "" EXIT
}


[ "${_USING_LOCALSTACK_CONFIG:-}" == "true" ] || {
    ERR=''
    ERR+='ERROR: $_USING_LOCALSTACK_CONFIG is not `true`\n\n'
    ERR+='HINT: ensure `.env.localstack.example` has been copied to `.env.localstack` '
    ERR+='and that the latter has been sourced like `source .env.localstack` '
    ERR+='before running this script.'
    ercho "${ERR}" 10
}

find_this "${BASH_SOURCE[0]}"

LAMBDA_DIST_BUILD="${THIS_DIR}/build-lambda-dist.py"

ROOT_DIR="${THIS_DIR}/.."
CF_DIR="${ROOT_DIR}/cloudformation"
BUILD_DIR="${CF_DIR}/_build"
CORE="${CF_DIR}/core"
LAMBDA_PACKAGES="${CORE}/lambda-packages"
LAMBDA_ZIP="${LAMBDA_PACKAGES}/cirrus-lambda-dist.zip"
MINIMAL_DIR="${CF_DIR}/workflows/minimal"


_build_lambda_dist() {
    mkdir -p "${LAMBDA_PACKAGES}"
    python "${LAMBDA_DIST_BUILD}" \
        --cpu-arch "${LAMBDA_ARCH}" \
        --python-version "${LAMBDA_PYTHON_VERSION}" \
        --output-zip "${LAMBDA_ZIP}"
}


_get_bucket() {
    local stack_name="${1:?must provide stack name containing bucket}"
    local bucket_key="${2:?must provide bucket key}"

    aws cloudformation describe-stacks \
        --stack-name ${stack_name} \
        --query 'Stacks[0].Outputs[?OutputKey==`'"${bucket_key}"'`].OutputValue' \
        --output text \
        2> /dev/null
}


_empty_bucket() {
    local bucket_name="${1:?must provide bucket name}"
    aws s3 rm "s3://${bucket_name}" --recursive
}


bootstrap() {
    aws cloudformation create-stack \
        --stack-name ${BOOTSTRAP_STACK} \
        --template-body "file://${CF_DIR}/bootstrap/bootstrap.yaml" \
        --parameters \
            "ParameterKey=ResourcePrefix,ParameterValue=${RESOURCE_PREFIX}" \
        --disable-rollback
    aws cloudformation wait stack-create-complete --stack-name ${BOOTSTRAP_STACK}
}


debootstrap() {
    local artifact_bucket="$(_get_bucket "${BOOTSTRAP_STACK}" "${ARTIFACT_BUCKET_KEY}")"
    _empty_bucket "${artifact_bucket}"
    aws cloudformation delete-stack --stack-name "${BOOTSTRAP_STACK}"
    aws cloudformation wait stack-delete-complete --stack-name "${MAIN_STACK}"
}


deploy() {
    local bucket_name="$(_get_bucket "${BOOTSTRAP_STACK}" "${ARTIFACT_BUCKET_KEY}")"
    local packaged_template="${BUILD_DIR}/packaged-template.yaml"

    _build_lambda_dist >/dev/null 2>&1

    (
        cd "${CF_DIR}"
        mkdir -p "${BUILD_DIR}"
    )

    aws cloudformation package \
        --template-file "${CF_DIR}/main.yaml" \
        --s3-bucket "${bucket_name}" \
        --output-template-file "${packaged_template}"
    aws cloudformation deploy \
        --stack-name "${MAIN_STACK}" \
        --template-file "${packaged_template}" \
        --parameter-overrides \
            "ResourcePrefix=${RESOURCE_PREFIX}" \
            "LambdaPythonVersion=${LAMBDA_PYTHON_VERSION}" \
            "LambdaArch=${LAMBDA_ARCH}" \
            "LogLevel=${LOG_LEVEL}" \
            "EnableVpc=false" \
        --capabilities CAPABILITY_NAMED_IAM \
        --disable-rollback

    aws cloudformation deploy \
        --stack-name "${MINIMAL_WORKFLOW_STACK}" \
        --template-file "${MINIMAL_DIR}/state_machine.yaml" \
        --parameter-overrides \
            "ResourcePrefix=${RESOURCE_PREFIX}" \
        --capabilities CAPABILITY_NAMED_IAM \
        --disable-rollback
}


delete() {
    aws cloudformation delete-stack --stack-name "${MINIMAL_WORKFLOW_STACK}"
    aws cloudformation wait stack-delete-complete --stack-name "${MINIMAL_WORKFLOW_STACK}"
    local data_bucket="$(_get_bucket "${MAIN_STACK}" "${DATA_BUCKET_KEY}")"
    local payload_bucket="$(_get_bucket "${MAIN_STACK}" "${PAYLOAD_BUCKET_KEY}")"
    [ -z "${data_bucket}" ] || [ "${data_bucket}" == "None" ] || _empty_bucket "${data_bucket}"
    [ -z "${payload_bucket}" ] || [ "${payload_bucket}" == "None" ] || _empty_bucket "${payload_bucket}"
    aws cloudformation delete-stack --stack-name "${MAIN_STACK}"
    aws cloudformation wait stack-delete-complete --stack-name "${MAIN_STACK}"
}

_test() {
    local total_tests=2 tests_failed=0 fail_rc=0 exp_fail_rc=10

    ercho "Testing success case..."
    <"${MINIMAL_DIR}/payload.json.template" cirrus payload template \
        -x id_suffix "-$(uuidgen)" \
        -x succeed true \
        -x replace true \
        | \
        cirrus manage "${RESOURCE_PREFIX}" run-workflow -p 1 -t 30 && {
            ercho "✅ Test passed"
        } || {
            ercho "❌ Expected rc 0, got ${$?}"
            tests_failed=$((tests_failed+1))
        }

    ercho "Testing failure case..."
    <"${MINIMAL_DIR}/payload.json.template" cirrus payload template \
        -x id_suffix "-$(uuidgen)" \
        -x succeed false \
        -x replace true \
        | \
        cirrus manage "${RESOURCE_PREFIX}" run-workflow -p 1 -t 30 && {
            ercho "❌ Expected rc 10, got 0"
            tests_failed=$((tests_failed+1))
        } || {
            fail_rc=$?
            [ "$fail_rc" -eq "$exp_fail_rc" ] && {
                echo "✅ Test passed"
            } || {
                ercho "❌ Expected rc ${exp_fail_rc}, got ${fail_rc}"
                tests_failed=$((tests_failed+1))
            }
        }

    ercho "---"

    [ "$tests_failed" -eq 0 ] || ercho "❌ Test failures: ${tests_failed} of ${total_tests}" 1

    ercho "✅ All tests passed (${total_tests} of ${total_tests})" 0
}


main() {
    local usage=$(cat <<EOF
USAGE: $0 COMMAND [ COMMAND_OPTS ] [ COMMAND_ARGS ]

cirrus localstack deployment tool

Supported Commands:

  help         show this message
  bootstrap    set up cirrus bootstrap stack
  debootstrap  tear down cirrus bootstrap stack
  deploy       set up/update cirrus sandbox deployment
  delete       tear down cirrus sandbox deployment
  test         submit successful and failing workflow
                 payloads and verify results
EOF
    )

    local cmd="${1:-}"; shift ||:
    case "${cmd:-}" in
        bootstrap)   bootstrap "${@}" ;;
        debootstrap) debootstrap "${@}" ;;
        deploy)      deploy "${@}" ;;
        delete)      delete "${@}" ;;
        test)        _test "${@}" ;;
        help|-h|--help) ercho "${usage}" 0 ;;
        ?*) ercho "unknown command: '$cmd'" 1 ;;
        *)  ercho "${usage}" 0 ;;
    esac
}


main "${@}"
