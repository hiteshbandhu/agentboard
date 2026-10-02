#!/bin/zsh
# Stands in for the hallmonitor CLI when capturing the macOS app for the
# launch video: demo fleet, fake usage ledger, no real machine data.
here=${0:A:h}
export HOME=$here/out/home XDG_DATA_HOME=$here/out/xdg HALLMONITOR_HOSTNAME=macbook-pro
bin=$here/../bin/hallmonitor
if [[ ${1:-} == usage ]]; then exec $bin "$@" --no-update; fi
exec $bin --demo "$@"
