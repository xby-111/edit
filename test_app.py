try:
    from app.main import app
    print('App loaded successfully')
    print(f'App title: {app.title}')
except Exception as e:
    print(f'Error loading app: {e}')
    import traceback
    traceback.print_exc()