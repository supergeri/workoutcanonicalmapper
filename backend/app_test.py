from fastapi import FastAPI
app = FastAPI()

@app.get('/debug/garmin-test')
def test():
    return {'status': 'test'}
