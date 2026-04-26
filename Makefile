SERVICE  = piserver
VENV     = /home/pi/piserver/venv
PIP      = $(VENV)/bin/pip
SYSTEMD  = /etc/systemd/system/$(SERVICE).service

.PHONY: setup deps update start stop restart status logs activate ldr

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

## Run the LDR sensor monitor script
ldr:
	$(VENV)/bin/python3 scripts/sense_stereo.py

