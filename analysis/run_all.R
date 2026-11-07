# Lance les analyses sur les évaluations sélectionnées.

if (.Platform$OS.type == "windows" && !l10n_info()[["UTF-8"]]) {
  Sys.setlocale("LC_CTYPE", ".UTF-8")
}
all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", all_args, value = TRUE)
if (length(file_arg) != 1) stop("Le script en cours d’exécution est introuvable.")
script_path <- normalizePath(sub("^--file=", "", file_arg), winslash = "/", mustWork = TRUE)
script_dir <- dirname(script_path)
source(file.path(script_dir, "functions_data.R"), encoding = "UTF-8")
source(file.path(script_dir, "functions_plots.R"), encoding = "UTF-8")
source(file.path(script_dir, "functions_final_plot.R"), encoding = "UTF-8")

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript run_all.R <dossier_entree> <dossier_sortie> [uuid_evaluation_finale] [uuid_evaluation_etalon] [dossier_descriptif]")
}
input_dir <- normalizePath(args[[1]], winslash = "/", mustWork = TRUE)
output_dir <- normalizePath(args[[2]], winslash = "/", mustWork = FALSE)
focus_id <- if (length(args) >= 3) as.character(args[[3]]) else ""
baseline_id <- if (length(args) >= 4) as.character(args[[4]]) else ""
# Valide les entrées avant d’envoyer les messages dans le journal.
organized <- length(args) >= 5
descriptive_dir <- if (organized) args[[5]] else output_dir
data_list <- load_analysis_data(input_dir)
assessment_table <- unique(data_list$responses[c("assessment_id", "assessment_date")])
assessment_table <- assessment_table[order(assessment_table$assessment_date, assessment_table$assessment_id), , drop = FALSE]
if (!nzchar(baseline_id) && nrow(assessment_table)) baseline_id <- as.character(assessment_table$assessment_id[[1]])
if (!nzchar(focus_id) && nrow(assessment_table)) focus_id <- as.character(tail(assessment_table$assessment_id, 1))

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
plot_dir <- file.path(output_dir, "figures")
dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)
general_figures <- file.path(descriptive_dir, "figures")
dir.create(general_figures, recursive = TRUE, showWarnings = FALSE)
log_path <- file.path(if (organized) dirname(descriptive_dir) else output_dir, "r_analysis.log")
log_connection <- file(log_path, open = "wt", encoding = "UTF-8")
sink(log_connection, type = "output", split = TRUE)
sink(log_connection, type = "message", append = TRUE)
on.exit({sink(type = "message"); sink(type = "output"); close(log_connection)}, add = TRUE)

cat("Analyse reproductible PyStats\n")
cat("Début :", format(Sys.time(), tz = "UTC", usetz = TRUE), "\n")
cat("Entrée :", input_dir, "\nSortie :", output_dir, "\nÉvaluation finale :", focus_id, "\nÉvaluation étalon :", baseline_id, "\n")
cat("Évaluations sélectionnées :", paste(assessment_table$assessment_id, collapse = ", "), "\n")

bootstrap_replicates <- suppressWarnings(as.integer(Sys.getenv("PYSTATS_BOOTSTRAP_REPLICATES", "2000")))
if (is.na(bootstrap_replicates) || bootstrap_replicates < 100L) {
  stop("PYSTATS_BOOTSTRAP_REPLICATES doit être un entier supérieur ou égal à 100.")
}

graph_status <- data.frame(
  graph_name = character(), file_stem = character(), status = character(),
  reason = character(), comment = character(), stringsAsFactors = FALSE
)
record_graph_status <- function(graph_name, file_stem, status, reason = "", comment = "") {
  graph_status <<- rbind(
    graph_status,
    data.frame(
      graph_name = graph_name, file_stem = file_stem, status = status,
      reason = reason, comment = comment, stringsAsFactors = FALSE
    )
  )
}
requirement <- function(ok, comment = "") list(ok = isTRUE(ok), comment = as.character(comment))
run_graph <- function(graph_name, file_stem, prerequisite, action) {
  if (is_teacher_view()) graph_name <- paste(graph_name, "(enseignant)")
  if (!isTRUE(prerequisite$ok)) {
    record_graph_status(graph_name, file_stem, "not_generated", "manque de données", prerequisite$comment)
    cat("Graphique omis :", graph_name, "– données insuffisantes –", prerequisite$comment, "\n")
    return(invisible(FALSE))
  }
  error <- tryCatch({action(); NULL}, error = function(error) error)
  if (is.null(error)) {
    record_graph_status(graph_name, file_stem, "generated")
    return(invisible(TRUE))
  }
  record_graph_status(graph_name, file_stem, "not_generated", "code", conditionMessage(error))
  cat("Graphique omis :", graph_name, "- code -", conditionMessage(error), "\n")
  invisible(FALSE)
}

# Calcule les effectifs à part pour signaler les graphiques sans données suffisantes.
focus_responses <- focus_rows(latest_attempt_rows(data_list$responses), focus_id)
focus_scored <- focus_responses[as.numeric(focus_responses$is_practice_item) == 0, , drop = FALSE]
timed <- focus_scored[focus_scored$completion_status == "answered" &
                      is.finite(focus_scored$total_response_time_ms), , drop = FALSE]
focus_students <- focus_rows(data_list$students, focus_id)
focus_families <- focus_rows(data_list$families, focus_id)
focus_items <- focus_rows(data_list$items, focus_id)
session_count <- length(unique(as.character(data_list$students$assessment_id)))
student_session_counts <- table(as.character(data_list$students$student_export_id))
repeated_students <- sum(student_session_counts >= 2)
baseline_students <- unique(as.character(
  data_list$responses$student_export_id[as.character(data_list$responses$assessment_id) == baseline_id]
))
final_students <- unique(as.character(
  data_list$responses$student_export_id[as.character(data_list$responses$assessment_id) == focus_id]
))
paired_students <- intersect(baseline_students, final_students)
anchor_rows <- data_list$responses[
  as.numeric(data_list$responses$is_practice_item) == 0 & as.numeric(data_list$responses$is_anchor_item) == 1,
  , drop = FALSE
]
final_plot_requirement <- if (baseline_id == focus_id) {
  requirement(FALSE, "deux évaluations distinctes sont nécessaires")
} else if (length(paired_students) < 5) {
  requirement(FALSE, "moins de cinq élèves sont présents aux deux dates")
} else {
  tryCatch(
    {
      final_prepared <- prepare_final_performance_data(data_list$responses, baseline_id, focus_id)
      requirement(TRUE)
    },
    error = function(error) requirement(FALSE, conditionMessage(error))
  )
}

correlations <- tryCatch(
  build_extended_correlation_results(data_list, replicates = bootstrap_replicates),
  error = function(error) {
    cat("Analyse des corrélations omise :", conditionMessage(error), "\n")
    data.frame()
  }
)
write.csv(correlations, file.path(output_dir, "correlation_results.csv"), row.names = FALSE, na = "")
positions <- tryCatch(
  position_summary(focus_responses),
  error = function(error) {
    cat("Synthèse par position omise :", conditionMessage(error), "\n")
    data.frame()
  }
)
write.csv(positions, file.path(output_dir, "position_effect_summary.csv"), row.names = FALSE, na = "")

run_graph(
  "Performance par famille", "06_fact_family_performance",
  requirement(nrow(focus_families) > 0, "aucune famille de faits exploitable dans l’évaluation finale"),
  function() save_plot_formats(general_figures, "06_fact_family_performance", function() draw_family_performance(data_list$families, focus_id))
)

run_graph(
  "Difficulté des items", "07_item_difficulty",
  requirement(nrow(focus_items) > 0, "aucun item final ne possède de résumé exploitable"),
  function() save_plot_formats(general_figures, "07_item_difficulty", function() draw_item_difficulty(data_list$items, focus_id, timed), 2200, 1400)
)

run_graph(
  "Distribution des temps individuels par table", "13_distribution_temps",
  requirement(nrow(timed) > 0, "aucune réponse chronométrée"),
  function() write_table_distributions(timed, file.path(general_figures, "13_distribution_temps.pdf"), timed$assessment_date[1])
)

correlation_view <- function(id) {
  block <- focus_rows(data_list$students, id)
  index <- match(id, assessment_table$assessment_id)
  caption <- sprintf("Évaluation %d du %s   |   %d élèves", index, assessment_table$assessment_date[index],
                     length(unique(block$student_export_id)))
  if (nrow(block) < 3) return(empty_plot("Moins de trois élèves avec données.", caption))
  draw_correlogram(block, caption)
  mtext(sprintf("Sélection complète : %d élèves distincts, %d évaluation(s), %d passations.",
                length(unique(data_list$students$student_export_id)), nrow(assessment_table), nrow(data_list$students)),
        side = 1, line = 10.2, cex = 0.70)
}
run_graph(
  "Corrélogramme", "08_correlogram",
  requirement(nrow(data_list$students) >= 3, "moins de trois résumés élève-évaluation"),
  function() {
    save_plot_formats(general_figures, "08_correlogram", function() correlation_view(focus_id), 1700, 1600)
    if (nrow(assessment_table) > 1) {
      pdf(file.path(general_figures, "08_correlogram_par_evaluation.pdf"), width = 9.5, height = 9, useDingbats = FALSE)
      on.exit(dev.off(), add = TRUE)
      for (id in assessment_table$assessment_id) correlation_view(id)
    }
  }
)

run_graph(
  "Effets de position", "09_position_effects",
  requirement(length(unique(focus_scored$item_position)) >= 2, "moins de deux positions d’item observées"),
  function() save_plot_formats(general_figures, "09_position_effects", function() draw_position_effects(data_list$responses, focus_id), 1800, 1500)
)

run_graph(
  "Évolution par famille", "11_fact_family_evolution",
  requirement(session_count >= 2 && nrow(data_list$families) > 0, "au moins deux évaluations avec familles sont nécessaires"),
  function() save_plot_formats(general_figures, "11_fact_family_evolution", function() draw_family_evolution(data_list$families), 1800, 1500)
)

run_graph(
  "Évolution des items d’ancrage", "12_anchor_item_evolution",
  requirement(session_count >= 2 && nrow(anchor_rows) > 0, "aucun item d’ancrage observé dans le pool sélectionné"),
  function() save_plot_formats(general_figures, "12_anchor_item_evolution", function() draw_anchor_evolution(data_list$responses), 1800, 1400)
)

render_student_views <- function(output_dir, identities = NULL) {
  plot_dir <- file.path(output_dir, "figures")
  previous <- options(pystats.student_names = identities)
  on.exit(options(previous), add = TRUE)
  dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)
  run_graph(
    "Carte de chaleur élèves × items", "01_heatmap_students_items",
    requirement(nrow(focus_scored) > 0, "aucune réponse notée dans l’évaluation finale"),
    function() save_plot_formats(plot_dir, "01_heatmap_students_items", function() draw_heatmap(data_list$responses, focus_id), 2200, 1400)
  )

  run_graph(
    "Profils vitesse–exactitude", "02_student_speed_accuracy",
    requirement(nrow(focus_students) >= 2, "moins de deux élèves disposent d’un résumé final"),
    function() save_plot_formats(plot_dir, "02_student_speed_accuracy", function() draw_student_scatter(data_list$students, focus_id))
  )

  run_graph(
    "Évolution des temps de réaction", "03_reaction_time_evolution",
    requirement(session_count >= 2 && repeated_students >= 2, "au moins deux évaluations et deux élèves appariés sont nécessaires"),
    function() save_plot_formats(plot_dir, "03_reaction_time_evolution", function() draw_reaction_evolution(data_list$students))
  )

  run_graph(
    "Évolution de la réussite", "04_success_evolution",
    requirement(session_count >= 2 && repeated_students >= 2, "au moins deux évaluations et deux élèves appariés sont nécessaires"),
    function() save_plot_formats(plot_dir, "04_success_evolution", function() draw_success_evolution(data_list$students))
  )

  run_graph(
    "Trajectoires vitesse–exactitude", "05_speed_accuracy_trajectories",
    requirement(session_count >= 2 && repeated_students >= 2, "au moins deux évaluations et deux élèves appariés sont nécessaires"),
    function() save_plot_formats(plot_dir, "05_speed_accuracy_trajectories", function() draw_speed_accuracy_trajectory(data_list$students))
  )

  run_graph(
    "Coordonnées parallèles", "10_parallel_coordinates",
    requirement(nrow(focus_students) >= 3, "moins de trois élèves disposent de variables multidimensionnelles"),
    function() save_plot_formats(plot_dir, "10_parallel_coordinates", function() draw_parallel_coordinates(data_list$students, focus_id), 2000, 1300)
  )

  run_graph(
    "Position finale : réussite, fluence et progression", "final_performance_scatter",
    final_plot_requirement,
    function() generate_final_performance_outputs(data_list, baseline_id, focus_id, output_dir, final_prepared)
  )

  run_graph(
    "Nuage vitesse–exactitude interactif", "student_speed_accuracy_interactive",
    requirement(nrow(focus_students) >= 2, "moins de deux élèves disposent d’un résumé final"),
    function() write_interactive_scatter(data_list$students, focus_id, file.path(output_dir, "student_speed_accuracy_interactive.html"))
  )

  run_graph(
    "Coordonnées parallèles interactives", "parallel_coordinates_interactive",
    requirement(nrow(focus_students) >= 3, "moins de trois élèves disposent de variables multidimensionnelles"),
    function() write_interactive_parallel(data_list$students, focus_id, file.path(output_dir, "parallel_coordinates_interactive.html"))
  )

  if (nrow(focus_students) > 0) {
    write_class_report(data_list, focus_id, file.path(output_dir, "class_report.pdf"))
  }
  if (nrow(data_list$students) > 0) {
    write_individual_reports(data_list$students, file.path(output_dir, "individual_reports"))
  }
}
render_student_views(output_dir)
write.csv(graph_status, file.path(output_dir, "graph_generation_status.csv"), row.names = FALSE, na = "")
if (length(args) >= 6) {
  graph_status <- graph_status[FALSE, ]
  identity_file <- args[[6]]
  identity_rows <- unique(read.csv(identity_file, stringsAsFactors = FALSE, fileEncoding = "UTF-8",
                                   colClasses = "character", na.strings = character())[
    c("student_export_id", "last_name", "first_name")])
  labels <- trimws(paste(identity_rows$last_name, identity_rows$first_name))
  ambiguous <- duplicated(labels) | duplicated(labels, fromLast = TRUE) | !nzchar(labels)
  labels[ambiguous] <- paste(labels[ambiguous], identity_rows$student_export_id[ambiguous])
  names(labels) <- identity_rows$student_export_id
  render_student_views(dirname(identity_file), labels)
  write.csv(graph_status, file.path(dirname(identity_file), "graph_generation_status.csv"), row.names = FALSE, na = "")
}

session_lines <- capture.output(sessionInfo())
writeLines(session_lines, file.path(output_dir, "R_SESSION_INFO.txt"), useBytes = TRUE)
metadata <- data.frame(
  field = c(
    "generated_utc", "r_version", "input_dir", "selected_assessment_ids",
    "baseline_assessment_id", "focus_assessment_id", "normality_assumed", "bootstrap_replicates"
  ),
  value = c(
    format(Sys.time(), tz = "UTC", usetz = TRUE), R.version.string, input_dir,
    paste(assessment_table$assessment_id, collapse = "|"), baseline_id, focus_id,
    "false", as.character(bootstrap_replicates)
  ),
  stringsAsFactors = FALSE
)
write.csv(metadata, file.path(output_dir, "analysis_metadata.csv"), row.names = FALSE)
cat("Fin :", format(Sys.time(), tz = "UTC", usetz = TRUE), "\n")
