"""
Mortalidad en Colombia 2019 - Aplicación web interactiva con Plotly y Dash.

Fuente: DANE, Estadísticas Vitales (EEVV) 2019 - defunciones no fetales.
"""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
if not (DATA / "processed" / "defunciones_2019.csv.gz").exists():
    # Si alguien clona el repo sin los procesados, se generan a partir de los Excel.
    from scripts.preparar_datos import main as preparar
    preparar()

DF = pd.read_csv(
    DATA / "processed" / "defunciones_2019.csv.gz",
    dtype={"COD_DANE": str, "COD_DEPARTAMENTO": str, "COD_MUERTE": str},
)
CODIGOS = pd.read_csv(DATA / "processed" / "codigos_muerte.csv", dtype=str)
DIVIPOLA = pd.read_csv(DATA / "processed" / "divipola.csv", dtype=str)
with open(DATA / "geo" / "departamentos_colombia.geojson", encoding="utf-8") as f:
    GEOJSON = json.load(f)

MINUSCULAS = {"de", "del", "la", "las", "los", "y", "e", "el", "d.c."}


def nombre_bonito(texto: str) -> str:
    """'NORTE DE SANTANDER' -> 'Norte de Santander' (conserva tildes)."""
    if texto.startswith("ARCHIPIÉLAGO DE SAN ANDRÉS"):
        return "San Andrés y Providencia"
    palabras = texto.lower().split()
    out = [p if (i > 0 and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palabras)]
    return " ".join(out).replace("D.c.", "D.C.").replace("d.c.", "D.C.")


DF["DEPTO"] = DF["DEPARTAMENTO"].map(nombre_bonito)
DF["MPIO"] = DF["MUNICIPIO"].map(nombre_bonito)
# Capitales de departamento: código de municipio 001, salvo Cundinamarca (25001 es
# Agua de Dios; su capital es Bogotá, 11001).
DF["ES_CAPITAL"] = (DF["COD_DANE"].str[2:] == "001") & (DF["COD_DANE"] != "25001")

SEXOS = {1: "Hombre", 2: "Mujer", 3: "Indeterminado"}
DF["SEXO_TXT"] = DF["SEXO"].map(SEXOS)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGOS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Tabla de referencia de la actividad: GRUPO_EDAD1 -> ciclo de vida
GRUPOS_EDAD = [
    ("Mortalidad neonatal", range(0, 5), "Menor de 1 mes"),
    ("Mortalidad infantil", range(5, 7), "1 a 11 meses"),
    ("Primera infancia", range(7, 9), "1 a 4 años"),
    ("Niñez", range(9, 11), "5 a 14 años"),
    ("Adolescencia", range(11, 12), "15 a 19 años"),
    ("Juventud", range(12, 14), "20 a 29 años"),
    ("Adultez temprana", range(14, 17), "30 a 44 años"),
    ("Adultez intermedia", range(17, 20), "45 a 59 años"),
    ("Vejez", range(20, 25), "60 a 84 años"),
    ("Longevidad / Centenarios", range(25, 29), "85 a 100+ años"),
    ("Edad desconocida", range(29, 30), "Sin información"),
]
MAPA_EDAD = {cod: cat for cat, rango, _ in GRUPOS_EDAD for cod in rango}
RANGO_EDAD = {cat: rng for cat, _, rng in GRUPOS_EDAD}
ORDEN_EDAD = [g[0] for g in GRUPOS_EDAD]
DF["CICLO_VIDA"] = DF["GRUPO_EDAD1"].map(MAPA_EDAD)

DEPTOS = (DF[["COD_DEPARTAMENTO", "DEPTO"]].drop_duplicates()
          .sort_values("DEPTO").itertuples(index=False))
OPCIONES_DEPTO = [{"label": "Toda Colombia", "value": "TODOS"}] + [
    {"label": d.DEPTO, "value": d.COD_DEPARTAMENTO} for d in DEPTOS
]
NOMBRE_DEPTO = {o["value"]: o["label"] for o in OPCIONES_DEPTO}

# ---------------------------------------------------------------------------
# Estilo de los gráficos (paleta validada para daltonismo)
# ---------------------------------------------------------------------------
AZUL = "#2a78d6"
COLOR_SEXO = {"Hombre": "#2a78d6", "Mujer": "#eb6834", "Indeterminado": "#1baf7a"}
ROJO = "#e34948"
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf",
              "#1c5cab", "#184f95", "#104281", "#0d366b"]
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TENUE = "#898781"
GRILLA = "#e1e0d9"
EJE = "#c3c2b7"
FUENTE = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def estilo(fig: go.Figure, alto: int = 380, **kwargs) -> go.Figure:
    kwargs.setdefault("margin", dict(l=10, r=20, t=10, b=10))
    fig.update_layout(
        height=alto,
        font=dict(family=FUENTE, size=13, color=TINTA_2),
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        hoverlabel=dict(bgcolor="white", bordercolor=EJE, font=dict(family=FUENTE, color=TINTA)),
        separators=",.",
        **kwargs,
    )
    fig.update_xaxes(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
                     title_font=dict(color=TINTA_2), tickfont=dict(color=TENUE))
    fig.update_yaxes(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
                     title_font=dict(color=TINTA_2), tickfont=dict(color=TENUE))
    return fig


def fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def filtrar(depto: str, sexo: str) -> pd.DataFrame:
    d = DF
    if depto and depto != "TODOS":
        d = d[d["COD_DEPARTAMENTO"] == depto]
    if sexo and sexo != "TODOS":
        d = d[d["SEXO_TXT"] == sexo]
    return d


def ambito(depto: str, sexo: str) -> str:
    lugar = NOMBRE_DEPTO.get(depto, "Toda Colombia")
    if sexo and sexo != "TODOS":
        return f"{lugar} · {'Hombres' if sexo == 'Hombre' else 'Mujeres'}"
    return lugar


# ---------------------------------------------------------------------------
# Constructores de cada gráfico
# ---------------------------------------------------------------------------
def fig_mapa(sexo: str, depto_sel: str) -> go.Figure:
    d = filtrar("TODOS", sexo)
    tot = d.groupby(["COD_DEPARTAMENTO", "DEPTO"]).size().reset_index(name="MUERTES")
    tot["PCT"] = tot["MUERTES"] / tot["MUERTES"].sum() * 100
    tot["TXT"] = tot["MUERTES"].map(fmt)
    fig = go.Figure(go.Choroplethmap(
        geojson=GEOJSON,
        featureidkey="properties.DPTO_CCDGO",
        locations=tot["COD_DEPARTAMENTO"],
        z=tot["MUERTES"],
        customdata=tot[["DEPTO", "TXT", "PCT"]],
        colorscale=[[i / (len(RAMPA_AZUL) - 1), c] for i, c in enumerate(RAMPA_AZUL)],
        marker_line_color="#fcfcfb",
        marker_line_width=0.8,
        colorbar=dict(title=dict(text="Muertes", font=dict(size=12)), thickness=12, len=0.7,
                      tickformat=",d", outlinewidth=0),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} muertes"
                      "<br>%{customdata[2]:.1f}% del país<extra></extra>",
    ))
    if depto_sel and depto_sel != "TODOS":
        fila = tot[tot["COD_DEPARTAMENTO"] == depto_sel]
        fig.add_trace(go.Choroplethmap(
            geojson=GEOJSON, featureidkey="properties.DPTO_CCDGO",
            locations=fila["COD_DEPARTAMENTO"], z=[1],
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_color=TINTA, marker_line_width=3, hoverinfo="skip",
        ))
    # Mapa sin teselas externas: solo las geometrías del DANE sobre fondo blanco.
    fig.update_layout(map=dict(style="white-bg", center=dict(lat=4.3, lon=-73.5), zoom=4.1))
    return estilo(fig, alto=520)


def fig_lineas(depto: str, sexo: str) -> go.Figure:
    d = filtrar(depto, sexo)
    mes = d.groupby("MES").size().reindex(range(1, 13), fill_value=0)
    prom = mes.mean()
    fig = go.Figure(go.Scatter(
        x=MESES, y=mes.values, mode="lines+markers",
        line=dict(color=AZUL, width=2.5), marker=dict(size=8, color=AZUL, line=dict(color="white", width=2)),
        customdata=MESES_LARGOS,
        hovertemplate="<b>%{customdata}</b><br>%{y:,d} muertes<extra></extra>",
        name="Muertes",
    ))
    fig.add_hline(y=prom, line=dict(color=TENUE, width=1, dash="dot"),
                  annotation_text=f"Promedio mensual: {fmt(prom)}",
                  annotation_position="top left", annotation_font=dict(color=TINTA_2, size=12))
    imax, imin = int(mes.idxmax()), int(mes.idxmin())
    for i, pos in ((imax, "top center"), (imin, "bottom center")):
        fig.add_annotation(x=MESES[i - 1], y=mes[i], text=f"<b>{fmt(mes[i])}</b>",
                           showarrow=False, yshift=16 if pos.startswith("top") else -16,
                           font=dict(color=TINTA, size=12))
    fig.update_yaxes(title_text="Número de muertes", tickformat=",d",
                     range=[mes.min() * 0.85, mes.max() * 1.08])
    fig.update_xaxes(title_text="Mes de defunción (2019)", showgrid=False)
    return estilo(fig, alto=520, showlegend=False, hovermode="x")


def fig_violentas(depto: str, sexo: str) -> go.Figure:
    d = filtrar(depto, sexo)
    h = d[d["COD_MUERTE"].str.startswith("X95")]
    top = (h.groupby(["COD_DANE", "MPIO", "DEPTO"]).size().reset_index(name="CASOS")
           .sort_values(["CASOS", "MPIO"], ascending=[False, True]).head(5))
    top["ETIQ"] = top["MPIO"] + "<br><span style='font-size:11px;color:#898781'>" + top["DEPTO"] + "</span>"
    top = top.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=top["CASOS"], y=top["ETIQ"], orientation="h",
        marker=dict(color=ROJO, cornerradius=4),
        text=top["CASOS"].map(fmt), textposition="outside", textfont=dict(color=TINTA, size=12),
        customdata=top[["MPIO", "DEPTO"]],
        hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                      "%{x:,d} homicidios por arma de fuego (X95)<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_xaxes(title_text="Homicidios con arma de fuego (CIE-10 X95)", tickformat=",d")
    fig.update_yaxes(showgrid=False, title_text="Municipio")
    if top.empty:
        fig.add_annotation(text="Sin homicidios X95 para este filtro", showarrow=False,
                           xref="paper", yref="paper", x=0.5, y=0.5, font=dict(color=TENUE))
    return estilo(fig, showlegend=False, bargap=0.35)


def fig_circular(depto: str, sexo: str, universo: str) -> go.Figure:
    d = filtrar(depto, sexo)
    if universo == "CAPITALES":
        d = d[d["ES_CAPITAL"]]
    menor = (d.groupby(["COD_DANE", "MPIO", "DEPTO"]).size().reset_index(name="MUERTES")
             .sort_values(["MUERTES", "MPIO"]).head(10))
    menor["ETIQ"] = menor["MPIO"] + " (" + menor["DEPTO"] + ")"
    colores = RAMPA_AZUL[::-1][: len(menor)]
    tinta = ["white" if i < 7 else TINTA for i in range(len(menor))]
    fig = go.Figure(go.Pie(
        labels=menor["ETIQ"], values=menor["MUERTES"], sort=False, direction="clockwise",
        marker=dict(colors=colores, line=dict(color="#fcfcfb", width=2)),
        texttemplate="%{value:,d}", textposition="inside", insidetextfont=dict(color=tinta, size=12),
        hovertemplate="<b>%{label}</b><br>%{value:,d} muertes<br>%{percent} del grupo<extra></extra>",
    ))
    return estilo(fig, alto=420, legend=dict(font=dict(size=12, color=TINTA_2), x=1.02, y=0.5,
                                             yanchor="middle",
                                             title=dict(text="Municipio (departamento)",
                                                        font=dict(size=12, color=TINTA))),
                  margin=dict(l=10, r=10, t=10, b=10))


def datos_tabla(depto: str, sexo: str) -> list[dict]:
    d = filtrar(depto, sexo)
    total = len(d)
    top = d.groupby("COD_MUERTE").size().reset_index(name="TOTAL")
    top = top.merge(CODIGOS, on="COD_MUERTE", how="left")
    top = top.sort_values(["TOTAL", "COD_MUERTE"], ascending=[False, True]).head(10)
    top["PUESTO"] = range(1, len(top) + 1)
    top["TOTAL_TXT"] = top["TOTAL"].map(fmt)
    top["PCT_TXT"] = (top["TOTAL"] / total * 100).map(lambda v: f"{v:.2f}%".replace(".", ","))
    return top[["PUESTO", "COD_MUERTE", "DESCRIPCION", "TOTAL_TXT", "PCT_TXT"]].to_dict("records")


def fig_apiladas(modo: str, sexo_sel: str) -> go.Figure:
    t = DF.pivot_table(index="DEPTO", columns="SEXO_TXT", values="MES", aggfunc="size", fill_value=0)
    t = t.reindex(columns=["Hombre", "Mujer", "Indeterminado"], fill_value=0)
    t["TOTAL"] = t.sum(axis=1)
    t = t.sort_values("TOTAL")
    fig = go.Figure()
    for sexo in ["Hombre", "Mujer", "Indeterminado"]:
        val = t[sexo] / t["TOTAL"] * 100 if modo == "PCT" else t[sexo]
        atenuar = sexo_sel not in ("TODOS", None, sexo)
        fig.add_trace(go.Bar(
            y=t.index, x=val, name=sexo, orientation="h",
            marker=dict(color=COLOR_SEXO[sexo], line=dict(color="#fcfcfb", width=1)),
            opacity=0.25 if atenuar else 1,
            customdata=list(zip(t[sexo].map(fmt), (t[sexo] / t["TOTAL"] * 100))),
            hovertemplate=f"<b>%{{y}}</b><br>{sexo}: %{{customdata[0]}} muertes"
                          f" (%{{customdata[1]:.1f}}%)<extra></extra>",
        ))
    fig.update_xaxes(title_text="Porcentaje de muertes del departamento" if modo == "PCT"
                     else "Número de muertes", tickformat=".0f" if modo == "PCT" else ",d",
                     ticksuffix="%" if modo == "PCT" else "", side="top")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=TINTA_2), title_text="Departamento")
    return estilo(fig, alto=820, barmode="stack", bargap=0.25,
                  legend=dict(orientation="h", y=-0.03, x=0, yanchor="top", title_text="Sexo: ",
                              traceorder="normal"),
                  margin=dict(l=10, r=20, t=40, b=40))


def fig_histograma(depto: str, sexo: str) -> go.Figure:
    d = filtrar(depto, sexo)
    c = d["CICLO_VIDA"].value_counts().reindex(ORDEN_EDAD, fill_value=0)
    pct = c / c.sum() * 100 if c.sum() else c * 0
    fig = go.Figure(go.Bar(
        x=[f"{k.replace(' / ', ' /<br>')}<br><span style='font-size:11px;color:#898781'>{RANGO_EDAD[k]}</span>" for k in c.index],
        y=c.values, marker=dict(color=AZUL, cornerradius=4),
        customdata=list(zip(c.index, [RANGO_EDAD[k] for k in c.index], pct.values)),
        text=[fmt(v) for v in c.values], textposition="outside", textfont=dict(color=TINTA, size=11),
        hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>%{y:,d} muertes"
                      "<br>%{customdata[2]:.1f}% del total<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_yaxes(title_text="Número de muertes", tickformat=",d")
    fig.update_xaxes(title_text="Grupo de edad (GRUPO_EDAD1 agrupado según ciclo de vida)",
                     showgrid=False, tickangle=0, tickfont=dict(size=11))
    return estilo(fig, alto=430, bargap=0.08, showlegend=False, margin=dict(l=10, r=10, t=30, b=10))


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def tarjeta(titulo, descripcion, contenido, id_ambito=None, ancho="medio"):
    return html.Section(className=f"tarjeta {ancho}", children=[
        html.Div(className="tarjeta-cabecera", children=[
            html.H2(titulo),
            html.P(descripcion, className="descripcion"),
            html.Span(id=id_ambito, className="ambito") if id_ambito else None,
        ]),
        contenido,
    ])


def kpi(id_valor, etiqueta):
    return html.Div(className="kpi", children=[
        html.Span(id=id_valor, className="kpi-valor"),
        html.Span(etiqueta, className="kpi-etiqueta"),
    ])


app = Dash(__name__, title="Mortalidad en Colombia 2019")
server = app.server  # para gunicorn

GRAFICO_CFG = {"displaylogo": False, "locale": "es",
               "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

app.layout = html.Div(className="pagina", children=[
    html.Header(className="encabezado", children=[
        html.Div([
            html.P("DANE · Estadísticas Vitales · Defunciones no fetales", className="supra"),
            html.H1("Mortalidad en Colombia, 2019"),
            html.P("Explora cómo se distribuyeron las muertes por territorio, mes, causa, sexo y edad. "
                   "Haz clic en un departamento del mapa o usa los filtros para recalcular los gráficos.",
                   className="bajada"),
        ]),
    ]),

    html.Div(className="filtros", children=[
        html.Div([html.Label("Departamento", htmlFor="f-depto"),
                  dcc.Dropdown(id="f-depto", options=OPCIONES_DEPTO, value="TODOS", clearable=False)],
                 className="filtro"),
        html.Div([html.Label("Sexo", htmlFor="f-sexo"),
                  dcc.RadioItems(id="f-sexo", inline=True, className="segmentado",
                                 options=[{"label": "Todos", "value": "TODOS"},
                                          {"label": "Hombres", "value": "Hombre"},
                                          {"label": "Mujeres", "value": "Mujer"}],
                                 value="TODOS")],
                 className="filtro"),
        html.Button("Restablecer filtros", id="btn-reset", className="boton"),
    ]),

    html.Div(className="kpis", children=[
        kpi("k-total", "muertes registradas"),
        kpi("k-hom", "homicidios con arma de fuego (X95)"),
        kpi("k-mayores", "ocurrieron en personas de 60 años o más"),
        kpi("k-causa", "principal causa"),
    ]),

    html.Main(className="rejilla", children=[
        tarjeta("1. Muertes por departamento",
                "Distribución total de defunciones por departamento. Más oscuro = más muertes. "
                "Haz clic en un departamento para filtrar el resto de la página.",
                dcc.Graph(id="g-mapa", config={**GRAFICO_CFG, "scrollZoom": False}),
                id_ambito="a-mapa", ancho="medio"),
        tarjeta("2. Muertes por mes",
                "Total de defunciones en cada mes de 2019. La línea punteada marca el promedio mensual.",
                dcc.Graph(id="g-lineas", config=GRAFICO_CFG), id_ambito="a-lineas", ancho="medio"),
        tarjeta("3. Las 5 ciudades más violentas",
                "Municipios con más homicidios por agresión con disparo de armas de fuego "
                "y casos no especificados (CIE-10 X950–X959).",
                dcc.Graph(id="g-violentas", config=GRAFICO_CFG), id_ambito="a-violentas", ancho="medio"),
        tarjeta("4. Las 10 ciudades con menor mortalidad",
                "Municipios con el menor número de defunciones registradas en 2019.",
                html.Div([
                    dcc.RadioItems(id="f-universo", inline=True, className="segmentado chico",
                                   options=[{"label": "Todos los municipios", "value": "TODOS"},
                                            {"label": "Solo capitales de departamento", "value": "CAPITALES"}],
                                   value="TODOS"),
                    dcc.Graph(id="g-circular", config=GRAFICO_CFG),
                    html.P(id="nota-circular", className="nota"),
                ]),
                id_ambito="a-circular", ancho="medio"),
        tarjeta("5. Las 10 principales causas de muerte",
                "Códigos CIE-10 con más casos, ordenados de mayor a menor.",
                dash_table.DataTable(
                    id="t-causas",
                    columns=[
                        {"name": "#", "id": "PUESTO"},
                        {"name": "Código", "id": "COD_MUERTE"},
                        {"name": "Causa de muerte", "id": "DESCRIPCION"},
                        {"name": "Total de casos", "id": "TOTAL_TXT"},
                        {"name": "% del total", "id": "PCT_TXT"},
                    ],
                    style_as_list_view=True,
                    style_table={"overflowX": "auto"},
                    style_header={"fontWeight": "600", "backgroundColor": "#f3f2ee", "color": TINTA,
                                  "borderBottom": f"1px solid {EJE}", "fontFamily": FUENTE},
                    style_cell={"fontFamily": FUENTE, "fontSize": "14px", "padding": "10px 12px",
                                "textAlign": "left", "color": TINTA_2, "whiteSpace": "normal",
                                "height": "auto", "borderBottom": f"1px solid {GRILLA}"},
                    style_cell_conditional=[
                        {"if": {"column_id": c}, "textAlign": "right", "width": w,
                         "fontVariantNumeric": "tabular-nums"}
                        for c, w in (("TOTAL_TXT", "130px"), ("PCT_TXT", "100px"), ("PUESTO", "40px"))
                    ] + [{"if": {"column_id": "COD_MUERTE"}, "width": "80px", "fontWeight": "600",
                          "color": TINTA}],
                ),
                id_ambito="a-tabla", ancho="ancho"),
        tarjeta("6. Muertes por sexo en cada departamento",
                "Comparación de defunciones de hombres y mujeres por departamento. "
                "Cambia a porcentaje para comparar la proporción sin importar el tamaño del departamento.",
                html.Div([
                    dcc.RadioItems(id="f-modo", inline=True, className="segmentado chico",
                                   options=[{"label": "Número de muertes", "value": "ABS"},
                                            {"label": "Porcentaje (%)", "value": "PCT"}],
                                   value="ABS"),
                    dcc.Graph(id="g-apiladas", config=GRAFICO_CFG),
                ]), ancho="ancho"),
        tarjeta("7. Muertes a lo largo del ciclo de vida",
                "Distribución de las defunciones según los rangos de GRUPO_EDAD1 de la tabla de referencia.",
                dcc.Graph(id="g-histograma", config=GRAFICO_CFG), id_ambito="a-histograma", ancho="ancho"),
    ]),

    html.Footer(className="pie", children=[
        html.P(["Fuente: DANE — Estadísticas Vitales (EEVV) 2019, defunciones no fetales; "
                "catálogo CIE-10 y DIVIPOLA. Geometrías: Marco Geoestadístico Nacional 2018 (DANE). ",
                "Maestría en Inteligencia Artificial — Aplicaciones I, Universidad de La Salle."]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("f-depto", "value"),
    Output("f-sexo", "value"),
    Input("g-mapa", "clickData"),
    Input("btn-reset", "n_clicks"),
    State("f-depto", "value"),
    prevent_initial_call=True,
)
def seleccionar_depto(click, _reset, actual):
    if ctx.triggered_id == "btn-reset":
        return "TODOS", "TODOS"
    if click and click.get("points"):
        cod = click["points"][0].get("location")
        return ("TODOS" if cod == actual else cod), no_update
    return no_update, no_update


@callback(
    Output("g-mapa", "figure"), Output("g-lineas", "figure"), Output("g-violentas", "figure"),
    Output("t-causas", "data"), Output("g-histograma", "figure"),
    Output("a-mapa", "children"), Output("a-lineas", "children"), Output("a-violentas", "children"),
    Output("a-tabla", "children"), Output("a-histograma", "children"),
    Output("k-total", "children"), Output("k-hom", "children"),
    Output("k-mayores", "children"), Output("k-causa", "children"),
    Input("f-depto", "value"), Input("f-sexo", "value"),
)
def actualizar(depto, sexo):
    d = filtrar(depto, sexo)
    amb = ambito(depto, sexo)
    amb_mapa = ambito("TODOS", sexo)
    n = len(d)
    hom = d["COD_MUERTE"].str.startswith("X95").sum()
    mayores = d["CICLO_VIDA"].isin(["Vejez", "Longevidad / Centenarios"]).sum()
    tabla = datos_tabla(depto, sexo)
    causa = f"{tabla[0]['DESCRIPCION']} ({tabla[0]['COD_MUERTE']})" if tabla else "—"
    return (
        fig_mapa(sexo, depto), fig_lineas(depto, sexo), fig_violentas(depto, sexo),
        tabla, fig_histograma(depto, sexo),
        amb_mapa, amb, amb, amb, amb,
        fmt(n), fmt(hom), f"{(mayores / n * 100) if n else 0:.1f}%".replace(".", ","), causa,
    )


@callback(
    Output("g-circular", "figure"), Output("a-circular", "children"), Output("nota-circular", "children"),
    Input("f-depto", "value"), Input("f-sexo", "value"), Input("f-universo", "value"),
)
def actualizar_circular(depto, sexo, universo):
    fig = fig_circular(depto, sexo, universo)
    d = filtrar(depto, sexo)
    if universo == "CAPITALES":
        d = d[d["ES_CAPITAL"]]
    conteo = d.groupby("COD_DANE").size()
    nota = ""
    if not conteo.empty:
        minimo = conteo.min()
        empatados = (conteo == minimo).sum()
        if empatados > 1:
            nota = (f"Nota: {empatados} municipios empatan con {fmt(minimo)} "
                    f"{'muerte' if minimo == 1 else 'muertes'}; ante empates se ordenan alfabéticamente.")
    return fig, ambito(depto, sexo), nota


@callback(Output("g-apiladas", "figure"), Input("f-modo", "value"), Input("f-sexo", "value"))
def actualizar_apiladas(modo, sexo):
    return fig_apiladas(modo, sexo)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
