from fastapi import FastAPI, WebSocket, UploadFile
import pandas as pd
import openai, plotly.express as px

app = FastAPI()
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
async def ws_endpoint(ws: WebSocket):
    """
    WebSocket pour poser des questions en langage naturel.
    Renvoie un JSON contenant :
      - "table" : tableau Pandas converti en dict
      - "chart" : graphique Plotly converti en JSON
      - "error" : en cas de problème
    """
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

            await ws.send_json(result_json)

        except Exception as e:
            await ws.send_json({"error": str(e), "code": code})