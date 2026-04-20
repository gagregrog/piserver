#!/bin/bash
set -euo pipefail

dev=$(sudo ir-keytable 2>/dev/null \
    | awk '/^Found/{path=$2} /Name:.*gpio_ir_recv/{print path; exit}' \
    | grep -oE 'rc[0-9]+')

if [ -z "$dev" ]; then
    echo "IR receiver not found — run 'sudo ir-keytable' to list devices"
    exit 1
fi

# Restore the default protocol on exit (including Ctrl+C) so the WM8960
# audio HAT continues to work after reboot. Changing to 'sony' and leaving
# it persists via udev and breaks the soundcard driver at next boot.
trap "echo 'Restoring default protocol...'; sudo ir-keytable -s '$dev' -p rc-6 >/dev/null" EXIT

echo "Using $dev — point remote at receiver and press a button (Ctrl+C to stop)"
sudo ir-keytable -s "$dev" -p sony -t
