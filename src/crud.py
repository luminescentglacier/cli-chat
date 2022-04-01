from datetime import datetime
from typing import Optional

from sqlalchemy import select, exc
from sqlalchemy.orm import subqueryload

from db import User, Chat, Session, Message
from models import UserCredentials, ChatCreate, MessageCreate

import syslog

syslog.openlog("cli-chat")


def get_user(ses: Session, user_id: int) -> Optional[User]:
    return ses.get(User, user_id)


def get_user_by_name(ses: Session, name: str) -> Optional[User]:
    q = select(User).where(User.name == name)
    return ses.execute(q).scalar_one_or_none()


def create_user(ses: Session, credentials: UserCredentials) -> Optional[int]:
    user = User(name=credentials.name, password=credentials.password)
    ses.add(user)
    try:
        ses.commit()
        return user.id
    except exc.IntegrityError:
        return None


def create_chat(
    ses: Session, chat_info: ChatCreate, owner_user_id: int
) -> Optional[int]:
    chat = Chat(title=chat_info.title)
    chat.members.append(ses.get(User, owner_user_id))
    try:
        ses.commit()
        return chat.id
    except exc.IntegrityError as err:
        return None


def get_chat(ses: Session, chat_id) -> Optional[User]:
    return ses.get(Chat, chat_id)


def get_chat_list(ses: Session) -> list[Chat]:
    q = select(Chat).options(subqueryload(Chat.members))
    return ses.execute(q).scalars().all()


def get_chat_history(
    ses: Session, chat_id: int, offset: int, limit: Optional[int] = None
):
    q = select(Message).where(Message.chat_id == chat_id, Message.id >= offset)
    if limit:
        q = q.limit(limit)
    return ses.execute(q).scalars().all()


def create_message(
    ses: Session, msg: MessageCreate, user_id: int, chat_id: int
) -> Message:
    message = Message(
        chat_id=chat_id, user_id=user_id, text=msg.text, timestamp=datetime.now()
    )
    ses.add(message)
    ses.commit()
    syslog.syslog(
        syslog.LOG_INFO, f"C{message.chat_id}:U{message.user_id}:{message.text}"
    )
    return message
