# Graphique final et données utilisées pour le tracer.

summarize_final_plot_session <- function(responses, assessment_id, prefix) {
  session <- responses[as.character(responses$assessment_id) == assessment_id, , drop = FALSE]
  students <- sort(unique(as.character(session$student_export_id)))
  if (!length(students)) return(data.frame())
  rows <- lapply(students, function(student_id) {
    block <- session[as.character(session$student_export_id) == student_id, , drop = FALSE]
    valid_presented <- block$completion_status %in% c("answered", "omission", "timeout", "global_timeout")
    valid_answered <- block$completion_status == "answered" &
      is.finite(as.numeric(block$total_response_time_ms)) & as.numeric(block$total_response_time_ms) > 0
    correct <- block$completion_status == "answered" & as.numeric(block$is_correct) == 1
    correct_count <- sum(correct, na.rm = TRUE)
    presented_count <- sum(valid_presented, na.rm = TRUE)
    duration_seconds <- sum(as.numeric(block$total_response_time_ms[valid_answered]), na.rm = TRUE) / 1000
    data.frame(
      student_export_id = student_id,
      correct_count = correct_count,
      items_presented = presented_count,
      valid_answered_items = sum(valid_answered, na.rm = TRUE),
      valid_duration_seconds = duration_seconds,
      accuracy = if (presented_count > 0) correct_count / presented_count else NA_real_,
      exact_rate_per_second = if (duration_seconds > 0) correct_count / duration_seconds else NA_real_,
      omission_count = sum(block$completion_status == "omission", na.rm = TRUE),
      timeout_count = sum(block$completion_status %in% c("timeout", "global_timeout"), na.rm = TRUE),
      interrupted_count = sum(block$completion_status == "interrupted", na.rm = TRUE),
      not_presented_count = sum(block$completion_status == "not_presented", na.rm = TRUE),
      stringsAsFactors = FALSE
    )
  })
  output <- do.call(rbind, rows)
  names(output)[names(output) != "student_export_id"] <- paste0(prefix, "_", names(output)[names(output) != "student_export_id"])
  output
}

robust_bivariate_model <- function(points) {
  points <- as.matrix(points)
  if (nrow(points) < 5 || ncol(points) != 2) stop("Il faut au moins cinq élèves avec des mesures complètes.")
  center <- NULL
  covariance <- NULL
  method <- ""
  warning <- ""
  if (requireNamespace("robustbase", quietly = TRUE)) {
    fitted <- tryCatch(robustbase::covMcd(points), error = function(error) error)
    if (!inherits(fitted, "error")) {
      center <- as.numeric(fitted$center)
      covariance <- as.matrix(fitted$cov)
      method <- "robustbase::covMcd"
    } else {
      warning <- paste("Échec de covMcd :", conditionMessage(fitted))
    }
  } else {
    warning <- "robustbase est absent. Le calcul utilise les médianes marginales et la covariance classique."
  }
  if (is.null(center) || is.null(covariance)) {
    center <- c(median(points[, 1]), median(points[, 2]))
    covariance <- stats::cov(points)
    method <- "median_center_classical_covariance_fallback"
  }
  identifiable <- all(is.finite(covariance)) && all(dim(covariance) == c(2, 2)) &&
    is.finite(det(covariance)) && det(covariance) > .Machine$double.eps
  if (!identifiable) {
    return(list(
      center = center,
      covariance = covariance,
      direction = c(NA_real_, NA_real_),
      score_sd = NA_real_,
      identifiable = FALSE,
      method = method,
      warning = paste(c(warning, "La covariance est singulière. L’axe, les distances et les ellipses sont omis."), collapse = "; ")
    ))
  }
  eigen_result <- eigen(covariance, symmetric = TRUE)
  direction <- as.numeric(eigen_result$vectors[, 1])
  if (sum(direction) < 0) direction <- -direction
  score_sd <- sqrt(as.numeric(t(direction) %*% covariance %*% direction))
  list(
    center = center,
    covariance = covariance,
    direction = direction,
    score_sd = score_sd,
    identifiable = is.finite(score_sd) && score_sd > 0,
    method = method,
    warning = warning
  )
}

prepare_final_performance_data <- function(responses, baseline_id, final_id) {
  if (!nzchar(baseline_id) || !nzchar(final_id) || baseline_id == final_id) {
    stop("Sélectionnez deux évaluations distinctes.")
  }
  scored <- latest_attempt_rows(responses)
  scored <- scored[as.numeric(scored$is_practice_item) == 0, , drop = FALSE]
  baseline <- summarize_final_plot_session(scored, baseline_id, "baseline")
  final <- summarize_final_plot_session(scored, final_id, "final")
  if (!nrow(baseline) || !nrow(final)) stop("Il manque des réponses notées pour l’évaluation étalon ou finale.")
  all_students <- data.frame(
    student_export_id = sort(unique(c(baseline$student_export_id, final$student_export_id))),
    stringsAsFactors = FALSE
  )
  paired <- merge(all_students, baseline, by = "student_export_id", all.x = TRUE, sort = FALSE)
  paired <- merge(paired, final, by = "student_export_id", all.x = TRUE, sort = FALSE)
  paired$baseline_assessment_id <- baseline_id
  paired$final_assessment_id <- final_id
  paired$accuracy_change_raw <- paired$final_correct_count - paired$baseline_correct_count
  paired$accuracy_change_proportion <- paired$final_accuracy - paired$baseline_accuracy
  paired$pairing_status <- ifelse(
    is.na(paired$baseline_correct_count), "missing_baseline",
    ifelse(
      is.na(paired$final_correct_count), "missing_final",
      ifelse(
        !is.finite(paired$baseline_exact_rate_per_second) | !is.finite(paired$final_exact_rate_per_second),
        "invalid_duration", "complete"
      )
    )
  )
  eligible <- paired$pairing_status == "complete" & is.finite(paired$accuracy_change_proportion)
  if (sum(eligible) < 5) stop("Moins de cinq élèves disposent de mesures complètes aux deux évaluations.")
  count_axis <- length(unique(c(
    paired$baseline_items_presented[eligible], paired$final_items_presented[eligible]
  ))) == 1
  paired$final_x_value <- if (count_axis) paired$final_correct_count else 100 * paired$final_accuracy
  paired$baseline_x_value <- if (count_axis) paired$baseline_correct_count else 100 * paired$baseline_accuracy
  points <- paired[eligible, c("final_x_value", "final_exact_rate_per_second"), drop = FALSE]
  model <- robust_bivariate_model(points)
  paired$z_performance <- NA_real_
  paired$performance_group <- "Non classé"
  paired$robust_distance <- NA_real_
  if (model$identifiable) {
    centered <- sweep(as.matrix(points), 2, model$center, "-")
    scores <- as.numeric(centered %*% model$direction) / model$score_sd
    inverse_covariance <- solve(model$covariance)
    distances <- sqrt(rowSums((centered %*% inverse_covariance) * centered))
    paired$z_performance[eligible] <- scores
    paired$robust_distance[eligible] <- distances
    paired$performance_group[eligible] <- ifelse(
      scores < -1, "Performance relative basse",
      ifelse(scores > 1, "Performance relative haute", "Zone centrale")
    )
  }
  paired$display_id <- sprintf("E%02d", match(paired$student_export_id, sort(paired$student_export_id)))
  delta <- paired$accuracy_change_proportion[eligible]
  robust_limit <- max(abs(stats::quantile(delta, c(0.05, 0.95), na.rm = TRUE, names = FALSE)))
  if (!is.finite(robust_limit) || robust_limit <= 0) robust_limit <- max(abs(delta), na.rm = TRUE)
  if (!is.finite(robust_limit) || robust_limit <= 0) robust_limit <- 0.01
  paired$accuracy_change_display <- pmax(-robust_limit, pmin(robust_limit, paired$accuracy_change_proportion))
  paired$color_value_clipped <- abs(paired$accuracy_change_proportion) > robust_limit
  paired$plot_eligible <- eligible
  paired$robust_center_x <- model$center[[1]]
  paired$robust_center_y <- model$center[[2]]
  paired$principal_direction_x <- model$direction[[1]]
  paired$principal_direction_y <- model$direction[[2]]
  paired$principal_score_sd <- model$score_sd
  paired$center_method <- model$method
  paired$color_symmetric_limit <- robust_limit
  list(
    data = paired,
    model = model,
    count_axis = count_axis,
    color_limit = robust_limit,
    missing_count = sum(!eligible)
  )
}

ellipse_coordinates <- function(x, y, level = 0.68, points = 160L) {
  values <- cbind(as.numeric(x), as.numeric(y))
  values <- values[is.finite(values[, 1]) & is.finite(values[, 2]), , drop = FALSE]
  if (nrow(values) < 5) return(NULL)
  covariance <- stats::cov(values)
  if (!all(is.finite(covariance)) || det(covariance) <= .Machine$double.eps) return(NULL)
  decomposition <- eigen(covariance, symmetric = TRUE)
  if (any(decomposition$values <= 0)) return(NULL)
  angles <- seq(0, 2 * pi, length.out = points)
  circle <- rbind(cos(angles), sin(angles))
  radius <- sqrt(stats::qchisq(level, df = 2))
  transform <- decomposition$vectors %*% diag(sqrt(decomposition$values), 2)
  coordinates <- t(matrix(colMeans(values), nrow = 2, ncol = points) + radius * transform %*% circle)
  data.frame(x = coordinates[, 1], y = coordinates[, 2])
}

progression_colors <- function(values, limit) {
  palette <- grDevices::colorRampPalette(c("#D73027", "#FFFFFF", "#1A9850"))(201)
  scaled <- pmax(-1, pmin(1, as.numeric(values) / limit))
  palette[pmax(1, pmin(201, round((scaled + 1) * 100) + 1))]
}

draw_final_performance_scatter <- function(prepared) {
  data <- prepared$data[prepared$data$plot_eligible, , drop = FALSE]
  model <- prepared$model
  x <- data$final_x_value
  y <- data$final_exact_rate_per_second
  x_padding <- max(diff(range(x)), 1) * 0.08
  y_padding <- max(diff(range(y)), 0.01) * 0.10
  x_limits <- range(x) + c(-x_padding, x_padding)
  y_limits <- range(y) + c(-y_padding, y_padding)
  x_label <- if (prepared$count_axis) {
    "Items réussis lors de l’évaluation finale"
  } else {
    "Taux de réussite final (%)"
  }
  layout(matrix(1:2), heights = c(3.8, 1.22))
  on.exit(layout(1), add = TRUE)
  par(mar = c(4, 5, 3.8, 2))
  plot(
    x, y, type = "n", xlim = x_limits, ylim = y_limits, panel.first = panel_grid(),
    xlab = x_label, ylab = "Débit exact final (items réussis par seconde)",
    main = "Position finale des élèves : réussite, fluence et progression"
  )
  mtext(
    "Chaque point situe un élève à la dernière passation. La couleur indique l’évolution de sa justesse.",
    side = 3, line = 0.7, cex = 0.82
  )
  abline(v = median(x), h = median(y), col = "grey75", lty = 3)
  group_colors <- c(
    "Performance relative basse" = "#E69F00",
    "Zone centrale" = "#999999",
    "Performance relative haute" = "#56B4E9"
  )
  for (group_name in names(group_colors)) {
    block <- data[data$performance_group == group_name, , drop = FALSE]
    ellipse <- ellipse_coordinates(block$final_x_value, block$final_exact_rate_per_second)
    if (is.null(ellipse)) {
      cat("Ellipse omise pour le groupe suivant, faute d’effectif ou en raison d’une covariance singulière :", group_name, "\n")
    } else {
      polygon(
        ellipse$x, ellipse$y,
        col = adjustcolor(group_colors[[group_name]], alpha.f = 0.16),
        border = group_colors[[group_name]], lwd = 1.2
      )
    }
  }
  if (model$identifiable) {
    direction <- model$direction
    if (abs(direction[[1]]) > 1e-12) {
      slope <- direction[[2]] / direction[[1]]
      intercept <- model$center[[2]] - slope * model$center[[1]]
      abline(a = intercept, b = slope, col = "#C00000", lty = 2, lwd = 2.3)
    } else {
      abline(v = model$center[[1]], col = "#C00000", lty = 2, lwd = 2.3)
    }
  }
  point_sizes <- if (length(unique(data$final_valid_answered_items)) > 1) {
    1.2 + 0.7 * sqrt(data$final_valid_answered_items / max(data$final_valid_answered_items))
  } else {
    rep(1.7, nrow(data))
  }
  colors <- progression_colors(data$accuracy_change_display, prepared$color_limit)
  points(x, y, pch = 21, bg = colors, col = "#202020", lwd = 1, cex = point_sizes)
  if (is_teacher_view()) linked_labels(x, y, data$display_id, point_sizes)
  if (model$identifiable) points(model$center[[1]], model$center[[2]], pch = 4, lwd = 2.5, cex = 1.8)
  robust_method <- identical(model$method, "robustbase::covMcd")
  center_label <- if (robust_method) "Centre bivarié robuste" else "Centre bivarié de repli (médianes)"
  axis_label <- if (robust_method) "Axe principal robuste de performance" else "Axe principal de repli (covariance classique)"
  par(mar = c(0.3,2,0.2,2))
  plot.new()
  plot.window(c(0,1), c(0,1), xaxs = "i", yaxs = "i")
  rect(0,0,1,1,col = "#F1F4F5", border = NA)
  text(0.025,0.87,"Repères de lecture", adj = 0, font = 2, cex = 0.82)
  legend(0.012,0.77, c("Baisse", "Stabilité", "Progression"), pch = 21,
         pt.bg = c("#D73027","white","#1A9850"), horiz = TRUE, bty = "n", cex = 0.68)
  legend(0.012,0.49, c(center_label,axis_label), pch = c(4,NA), lty = c(NA,2),
         col = c("black","#C00000"), bty = "n", cex = 0.65)
  text(0.025,0.08,"Repères relatifs à cette classe.",adj = 0,cex = 0.65)
  movement <- function(d) factor(sign(d), levels = c(-1,0,1))
  counts <- table(movement(data$final_x_value - data$baseline_x_value),
                  movement(data$final_exact_rate_per_second - data$baseline_exact_rate_per_second))
  text(0.51,0.87,sprintf("Évolution des %d élèves appariés",sum(counts)),adj = 0,font = 2,cex = 0.82)
  cols <- c(0.72,0.82,0.94)
  text(cols,0.68,c("Débit réduit","Stable","Accru"),cex = 0.67)
  for (i in 1:3) {
    baseline <- 0.68 - 0.17*i
    text(0.51,baseline,c("Justesse réduite","Stable","Accrue")[i],adj = 0,cex = 0.74)
    text(cols,baseline,counts[i,],cex = 0.78,font = 2)
  }
}

final_plot_html_escape <- function(value) {
  value <- gsub("&", "&amp;", as.character(value), fixed = TRUE)
  value <- gsub("<", "&lt;", value, fixed = TRUE)
  value <- gsub(">", "&gt;", value, fixed = TRUE)
  value <- gsub('"', "&quot;", value, fixed = TRUE)
  value
}

write_final_performance_html <- function(prepared, path) {
  data <- prepared$data[prepared$data$plot_eligible, , drop = FALSE]
  width <- 1100; height <- 760; left <- 95; right <- 40; top <- 90; bottom <- 100
  x_all <- c(data$baseline_x_value, data$final_x_value)
  y_all <- c(data$baseline_exact_rate_per_second, data$final_exact_rate_per_second)
  x_range <- range(x_all, finite = TRUE); y_range <- range(y_all, finite = TRUE)
  if (diff(x_range) == 0) x_range <- x_range + c(-0.5, 0.5)
  if (diff(y_range) == 0) y_range <- y_range + c(-0.01, 0.01)
  map_x <- function(value) left + (value - x_range[[1]]) / diff(x_range) * (width - left - right)
  map_y <- function(value) height - bottom - (value - y_range[[1]]) / diff(y_range) * (height - top - bottom)
  colors <- progression_colors(data$accuracy_change_display, prepared$color_limit)
  trajectories <- vapply(seq_len(nrow(data)), function(index) {
    tooltip <- sprintf(
      "%s (%s) | réussite %d/%d (%.1f%%) → %d/%d (%.1f%%) | débit %.3f → %.3f items/s | évolution %+.1f points",
      data$display_id[[index]], data$student_export_id[[index]],
      data$baseline_correct_count[[index]], data$baseline_items_presented[[index]], 100 * data$baseline_accuracy[[index]],
      data$final_correct_count[[index]], data$final_items_presented[[index]], 100 * data$final_accuracy[[index]],
      data$baseline_exact_rate_per_second[[index]], data$final_exact_rate_per_second[[index]],
      100 * data$accuracy_change_proportion[[index]]
    )
    sprintf(
      paste0(
        '<g class="pupil"><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" ',
        'stroke="#777" stroke-opacity=".35" marker-end="url(#arrow)"/>',
        '<circle cx="%.1f" cy="%.1f" r="4" fill="#777" opacity=".35"/>',
        '<circle cx="%.1f" cy="%.1f" r="9" fill="%s" stroke="#202020"><title>%s</title></circle>',
        '<text x="%.1f" y="%.1f" font-size="11" text-anchor="middle">%s</text></g>'
      ),
      map_x(data$baseline_x_value[[index]]), map_y(data$baseline_exact_rate_per_second[[index]]),
      map_x(data$final_x_value[[index]]), map_y(data$final_exact_rate_per_second[[index]]),
      map_x(data$baseline_x_value[[index]]), map_y(data$baseline_exact_rate_per_second[[index]]),
      map_x(data$final_x_value[[index]]), map_y(data$final_exact_rate_per_second[[index]]), colors[[index]],
      final_plot_html_escape(tooltip), map_x(data$final_x_value[[index]]),
      map_y(data$final_exact_rate_per_second[[index]]) - 13, final_plot_html_escape(data$display_id[[index]])
    )
  }, character(1))
  x_label <- if (prepared$count_axis) "Items réussis (final)" else "Taux de réussite final (%)"
  html <- sprintf(
    paste0(
      '<!doctype html><html lang="fr"><meta charset="utf-8"><title>Performance finale</title>',
      '<style>body{font-family:Arial;margin:22px;color:#222}svg{border:1px solid #bbb;background:white}',
      '.pupil:hover circle:last-of-type{stroke-width:3}.note{max-width:1050px}</style>',
      '<h1>Position finale des élèves : réussite, fluence et progression</h1>',
      '<p class="note">Les flèches relient l’étalonnage à la position finale. Survolez un point final pour les valeurs brutes. ',
      'Cette évolution est descriptive et ne démontre pas un effet causal.</p>',
      '<svg viewBox="0 0 %d %d" width="100%%"><defs><marker id="arrow" markerWidth="8" markerHeight="8" ',
      'refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#777" opacity=".5"/></marker></defs>',
      '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#222"/>',
      '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#222"/>%s',
      '<text x="%d" y="%d" text-anchor="middle" font-size="16">%s</text>',
      '<text transform="translate(25,%d) rotate(-90)" text-anchor="middle" font-size="16">Débit exact final (items/s)</text>',
      '</svg><p>Rouge = baisse, blanc = stabilité, vert = progression. %s</p></html>'
    ),
    width, height, left, height - bottom, width - right, height - bottom,
    left, top, left, height - bottom, paste(trajectories, collapse = "\n"),
    round((left + width - right) / 2), height - 35, final_plot_html_escape(x_label), round((top + height - bottom) / 2),
    if (is_teacher_view()) "COPIE NOMINATIVE INTERNE — NE PAS DIFFUSER" else "Les identifiants sont pseudonymisés."
  )
  writeLines(html, path, useBytes = TRUE)
}

generate_final_performance_outputs <- function(data_list, baseline_id, final_id, output_dir,
    prepared = prepare_final_performance_data(data_list$responses, baseline_id, final_id)) {
  if (is_teacher_view()) prepared$data$display_id <- student_labels(prepared$data$student_export_id)
  if (nzchar(prepared$model$warning)) cat("Avertissement pour le graphique final :", prepared$model$warning, "\n")
  if (prepared$missing_count > 0) cat("Élèves sans paire de mesures pour le graphique final :", prepared$missing_count, "\n")
  write.csv(
    prepared$data,
    file.path(output_dir, "final_performance_scatter_data.csv"),
    row.names = FALSE, na = ""
  )
  png_path <- file.path(output_dir, "final_performance_scatter.png")
  pdf_path <- file.path(output_dir, "final_performance_scatter.pdf")
  png(png_path, width = 3000, height = 2100, res = 300, bg = "white")
  tryCatch(
    draw_final_performance_scatter(prepared),
    error = function(error) {
      if (grDevices::dev.cur() > 1) grDevices::dev.off()
      unlink(c(png_path, pdf_path))
      stop(error)
    }
  )
  dev.off()
  pdf(pdf_path, width = 10, height = 7, useDingbats = FALSE)
  tryCatch(
    draw_final_performance_scatter(prepared),
    error = function(error) {
      if (grDevices::dev.cur() > 1) grDevices::dev.off()
      unlink(c(png_path, pdf_path))
      stop(error)
    }
  )
  dev.off()
  write_final_performance_html(prepared, file.path(output_dir, "final_performance_scatter.html"))
  invisible(prepared)
}
