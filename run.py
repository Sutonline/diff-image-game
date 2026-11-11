import uvicorn

if __name__ == "__main__":
    print("🚀 启动图片找茬游戏比对服务器...")
    print("📍 访问地址: http://127.0.0.1:8000")
    uvicorn.run("diff_game.app:app", host="127.0.0.1", port=8000, reload=True)
