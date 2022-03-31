import asyncio
import secrets
import uuid
from asyncio import Queue
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, HTTPException, status, WebSocket, Query, Depends, WebSocketDisconnect
from fastapi import security
from fastapi.security import HTTPBasicCredentials
from starlette.requests import Request

import crud
from db import User, Chat, Base, Session, engine
from models import (
    UserCredentials,
    UserPublic,
    ChatInfo,
    ChatCreate,
    MessageInHistory,
    MessageCreate,
)

Base.metadata.create_all(engine)


class Broker:
    def __init__(self):
        self.subscribers: [int, dict[uuid.UUID, Queue]] = defaultdict(dict)

    def subscribe(self, chat_id: int, token: uuid.UUID) -> Queue:
        print("Subbed")
        self.subscribers[chat_id][token] = Queue()
        return self.subscribers[chat_id][token]

    def unsubscribe(self, chat_id: int, token: uuid.UUID):
        print("Unsubbed")
        self.subscribers[chat_id].pop(token)

    async def publish(self, chat_id: int, message: MessageInHistory):
        tasks = [sub.put(message) for sub in self.subscribers[chat_id].values()]
        await asyncio.gather(*tasks)


class HTTPBasicWs(security.HTTPBasic):
    async def __call__(
        self, request: Request = None, ws: WebSocket = None
    ) -> Optional[HTTPBasicCredentials]:
        if request:
            return await super().__call__(request)
        else:
            return await super().__call__(ws)


app = FastAPI()
broker = Broker()
auth_scheme = HTTPBasicWs()


async def get_session() -> Session:
    session = Session()
    try:
        yield session
    finally:
        session.close()


async def get_current_user(
    credentials: security.HTTPBasicCredentials = Depends(auth_scheme),
    ses: Session = Depends(get_session),
) -> User:
    user = crud.get_user_by_name(ses, credentials.username)
    if not user or not secrets.compare_digest(credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


async def get_current_chat(chat_id: int, ses: Session = Depends(get_session)) -> Chat:
    chat = crud.get_chat(ses, chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat does not exist",
        )
    return chat


async def filter_chat_members(
    user: User = Depends(get_current_user), chat=Depends(get_current_chat)
):
    if user not in chat.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you are not a member of this chat",
        )


async def get_chat_stream(chat: Chat = Depends(get_current_chat)):
    token = uuid.uuid4()
    try:
        yield broker.subscribe(chat.id, token)
    finally:
        broker.unsubscribe(chat.id, token)


@app.post("/v1/register", status_code=201)
async def create_user(
    credentials: UserCredentials, ses: Session = Depends(get_session)
):
    user_id = crud.create_user(ses, credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="this username is already taken",
        )
    return user_id


@app.get("/v1/login", response_model=UserPublic)
async def try_login(user: User = Depends(get_current_user)):
    return UserPublic.from_orm(user)


@app.get("/v1/chats", response_model=list[ChatInfo])
async def get_chats(ses: Session = Depends(get_session)):
    return crud.get_chat_list(ses)


@app.post("/v1/chats", response_model=int)
async def create_chat(
    chat: ChatCreate,
    user: User = Depends(get_current_user),
    ses: Session = Depends(get_session),
):
    return crud.create_chat(ses, chat, user.id)


@app.get("/v1/chats/{chat_id}", response_model=ChatInfo)
async def get_chat_info(chat: Chat = Depends(get_current_chat)):
    return chat


@app.post("/v1/chats/{chat_id}/join", response_model=ChatInfo)
async def add_user_to_chat(
    chat: Chat = Depends(get_current_chat),
    user: User = Depends(get_current_user),
    ses: Session = Depends(get_session),
):
    if user not in chat.members:
        chat.members.append(user)
    ses.commit()
    return chat


@app.get(
    "/v1/chats/{chat_id}/history",
    dependencies=[Depends(filter_chat_members)],
    response_model=list[MessageInHistory],
)
async def get_chat_history(
    offset: int = Query(..., ge=0),
    limit: int = Query(..., ge=0),
    chat: Chat = Depends(get_current_chat),
    ses: Session = Depends(get_session),
):
    return crud.get_chat_history(ses, chat.id, offset, limit)


@app.post(
    "/v1/chats/{chat_id}/message",
    dependencies=[Depends(filter_chat_members)],
    response_model=MessageInHistory,
)
async def post_message_to_chat(
    message: MessageCreate,
    user: User = Depends(get_current_user),
    chat: Chat = Depends(get_current_chat),
    ses: Session = Depends(get_session),
):
    msg = crud.create_message(ses, message, user.id, chat.id)
    msg = MessageInHistory.from_orm(msg)
    await broker.publish(chat.id, msg)
    return msg


@app.websocket("/v1/chats/{chat_id}/listen")
async def ws_listen_to_chat(
    ws: WebSocket,
    user: User = Depends(get_current_user),
    chat: Chat = Depends(get_current_chat),
    stream: Queue = Depends(get_chat_stream),
    _=Depends(filter_chat_members),
):
    await ws.accept()
    try:
        while True:
            msg: MessageInHistory = await stream.get()
            await ws.send_text(msg.json())
    except WebSocketDisconnect:
        pass
