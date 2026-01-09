import shutil
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import engine, SessionLocal
import models
from auth import hash_password, verify_password, create_token, decode_token

# ---------- Setup ----------
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
PHOTOS_DIR = UPLOAD_DIR / "photos"
RESUMES_DIR = UPLOAD_DIR / "resumes"

PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
RESUMES_DIR.mkdir(parents=True, exist_ok=True)

# Serve static CSS/JS from frontend/assets
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

# Serve uploaded files (photos and resumes)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# OAuth scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# ---------- DB Dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Schemas ----------
class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class ProfileUpdate(BaseModel):
    phone: str = ""
    bio: str = ""

# ---------- Auth Dependency ----------
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

# ==========================================================
# ✅ FRONTEND ROUTES (OPEN WEBSITE PAGES)
# ==========================================================

# ✅ MAIN LINK opens login automatically
@app.get("/")
def root():
    return RedirectResponse(url="/login")

@app.get("/login")
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/signup")
def signup_page():
    return FileResponse(FRONTEND_DIR / "signup.html")

@app.get("/dashboard")
def dashboard_page():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

# ==========================================================
# ✅ API ROUTES (BACKEND)
# ==========================================================

@app.post("/api/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter_by(username=user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = models.User(
        username=user.username,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    return {"status": "User created"}

@app.post("/api/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter_by(username=user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(db_user.username)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "phone": current_user.phone,
        "bio": current_user.bio,
        "photo": current_user.photo,
        "resume": current_user.resume
    }

@app.put("/api/me")
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    current_user.phone = data.phone
    current_user.bio = data.bio
    db.commit()
    return {"status": "Profile updated"}

@app.post("/api/upload/photo")
def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files allowed")

    # Use original filename extension safely
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    filename = f"user_{current_user.id}_photo{ext}"
    filepath = PHOTOS_DIR / filename

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Store URL path for frontend
    current_user.photo = f"/uploads/photos/{filename}"
    db.commit()

    return {"status": "Photo uploaded"}

@app.post("/api/upload/resume")
def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    filename = f"user_{current_user.id}_resume.pdf"
    filepath = RESUMES_DIR / filename

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    current_user.resume = f"/uploads/resumes/{filename}"
    db.commit()

    return {"status": "Resume uploaded"}
