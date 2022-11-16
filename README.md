# SYNC BOT

This is a simple bot designed to keep zhinst-qcodes in sync with zhinst-toolkit. 

A large portion of the zhinst-qcodes driver is auto generated based on zhinst-toolkit. 
The generation is implemented in https://github.com/zhinst/zhinst-qcodes/tree/main/generator.
To avoid that, the two repository to get out of sync. 

At the moment, is able to do the following tasks: 
* Checks for every pull request in zhinst-toolkit if its changes cause the 
  autogenerated part in zhinst-qcodes to change.
* If so, it automatically commits them to a branch with the same name.
* If no pull request for this branch exists it will create one automatically.
* This above steps will be repeated for every new change that happens within the 
  pull request.
* If the pull request in zhinst-toolkit is closed, reopened, the bot will apply
  the same action in zhinst-qcodes.
* If a pull request in zhinst-toolkit is merged, it will create a comment for 
  this is zhinst-qcodes. However, it will NOT merge the zhinst-qcodes part 
  automatically.

## Usage

The app uses smee.io (A Webhook payload delivery service). This service sends 
all received payloads to a locally running application. The bypasses the problem
of the bot running within a private network.

The client is called `smee-client` and is a node package. It posts all received 
messages to a local port (localhost:5000). To start the client use the following
command:

```bash
smee -u https://smee.io/<smee-key> --port 5000
```

The bot is implemented through a flask application in `app.py`. It listens 
to a port on the localhost. 

```bash
python app.py --port 5000 --id <app-id> --secret <app-secret>
```

For convenience, a docker container can be used. 

```bash
docker build -t <container-name>  . 
```

The entry point to the docker container is `start_service.sh`.

```bash
./start_service.sh <smee-key> <app-id> <app-secret>
```

