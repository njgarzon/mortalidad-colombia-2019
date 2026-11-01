"""
Preparación de datos - Mortalidad no fetal Colombia 2019 (DANE, EEVV).

Lee los tres archivos Excel originales de data/raw/, los limpia y los une,
y deja en data/processed/ archivos livianos (CSV comprimido) que la app
carga en segundos. Así el despliegue en la nube no tiene que leer 19 MB de
Excel cada vez que arranca.

Uso:
    python scripts/preparar_datos.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
OUT = BASE / "data" / "processed"


def cargar_defunciones() -> pd.DataFrame:
    df = pd.read_excel(RAW / "NoFetal2019.xlsx", sheet_name="No_Fetales_2019", dtype=str)
    df = df[["COD_DANE", "COD_DEPARTAMENTO", "MES", "SEXO", "GRUPO_EDAD1",
             "MANERA_MUERTE", "COD_MUERTE"]].copy()
    for col in df.columns:
        df[col] = df[col].str.strip()
    df["MES"] = df["MES"].astype(int)
    df["SEXO"] = df["SEXO"].astype(int)
    df["GRUPO_EDAD1"] = df["GRUPO_EDAD1"].astype(int)
    return df


def cargar_divipola() -> pd.DataFrame:
    dv = pd.read_excel(RAW / "Divipola.xlsx", sheet_name="Hoja1", dtype=str)
    dv = dv[["COD_DANE", "COD_DEPARTAMENTO", "DEPARTAMENTO", "MUNICIPIO"]].copy()
    for col in dv.columns:
        dv[col] = dv[col].str.strip()
    return dv


def cargar_codigos() -> pd.DataFrame:
    """Catálogo CIE-10: devuelve una tabla código -> descripción.

    El archivo trae códigos a 4 caracteres (p. ej. I219) y a 3 caracteres
    (p. ej. C61). En los datos de defunciones aparecen ambos, así que se
    construye un solo diccionario con los dos niveles.
    """
    cod = pd.read_excel(RAW / "CodigosDeMuerte.xlsx", header=None, skiprows=9, dtype=str)
    cod.columns = ["CAPITULO", "NOMBRE_CAPITULO", "COD3", "DESC3", "COD4", "DESC4"]
    cod = cod.dropna(subset=["COD3"])
    cuatro = cod[["COD4", "DESC4"]].rename(columns={"COD4": "COD_MUERTE", "DESC4": "DESCRIPCION"})
    tres = cod[["COD3", "DESC3"]].rename(columns={"COD3": "COD_MUERTE", "DESC3": "DESCRIPCION"})
    out = pd.concat([cuatro, tres]).dropna()
    out["COD_MUERTE"] = out["COD_MUERTE"].str.strip()
    out["DESCRIPCION"] = out["DESCRIPCION"].str.strip()
    return out.drop_duplicates("COD_MUERTE")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = cargar_defunciones()
    dv = cargar_divipola()
    cod = cargar_codigos()

    df = df.merge(dv[["COD_DANE", "DEPARTAMENTO", "MUNICIPIO"]], on="COD_DANE", how="left")
    sin_muni = df["MUNICIPIO"].isna().sum()
    sin_causa = (~df["COD_MUERTE"].isin(cod["COD_MUERTE"])).sum()

    df.to_csv(OUT / "defunciones_2019.csv.gz", index=False, compression="gzip")
    dv.to_csv(OUT / "divipola.csv", index=False)
    cod.to_csv(OUT / "codigos_muerte.csv", index=False)

    print(f"Defunciones: {len(df):,} registros")
    print(f"Registros sin municipio en DIVIPOLA: {sin_muni}")
    print(f"Registros con código CIE-10 sin descripción: {sin_causa}")
    print(f"Archivos generados en {OUT}")


if __name__ == "__main__":
    main()
