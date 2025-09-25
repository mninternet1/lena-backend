from fastapi import FastAPI, Depends
from pydantic import BaseModel
import openai
import os

from database import Base, engine, SessionLocal
import models
from sqlalchemy.orm import Session

# Tworzymy tabele w bazie (jeśli jeszcze ich nie ma)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# 🔹 Endpoint dla Render healthcheck
@app.get("/")
def root():
    return {"status": "ok", "message": "Lena backend is running 🚀"}

# Klucz API do OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Model danych dla wiadomości
class Message(BaseModel):
    user_id: str
    text: str

# Dependency do bazy
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/chat")
async def chat(message: Message, db: Session = Depends(get_db)):
    # Sprawdź, czy użytkownik istnieje
    user = db.query(models.User).filter(models.User.user_id == message.user_id).first()
    if not user:
        user = models.User(user_id=message.user_id, name=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Historia ostatnich 5 wiadomości
    history = (
        db.query(models.Message)
        .filter(models.Message.user_id == user.id)
        .order_by(models.Message.created_at.desc())
        .limit(5)
        .all()
    )
    history = list(reversed(history))

    # Budowanie kontekstu rozmowy
    messages = [
        {"role": "system", "content": "Jesteś Leną, ciepłą i żartobliwą kobietą, pamiętasz użytkownika."}
    ]
    for h in history:
        role = "user" if h.sender == "user" else "assistant"
        messages.append({"role": role, "content": h.text})

    messages.append({"role": "user", "content": message.text})

    # Odpowiedź z OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message["content"]

    # Zapis wiadomości do bazy
    user_msg = models.Message(user_id=user.id, text=message.text, sender="user")
    lena_msg = models.Message(user_id=user.id, text=reply, sender="assistant")
    db.add(user_msg)
    db.add(lena_msg)
    db.commit()

    return {"reply": reply}
