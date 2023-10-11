#!/usr/bin/bash

REPO=$1
DATA=$2
WORKFLOW=$3

if [ -z "$REPO" ]; then
    echo "No repo specified"
    exit 1
elif [ -z "$DATA" ]; then
    echo "No data specified"
    exit 1
fi

if [ "$WORKFLOW" ]; then
	URL="https://api.github.com/repos/duckdb/${REPO}/actions/workflows/${WORKFLOW}/dispatches"
else
	URL="https://api.github.com/repos/duckdb/${REPO}/dispatches"
fi

echo "Triggering $REPO with data $DATA"
echo "URL: $URL"

curl -XPOST -u "${PAT_USER}:${PAT_TOKEN}" -H "Accept: application/vnd.github.everest-preview+json" -H "Content-Type: application/json" $URL --data '$(DATA)'

