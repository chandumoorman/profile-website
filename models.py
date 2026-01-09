from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    phone = Column(String, default="")
    bio = Column(String, default="")
    photo = Column(String, default="")
    resume = Column(String, default="")
