from __future__ import annotations

import pandas as pd
import plotly.express as px
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

IRIS_DF = px.data.iris().rename(
    columns={
        "sepal_length": "Sepal.Length",
        "sepal_width": "Sepal.Width",
        "petal_length": "Petal.Length",
        "petal_width": "Petal.Width",
        "species": "Species",
    }
)

app_ui = ui.page_fluid(
    ui.h2("Python Shiny Docker Demo"),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Filters"),
            ui.input_select(
                id="species",
                label="Species",
                choices=["All", *sorted(IRIS_DF["Species"].unique().tolist())],
                selected="All",
            ),
        ),
        ui.h4("Iris Table"),
        ui.output_table("iris_table"),
        ui.hr(),
        ui.h4("Plotly Scatter"),
        output_widget("scatter_plot"),
    ),
)


def server(input, output, session):
    @reactive.calc
    def filtered_iris() -> pd.DataFrame:
        species = input.species()
        if species == "All":
            return IRIS_DF
        return IRIS_DF.loc[IRIS_DF["Species"] == species]

    @render.table
    def iris_table():
        return filtered_iris().head(10)

    @render_widget
    def scatter_plot():
        frame = filtered_iris()
        return px.scatter(
            frame,
            x="Sepal.Length",
            y="Petal.Length",
            color="Species",
            title="Sepal Length vs Petal Length",
        )


app = App(app_ui, server)
