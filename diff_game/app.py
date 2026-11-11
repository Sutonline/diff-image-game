import base64
import os
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from diff_game.engine import compare_game_sheet

app = FastAPI(title="Spot The Difference Game Engine")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Spot the Difference Game Tool</h1>", status_code=200)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.post("/api/compare")
async def api_compare(
    file: UploadFile = File(...),
    split_mode: str = Form("auto"),
    diff_threshold: int = Form(25),
    min_area: int = Form(40),
    blur_radius: int = Form(3),
):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Cannot decode image. Unsupported format or corrupt data.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading uploaded file: {str(e)}")

    try:
        result, annotated_img = compare_game_sheet(
            image=image,
            split_mode=split_mode,
            diff_threshold=diff_threshold,
            min_area=min_area,
            blur_radius=blur_radius,
        )

        success, buffer = cv2.imencode(".png", annotated_img)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to encode annotated image")

        b64_str = base64.b64encode(buffer).decode("utf-8")
        b64_data = f"data:image/png;base64,{b64_str}"

        res_dict = result.model_dump()
        res_dict["annotated_image_base64"] = b64_data
        return res_dict
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison engine error: {str(e)}")
