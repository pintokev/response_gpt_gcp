import pandas as pd
import requests
from flask import request


def categoriser_lignes(categorie):
    return {"categorie": categorie}


def count_by_categorie(categorie, filename="tickets.csv"):
    df = pd.read_csv(filename)
    count = len(df[df["categorie"] == categorie])

    return {
        "categorie": categorie,
        "count": int(count)
    }


def get_examples_by_categorie(categorie, offset=0, limit=10, filename="tickets.csv"):
    if offset < 0:
        return {"error": "offset doit être >= 0"}
    if limit <= 0:
        return {"error": "limit doit être > 0"}

    df = pd.read_csv(filename)
    filtered = df[df["categorie"] == categorie].reset_index(drop=True)

    total = len(filtered)
    examples = filtered.iloc[offset:offset + limit].to_dict(orient="records")
    has_more = offset + limit < total

    return {
        "categorie": categorie,
        "offset": offset,
        "limit": limit,
        "returned": len(examples),
        "total": total,
        "has_more": has_more,
        "examples": examples
    }


def check_factures(categorie, filename="tickets.csv"):
    df = pd.read_csv(filename)

    if "facture_status" not in df.columns:
        df["facture_status"] = ""

    mask = df["categorie"] == categorie

    for idx in df[mask].index:
        result = get_pdf(df.loc[idx].to_dict())
        df.at[idx, "facture_status"] = "facture OK" if result == "OK" else "facture KO"

    df.to_csv(filename, index=False)

    return {
        "categorie": categorie,
        "updated_rows": int(mask.sum())
    }


def get_pdf(row):
    return "OK"

def call_accueil_facture(contractKey):
    response = requests.get(
        "http://orange_api:5000/facture/accueil",
        params={"contractKey": contractKey},
        headers={"Host": "localhost:5000"},
        timeout=30
    )
    response.raise_for_status()
    return response.json()