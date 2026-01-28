from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/recommend/{userid}")
def recommend(userid: str):
    # TODO: call your model here
    return "123,456,789"

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8082)

