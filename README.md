## MPD Pi Bridge

### Setup

Clone the repo onto the Pi, then run:

```bash
make setup
```

This installs system packages, creates the virtualenv, installs dependencies, registers and starts the systemd service.

### Service Commands

```bash
make update   # git pull + install deps + restart
make restart  # restart the service
make start    # start the service
make stop     # stop the service
make status   # show service status
make logs     # tail service logs
```

## Usage

Access the API via the pi's hostname, for example raspberrypi.local.

View the available routes at http://{hostname}.local:8000/docs

Send a post to the available endpoints. For example, to play the queue:

```bash
curl -X POST http://{hostname}.local:8000/play
```

### Restarting Mopidy

The `POST /service/mopidy/restart` endpoint restarts the mopidy service. Because this requires sudo, the `pi` user must be granted passwordless sudo for that specific command.

Run `sudo visudo` on the Pi and add this line at the end of the file:

```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart mopidy
```

Without this, the endpoint returns a `401` error.

### Quick Play

`quickplay.json` contains a list of artist/album targets for the `/quickplay/{number}` endpoint. An example is committed to the repo. To customize it locally without your changes being picked up by git, run:

```bash
git update-index --skip-worktree quickplay.json
```

To commit a deliberate update to the example, reverse that first:

```bash
git update-index --no-skip-worktree quickplay.json
```
