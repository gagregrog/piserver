SERVICE  = piserver
VENV     = /home/pi/piserver/venv
PIP      = $(VENV)/bin/pip
SYSTEMD  = /etc/systemd/system/$(SERVICE).service

.PHONY: setup deps update start stop restart status logs read-sony repair

## First-time setup: create venv, install deps, register and start service
setup: $(VENV) $(SYSTEMD) deps
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE)
	sudo systemctl start $(SERVICE)

$(VENV):
	sudo apt install -y python3-full python3-pip ir-keytable
	python3 -m venv $(VENV)

$(SYSTEMD): $(SERVICE).service
	sudo ln -sf $(CURDIR)/$(SERVICE).service $(SYSTEMD)

## Install/update Python dependencies
deps: $(VENV)
	$(PIP) install -r requirements.txt

## Pull latest changes, reinstall deps if needed, restart service
update:
	git pull
	$(MAKE) deps
	$(MAKE) restart

## Service management
start:
	sudo systemctl start $(SERVICE)
	sudo systemctl status $(SERVICE) --no-pager

stop:
	sudo systemctl stop $(SERVICE)

restart:
	sudo systemctl restart $(SERVICE)
	sudo systemctl status $(SERVICE) --no-pager

status:
	sudo systemctl status $(SERVICE) --no-pager

logs:
	sudo journalctl -u $(SERVICE) -f

## Decode a Sony remote button — point remote at the IR receiver and press a button
read-sony:
	bash scripts/read-sony.sh

## Repair the WM8960 audio HAT when it disappears from aplay -l
repair:
	@echo "This will reinstall the WM8960 DKMS module and reboot."
	@printf "Continue? [y/N] " && read ans && [ "$$ans" = y ] || exit 0
	sudo dkms remove wm8960-soundcard/1.0 --all
	cd /home/pi/WM8960-Audio-HAT && sudo ./install.sh
	sudo reboot
