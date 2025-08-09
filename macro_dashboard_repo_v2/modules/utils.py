
def create_card(title, kv_dict):
    from dash import html
    import dash_bootstrap_components as dbc
    rows = []
    for k, v in kv_dict.items():
        rows.append(html.Div([html.Span(str(k)), html.Span(str(v) if v is not None else "—", className="float-end")],
                             className="py-1 border-bottom"))
    body = dbc.CardBody([html.H6(title, className="card-title"), *rows])
    return dbc.Card(body, className="shadow-sm h-100")

def pct_fmt(x):
    try:
        return f"{x:+.2f}%"
    except Exception:
        return "—"

def bp_fmt(x):
    try:
        return f"{x:+.0f}bp"
    except Exception:
        return "—"
