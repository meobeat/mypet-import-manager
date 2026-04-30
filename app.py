from openai import OpenAI
import importlib.util
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
import streamlit as st
import pandas as pd
import pdfplumber
from pathlib import Path
import importlib.util
from openai import OpenAI
from rapidfuzz import fuzz

st.set_page_config(page_title="MyPet Import Manager PRO", layout="wide")
st.title("🐾 MyPet Import Manager PRO")

import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATA_DIR = Path("data")
PARSERS_DIR = Path("parsers")
DATA_DIR.mkdir(exist_ok=True)
PARSERS_DIR.mkdir(exist_ok=True)

ARCHIVIO_CASSA_FILE = DATA_DIR / "articoli_cassa.csv"
MAPPA_FILE = DATA_DIR / "mappa_codici_fornitore.csv"


def carica_csv(path, colonne):
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.DataFrame(columns=colonne)


def salva_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def carica_archivio():
    return carica_csv(ARCHIVIO_CASSA_FILE, [
        "Barcode Interno", "Id Interno", "Descrizione", "Id Categoria",
        "Id Reparto", "Prezzo", "Fornitore", "Codice Fornitore",
        "Taglia", "Colore"
    ])


def carica_mappa():
    return carica_csv(MAPPA_FILE, [
        "Fornitore", "Codice Fattura", "Taglia", "Barcode Interno", "Note"
    ])


def lista_parser():
    return sorted([f.stem for f in PARSERS_DIR.glob("*.py")])


def carica_parser(nome):
    percorso = PARSERS_DIR / f"{nome}.py"
    if not percorso.exists():
        return None

    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def riconosci_parser(text):
    for nome in lista_parser():
        modulo = carica_parser(nome)
        if modulo and hasattr(modulo, "can_parse"):
            try:
                if modulo.can_parse(text):
                    return nome
            except Exception:
                pass
    return None


def estrai_dati(text, parser_nome):
    modulo = carica_parser(parser_nome)
    if modulo is None:
        return pd.DataFrame(columns=["Codice", "Taglia", "Quantità"])
    return modulo.parse(text)


def estrai_testo_pdf(pdf_file):
    testo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            testo += (page.extract_text() or "") + "\n"
    return testo


def trova_barcode(archivio, mappa, codice, taglia, fornitore):
    codice = str(codice).upper().strip()
    taglia = str(taglia).upper().strip()
    fornitore = str(fornitore).upper().strip()

    mappa_tmp = mappa.copy().fillna("")
    for col in mappa_tmp.columns:
        mappa_tmp[col] = mappa_tmp[col].astype(str).str.upper().str.strip()

    match_mappa = mappa_tmp[
        (mappa_tmp["Fornitore"] == fornitore) &
        (mappa_tmp["Codice Fattura"] == codice) &
        (mappa_tmp["Taglia"] == taglia)
    ]

    if len(match_mappa) == 1:
        return match_mappa.iloc[0]["Barcode Interno"], "MAPPA"

    archivio_tmp = archivio.copy().fillna("")
    for col in archivio_tmp.columns:
        archivio_tmp[col] = archivio_tmp[col].astype(str).str.upper().str.strip()

    risultati = []
    for _, row in archivio_tmp.iterrows():
        testo = " ".join([str(v) for v in row.values])
        if codice in testo and taglia in testo:
            risultati.append(row)

    if len(risultati) == 1:
        return risultati[0]["Barcode Interno"], "OK"

    if len(risultati) > 1:
        return "", "DUPLICATO"

    return "", "NON TROVATO"


def suggerisci_articoli(archivio, codice, taglia, limite=5):
    archivio_tmp = archivio.copy().fillna("")
    query = f"{codice} {taglia}".upper().strip()
    candidati = []

    for _, row in archivio_tmp.iterrows():
        testo = " ".join([str(v) for v in row.values]).upper()
        score = fuzz.partial_ratio(query, testo)

        candidati.append({
            "Score": score,
            "Barcode Interno": row.get("Barcode Interno", ""),
            "Id Interno": row.get("Id Interno", ""),
            "Descrizione": row.get("Descrizione", ""),
            "Prezzo": row.get("Prezzo", "")
        })

    return pd.DataFrame(candidati).sort_values("Score", ascending=False).head(limite)


uploaded_pdf = st.file_uploader("Carica fattura PDF", type=["pdf"], key="pdf_global")

if uploaded_pdf is not None:
    st.session_state["pdf_file"] = uploaded_pdf

pdf_file = st.session_state.get("pdf_file", None)

tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Import fattura",
    "📚 Archivio Cassa",
    "🧠 Mappe fornitore",
    "🤖 AI Parser"
])


with tab1:
    st.header("📦 Import fattura → stocks.csv")

    archivio = carica_archivio()
    mappa = carica_mappa()

    fornitore = st.text_input("Nome fornitore", value="Generico")

    if pdf_file:

        testo = estrai_testo_pdf(pdf_file)
        parser_list = lista_parser()

        if not parser_list:
            st.error("Nessun parser trovato.")
            st.warning("Vai nella tab 🤖 AI Parser per crearne uno nuovo.")
            df = pd.DataFrame(columns=["Codice", "Taglia", "Quantità"])

        else:
            parser_auto = riconosci_parser(testo)

            if parser_auto:
                st.success(f"Parser automatico: {parser_auto}")
                index_default = parser_list.index(parser_auto)
            else:
                st.warning("Parser non riconosciuto automaticamente.")
                index_default = 0

            parser_scelto = st.selectbox("Scegli parser", parser_list, index=index_default)

            df = estrai_dati(testo, parser_scelto)

        st.subheader("Righe lette dalla fattura")
        st.dataframe(df, width="stretch")

        risultati = []

        for _, r in df.iterrows():

            barcode, stato = trova_barcode(
                archivio=archivio,
                mappa=mappa,
                codice=r["Codice"],
                taglia=r["Taglia"],
                fornitore=fornitore
            )

            risultati.append({
                "Fornitore": fornitore,
                "Codice": r["Codice"],
                "Taglia": r["Taglia"],
                "Quantità": r["Quantità"],
                "Barcode": barcode,
                "Stato": stato
            })

        df_r = pd.DataFrame(
    risultati,
    columns=["Fornitore", "Codice", "Taglia", "Quantità", "Barcode", "Stato"]
)

        st.subheader("Matching articoli")
        st.dataframe(df_r, width="stretch")

        anomalie = df_r[~df_r["Stato"].isin(["OK", "MAPPA"])]

        if not anomalie.empty:
            st.subheader("Correzioni manuali")

            for i, r in anomalie.iterrows():

                with st.expander(f"{r['Codice']} - {r['Taglia']}"):

                    suggerimenti = suggerisci_articoli(archivio, r["Codice"], r["Taglia"])

                    st.write("Suggerimenti automatici:")
                    st.dataframe(suggerimenti, width="stretch")

                    ean = st.text_input("EAN corretto", key=f"ean_{i}")

                    if st.button("Salva", key=f"save_{i}"):

                        nuova = pd.DataFrame([{
                            "Fornitore": fornitore,
                            "Codice Fattura": r["Codice"],
                            "Taglia": r["Taglia"],
                            "Barcode Interno": ean,
                            "Note": "manuale"
                        }])

                        mappa = pd.concat([mappa, nuova], ignore_index=True)
                        salva_csv(mappa, MAPPA_FILE)

                        st.success("Salvato")

    else:
        st.info("Carica una fattura PDF per iniziare.")

with tab2:
    st.header("📚 Archivio prodotti Cassa in Cloud")

    upload_archivio = st.file_uploader("Carica CSV articoli Cassa", type=["csv"], key="archivio_upload")

    if upload_archivio:
        nuovo = pd.read_csv(upload_archivio, dtype=str).fillna("")
        salva_csv(nuovo, ARCHIVIO_CASSA_FILE)
        st.success("Archivio Cassa aggiornato.")

    archivio = carica_archivio()
    st.dataframe(archivio, width="stretch")

    st.download_button(
        "⬇️ Scarica archivio_cassa.csv",
        archivio.to_csv(index=False).encode("utf-8-sig"),
        "articoli_cassa.csv",
        "text/csv"
    )


with tab3:
    st.header("🧠 Mappe fornitore")

    mappa = carica_mappa()
    st.dataframe(mappa, width="stretch")

    st.download_button(
        "⬇️ Scarica mappa_codici_fornitore.csv",
        mappa.to_csv(index=False).encode("utf-8-sig"),
        "mappa_codici_fornitore.csv",
        "text/csv"
    )


with tab4:
    st.header("🤖 AI - Generatore Parser")

    nome_parser = st.text_input("Nome parser da salvare", value="nuovo_parser")

    if st.button("Genera parser con AI"):
        if not pdf_file:
            st.warning("Carica prima una fattura PDF")
        else:
            testo_ai = estrai_testo_pdf(pdf_file)

with st.spinner("Analisi fattura in corso..."):
    try:
        risposta = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
Sei un programmatore Python esperto in parsing di fatture PDF.

Genera SOLO codice Python valido.

Il codice deve contenere:
import re
import pandas as pd

def can_parse(text):
    return True

def parse(text):
    return un DataFrame con colonne Codice, Taglia, Quantità
"""
                },
                {"role": "user", "content": testo_ai[:5000]}
            ]
        )

        st.session_state["parser_generato"] = risposta.choices[0].message.content

    except Exception as e:
        st.error("Errore OpenAI")
        st.code(str(e))

    if "parser_generato" in st.session_state:
        codice = st.session_state["parser_generato"]

        st.subheader("Codice parser generato")
        st.code(codice, language="python")

        if st.button("💾 Salva parser"):
            codice_pulito = codice.replace("```python", "").replace("```", "").strip()
            percorso = PARSERS_DIR / f"{nome_parser}.py"

            with open(percorso, "w", encoding="utf-8") as f:
                f.write(codice_pulito)

            st.success(f"Parser salvato: {percorso}")
