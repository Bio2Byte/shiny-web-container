library(shiny)
library(plotly)

ui <- fluidPage(
  titlePanel("R Shiny Docker Demo"),
  sidebarLayout(
    sidebarPanel(
      h4("Filters"),
      selectInput(
        inputId = "species",
        label = "Species",
        choices = c("All", unique(iris$Species)),
        selected = "All"
      )
    ),
    mainPanel(
      h4("Iris Table"),
      tableOutput("iris_table"),
      hr(),
      h4("Plotly Scatter"),
      plotlyOutput("scatter_plot")
    )
  )
)

server <- function(input, output, session) {
  filtered_iris <- reactive({
    if (input$species == "All") {
      iris
    } else {
      iris[iris$Species == input$species, ]
    }
  })

  output$iris_table <- renderTable({
    head(filtered_iris(), 10)
  })

  output$scatter_plot <- renderPlotly({
    plot_ly(
      data = filtered_iris(),
      x = ~Sepal.Length,
      y = ~Petal.Length,
      type = "scatter",
      mode = "markers",
      color = ~Species
    ) |>
      layout(
        xaxis = list(title = "Sepal Length"),
        yaxis = list(title = "Petal Length")
      )
  })
}

shinyApp(ui = ui, server = server)
