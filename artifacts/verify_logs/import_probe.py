mods = ["fastapi","pydantic","uvicorn","jose","py_opengauss","websockets"]
for m in mods:
    try:
        __import__(m)
        print(f"[OK] import {m}")
    except Exception as e:
        print(f"[FAIL] import {m}: {type(e).__name__}: {e}")