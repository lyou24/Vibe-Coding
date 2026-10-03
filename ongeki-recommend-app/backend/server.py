import os
import sys

# backendディレクトリをsys.pathに追加（Renderなどのルート実行時のModuleNotFoundErrorを防止）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends
from fastapi.staticfiles import StaticFiles
import uvicorn
from fetch_user import fetch_user_details, fetch_user_rating_profile, save_user_data
from recommend_engine import RecommendEngine
from fetch_music import update_music_master
import time
from collect_high_rate_users import run_collection
from pydantic import BaseModel

APP_PASSCODE = os.environ.get("APP_PASSCODE", "123123")

def verify_passcode(x_passcode: str = Header(None)):
    if x_passcode != APP_PASSCODE:
        raise HTTPException(status_code=401, detail="合言葉が無効または指定されていません")
    return True

class VerifyPasscodeRequest(BaseModel):
    passcode: str

class UpdateCacheRequest(BaseModel):
    min_rating: float = 19.0

app = FastAPI(title="Ongeki Recommend API")

@app.post("/api/verify_passcode")
def api_verify_passcode(req: VerifyPasscodeRequest):
    if req.passcode == APP_PASSCODE:
        return {"status": "success", "message": "合言葉が認証されました"}
    raise HTTPException(status_code=401, detail="合言葉が違います")

@app.get("/api/recommend/{user_id}", dependencies=[Depends(verify_passcode)])
def get_recommendation(user_id: str):
    # Fetch latest user data
    details = fetch_user_details(user_id)
    rating_prof = fetch_user_rating_profile(user_id)
    
    if details and rating_prof:
        save_user_data(user_id, {
            "scores": details,
            "rating_profile": rating_prof
        })
    else:
        # キャッシュが存在するか確認してフォールバック
        cache_path = os.path.join(os.path.dirname(__file__), "data", f"user_{user_id}.json")
        if not os.path.exists(cache_path):
            raise HTTPException(
                status_code=404, 
                detail=f"ユーザーID '{user_id}' のデータをongeki-score.netから取得できませんでした（IDが存在しない、非公開、または外部サーバーアクセス制限の可能性があります）"
            )
        print(f"Using cached data for user {user_id} as external fetch failed")
    
    # Run recommendation engine
    try:
        engine = RecommendEngine(target_user_id=user_id)
        result = engine.analyze()
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Recommendation engine failed: {str(e)}")

@app.post("/api/update_music", dependencies=[Depends(verify_passcode)])
def update_music():
    try:
        update_music_master()
        return {"status": "success", "message": "Music master updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update music master: {str(e)}")

update_state = {
    "is_running": False,
    "cancel_requested": False
}

def check_cancel():
    global update_state
    return update_state["cancel_requested"]

def update_all_users_cache(min_rating: float = 19.0):
    global update_state
    update_state["is_running"] = True
    update_state["cancel_requested"] = False
    
    try:
        run_collection(check_cancel=check_cancel, min_rating=min_rating)
    except Exception as e:
        print(f"Error during collection: {e}")
        
    update_state["is_running"] = False
    update_state["cancel_requested"] = False

@app.post("/api/update_cache", dependencies=[Depends(verify_passcode)])
def update_cache(req: UpdateCacheRequest, background_tasks: BackgroundTasks):
    global update_state
    if update_state["is_running"]:
        return {"status": "error", "message": "Already running"}
    background_tasks.add_task(update_all_users_cache, req.min_rating)
    return {"status": "success", "message": f"Background cache update started with min_rating={req.min_rating}"}

@app.post("/api/stop_update", dependencies=[Depends(verify_passcode)])
def stop_update():
    global update_state
    if update_state["is_running"]:
        update_state["cancel_requested"] = True
        return {"status": "success", "message": "Stop requested"}
    return {"status": "error", "message": "Not running"}

@app.get("/api/update_status")
def get_update_status():
    global update_state
    return update_state

# Mount frontend static files
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    print(f"Warning: Frontend build directory not found at {frontend_dist}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

