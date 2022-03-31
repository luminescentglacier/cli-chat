import argparse
import logging
import threading
import time
from base64 import b64encode

import requests
from pydantic import parse_raw_as
from requests.auth import HTTPBasicAuth
from websocket import WebSocketApp

from models import (
    UserCredentials,
    ChatInfo,
    MessageCreate,
    ChatCreate,
    MessageInHistory,
    UserPublic,
)

logging.basicConfig(format="%(message)s", level=logging.INFO)


class Api:
    def __init__(self, credentials: UserCredentials, host: str = "127.0.0.1:8000"):
        self.credentials = credentials
        self.host = host
        self.version = "v1"
        self.url = f"http://{self.host}/{self.version}"
        self.s = requests.Session()
        self.s.auth = HTTPBasicAuth(self.credentials.name, self.credentials.password)

    def register(self):
        r = self.s.post(f"{self.url}/register", data=self.credentials.json())
        if not r.ok:
            raise RuntimeError(f"unable to register user ({r.json()['detail']})")

    def login(self) -> UserPublic:
        r = self.s.get(f"{self.url}/login")
        if not r.ok:
            raise RuntimeError(f"unable to login ({r.json()['detail']})")
        return UserPublic.parse_raw(r.content)

    def get_chats(self) -> list[ChatInfo]:
        r = self.s.get(f"{self.url}/chats")
        if r.ok:
            return parse_raw_as(list[ChatInfo], r.content)
        else:
            raise RuntimeError(f"unable to retrieve chat list: ({r.json()['tail']})")

    def create_chat(self, chat: ChatCreate) -> int:
        r = self.s.post(f"{self.url}/chats", data=chat.json())
        if r.ok:
            return int(r.content)
        else:
            raise RuntimeError(f"unable to create new chat: ({r.json()['tail']})")

    def join_chat(self, chat_id: int) -> ChatInfo:
        r = self.s.post(f"{self.url}/chats/{chat_id}/join")
        if r.ok:
            return ChatInfo.parse_raw(r.content)
        else:
            raise RuntimeError(f"unable to create new chat: ({r.json()['tail']})")

    def send_message(self, chat_id, msg: MessageCreate):
        r = self.s.post(f"{self.url}/chats/{chat_id}/message", data=msg.json())
        if not r.ok:
            raise RuntimeError(f"unable to send message ({r.json()['detail']})")

    def history(
        self, chat_id: int, offset: int = 0, limit: int = 100
    ) -> list[MessageInHistory]:
        r = self.s.get(
            f"{self.url}/chats/{chat_id}/history",
            params={"offset": offset, "limit": limit},
        )
        if r.ok:
            return parse_raw_as(list[MessageInHistory], r.content)
        else:
            raise RuntimeError(
                f"unable to retrieve chat history ({r.json()['detail']})"
            )

    def listen_chat(self, chat_id, **kwargs) -> WebSocketApp:
        credentials = b64encode(
            f"{self.s.auth.username}:{self.s.auth.password}".encode()
        ).decode()
        auth = f"Basic {credentials}"
        app = WebSocketApp(
            f"ws://{self.host}/{self.version}/chats/{chat_id}/listen",
            **kwargs,
            header={"Authorization": auth},
        )
        return app


def delim():
    logging.info("~" * 40)


def register_prompt(api: Api):
    logging.info("Trying to register...")
    try:
        api.register()
    except RuntimeError as err:
        logging.info(f"Error: {err}")
        return
    logging.info("Success!")


def create_chat_prompt(api):
    title = input("Chat title:\n > ")
    req = ChatCreate(title=title)
    try:
        chat_id = api.create_chat(req)
        logging.info(f"Success! Created new chat with ID {chat_id}")
    except RuntimeError as err:
        logging.info(f"Error: {err}")


class ChatApp:
    chat: ChatInfo = None
    user_id: int = None

    def __init__(self, api: Api):
        self.api = api

        delim()
        self.login()
        delim()
        self.join_chat()
        delim()
        self.read_chat_history()
        reading_thread = threading.Thread(target=self.receive_updates)
        reading_thread.start()
        time.sleep(0.5)
        self.receive_user_input()

    def login(self):
        try:
            logging.info(f"Logging in as {self.api.credentials.name}...")
            self.user_id = self.api.login().id
        except RuntimeError as err:
            logging.info(f"Error: {err}")
            exit(1)
        logging.info("Success!")

    def receive_user_input(self):
        while True:
            text = input(" > ")
            self.api.send_message(self.chat.id, MessageCreate(text=text))

    def join_chat(self):
        all_chats = self.api.get_chats()
        if not all_chats:
            logging.info(
                'Error: no available chat rooms. Create one with command "create"'
            )
            exit(1)

        open_chats = list()
        logging.info("Your chats:")
        for chat in all_chats:
            if self.user_id in (m.id for m in chat.members):
                logging.info(
                    f"ID {chat.id}: {chat.title} ({len(chat.members)} member(s))"
                )
            else:
                open_chats.append(chat)
        logging.info("\nOpen chats:")
        for chat in open_chats:
            logging.info(f"ID {chat.id}: {chat.title} ({len(chat.members)} member(s))")

        while True:
            chat_id = int(input("\nJoin chat with ID: "))
            if chat_id not in [chat.id for chat in all_chats]:
                logging.info("Please enter correct chat ID")
            else:
                break

        self.chat = next(chat for chat in all_chats if chat.id == chat_id)

        if self.chat in open_chats:
            try:
                self.api.join_chat(self.chat.id)
            except RuntimeError as err:
                logging.info(f"Error: unable to join the chat ({err})")
                exit(1)

    def read_chat_history(self):
        logging.info("~~~ Chat history ~~~")
        for message in self.api.history(self.chat.id):
            logging.info(f"[{message.timestamp}] {message.user.name}: {message.text}")
        logging.info("~~~ End of chat history ~~~")

    def receive_updates(self):
        logging.info("Connecting to server...")
        wsapp = self.api.listen_chat(self.chat.id)
        wsapp.on_message = self.read_message
        wsapp.on_open = lambda _: logging.info("Connected!")
        wsapp.run_forever()

    def read_message(self, wsapp, data):
        message: MessageInHistory = MessageInHistory.parse_raw(data)
        logging.info(f"\r[{message.timestamp}] {message.user.name}: {message.text}")


def main():
    parser = argparse.ArgumentParser(description="Simple CLI chat using websockets")
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-u", metavar="USERNAME", help="your username", required=True
    )
    parent_parser.add_argument(
        "-p", metavar="PASSWORD", help="your password", required=True
    )
    parent_parser.add_argument(
        "--host", help="server host address (default: 127.0.0.1)", default="127.0.0.1"
    )
    parent_parser.add_argument(
        "--port", help="server port (default: 8000)", default=8000
    )

    subparsers = parser.add_subparsers(title="commands", dest="command")
    register_parser = subparsers.add_parser(
        "register",
        description="Register on server using entered credentials",
        parents=[parent_parser],
    )
    chat_cmd = subparsers.add_parser(
        "join", description="Connect to existing chat room", parents=[parent_parser]
    )
    create_cmd = subparsers.add_parser(
        "create", description="Create new chat room", parents=[parent_parser]
    )

    args = parser.parse_args()
    api = Api(UserCredentials(name=args.u, password=args.p), f"{args.host}:{args.port}")

    match args.command:
        case "register":
            register_prompt(api)
        case "create":
            create_chat_prompt(api)
        case "join":
            ChatApp(api)


if __name__ == "__main__":
    main()
