import importlib.util
mods = ['fastapi','pydantic','jose','uvicorn','py_opengauss','websockets']
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(','.join(missing))