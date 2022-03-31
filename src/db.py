from pathlib import Path

import sqlalchemy
from sqlalchemy import Table, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

DATABASE_FILE = Path(__file__).parent / "data.sqlite"
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

Base = declarative_base()

Session = sessionmaker(bind=engine)

chat_members_table = Table(
    "chats_members",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("chat_id", ForeignKey("chats.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True)
    password = Column(String)

    chats = relationship("Chat", secondary=chat_members_table, back_populates="members")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)

    members = relationship("User", secondary=chat_members_table, back_populates="chats")
    messages = relationship("Message", back_populates="chat")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    text = Column(String)
    timestamp = Column(DateTime)

    user = relationship("User")
    chat = relationship("Chat", back_populates="messages")
