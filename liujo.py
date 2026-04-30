import re
import pandas as pd

def can_parse(text):
    text = text.upper()
    return "LIU JO PETS" in text or "ME PET S.R.L." in text

def parse(text):
    righe = []

    pattern = r"(PC\d+|PW\d+|SCATO\d+|TARG\d+|CAR\d+).*?Taglie --> (.*?)\nQuantità --> (.*?)\n"
    matches = re.findall(pattern, text, re.DOTALL)

    for codice, taglie, quantita in matches:
        taglie_list = taglie.split()
        quantita_list = quantita.split()

        for t, q in zip(taglie_list, quantita_list):
            q_pulita = re.sub(r"\D", "", q)

            if q_pulita:
                righe.append({
                    "Codice": codice.strip().upper(),
                    "Taglia": t.strip().upper(),
                    "Quantità": int(q_pulita)
                })

    return pd.DataFrame(righe)