## MPD Pi Bridge

### Setup

### Install

Install python and pip:

```bash
sudo apt install python3-full

sudo apt install python3-pip
```

Make and activate the virtualenv

```bash
python3 -m venv /home/pi/piserver/venv
source /home/pi/piserver/venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Install the Service

Symlink it to systemd:

```bash
sudo ln -s /home/pi/piserver/piserver.service /etc/systemd/system/piserver.service
```

### Service Commands

```bash
# enable the service
sudo systemctl enable piserver

# start the service
sudo systemctl start piserver

# restart the service
sudo systemctl daemon-reload

# check on the service
sudo systemctl status piserver

# view the logs
sudo journalctl -u piserver -f
```

## Usage

Access the API via the pi's hostname, for example raspberrypi.local.

View the available routes at http://{hostname}.local:8000/docs

Send a post to the available endpoints. For example, to play the queue;

```bash
curl -X POST http://{hostname}.local:8000/play
```
