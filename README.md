# CLI Chat
Simple cli chat using WebSockets and FastAPI

## Setup your project

```bash
git clone https://github.com/luminescentglacier/cli-chat
cd cli-chat
python3.10 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

## Run the server

```bash
cd src
uvicorn server:app
```

## Launch the client
First register your account:

```bash
python client.py register -u USERNAME -p PASSWORD
```

Then create a chat room:

```bash
python client.py create -u USERNAME -p PASSWORD
```

After that you can join created chat from any account:

```bash
python client.py join -u USERNAME -p PASSWORD
# follow the on-screen instructions
```
Run another client instance in another terminal window to chat with yourself

## Libraries used

- FastApi
- Pydantic 
- SQLAlchemy
- websocket-client