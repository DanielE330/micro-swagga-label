from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import SessionLocal, engine, Base
import models, schema

Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/users")
def create_user(user: schema.UserCreate, db: Session = Depends(get_db)) -> dict:
    existing = db.query(models.User).filter_by(login=user.login).first()
    if existing:
        raise HTTPException(status_code=400, detail="пользователь существует")

    new_user = models.User(
        login = user.login,
        password = user.password
    )

    db.add(new_user)
    db.commit()

    return {"message": "пользователь создан"}

@app.delete("/users/{user_login}")
def delete_user(user_login: str, db: Session = Depends(get_db)) -> dict:
    user = db.query(models.User).filter_by(login=user_login).first()
    if not user:
        raise HTTPException(status_code=404, detail="пользователь не найден")

    db.delete(user)
    db.commit()

    return {"message": "пользователь удалён"}