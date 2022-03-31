from datetime import datetime

from pydantic import BaseModel


class UserCredentials(BaseModel):
    name: str
    password: str


class UserDB(UserCredentials):
    id: int


class UserPublic(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class ChatCreate(BaseModel):
    title: str


class ChatDB(ChatCreate):
    id: int


class ChatInfo(ChatDB):
    members: list[UserPublic]

    class Config:
        orm_mode = True


class MessageCreate(BaseModel):
    text: str


class MessageInHistory(MessageCreate):
    timestamp: datetime
    user: UserPublic

    class Config:
        orm_mode = True
