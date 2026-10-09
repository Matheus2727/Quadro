from flask import Flask, render_template, request, redirect, session
from werkzeug.security import check_password_hash
import sqlite3
import os
import uuid
from google_auth_oauthlib.flow import InstalledAppFlow
import requests
import time
import random
from pathlib import Path
import subprocess

app = Flask(__name__)
app.secret_key = "Ss123$%¨"
PHOTOS_FOLDER = Path('src') / 'static' / 'DB.db'
lista_photos = []

def get_db():
    db_path = Path('DB') / 'DB.db'
    return sqlite3.connect(db_path)

@app.route("/")
def home():
    if len(lista_photos) == 0:
        shuffle()

    tags_desejadas = session.get("tags_desejadas", [])

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""select Tempo from Configs""")
    res = cursor.fetchall()
    if len(res) == 0:
        cursor.execute("""
        insert into Configs (Tempo) values (?)
        """,(5))
        conn.commit()
        tempo = 5

    else:
        tempo = res[0]["Tempo"]

    cursor.execute("""select distinct Tag from Tags""")
    res_tags = cursor.fetchall()

    conn.close()

    if tags_desejadas == []:
        for t in res_tags:
            tags_desejadas.append(t["Tag"])

        session["tags_desejadas"] = tags_desejadas

    valores_tags = []
    for t in res_tags:
        if t["Tag"] in tags_desejadas:
            valores_tags.append({"t": t["Tag"], "v": 1})

        else:
            valores_tags.append({"t": t["Tag"], "v": 0})

    return render_template("home.html", tempo=tempo, valores_tags=valores_tags)

@app.route("/atualizarConfigs", methods=["POST"])
def atualizarConfigs():
    tempo = int(request.form["Tempo"])

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
    update Configs set Tempo = (?) where rowid = (?)
    """, (tempo, 1))

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/cancelar")
def cancelar():
    shuffle()
    return redirect("/")

@app.route("/login", methods=["GET"])
def login():
    import auth
    #return render_template("login.html", url="")
    CLIENT_ID = auth.CLIENT_ID
    CLIENT_SECRET = auth.CLIENT_SECRET
    SCOPES = ["https://www.googleapis.com/auth/photospicker.mediaitems.readonly"]
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [
                    "http://localhost"
                ]
            }
        },
        SCOPES
    )
    credentials = flow.run_local_server(port=0)
    session["credentials_token"] = credentials.token
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }
    session["headers"] = headers

    response = requests.post(
        "https://photospicker.googleapis.com/v1/sessions",
        headers=headers
    )

    session_google = response.json()
    
    picker_uri = session_google["pickerUri"]

    print("Abra no navegador:")
    print(picker_uri)

    session["session_google"] = session_google
    return render_template("login.html", url=picker_uri)

@app.route("/picker", methods=["GET"])
def picker():
    session_google = session["session_google"]
    headers = session["headers"]
    credentials_token = session["credentials_token"]
    
    session_id = session_google["id"]

    poll_interval = session_google["pollingConfig"]["pollInterval"]
    poll_interval = int(poll_interval.rstrip("s"))

    print("Obtendo conjunto de IDs")
    while True:
        response = requests.get(
            f"https://photospicker.googleapis.com/v1/sessions/{session_id}",
            headers=headers
        )
        response.raise_for_status()
        session_google = response.json()
        if session_google.get("mediaItemsSet"):
            break

        time.sleep(poll_interval)

    response = requests.get(
        "https://photospicker.googleapis.com/v1/mediaItems",
        headers=headers,
        params={
            "sessionId": session_id
        }
    )
    response.raise_for_status() # provavelmente tem q tirar isso aqui
    data = response.json()

    print("salvando fotos")

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""select ID_Photo from Photos""")
    res = cursor.fetchall()

    num_selecionadas = len(data.get("mediaItems", []))
    num_intersect = 0
    ids_selecionados = []
    for item in data.get("mediaItems", []):
        media_id = item["id"]
        ids_selecionados.append(media_id)
        for f in res:
            if f["ID_Photo"] == media_id:
                print("foto ja existe")
                num_intersect += 1
                break

        else:
            base_url = item["mediaFile"]["baseUrl"]
            url = base_url + "=w1920-h1080"
            foto = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {credentials_token}"
                }
            )
            foto.raise_for_status() # provavelmente tem q tirar isso aqui
            nome = media_id + "." + item["mediaFile"]["mimeType"].split("/")[1]
            with open(os.path.join(PHOTOS_FOLDER, nome), "wb") as f:
                f.write(foto.content)

            cursor.execute("""
            insert into Photos (ID_Photo, Extension_Photo, Data_Photo, Width, Height) values (?,?,?,?,?)
            """,(media_id,item["mediaFile"]["mimeType"],item["createTime"],item["mediaFile"]["mediaFileMetadata"]["width"],item["mediaFile"]["mediaFileMetadata"]["height"]))

    conn.commit()
    conn.close()

    session["num_total"] = None
    session["ids_selecionados"] = ids_selecionados
    return render_template("posLogin.html", num_selecionadas=num_selecionadas, num_intersect=num_intersect, tag="")

def obter_total():
    num_total = len(lista_photos)
    session["num_total"] = num_total
    return num_total

def shuffle():
    print("shuffle")
    global lista_photos
    tags_desejadas = session.get("tags_desejadas", ["Colorido","Placa"])
    tags_desejadas_format = []
    for t in tags_desejadas:
        tags_desejadas_format.append("Tag = '" + t + "'")

    tags_composto = " or ".join(tags_desejadas_format)

    if tags_desejadas != []:
        tags_composto = "and (" + tags_composto + ")"

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""select a.ID_Photo, Extension_Photo from Photos a 
    left join Tags b on a.ID_Photo = b.ID_Photo where 1=1 {}
    order by random()""".format(tags_composto))
    res = cursor.fetchall()
    
    conn.close()

    lista_photos = res
    obter_total()

def obter_foto():
    indice_atual = session.get("indice_atual", 0)
    num_total = session.get("num_total", None)
    if True:
        num_total = obter_total()

    if indice_atual < num_total:
        session["indice_atual"] = indice_atual + 1
        return lista_photos[indice_atual]

    else:
        shuffle()
        session["indice_atual"] = 1
        return lista_photos[0]

@app.route("/photos")
def photos():
    tags_desejadas = session.get("tags_desejadas", [])
    tags_desejadas_format = []
    for t in tags_desejadas:
        tags_desejadas_format.append("Tag = '" + t + "'")

    tags_composto = " or ".join(tags_desejadas_format)

    if tags_desejadas != []:
        tags_composto = "and (" + tags_composto + ")"

    photo = obter_foto()
    
    ID_Photo = photo["ID_Photo"]
    Extension_Photo = photo["Extension_Photo"]

    nome = ID_Photo + "." + Extension_Photo.split("/")[1]

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""select Tempo from Configs""")
    res = cursor.fetchall()
    tempo = res[0]["Tempo"]
    
    conn.close()

    return render_template('photos.html', nome=nome, tempo=tempo*1000)

@app.route("/addTag", methods=["POST"])
def addTag():
    tag = request.form["Tag"]
    num_selecionadas = request.form["num_selecionadas"]
    num_intersect = request.form["num_intersect"]
    ids_selecionados = session.get("ids_selecionados", [])

    conn = get_db()
    cursor = conn.cursor()

    for id in ids_selecionados:
        cursor.execute("""
                select ID_Photo from Tags where ID_Photo = (?) and Tag = (?)
            """, (id, tag))
        res = cursor.fetchall()
        if len(res) == 0:
            cursor.execute("""
                    insert into Tags (ID_Photo, Tag) values (?,?)
                """, (id, tag))
            conn.commit()

    conn.close()
    
    return render_template("posLogin.html", num_selecionadas=int(num_selecionadas), num_intersect=int(num_intersect), tag=tag)

@app.route("/addTagOne", methods=["POST"])
def addTagOne():
    tag = request.form["Tag"]
    id = request.form["ID_Photo"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
            select ID_Photo from Tags where ID_Photo = (?) and Tag = (?)
        """, (id, tag))
    res = cursor.fetchall()
    if len(res) == 0:
        cursor.execute("""
                insert into Tags (ID_Photo, Tag) values (?,?)
            """, (id, tag))
        conn.commit()

    conn.close()

    return redirect("/editTagsFotos")

@app.route("/deleteTagOne", methods=["POST"])
def deleteTagOne():
    tag = request.form["Tag"]
    id = request.form["ID_Photo"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
            delete from Tags where ID_Photo = (?) and Tag = (?)
        """, (id, tag))
    conn.commit()

    conn.close()

    return redirect("/editTagsFotos")

@app.route("/editTagsFotos", methods=["GET"])
def editTagsFotos():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""select * from Photos""")
    res_photos = cursor.fetchall()

    cursor.execute("""select * from Tags""")
    res_tags = cursor.fetchall()
    
    conn.close()

    photos_format = []
    for pho in res_photos:
        tags = []
        pho_format = {**pho}
        ID_Photo = pho["ID_Photo"]
        Extension_Photo = pho["Extension_Photo"]
        pho_format["Nome_Photo"] = ID_Photo + "." + Extension_Photo.split("/")[1]
        for t in res_tags:
            if t["ID_Photo"] == pho["ID_Photo"]:
                tags.append(t["Tag"])

        pho_format["Tags"] = tags
        photos_format.append(pho_format)

    return render_template("editPhotos.html", photos=photos_format)

@app.route("/applyTags", methods=["POST"])
def applyTags():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""select distinct Tag from Tags""")
    res_tags = cursor.fetchall()

    conn.close()

    tags_desejadas = []
    for t in res_tags:
        valor = int(request.form[t["Tag"]])
        if valor == 1:
            tags_desejadas.append(t["Tag"])

    session["tags_desejadas"] = tags_desejadas
    return redirect("/cancelar")

@app.route("/gitPull")
def gitPull():
    try:
        resultado = subprocess.run(
            ['git', 'pull'],
            cwd='/home/remoto/Desktop/PRD/Quadro/src',
            capture_output=True,
            text=True,
            timeout=30
        )

        if resultado.returncode != 0:
            return render_template("retornoGitPull.html", retorno=str(resultado.stderr))

        return render_template("retornoGitPull.html", retorno=str(resultado.stdout))

    except subprocess.TimeoutExpired:
        return render_template("retornoGitPull.html", retorno="Falhou por Timeout")

if __name__ == "__main__":
    app.run(host="::", debug=True)






    