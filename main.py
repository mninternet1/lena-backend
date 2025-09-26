from fastapi import FastAPI, Depends, Security, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import Base, engine, SessionLocal
import models
import os
from openai import OpenAI
import auth  # nasz plik z JWT

# Tworzymy tabele w bazie
Base.metadata.create_all(bind=engine)

app = FastAPI()

# 🔹 CORS
origins = [
    "https://lena-frontend.vercel.app",
    "http://localhost:3000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔹 OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔹 Model wiadomości od użytkownika
class Message(BaseModel):
    text: str

# 🔹 DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 🔹 Endpoint testowy
@app.get("/")
def root():
    return {"status": "ok", "message": "Lena backend działa 🚀"}

# 🔹 Rejestracja
@app.post("/register")
def register(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == form_data.username).first()
    if user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_pw = auth.get_password_hash(form_data.password)
    new_user = models.User(user_id=form_data.username, password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"msg": "User created successfully"}

# 🔹 Logowanie
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = auth.create_access_token(data={"sub": user.user_id})
    return {"access_token": access_token, "token_type": "bearer"}

# 🔹 Czat z obsługą JWT
security = HTTPBearer()

@app.post("/chat")
async def chat(
    message: Message,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    # 1. Odczytaj token
    token = credentials.credentials
    payload = auth.decode_token(token)
    username = payload.get("sub")

    # 2. Znajdź usera w bazie
    user = db.query(models.User).filter(models.User.user_id == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3. Pobierz historię rozmowy
    history = (
        db.query(models.Message)
        .filter(models.Message.user_id == user.id)
        .order_by(models.Message.created_at.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))

    # 4. Zbuduj kontekst
    messages = [
        {"role": "system", "content": "Jesteś Leną, ciepłą kobietą, pamiętasz użytkownika i jego wcześniejsze rozmowy."}
    ]
    for h in history:
        role = "user" if h.sender == "user" else "assistant"
        messages.append({"role": role, "content": h.text})

    messages.append({"role": "user", "content": message.text})

    # 5. Zapytanie do OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message.content

    # 6. Zapisz wiadomości do bazy
    user_msg = models.Message(user_id=user.id, text=message.text, sender="user")
    lena_msg = models.Message(user_id=user.id, text=reply, sender="assistant")
    db.add(user_msg)
    db.add(lena_msg)
    db.commit()

    return {"reply": reply}
