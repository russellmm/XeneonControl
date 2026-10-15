#!/usr/bin/env bash
set -euo pipefail
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends python3 python3-tk libusb-1.0-0 python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
sudo install -m 0644 "$task_dir/70-xeneon-control.rules" /etc/udev/rules.d/70-xeneon-control.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=1b1c --attr-match=idProduct=0d05
echo 'Setup complete. Reconnect the USB data cable if needed, then run: bash launch-ubuntu.sh'
