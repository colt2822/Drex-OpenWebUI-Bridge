import os

import uvicorn


def main() -> None:
    uvicorn.run("drex_chat.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
