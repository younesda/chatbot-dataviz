from fastapi import FastAPI, WebSocket, UploadFile, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import openai, plotly.express as px

app = FastAPI()

# ✅ CORS configuration (important for HTTP requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tu peux restreindre à ["http://localhost:3000", "https://ton-domaine.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

dataframe_cache = None

@app.post("/upload_csv/")
async def upload_csv(file: UploadFile):
    """
    Endpoint pour uploader un CSV.
    Retourne confirmation et liste des colonnes.
    """
    global dataframe_cache
    dataframe_cache = pd.read_csv(file.file)
    return {"message": "CSV chargé avec succès", "colonnes": list(dataframe_cache.columns)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket pour poser des questions en langage naturel.
    Renvoie un JSON contenant :
      - "table" : tableau Pandas converti en dict
      - "chart" : graphique Plotly converti en JSON
      - "error" : en cas de problème
    """
    await websocket.accept()
    global dataframe_cache

    try:
        while True:
            prompt = await websocket.receive_text()

            if dataframe_cache is None:
                await websocket.send_json({"error": "⚠ Aucun CSV chargé."})
                continue

            system_prompt = """
            Tu es un assistant data.
            Tu as un DataFrame pandas nommé df.
            Selon la demande, écris du code Python qui produit soit :
            - une variable 'fig' (graphique plotly.express)
            - OU une variable 'result' (tableau pandas)
            Retourne uniquement du code Python exécutable.
            """

            # Appel au LLM pour générer le code
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )

            code = response["choices"][0]["message"]["content"]

            try:
                # Exécution du code généré
                local_env = {"df": dataframe_cache, "px": px, "pd": pd}
                exec(code, local_env)

                result_json = {}

                if "fig" in local_env:
                    # Graphique Plotly renvoyé en JSON
                    result_json["chart"] = local_env["fig"].to_json()
                elif "result" in local_env:
                    # Tableau Pandas renvoyé en JSON
                    result_json["table"] = local_env["result"].to_dict(orient="records")
                else:
                    result_json["error"] = "Aucun résultat généré par le LLM."

                await websocket.send_json(result_json)

            except Exception as e:
                await websocket.send_json({"error": str(e), "code": code})

    except WebSocketDisconnect:
        print("🔌 Client déconnecté du WebSocket")


# ✅ Petit endpoint test pour savoir si l’API tourne
@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong"}
