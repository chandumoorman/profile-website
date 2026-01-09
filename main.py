import shutil
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import engine, SessionLocal
import models
from auth import hash_password, verify_password, create_token, decode_token

# ------------------ DB setup ------------------
models.Base.metadata.create_all(bind=engine)

# ✅ Create app first
app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ------------------ Paths (absolute) ------------------
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
PHOTO_DIR = UPLOAD_DIR / "photos"
RESUME_DIR = UPLOAD_DIR / "resumes"

# Create directories safely
PHOTO_DIR.mkdir(parents=True, exist_ok=True)
RESUME_DIR.mkdir(parents=True, exist_ok=True)

# Serve upload files publicly
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# ------------------ DB dependency ------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------ Schemas ------------------
class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class ProfileUpdate(BaseModel):
    phone: str = ""
    bio: str = ""

# ------------------ Auth dependency ------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

# ------------------ API routes ------------------
@app.get("/")
def home():
    return {"message": "Profile website backend running 🚀"}

@app.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter_by(username=user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = models.User(
        username=user.username,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    return {"status": "User created"}

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter_by(username=user.username).first()

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(db_user.username)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "phone": current_user.phone,
        "bio": current_user.bio,
        "photo": current_user.photo,
        "resume": current_user.resume
    }

@app.put("/me")
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    current_user.phone = data.phone
    current_user.bio = data.bio
    db.commit()
    return {"status": "Profile updated"}

@app.post("/upload/photo")
def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files allowed")

    filename = f"user_{current_user.id}_photo.jpg"
    filepath = PHOTO_DIR / filename

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # store relative path
    current_user.photo = f"uploads/photos/{filename}"
    db.commit()
    return {"status": "Photo uploaded", "path": current_user.photo}

@app.post("/upload/resume")
def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    filename = f"user_{current_user.id}_resume.pdf"
    filepath = RESUME_DIR / filename

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    current_user.resume = f"uploads/resumes/{filename}"
    db.commit()
    return {"status": "Resume uploaded", "path": current_user.resume}

# ------------------ Frontend routes ------------------
# ✅ These 3 will never 404 if frontend files exist

@app.get("/signup-page")
def signup_page():
    return FileResponse(FRONTEND_DIR / "signup.html")

@app.get("/login-page")
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/dashboard")
def dashboard_page():
    return FileResponse(FRONTEND_DIR / "dashboard.html")
