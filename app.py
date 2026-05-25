import os, json, re
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import httpx

load_dotenv()

app = FastAPI(title="ZeroWaste Chef")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AI_API_KEY = os.getenv("AI_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
AI_MODEL = os.getenv("AI_MODEL", "google/gemma-4-31b-it:free")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")

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


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def _call_gemini(ingredients: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={AI_API_KEY}"
    prompt = f"المكونات المتوفرة: {ingredients}\n\nقدم وصفة واحدة مبتكرة وسريعة باستخدام هذه المكونات."
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]
        }]
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(_clean_json(raw))


async def _call_openai(ingredients: str) -> dict:
    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    prompt = f"المكونات المتوفرة: {ingredients}\n\nقدم وصفة واحدة مبتكرة وسريعة باستخدام هذه المكونات."
    payload = {
        "model": AI_MODEL or "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://zerowaste-chef.app",
        "X-Title": "ZeroWaste Chef"
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
    return json.loads(_clean_json(raw))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate")
async def generate(ingredients: str = Form(...)):
    if not AI_API_KEY or AI_API_KEY == "YOUR_API_KEY_HERE":
        return JSONResponse(
            status_code=400,
            content={"error": "لم يتم ضبط مفتاح API. يرجى تعديل ملف .env ووضع المفتاح الصحيح."}
        )
    if not ingredients.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "الرجاء إدخال مكون واحد على الأقل."}
        )
    try:
        if AI_PROVIDER == "openai":
            recipe = await _call_openai(ingredients)
        else:
            recipe = await _call_gemini(ingredients)
        return JSONResponse(content=recipe)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=500,
            content={"error": "حدث خطأ في معالجة رد الذكاء الاصطناعي. يرجى المحاولة مرة أخرى."}
        )
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"فشل الاتصال بخدمة الذكاء الاصطناعي: {e.response.status_code}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"حدث خطأ غير متوقع: {str(e)}"}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
