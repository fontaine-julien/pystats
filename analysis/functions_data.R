# Chargement des données et statistiques descriptives robustes.

read_required_csv <- function(path, required_columns) {
  if (!file.exists(path)) stop(paste("Fichier obligatoire introuvable :", path))
  data <- read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, na.strings = c("", "NA"))
  missing <- setdiff(required_columns, names(data))
  if (length(missing) > 0) {
    stop(paste("Fichier incomplet", basename(path), "– colonnes manquantes :", paste(missing, collapse = ", ")))
  }
  data
}

load_analysis_data <- function(input_dir, descriptive_dir = input_dir) {
  responses <- read_required_csv(
    file.path(input_dir, "responses_long_pseudonymized.csv"),
    c("assessment_id", "assessment_date", "student_export_id", "item_position", "is_practice_item",
      "is_anchor_item", "fact_family", "is_correct", "total_response_time_ms", "timeout_status",
      "completion_status", "attempt_id", "reaction_time_first_key_ms", "typing_time_ms", "entered_answer",
      "operation_type", "operand_1", "operand_2", "expected_answer")
  )
  students <- read_required_csv(
    file.path(input_dir, "student_assessment_summary.csv"),
    c("assessment_id", "assessment_date", "student_export_id", "success_rate", "median_correct_time_ms",
      "mean_correct_time_ms", "correct_per_minute", "omission_rate", "timeout_rate")
  )
  families <- read_required_csv(
    file.path(descriptive_dir, "fact_family_summary.csv"),
    c("assessment_id", "assessment_date", "fact_family", "success_rate", "median_correct_time_ms")
  )
  items <- read_required_csv(
    file.path(descriptive_dir, "item_difficulty_summary.csv"),
    c("assessment_id", "fact_key", "fact_family", "success_rate", "median_correct_time_ms", "presentation_count")
  )
  class_long <- read_required_csv(
    file.path(descriptive_dir, "class_longitudinal_summary.csv"),
    c("assessment_id", "assessment_date", "student_count", "median_student_success_rate",
      "iqr_student_success_rate", "median_student_correct_time_ms", "iqr_student_correct_time_ms")
  )
  list(responses = responses, students = students, families = families, items = items, class_long = class_long)
}

latest_attempt_rows <- function(responses) {
  if (nrow(responses) == 0) return(responses)
  key <- paste(responses$assessment_id, responses$student_export_id, sep = "\r")
  latest <- tapply(as.character(responses$attempt_id), key, function(values) tail(values, 1))
  responses[as.character(responses$attempt_id) == unname(latest[key]), , drop = FALSE]
}

add_session_number <- function(data) {
  if (nrow(data) == 0) {
    data$session_number <- integer(0)
    return(data)
  }
  assessment_table <- unique(data[c("assessment_id", "assessment_date")])
  assessment_table <- assessment_table[order(assessment_table$assessment_date, assessment_table$assessment_id), ]
  assessment_table$session_number <- seq_len(nrow(assessment_table))
  merge(data, assessment_table, by = c("assessment_id", "assessment_date"), all.x = TRUE, sort = FALSE)
}

safe_median <- function(values) {
  values <- as.numeric(values)
  values <- values[is.finite(values)]
  if (length(values) == 0) NA_real_ else median(values)
}

safe_mean <- function(values) {
  values <- as.numeric(values)
  values <- values[is.finite(values)]
  if (length(values) == 0) NA_real_ else mean(values)
}

safe_iqr <- function(values) {
  values <- as.numeric(values)
  values <- values[is.finite(values)]
  if (length(values) == 0) NA_real_ else IQR(values, type = 7)
}

cluster_bootstrap_correlation <- function(data, subject, x, y, method = "spearman", replicates = 500L, seed = 20260731L) {
  complete <- data[is.finite(as.numeric(data[[x]])) & is.finite(as.numeric(data[[y]])) & !is.na(data[[subject]]), ]
  subjects <- unique(as.character(complete[[subject]]))
  estimate <- suppressWarnings(cor(as.numeric(complete[[x]]), as.numeric(complete[[y]]), method = method))
  if (nrow(complete) < 4 || length(subjects) < 3 || !is.finite(estimate)) {
    return(c(estimate = estimate, ci_low = NA_real_, ci_high = NA_real_, n_obs = nrow(complete), n_subjects = length(subjects)))
  }
  set.seed(seed)
  boot <- rep(NA_real_, replicates)
  row_blocks <- split(seq_len(nrow(complete)), as.character(complete[[subject]]))
  x_values <- as.numeric(complete[[x]])
  y_values <- as.numeric(complete[[y]])
  for (index in seq_len(replicates)) {
    sampled <- sample(subjects, length(subjects), replace = TRUE)
    sampled_rows <- unlist(row_blocks[sampled], use.names = FALSE)
    boot[[index]] <- suppressWarnings(cor(x_values[sampled_rows], y_values[sampled_rows], method = method))
  }
  boot <- boot[is.finite(boot)]
  interval <- if (length(boot) >= 50) quantile(boot, c(0.025, 0.975), names = FALSE, type = 7) else c(NA_real_, NA_real_)
  c(estimate = estimate, ci_low = interval[[1]], ci_high = interval[[2]], n_obs = nrow(complete), n_subjects = length(subjects))
}

repeated_rank_correlation <- function(data, subject, x, y, replicates = 500L) {
  complete <- data[is.finite(as.numeric(data[[x]])) & is.finite(as.numeric(data[[y]])) & !is.na(data[[subject]]), ]
  if (nrow(complete) == 0) {
    return(c(estimate = NA_real_, ci_low = NA_real_, ci_high = NA_real_, n_obs = 0, n_subjects = 0))
  }
  complete$.x_rank <- ave(as.numeric(complete[[x]]), complete[[subject]], FUN = rank, ties.method = "average")
  complete$.y_rank <- ave(as.numeric(complete[[y]]), complete[[subject]], FUN = rank, ties.method = "average")
  complete$.x_center <- complete$.x_rank - ave(complete$.x_rank, complete[[subject]], FUN = mean)
  complete$.y_center <- complete$.y_rank - ave(complete$.y_rank, complete[[subject]], FUN = mean)
  cluster_bootstrap_correlation(complete, subject, ".x_center", ".y_center", "pearson", replicates)
}

build_correlation_results <- function(data_list, replicates = 500L) {
  students <- add_session_number(data_list$students)
  responses <- latest_attempt_rows(data_list$responses)
  responses <- responses[responses$is_practice_item == 0 & responses$completion_status == "answered", , drop = FALSE]
  results <- list()
  add_result <- function(question, level, method, values, caveat) {
    data.frame(
      question = question,
      level = level,
      method = method,
      coefficient = unname(values[["estimate"]]),
      ci_low = unname(values[["ci_low"]]),
      ci_high = unname(values[["ci_high"]]),
      n_observations = as.integer(values[["n_obs"]]),
      n_students = as.integer(values[["n_subjects"]]),
      caveat = caveat,
      stringsAsFactors = FALSE
    )
  }
  values <- cluster_bootstrap_correlation(
    students, "student_export_id", "median_correct_time_ms", "success_rate", "spearman", replicates
  )
  results[[length(results) + 1]] <- add_result(
    "Temps médian correct et exactitude", "élève-évaluation", "Spearman; bootstrap par élève", values,
    "Association descriptive; les sessions répétées sont rééchantillonnées par élève."
  )
  values <- cluster_bootstrap_correlation(
    students, "student_export_id", "correct_per_minute", "success_rate", "spearman", replicates
  )
  results[[length(results) + 1]] <- add_result(
    "Réponses exactes par minute et exactitude", "élève-évaluation", "Spearman; bootstrap par élève", values,
    "Le score de débit ne remplace pas les deux dimensions séparées."
  )
  if ("correct_time_sd_ms" %in% names(students)) {
    values <- cluster_bootstrap_correlation(
      students, "student_export_id", "correct_time_sd_ms", "success_rate", "spearman", replicates
    )
    results[[length(results) + 1]] <- add_result(
      "Variabilité temporelle et exactitude", "élève-évaluation", "Spearman; bootstrap par élève", values,
      "Écart-type instable quand peu de réponses exactes."
    )
  }
  if (nrow(responses) > 0) {
    responses$is_correct_numeric <- as.numeric(responses$is_correct)
    values <- repeated_rank_correlation(
      responses, "student_export_id", "total_response_time_ms", "is_correct_numeric", replicates
    )
    results[[length(results) + 1]] <- add_result(
      "Temps total et exactitude par item", "réponse", "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "Exploratoire avec issue binaire; un modèle mixte logistique est préférable pour une analyse confirmatoire."
    )
    values <- repeated_rank_correlation(
      responses, "student_export_id", "item_position", "total_response_time_ms", replicates
    )
    results[[length(results) + 1]] <- add_result(
      "Position et temps total", "réponse", "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "Peut refléter fatigue, échauffement ou difficulté résiduelle des items."
    )
  }
  do.call(rbind, results)
}

build_extended_correlation_results <- function(data_list, replicates = 500L) {
  output <- list(build_correlation_results(data_list, replicates))
  students <- add_session_number(data_list$students)
  responses <- latest_attempt_rows(data_list$responses)
  responses <- responses[
    responses$is_practice_item == 0 & responses$completion_status == "answered", , drop = FALSE
  ]
  add_result <- function(question, level, method, values, caveat) {
    data.frame(
      question = question,
      level = level,
      method = method,
      coefficient = unname(values[["estimate"]]),
      ci_low = unname(values[["ci_low"]]),
      ci_high = unname(values[["ci_high"]]),
      n_observations = as.integer(values[["n_obs"]]),
      n_students = as.integer(values[["n_subjects"]]),
      caveat = caveat,
      stringsAsFactors = FALSE
    )
  }
  append_result <- function(question, level, method, values, caveat) {
    output[[length(output) + 1]] <<- add_result(question, level, method, values, caveat)
  }

  students$error_rate <- 1 - as.numeric(students$success_rate)
  values <- cluster_bootstrap_correlation(
    students, "student_export_id", "median_correct_time_ms", "error_rate", "spearman", replicates
  )
  append_result(
    "Temps médian correct et taux d’erreur", "élève-évaluation", "Spearman; bootstrap par élève", values,
    "Le taux d’erreur est le complément de l’exactitude; la ligne explicite la direction sans créer une dimension indépendante."
  )

  for (assessment_id in unique(as.character(students$assessment_id))) {
    session <- students[as.character(students$assessment_id) == assessment_id, , drop = FALSE]
    values <- cluster_bootstrap_correlation(
      session, "student_export_id", "median_correct_time_ms", "success_rate", "spearman", replicates
    )
    session_label <- paste0("session ", session$session_number[[1]], " (", session$assessment_date[[1]], ")")
    append_result(
      paste("Temps médian correct et exactitude —", session_label), "élève-session",
      "Spearman; bootstrap par élève", values,
      "Association transversale propre à une session; elle ne mesure pas une progression intra-élève."
    )
  }

  trajectory_blocks <- split(students, as.character(students$student_export_id))
  trajectories <- do.call(rbind, lapply(trajectory_blocks, function(block) {
    block <- block[order(block$assessment_date, block$assessment_id), , drop = FALSE]
    if (nrow(block) < 2) return(NULL)
    data.frame(
      student_export_id = block$student_export_id[[1]],
      initial_success_rate = as.numeric(block$success_rate[[1]]),
      success_rate_change = as.numeric(tail(block$success_rate, 1)) - as.numeric(block$success_rate[[1]]),
      stringsAsFactors = FALSE
    )
  }))
  if (!is.null(trajectories) && nrow(trajectories)) {
    values <- cluster_bootstrap_correlation(
      trajectories, "student_export_id", "initial_success_rate", "success_rate_change", "spearman", replicates
    )
    append_result(
      "Performance initiale et progression de l’exactitude", "élève", "Spearman; bootstrap par élève", values,
      "Le couplage mathématique et la régression vers la moyenne peuvent créer une association négative."
    )
  }

  if (nrow(responses) > 0) {
    responses$is_correct_numeric <- as.numeric(responses$is_correct)
    responses$response_length <- nchar(as.character(responses$entered_answer))

    values <- repeated_rank_correlation(
      responses, "student_export_id", "reaction_time_first_key_ms", "is_correct_numeric", replicates
    )
    append_result(
      "Latence du premier appui et exactitude", "réponse",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "Le premier appui reflète aussi l’attention et l’interaction avec le clavier."
    )

    values <- repeated_rank_correlation(
      responses, "student_export_id", "typing_time_ms", "response_length", replicates
    )
    append_result(
      "Temps de saisie et longueur de la réponse", "réponse",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "La longueur provient de la réponse validée; les corrections restent disponibles dans le fichier brut."
    )

    values <- repeated_rank_correlation(
      responses, "student_export_id", "item_position", "is_correct_numeric", replicates
    )
    append_result(
      "Position et exactitude", "réponse",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "La position reste confondue avec l’ordre figé et la difficulté propre des items."
    )

    family_keys <- interaction(
      responses$assessment_id, responses$student_export_id, responses$fact_family,
      drop = TRUE, lex.order = TRUE
    )
    family_blocks <- split(responses, family_keys)
    family_students <- do.call(rbind, lapply(family_blocks, function(block) {
      correct_times <- as.numeric(block$total_response_time_ms[block$is_correct_numeric == 1])
      data.frame(
        assessment_id = as.character(block$assessment_id[[1]]),
        student_export_id = as.character(block$student_export_id[[1]]),
        fact_family = as.character(block$fact_family[[1]]),
        family_success_rate = mean(block$is_correct_numeric, na.rm = TRUE),
        family_median_correct_time_ms = safe_median(correct_times),
        stringsAsFactors = FALSE
      )
    }))
    student_globals <- students[c(
      "assessment_id", "student_export_id", "success_rate", "median_correct_time_ms"
    )]
    names(student_globals)[3:4] <- c("global_success_rate", "global_median_correct_time_ms")
    family_students <- merge(
      family_students, student_globals, by = c("assessment_id", "student_export_id"), all.x = TRUE, sort = FALSE
    )
    values <- repeated_rank_correlation(
      family_students, "student_export_id", "family_success_rate", "global_success_rate", replicates
    )
    append_result(
      "Réussite d’une famille et réussite globale", "élève-famille-session",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "Une famille contribue mécaniquement au score global; l’association sert au repérage, pas à une validation externe."
    )
    values <- repeated_rank_correlation(
      family_students, "student_export_id", "family_median_correct_time_ms", "global_median_correct_time_ms", replicates
    )
    append_result(
      "Temps d’une famille et temps global", "élève-famille-session",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "Le temps global contient la famille comparée et le nombre de faits par famille peut différer."
    )

    anchor_keys <- interaction(
      responses$assessment_id, responses$student_export_id, drop = TRUE, lex.order = TRUE
    )
    anchor_blocks <- split(responses, anchor_keys)
    anchor_students <- do.call(rbind, lapply(anchor_blocks, function(block) {
      anchor <- block[as.numeric(block$is_anchor_item) == 1, , drop = FALSE]
      renewed <- block[as.numeric(block$is_anchor_item) == 0, , drop = FALSE]
      if (!nrow(anchor) || !nrow(renewed)) return(NULL)
      data.frame(
        student_export_id = as.character(block$student_export_id[[1]]),
        anchor_success_rate = mean(as.numeric(anchor$is_correct), na.rm = TRUE),
        renewed_success_rate = mean(as.numeric(renewed$is_correct), na.rm = TRUE),
        anchor_median_time_ms = safe_median(anchor$total_response_time_ms[as.numeric(anchor$is_correct) == 1]),
        renewed_median_time_ms = safe_median(renewed$total_response_time_ms[as.numeric(renewed$is_correct) == 1]),
        stringsAsFactors = FALSE
      )
    }))
    if (!is.null(anchor_students) && nrow(anchor_students)) {
      values <- cluster_bootstrap_correlation(
        anchor_students, "student_export_id", "anchor_success_rate", "renewed_success_rate", "spearman", replicates
      )
      append_result(
        "Exactitude sur ancres et items renouvelés", "élève-session", "Spearman; bootstrap par élève", values,
        "Les ancres peuvent bénéficier de la familiarité et ne constituent pas un équating formel."
      )
      values <- cluster_bootstrap_correlation(
        anchor_students, "student_export_id", "anchor_median_time_ms", "renewed_median_time_ms", "spearman", replicates
      )
      append_result(
        "Temps sur ancres et items renouvelés", "élève-session", "Spearman; bootstrap par élève", values,
        "La difficulté et le nombre d’items ne sont pas nécessairement identiques entre les deux ensembles."
      )
    }

    responses$fact_key <- paste(
      responses$operation_type, responses$operand_1, responses$operand_2, responses$expected_answer, sep = ":"
    )
    item_difficulty <- data_list$items[c("assessment_id", "fact_key", "success_rate")]
    names(item_difficulty)[3] <- "item_success_rate"
    response_difficulty <- merge(
      responses, item_difficulty, by = c("assessment_id", "fact_key"), all.x = TRUE, sort = FALSE
    )
    response_difficulty$item_empirical_difficulty <- 1 - as.numeric(response_difficulty$item_success_rate)
    correct_difficulty <- response_difficulty[
      response_difficulty$is_correct_numeric == 1, , drop = FALSE
    ]
    values <- repeated_rank_correlation(
      correct_difficulty, "student_export_id", "item_empirical_difficulty", "total_response_time_ms", replicates
    )
    append_result(
      "Difficulté empirique d’un item et temps correct", "réponse correcte",
      "Corrélation de rang centrée intra-élève; bootstrap par élève", values,
      "La difficulté empirique est 1 moins la réussite de classe; l’échantillon ne constitue pas un étalonnage psychométrique."
    )
  }
  do.call(rbind, output)
}

position_summary <- function(responses) {
  scored <- latest_attempt_rows(responses)
  scored <- scored[scored$is_practice_item == 0, , drop = FALSE]
  positions <- sort(unique(scored$item_position))
  rows <- lapply(positions, function(position) {
    block <- scored[scored$item_position == position, , drop = FALSE]
    answered <- block[block$completion_status == "answered", , drop = FALSE]
    correct_times <- as.numeric(answered$total_response_time_ms[answered$is_correct == 1])
    data.frame(
      item_position = position,
      n_presented = sum(block$completion_status != "not_presented"),
      success_rate = if (nrow(answered)) mean(as.numeric(answered$is_correct), na.rm = TRUE) else NA_real_,
      median_correct_time_ms = safe_median(correct_times),
      omission_rate = mean(block$completion_status == "omission", na.rm = TRUE),
      timeout_rate = mean(block$timeout_status != "none", na.rm = TRUE)
    )
  })
  do.call(rbind, rows)
}
