import os, json, traceback
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

app = FastAPI(title="ZeroWaste Chef")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates_path = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_path)

AI_API_KEY = os.getenv("AI_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
AI_MODEL = os.getenv("AI_MODEL", "google/gemma-4-31b-it:free")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")

SYSTEM_PROMPT = """أنت مساعد طبخ خبير. مهمتك توليد وصفة طعام بناءً على مكونات معينة.
يجب أن يكون الرد بصيغة JSON فقط ولا شيء غيره، وفق الهيكل التالي:
{
  "title": "اسم الوصفة",
  "calories": "السعرات الحرارية التقريبية (عدد)",
  "ingredients": ["مكون 1", "مكون 2", ...],
  "steps": ["خطوة 1", "خطوة 2", ...],
  "tips": "نصائح إضافية (اختياري)"
}
"""


@app.exception_handler(Exception)
async def debug_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": traceback.format_exc()}
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "python": os.sys.version, "static_exists": os.path.isdir(static_dir), "templates_exists": os.path.isdir(templates_path)}


@app.post("/generate")
async def generate(ingredients: str = Form(...)):
    if not AI_API_KEY or AI_API_KEY == "YOUR_API_KEY_HERE":
        return JSONResponse(status_code=400, content={"error": "API key not set."})
    if not ingredients.strip():
        return JSONResponse(status_code=400, content={"error": "Please enter ingredients."})
    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    prompt = f"Ingredients: {ingredients}\n\nCreate one creative recipe. Reply in JSON only."
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    text = raw.strip()
    for prefix in ["```json", "```"]:
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.endswith("```"):
        text = text[:-3]
    recipe = json.loads(text.strip())
    return JSONResponse(content=recipe)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
