from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
import models
from openai import OpenAI
import os

# Tworzymy tabele
Base.metadata.create_all(bind=engine)

app = FastAPI()

# 🔹 CORS – zezwalamy na frontend z Vercel
origins = [
    "https://lena-frontend.vercel.app",  # produkcja
    "http://localhost:3000"              # dev lokalny
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔹 OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔹 Schemat wiadomości z frontu
class Message(BaseModel):
    user_id: str
    text: str

# 🔹 DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def root():
    return {"status": "ok", "message": "Lena backend działa 🚀"}

@app.post("/chat")
async def chat(message: Message, db: Session = Depends(get_db)):
    # 1. Znajdź lub utwórz usera
    user = db.query(models.User).filter(models.User.user_id == message.user_id).first()
    if not user:
        user = models.User(user_id=message.user_id, name=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    # 2. Pobierz historię ostatnich 10 wiadomości
    history = (
        db.query(models.Message)
        .filter(models.Message.user_id == user.id)
        .order_by(models.Message.created_at.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))

    # 3. Budujemy kontekst rozmowy
    messages = [
        {"role": "system", "content": "Jesteś Leną, ciepłą kobietą, która pamięta użytkownika i jego poprzednie rozmowy."}
    ]
    for h in history:
        role = "user" if h.sender == "user" else "assistant"
        messages.append({"role": role, "content": h.text})

    messages.append({"role": "user", "content": message.text})

    # 4. Zapytanie do OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message.content

    # 5. Zapisz wiadomości w DB
    user_msg = models.Message(user_id=user.id, text=message.text, sender="user")
    lena_msg = models.Message(user_id=user.id, text=reply, sender="assistant")
    db.add(user_msg)
    db.add(lena_msg)
    db.commit()

    return {"reply": reply}
