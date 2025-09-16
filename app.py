from fastapi import FastAPI, WebSocket, UploadFile
import pandas as pd
import plotly.express as px
from openai import OpenAI

app = FastAPI()
client = OpenAI()
dataframe_cache = None

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong"}

@app.post("/upload_csv/")
async def upload_csv(file: UploadFile):
    global dataframe_cache
    dataframe_cache = pd.read_csv(file.file)
    return {"message": "CSV chargé avec succès", "colonnes": list(dataframe_cache.columns)}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    global dataframe_cache

    while True:
        prompt = await ws.receive_text()

        if dataframe_cache is None:
            await ws.send_json({"error": "⚠ Aucun CSV chargé."})
            continue

        system_prompt = """
        Tu es un assistant data.
        Tu as un DataFrame pandas nommé df.
        Selon la demande, écris du code Python qui produit soit :
        - une variable 'fig' (graphique plotly.express)
        - OU une variable 'result' (tableau pandas)
        Retourne uniquement du code Python exécutable.
        """

        try:
            # ✅ Appel OpenAI avec la nouvelle lib
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )

            code = response.choices[0].message.content

            local_env = {"df": dataframe_cache, "px": px, "pd": pd}
            exec(code, local_env)

            result_json = {}

            if "fig" in local_env:
                result_json["chart"] = local_env["fig"].to_json()
            elif "result" in local_env:
                result_json["table"] = local_env["result"].to_dict(orient="records")
            else:
                result_json["error"] = "Aucun résultat généré par le LLM."

            await ws.send_json(result_json)

        except Exception as e:
            await ws.send_json({"error": str(e), "code": code if 'code' in locals() else None})
