from fastapi import FastAPI, Depends
from pydantic import BaseModel
import openai
import os

from database import Base, engine, SessionLocal
import models
from sqlalchemy.orm import Session

Base.metadata.create_all(bind=engine)

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")

class Message(BaseModel):
    user_id: str
    text: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/chat")
async def chat(message: Message, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == message.user_id).first()
    if not user:
        user = models.User(user_id=message.user_id, name=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    history = (
        db.query(models.Message)
        .filter(models.Message.user_id == user.id)
        .order_by(models.Message.created_at.desc())
        .limit(5)
        .all()
    )
    history = list(reversed(history))

    messages = [
        {"role": "system", "content": "Jesteś Leną, ciepłą, żartobliwą kobietą."}
    ]
    for h in history:
        role = "user" if h.sender == "user" else "assistant"
        messages.append({"role": role, "content": h.text})

    messages.append({"role": "user", "content": message.text})

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message["content"]

    user_msg = models.Message(user_id=user.id, text=message.text, sender="user")
    lena_msg = models.Message(user_id=user.id, text=reply, sender="assistant")
    db.add(user_msg)
    db.add(lena_msg)
    db.commit()

    return {"reply": reply}
