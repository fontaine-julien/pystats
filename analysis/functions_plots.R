# Graphiques statiques et interactifs.

PALETTE <- c("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000")

panel_grid <- function() {
  bounds <- par("usr")
  rect(bounds[1], bounds[3], bounds[2], bounds[4], col = "#F5F7F8", border = NA)
  abline(v = axTicks(1), h = axTicks(2), col = "#DCE2E5", lwd = 0.7)
}

family_labels <- function(keys) {
  keys <- sub("^table_", "×", keys)
  keys <- sub("^division_by_", "÷", keys)
  keys <- sub("^addition_", "+", keys)
  keys <- sub("^subtraction_", "Retirer ", keys)
  sub("^complements_", "Complément à ", keys)
}

family_colors <- function(keys) {
  palette <- c("#174D80", "#E18B10", "#218369", "#9E3982", "#6A54AD",
               "#AC452C", "#579CC1", "#777E20", "#BD6880", "#624B39")
  colors <- unname(setNames(palette, paste0("table_", seq_along(palette)))[keys])
  other <- is.na(colors)
  if (any(other)) colors[other] <- profile_colors(keys[other])[keys[other]]
  colors
}

percent_limits <- function(values) {
  c(max(0, min(90, 10 * floor((min(values) - 5) / 10))), 100)
}

# Les pouces conservent les mêmes marges et espacements dans les différents formats.
linked_labels <- function(x, y, labels, sizes, cex = 0.76) {
  u <- par("usr")
  pin <- par("pin")
  sx <- diff(u[1:2]) / pin[1]
  sy <- diff(u[3:4]) / pin[2]
  px <- (x - u[1]) / sx
  py <- (y - u[3]) / sy
  widths <- strwidth(labels, units = "inches", cex = cex) / 2 + 0.035
  heights <- strheight("Mg", units = "inches", cex = cex) / 2 + 0.032
  radius <- rep_len(0.055 * sizes + 0.02, length(x))
  placed <- matrix(numeric(), ncol = 4)
  centers <- matrix(NA_real_, length(x), 2)
  angles <- seq(0, 2 * pi, length.out = 25)[-25]
  for (i in order(widths, decreasing = TRUE)) {
    w <- widths[i]
    h <- heights
    rings <- seq(0.04, max(pin), by = 0.10)
    cx <- px[i] + as.vector(outer(cos(angles), w + radius[i] + rings))
    cy <- py[i] + as.vector(outer(sin(angles), h + radius[i] + rings))
    valid <- cx - w >= 0 & cx + w <= pin[1] & cy - h >= 0 & cy + h <= pin[2]
    for (j in seq_along(px)) valid <- valid & (abs(cx-px[j]) > w+radius[j] | abs(cy-py[j]) > h+radius[j])
    for (j in seq_len(nrow(placed))) {
      valid <- valid & (abs(cx-placed[j,1]) > w+placed[j,3] | abs(cy-placed[j,2]) > h+placed[j,4])
    }
    distance <- (cx-px[i])^2 + (cy-py[i])^2
    distance[!valid] <- Inf
    if (!any(valid)) {
      # Si le voisinage est saturé, cherche une place dans tout le panneau.
      slots <- expand.grid(x = seq(w, max(w, pin[1]-w), length.out = 55),
                           y = seq(h, max(h, pin[2]-h), length.out = 55))
      penalty <- numeric(nrow(slots))
      for (j in seq_len(nrow(placed))) {
        penalty <- penalty + pmax(0, w+placed[j,3]-abs(slots$x-placed[j,1])) *
                             pmax(0, h+placed[j,4]-abs(slots$y-placed[j,2]))
      }
      for (j in seq_along(px)) {
        penalty <- penalty + pmax(0,w+radius[j]-abs(slots$x-px[j])) * pmax(0,h+radius[j]-abs(slots$y-py[j]))
      }
      k <- order(penalty, (slots$x-px[i])^2 + (slots$y-py[i])^2)[1]
      centers[i,] <- c(slots$x[k], slots$y[k])
    } else {
      k <- which.min(distance)
      centers[i,] <- c(cx[k], cy[k])
    }
    placed <- rbind(placed, c(centers[i,], w, h))
  }
  lx <- u[1] + centers[,1] * sx
  ly <- u[3] + centers[,2] * sy
  dx <- centers[,1] - px
  dy <- centers[,2] - py
  start <- pmin(1, radius / pmax(0.001, sqrt(dx^2 + dy^2)))
  end <- pmax(start, 1 - 1 / pmax(1, abs(dx)/widths, abs(dy)/heights))
  segments(x + start*dx*sx, y + start*dy*sy, x + end*dx*sx, y + end*dy*sy, col = "#778791", lwd = 0.7)
  rect(lx-widths*sx, ly-heights*sy, lx+widths*sx, ly+heights*sy, col = "#F5F7F8", border = NA)
  text(lx, ly, labels, cex = cex, col = "#203541")
}

is_teacher_view <- function() !is.null(getOption("pystats.student_names"))

student_labels <- function(ids) {
  if (!is_teacher_view()) return(as.character(ids))
  unname(getOption("pystats.student_names")[as.character(ids)])
}

profile_colors <- function(ids) {
  ids <- sort(unique(as.character(ids)))
  setNames(grDevices::hcl.colors(length(ids), "Dark 3"), ids)
}

profile_legend <- function(colors) {
  legend(par("usr")[2], par("usr")[4], legend = student_labels(names(colors)), col = colors,
         lty = 1, bty = "n", xpd = NA, cex = min(0.68, 15 / length(colors)))
}

empty_plot <- function(message, title = "Données insuffisantes") {
  plot.new()
  title(main = title)
  text(0.5, 0.5, message, cex = 1.1)
}

save_plot_formats <- function(output_dir, name, draw_function, width = 1800, height = 1200) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  devices <- list(
    png = function(path) png(path, width = width, height = height, res = 180, bg = "white"),
    pdf = function(path) pdf(path, width = width / 180, height = height / 180, useDingbats = FALSE),
    svg = function(path) svg(path, width = width / 180, height = height / 180, bg = "white")
  )
  created_paths <- file.path(output_dir, paste0(name, ".", names(devices)))
  for (extension in names(devices)) {
    path <- file.path(output_dir, paste0(name, ".", extension))
    devices[[extension]](path)
    tryCatch(
      draw_function(),
      error = function(error) {
        if (grDevices::dev.cur() > 1) grDevices::dev.off()
        unlink(created_paths)
        stop(error)
      }
    )
    dev.off()
  }
}

focus_rows <- function(data, focus_id) {
  if (is.null(focus_id) || !nzchar(focus_id)) return(data)
  data[as.character(data$assessment_id) == focus_id, , drop = FALSE]
}

draw_heatmap <- function(responses, focus_id) {
  data <- focus_rows(latest_attempt_rows(responses), focus_id)
  data <- data[data$is_practice_item == 0, , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucune réponse notée."))
  students <- sort(unique(as.character(data$student_export_id)))
  item_order <- unique(as.character(data$item_id[order(data$item_position)]))
  times <- matrix(NA_real_, nrow = length(students), ncol = length(item_order), dimnames = list(students, item_order))
  states <- matrix("not_presented", nrow = length(students), ncol = length(item_order), dimnames = list(students, item_order))
  for (index in seq_len(nrow(data))) {
    student_index <- match(as.character(data$student_export_id[index]), students)
    item_index <- match(as.character(data$item_id[index]), item_order)
    times[student_index, item_index] <- as.numeric(data$total_response_time_ms[index]) / 1000
    state <- as.character(data$completion_status[index])
    if (state == "answered") state <- if (as.numeric(data$is_correct[index]) == 1) "correct" else "incorrect"
    states[student_index, item_index] <- state
  }
  finite_times <- times[is.finite(times)]
  if (length(finite_times) == 0) finite_times <- c(0, 1)
  colors <- colorRampPalette(c("#F7FBFF", "#6BAED6", "#08306B"))(64)
  layout(matrix(1:2), heights = c(4.4, 1))
  on.exit(layout(1), add = TRUE)
  par(mar = c(3.8, 12, 3.2, 2))
  image(seq_along(item_order), seq_along(students), t(times), col = colors,
        zlim = range(finite_times), axes = FALSE, xlab = "Item (ordre de passation)", ylab = "",
        main = sprintf("Carte élèves x items - temps total (N=%d)", length(students)))
  axis(1, at = seq_along(item_order), labels = seq_along(item_order), las = 2, cex.axis = 0.7)
  axis(2, at = seq_along(students), labels = student_labels(students), las = 2, cex.axis = 0.7)
  symbols_map <- c(correct = 1, incorrect = 4, omission = 3, timeout = 8, global_timeout = 8, interrupted = 6, not_presented = 0)
  for (student_index in seq_along(students)) {
    for (item_index in seq_along(item_order)) {
      state <- states[student_index, item_index]
      if (state %in% names(symbols_map)) points(item_index, student_index, pch = symbols_map[[state]], cex = 0.55)
    }
  }
  mtext(if (is_teacher_view()) "Nom et prénom" else "Élève pseudonymisé", side = 2, line = 10.4, cex = 0.9)
  par(mar = c(0.4, 2, 0.4, 2))
  plot.new()
  plot.window(c(0, 1), c(0, 1), xaxs = "i", yaxs = "i")
  rect(0.01, 0.03, 0.99, 0.96, col = "#F5F7F8", border = "#BAC6CB")
  text(0.035, 0.75, "Légende", adj = 0, font = 2)
  text(0.035, 0.44, "Temps total (s)", adj = 0, cex = 0.85)
  edges <- seq(0.24, 0.94, length.out = length(colors) + 1)
  rect(head(edges,-1), 0.66, tail(edges,-1), 0.82, col = colors, border = NA)
  ticks <- seq(min(edges), max(edges), length.out = 5)
  text(ticks, 0.47, format(round(seq(min(finite_times), max(finite_times), length.out = 5), 1), decimal.mark = ","), cex = 0.75)
  legend(0.03, 0.32, c("Juste", "Faux", "Omission", "Expiration", "Interruption", "Non présenté"),
         pch = c(1,4,3,8,6,0), horiz = TRUE, bty = "n", cex = 0.78)
}

draw_student_scatter <- function(students, focus_id) {
  data <- focus_rows(students, focus_id)
  data <- data[is.finite(data$median_correct_time_ms) & is.finite(data$success_rate), , drop = FALSE]
  if (nrow(data) < 2) return(empty_plot("Au moins deux élèves avec temps et exactitude sont nécessaires."))
  x <- data$median_correct_time_ms / 1000
  y <- data$success_rate * 100
  valid_items <- pmax(1, as.numeric(data$items_answered))
  sizes <- 0.8 + 1.8 * sqrt(valid_items / max(valid_items))
  par(mar = c(6.2, 5, 4, 2), pty = if (dev.size()[2] > dev.size()[1]) "s" else "m")
  plot(x, y, pch = 21, bg = PALETTE[1], col = "#244253", cex = sizes, panel.first = panel_grid(),
       xlab = "Temps médian des réponses exactes (s)", ylab = "Taux de réussite (%)",
       ylim = percent_limits(y), main = sprintf("Profils vitesse-exactitude (%d élèves)", nrow(data)))
  abline(v = median(x), h = median(y), lty = 2, col = "grey35")
  linked_labels(x, y, student_labels(data$student_export_id), sizes)
  mtext("Les pointillés indiquent les médianes. La taille des disques indique le nombre de réponses.",
        side = 1, line = 4.3, cex = 0.73)
}

draw_reaction_evolution <- function(students) {
  data <- add_session_number(students)
  data <- data[is.finite(data$median_correct_time_ms), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucun temps médian disponible."))
  sessions <- sort(unique(data$session_number))
  y <- data$median_correct_time_ms / 1000
  colors <- profile_colors(data$student_export_id)
  par(mar = c(5, 5, 4, 11))
  plot(range(sessions), range(y, finite = TRUE), type = "n", xaxt = "n", panel.first = panel_grid(),
       xlab = "Session", ylab = "Temps des réponses exactes (s)",
       main = sprintf("Évolution des temps - trajectoires individuelles (N=%d)", length(unique(data$student_export_id))))
  axis(1, at = sessions)
  for (student in unique(data$student_export_id)) {
    block <- data[data$student_export_id == student, ]
    block <- block[order(block$session_number), ]
    lines(block$session_number, block$median_correct_time_ms / 1000, col = colors[[as.character(student)]], lwd = 0.8)
  }
  medians <- sapply(sessions, function(session) safe_median(data$median_correct_time_ms[data$session_number == session]) / 1000)
  means <- sapply(sessions, function(session) safe_mean(data$mean_correct_time_ms[data$session_number == session]) / 1000)
  quartiles <- sapply(sessions, function(session) quantile(data$median_correct_time_ms[data$session_number == session], c(.25,.75)) / 1000)
  polygon(c(sessions, rev(sessions)), c(quartiles[1,], rev(quartiles[2,])),
          col = adjustcolor(PALETTE[1], 0.18), border = NA)
  lines(sessions, medians, type = "b", pch = 19, lwd = 3, col = PALETTE[1])
  lines(sessions, means, type = "b", pch = 17, lwd = 2, lty = 2, col = PALETTE[2])
  legend("topright", c("Médiane des élèves", "Moyenne des temps moyens", "Élèves"),
         col = c(PALETTE[1], PALETTE[2], "grey45"), lty = c(1, 2, 1), lwd = c(3, 2, 1), bty = "n")
  mtext("La bande couvre la moitié centrale des temps médians individuels (Q1 à Q3).", side = 1, line = 3.5, cex = 0.75)
  profile_legend(colors)
}

draw_success_evolution <- function(students) {
  data <- add_session_number(students)
  data <- data[is.finite(data$success_rate), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucun taux de réussite disponible."))
  sessions <- sort(unique(data$session_number))
  colors <- profile_colors(data$student_export_id)
  par(mar = c(5, 5, 4, 11))
  plot(range(sessions), c(0, 100), type = "n", xaxt = "n", panel.first = panel_grid(), xlab = "Session", ylab = "Réussite (%)",
       main = sprintf("Évolution de la réussite (N=%d)", length(unique(data$student_export_id))))
  axis(1, at = sessions)
  for (student in unique(data$student_export_id)) {
    block <- data[data$student_export_id == student, ]
    block <- block[order(block$session_number), ]
    lines(block$session_number, 100 * block$success_rate, col = colors[[as.character(student)]], lwd = 0.8)
  }
  medians <- sapply(sessions, function(session) 100 * safe_median(data$success_rate[data$session_number == session]))
  q1 <- sapply(sessions, function(session) 100 * quantile(data$success_rate[data$session_number == session], 0.25, na.rm = TRUE))
  q3 <- sapply(sessions, function(session) 100 * quantile(data$success_rate[data$session_number == session], 0.75, na.rm = TRUE))
  polygon(c(sessions, rev(sessions)), c(q1, rev(q3)), col = adjustcolor(PALETTE[3], 0.18), border = NA)
  lines(sessions, medians, type = "b", pch = 19, lwd = 3, col = PALETTE[3])
  mtext("Bande = intervalle interquartile; lignes fines = élèves.", side = 1, line = 3.5, cex = 0.75)
  profile_legend(colors)
}

draw_family_evolution <- function(families) {
  data <- add_session_number(families)
  data <- data[is.finite(data$success_rate) | is.finite(data$median_correct_time_ms), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucune évolution par famille disponible."))
  sessions <- sort(unique(data$session_number))
  family_names <- unique(data$fact_family)
  colors <- setNames(family_colors(family_names), family_names)
  par(mfrow = c(2, 1), mar = c(4, 5, 3, 2))
  plot(range(sessions), range(data$median_correct_time_ms / 1000, finite = TRUE), type = "n", xaxt = "n", panel.first = panel_grid(),
       xlab = "Session", ylab = "Temps médian exact (s)", main = "Évolution des temps par groupe de calculs")
  axis(1, at = sessions)
  for (family_name in family_names) {
    block <- data[data$fact_family == family_name, ]
    block <- block[order(block$session_number), ]
    lines(block$session_number, block$median_correct_time_ms / 1000, type = "b", col = colors[[family_name]], pch = 19)
  }
  legend("topright", family_labels(family_names), col = colors, lty = 1, pch = 19, cex = 0.65, bty = "n")
  plot(range(sessions), c(0, 100), type = "n", xaxt = "n", panel.first = panel_grid(), xlab = "Session", ylab = "Réussite (%)",
       main = "Évolution de l’exactitude par famille")
  axis(1, at = sessions)
  for (family_name in family_names) {
    block <- data[data$fact_family == family_name, ]
    block <- block[order(block$session_number), ]
    lines(block$session_number, 100 * block$success_rate, type = "b", col = colors[[family_name]], pch = 19)
  }
  par(mfrow = c(1, 1))
}

draw_anchor_evolution <- function(responses) {
  data <- latest_attempt_rows(responses)
  data <- data[data$is_practice_item == 0 & data$is_anchor_item == 1, , drop = FALSE]
  data <- add_session_number(data)
  if (nrow(data) == 0) return(empty_plot("Aucun item d’ancrage dans les évaluations disponibles."))
  sessions <- sort(unique(data$session_number))
  time_values <- sapply(sessions, function(session) {
    block <- data[data$session_number == session & data$completion_status == "answered" & data$is_correct == 1, ]
    safe_median(block$total_response_time_ms) / 1000
  })
  success_values <- sapply(sessions, function(session) {
    block <- data[data$session_number == session & data$completion_status == "answered", ]
    if (nrow(block)) 100 * mean(as.numeric(block$is_correct), na.rm = TRUE) else NA_real_
  })
  par(mfrow = c(2, 1), mar = c(4, 5, 3, 2))
  plot(sessions, time_values, type = "b", pch = 19, col = PALETTE[1], xaxt = "n",
       xlab = "Session", ylab = "Temps médian exact (s)", main = "Items d’ancrage — temps")
  axis(1, at = sessions)
  plot(sessions, success_values, type = "b", pch = 19, col = PALETTE[3], xaxt = "n", ylim = c(0, 100),
       xlab = "Session", ylab = "Réussite (%)", main = "Items d’ancrage — exactitude")
  axis(1, at = sessions)
  mtext("L’exposition répétée peut produire un effet d’entraînement; interpréter avec les items renouvelés.",
        outer = TRUE, line = -1.2, cex = 0.75)
  par(mfrow = c(1, 1))
}

draw_speed_accuracy_trajectory <- function(students) {
  data <- add_session_number(students)
  data <- data[is.finite(data$correct_per_minute) & is.finite(data$success_rate), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Débit ou exactitude indisponible."))
  colors <- profile_colors(data$student_export_id)
  par(mar = c(5, 5, 4, 11))
  plot(data$correct_per_minute, 100 * data$success_rate, type = "n", ylim = c(0, 100), panel.first = panel_grid(),
       xlab = "Réponses exactes par minute", ylab = "Réussite (%)",
       main = "Trajectoires vitesse-exactitude")
  for (student in unique(data$student_export_id)) {
    block <- data[data$student_export_id == student, ]
    block <- block[order(block$session_number), ]
    lines(block$correct_per_minute, 100 * block$success_rate, col = colors[[as.character(student)]])
    points(block$correct_per_minute, 100 * block$success_rate, pch = 21, bg = colors[[as.character(student)]], cex = 0.8)
    if (nrow(block) > 1) {
      arrows(block$correct_per_minute[-nrow(block)], 100 * block$success_rate[-nrow(block)],
             block$correct_per_minute[-1], 100 * block$success_rate[-1], length = 0.08, col = colors[[as.character(student)]])
    }
  }
  mtext("Chaque flèche relie deux évaluations successives du même élève.", side = 1, line = 3.5, cex = 0.75)
  profile_legend(colors)
}

draw_family_performance <- function(families, focus_id) {
  data <- focus_rows(families, focus_id)
  data <- data[is.finite(data$success_rate) & is.finite(data$median_correct_time_ms), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucune synthèse par famille disponible."))
  x <- data$median_correct_time_ms / 1000
  y <- 100 * data$success_rate
  sizes <- 1 + 2 * sqrt(pmax(1, data$item_response_count) / max(data$item_response_count))
  par(mar = c(6.2, 5, 4, 2))
  plot(x, y, pch = 21, bg = family_colors(data$fact_family), cex = sizes, ylim = percent_limits(y),
       panel.first = panel_grid(), xlab = "Temps médian des réponses justes (s)", ylab = "Réussite (%)",
       main = if (all(grepl("^table_", data$fact_family))) "Performance par table" else "Performance par groupe de calculs")
  abline(v = median(x), h = median(y), lty = 2, col = "grey40")
  linked_labels(x, y, family_labels(data$fact_family), sizes, 0.9)
  mtext("La réussite est calculée sur les réponses saisies. La taille indique le nombre d’items observés.", side = 1, line = 4.3, cex = 0.72)
}

draw_item_difficulty <- function(items, focus_id, timed) {
  if (!nrow(timed)) return(empty_plot("Aucune réponse chronométrée."))
  key <- paste(timed$operation_type, timed$operand_1, timed$operand_2, timed$expected_answer, sep = ":")
  means <- tapply(timed$total_response_time_ms / 1000, key, mean)
  data <- focus_rows(items, focus_id)
  data$seconds <- as.numeric(means[as.character(data$fact_key)])
  data <- data[is.finite(data$success_rate) & is.finite(data$seconds), , drop = FALSE]
  if (nrow(data) == 0) return(empty_plot("Aucune synthèse par item disponible."))
  x <- 100 * data$success_rate
  y <- data$seconds
  sizes <- 0.8 + 1.8 * sqrt(pmax(1, data$presentation_count) / max(data$presentation_count))
  colors <- family_colors(data$fact_family)
  par(mar = c(7, 5, 4, 2))
  plot(x, y, pch = 21, bg = colors, cex = sizes, xlim = percent_limits(x),
       panel.first = panel_grid(), xlab = "Réussite parmi les réponses saisies (%)",
       ylab = "Temps moyen de toutes les réponses (s)", main = "Difficulté des opérations")
  abline(v = median(x), h = median(y), lty = 2, col = "grey40")
  ops <- c(multiplication = "×", addition = "+", subtraction = "-", division = "÷")
  facts <- timed[match(data$fact_key, key), ]
  labels <- paste(facts$operand_1, ops[facts$operation_type], facts$operand_2)
  complement <- startsWith(facts$operation_type, "complement_")
  labels[complement] <- paste(facts$operand_1[complement], "+ ? =", facts$operand_2[complement])
  linked_labels(x, y, labels, sizes)
  keys <- unique(data$fact_family)
  keys <- keys[order(suppressWarnings(as.integer(sub("^table_", "", keys))), keys)]
  legend("bottom", inset = c(0, -0.21), xpd = NA, ncol = min(10, length(keys)), legend = family_labels(keys),
         pch = 21, pt.bg = family_colors(keys), bty = "n", cex = 0.76)
}

write_table_distributions <- function(timed, path, assessment_date) {
  keys <- unique(timed$fact_family)
  keys <- keys[order(suppressWarnings(as.integer(sub("^table_", "", keys))), keys)]
  pupils <- aggregate(total_response_time_ms ~ fact_family + student_export_id, timed, mean)
  pupils$seconds <- pupils$total_response_time_ms / 1000
  breaks <- pretty(c(0, pupils$seconds), n = 8)
  breaks <- breaks[breaks >= 0]
  ymax <- max(vapply(split(pupils$seconds, pupils$fact_family), function(v)
    max(hist(v, breaks = breaks, plot = FALSE)$counts), integer(1)))
  pdf(path, width = 10.8, height = 11.4, useDingbats = FALSE)
  on.exit(dev.off(), add = TRUE)
  par(mfrow = c(2,2), pty = "s", mar = c(7.4,4.1,2.5,1.1), oma = c(1,0,4,0))
  for (i in seq_along(keys)) {
    k <- keys[i]
    values <- pupils$seconds[pupils$fact_family == k]
    block <- timed[timed$fact_family == k, ]
    histo <- hist(values, breaks = breaks, plot = FALSE)
    q <- quantile(values, c(.25,.5,.75), names = FALSE)
    plot(range(breaks), c(0,ymax+0.55), type = "n", xaxs = "i", yaxs = "i",
         xlab = "Temps moyen de l’élève (s)", ylab = "Nombre d’élèves", yaxt = "n",
         main = sprintf("%s   |   %d élèves", family_labels(k), length(values)),
         panel.first = panel_grid())
    axis(2, at = pretty(c(0,ymax))[pretty(c(0,ymax)) %% 1 == 0], las = 1)
    rect(q[1], 0, q[3], ymax+0.55, col = "#F1DBA3", border = NA)
    abline(v = q[c(1,3)], lty = 3, col = "#876B35")
    for (b in seq_along(histo$counts)) {
      count <- histo$counts[b]
      if (!count) next
      rect(breaks[b], 0, breaks[b+1], count, col = "#5D839477", border = "#647E89")
      inside <- values[cut(values, breaks, include.lowest = TRUE, labels = FALSE) == b]
      points(sort(inside), seq_len(count)-0.5, pch = 16, cex = 0.60, col = "#173E4D")
    }
    abline(v = q[2], lwd = 2.4, col = "#182D39")
    mtext(sprintf("Médiane %.2f s   |   Q1–Q3 : %.2f à %.2f s", q[2], q[1], q[3]), 1, 4.6, cex = 0.8)
    by_state <- function(correct) {
      v <- block$total_response_time_ms[block$is_correct == correct] / 1000
      if (!length(v)) return("aucune")
      sprintf("%.2f s (n=%d)", mean(v), length(v))
    }
    mtext(paste("Temps moyens   Justes :", by_state(1), "   Fausses :", by_state(0)), 1, 6.0, cex = 0.77)
    if ((i-1) %% 4 == 0) {
      heading <- if (all(grepl("^table_", keys))) "Temps de réponse par table" else "Temps de réponse par groupe de calculs"
      mtext(paste(heading, " | ", assessment_date), outer = TRUE, side = 3, line = 1.8, font = 2)
      mtext("Un point par élève. Bande ocre : moitié centrale. Trait foncé : médiane. Les omissions sont exclues.",
            outer = TRUE, side = 3, line = 0.3, cex = 0.8)
    }
  }
}

draw_correlogram <- function(students, caption = "") {
  candidates <- c("success_rate", "mean_correct_time_ms", "median_correct_time_ms", "correct_time_sd_ms",
                  "correct_time_iqr_ms", "correct_per_minute", "omission_rate", "timeout_rate")
  variables <- intersect(candidates, names(students))
  variables <- variables[sapply(students[variables], function(values) any(is.finite(as.numeric(values))))]
  if (length(variables) < 2) return(empty_plot("Moins de deux indicateurs exploitables."))
  matrix_data <- sapply(students[variables], as.numeric)
  correlations <- suppressWarnings(cor(matrix_data, method = "spearman", use = "pairwise.complete.obs"))
  correlations[crossprod(1L * is.finite(matrix_data)) < 3] <- NA_real_
  n <- ncol(correlations)
  friendly <- c(success_rate = "Réussite", mean_correct_time_ms = "Temps moyen juste",
    median_correct_time_ms = "Temps médian juste", correct_time_sd_ms = "Écart-type (justes)",
    correct_time_iqr_ms = "Écart interquartile (justes)", correct_per_minute = "Débit exact",
    omission_rate = "Omissions", timeout_rate = "Expirations")
  par(mar = c(12, 10, 5, 2), pty = "s")
  image(seq_len(n), seq_len(n), t(correlations[n:1, , drop = FALSE]), col = colorRampPalette(c("#B2182B", "white", "#2166AC"))(101),
        zlim = c(-1, 1), axes = FALSE, xlab = "", ylab = "", main = "Corrélations de Spearman")
  title(sub = NA, line = 0.5, main = caption, cex.main = 0.76)
  axis(1, at = seq_len(n), labels = friendly[variables], las = 2, cex.axis = 0.72)
  axis(2, at = seq_len(n), labels = rev(friendly[variables]), las = 2, cex.axis = 0.72)
  for (row in seq_len(n)) for (column in seq_len(n)) {
    value <- correlations[n - row + 1, column]
    text(column, row, if (is.finite(value)) sprintf("%.2f", value) else "NC", cex = 0.76,
         col = if (is.finite(value) && abs(value) > 0.65) "white" else "#263D46")
  }
  mtext("NC = non calculable (valeurs constantes ou moins de trois paires).", side = 1, line = 9.0, cex = 0.72)
}

draw_position_effects <- function(responses, focus_id) {
  rows <- latest_attempt_rows(focus_rows(responses, focus_id))
  rows <- rows[rows$is_practice_item == 0, , drop = FALSE]
  data <- position_summary(rows)
  if (is.null(data) || nrow(data) == 0) return(empty_plot("Aucune position présentée."))
  old <- par(no.readonly = TRUE)
  on.exit(par(old), add = TRUE)
  par(mfrow = c(2, 2), pty = "s", mar = c(4, 4, 3, 1), oma = c(3, 0, 0, 0))
  plot(data$item_position, data$median_correct_time_ms / 1000, type = "b", pch = 19, col = PALETTE[1],
       panel.first = panel_grid(), ylim = range(c(0.1, data$median_correct_time_ms / 1000), finite = TRUE),
       xlab = "Position", ylab = "Temps médian exact (s)", main = "Temps")
  plot(data$item_position, 100 * data$success_rate, type = "b", pch = 19, col = PALETTE[3], ylim = c(0, 100),
       panel.first = panel_grid(), xlab = "Position", ylab = "Réussite (%)", main = "Exactitude")
  plot(data$item_position, 100 * data$omission_rate, type = "h", lwd = 3, col = PALETTE[2],
       panel.first = panel_grid(), ylim = c(0, max(1, 100 * data$omission_rate, na.rm = TRUE)),
       xlab = "Position", ylab = "Omissions (%)", main = "Omissions")
  plot(data$item_position, 100 * data$timeout_rate, type = "h", lwd = 3, col = PALETTE[4],
       panel.first = panel_grid(), ylim = c(0, max(1, 100 * data$timeout_rate, na.rm = TRUE)),
       xlab = "Position", ylab = "Expirations (%)", main = "Expirations")
  same_order <- all(tapply(rows$item_id, rows$item_position, function(ids) length(unique(ids)) == 1))
  note <- if (same_order) "Même ordre d’items pour tous les élèves. Position et difficulté de l’item sont confondues." else "Difficulté des items non ajustée."
  mtext(note, outer = TRUE, side = 1, line = 0.6, cex = 0.76)
}

parallel_data <- function(students, focus_id) {
  data <- focus_rows(students, focus_id)
  variables <- c("success_rate", "median_correct_time_ms", "correct_time_iqr_ms", "correct_per_minute", "omission_rate")
  variables <- intersect(variables, names(data))
  complete <- data[complete.cases(data[c("student_export_id", variables)]), c("student_export_id", variables), drop = FALSE]
  if (nrow(complete) == 0 || length(variables) < 3) return(list(data = complete, variables = variables, scaled = matrix(numeric(0), 0, 0)))
  values <- sapply(complete[variables], as.numeric)
  # Inverse temps, variabilité et omissions pour orienter tous les axes dans le même sens.
  reverse <- variables %in% c("median_correct_time_ms", "correct_time_iqr_ms", "omission_rate", "timeout_rate")
  scaled <- apply(values, 2, function(column) {
    spread <- max(column) - min(column)
    if (!is.finite(spread) || spread == 0) rep(0.5, length(column)) else (column - min(column)) / spread
  })
  scaled[, reverse] <- 1 - scaled[, reverse, drop = FALSE]
  list(data = complete, variables = variables, scaled = scaled)
}

draw_parallel_coordinates <- function(students, focus_id) {
  prepared <- parallel_data(students, focus_id)
  if (nrow(prepared$data) < 2 || length(prepared$variables) < 3) return(empty_plot("Profils multidimensionnels insuffisants."))
  x <- seq_along(prepared$variables)
  friendly_labels <- c(
    success_rate = "Réussite",
    median_correct_time_ms = "Vitesse",
    correct_time_iqr_ms = "Régularité",
    correct_per_minute = "Débit exact",
    omission_rate = "Sans omission",
    timeout_rate = "Sans expiration"
  )
  axis_labels <- unname(friendly_labels[prepared$variables])
  axis_labels[is.na(axis_labels)] <- prepared$variables[is.na(axis_labels)]
  colors <- profile_colors(prepared$data$student_export_id)
  par(mar = c(7, 5, 5, 11))
  plot(range(x), c(0, 1), type = "n", xaxt = "n", panel.first = panel_grid(), xlab = "", ylab = "Position relative (haut = favorable)",
       main = sprintf("Profils multidimensionnels en coordonnées parallèles (N=%d)", nrow(prepared$data)))
  axis(1, at = x, labels = axis_labels, las = 2, cex.axis = 0.78)
  abline(v = x, col = "grey85")
  for (row in seq_len(nrow(prepared$data))) {
    lines(x, prepared$scaled[row, ], col = colors[[as.character(prepared$data$student_export_id[row])]], lwd = 1.3)
  }
  mtext("Chaque ligne représente un élève. Mise à l’échelle 0-1 descriptive, sans création de groupes.",
        side = 3, line = 0.4, cex = 0.72)
  profile_legend(colors)
}

html_escape <- function(value) {
  value <- gsub("&", "&amp;", as.character(value), fixed = TRUE)
  value <- gsub("<", "&lt;", value, fixed = TRUE)
  value <- gsub(">", "&gt;", value, fixed = TRUE)
  value <- gsub('"', "&quot;", value, fixed = TRUE)
  value
}

student_options_html <- function(students) {
  paste(c('<option value="all">Tous les élèves</option>',
          sprintf('<option value="%s">%s</option>', html_escape(students), html_escape(student_labels(students)))), collapse = "\n")
}

write_interactive_scatter <- function(students, focus_id, path) {
  data <- focus_rows(students, focus_id)
  data <- data[is.finite(data$median_correct_time_ms) & is.finite(data$success_rate), , drop = FALSE]
  if (nrow(data) == 0) return(writeLines("<html><body>Données insuffisantes.</body></html>", path, useBytes = TRUE))
  width <- 900; height <- 600; margin <- 70
  x <- data$median_correct_time_ms / 1000
  y <- 100 * data$success_rate
  scale_value <- function(values, low, high) {
    spread <- max(values) - min(values)
    if (spread == 0) rep((low + high) / 2, length(values)) else low + (values - min(values)) / spread * (high - low)
  }
  sx <- scale_value(x, margin, width - margin)
  sy <- height - scale_value(y, margin, height - margin)
  circles <- paste(sprintf(
    '<circle class="student" data-student="%s" cx="%.1f" cy="%.1f" r="7" fill="#0072B2" stroke="black"><title>%s — temps %.2f s; réussite %.1f%%</title></circle>',
    html_escape(data$student_export_id), sx, sy, html_escape(student_labels(data$student_export_id)), x, y
  ), collapse = "\n")
  html <- sprintf('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Vitesse–exactitude interactive</title>
<style>body{font-family:Arial;margin:24px}svg{border:1px solid #aaa}.student{cursor:pointer;transition:.2s}</style>
<h1>Vitesse–exactitude interactive</h1><p>Survoler un point ou isoler un élève. </p>
<label>Élève : <select id="filter" onchange="filterStudent(this.value)">%s</select></label>
<svg viewBox="0 0 %d %d" width="100%%"><line x1="%d" y1="%d" x2="%d" y2="%d" stroke="black"/>
<text x="450" y="590" text-anchor="middle">Temps médian exact (faible à gauche, élevé à droite)</text>
<text x="20" y="300" transform="rotate(-90 20 300)" text-anchor="middle">Réussite (faible en bas, élevée en haut)</text>%s</svg>
<script>function filterStudent(v){document.querySelectorAll(".student").forEach(e=>{e.style.opacity=(v==="all"||e.dataset.student===v)?1:.08;e.setAttribute("r",e.dataset.student===v?11:7)})}</script></html>',
    student_options_html(unique(data$student_export_id)), width, height, margin, height - margin, width - margin, height - margin, circles)
  writeLines(html, path, useBytes = TRUE)
}

write_interactive_parallel <- function(students, focus_id, path) {
  prepared <- parallel_data(students, focus_id)
  if (nrow(prepared$data) == 0 || length(prepared$variables) < 3) {
    return(writeLines("<html><body>Données insuffisantes.</body></html>", path, useBytes = TRUE))
  }
  width <- 1000; height <- 620; margin <- 80
  x <- seq(margin, width - margin, length.out = length(prepared$variables))
  paths <- character(nrow(prepared$data))
  for (row in seq_len(nrow(prepared$data))) {
    y <- height - margin - prepared$scaled[row, ] * (height - 2 * margin)
    points <- paste(sprintf("%.1f,%.1f", x, y), collapse = " ")
    student <- html_escape(prepared$data$student_export_id[row])
    paths[row] <- sprintf('<polyline class="student" data-student="%s" points="%s" fill="none" stroke="#0072B2" stroke-width="2" opacity=".55"><title>%s</title></polyline>', student, points, html_escape(student_labels(prepared$data$student_export_id[row])))
  }
  axes <- paste(sprintf('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#bbb"/><text x="%.1f" y="%d" text-anchor="middle" font-size="13">%s</text>',
                        x, margin, x, height - margin, x, height - 35, html_escape(prepared$variables)), collapse = "\n")
  html <- sprintf('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Profils multidimensionnels</title>
<style>body{font-family:Arial;margin:24px}svg{border:1px solid #aaa}.student{transition:.2s}</style>
<h1>Profils multidimensionnels interactifs</h1><p>Haut = position relative favorable. Il s’agit d’une description, pas d’une classification.</p>
<label>Élève : <select onchange="filterStudent(this.value)">%s</select></label><svg viewBox="0 0 %d %d" width="100%%">%s%s</svg>
<script>function filterStudent(v){document.querySelectorAll(".student").forEach(e=>{e.style.opacity=(v==="all"||e.dataset.student===v)?.8:.04;e.style.strokeWidth=e.dataset.student===v?"5":"2"})}</script></html>',
    student_options_html(unique(prepared$data$student_export_id)), width, height, axes, paste(paths, collapse = "\n"))
  writeLines(html, path, useBytes = TRUE)
}

write_class_report <- function(data_list, focus_id, path) {
  students <- focus_rows(data_list$students, focus_id)
  families <- focus_rows(data_list$families, focus_id)
  pdf(path, width = 10, height = 9.6, useDingbats = FALSE)
  on.exit(dev.off(), add = TRUE)
  par(mar = rep(2,4))
  plot.new()
  plot.window(c(0,1), c(0,1), xaxs = "i", yaxs = "i")
  rect(0, 0.69, 1, 0.98, col = "#214352", border = NA)
  text(0.055, 0.91, if (is_teacher_view()) "ENSEIGNANT   /   RAPPORT NOMINATIF" else "PUBLICATION   /   RAPPORT PSEUDONYMISÉ", adj = 0, col = "white", cex = 0.9)
  text(0.055, 0.81, "Faits numériques", adj = 0, col = "white", font = 2, cex = 2.6)
  text(0.055, 0.73, sprintf("Rapport de classe du %s   |   %d élèves avec données", students$assessment_date[1], nrow(students)), adj = 0, col = "white")
  tile <- function(y, value, label) {
    rect(0,y-0.046,1,y+0.046, col = "#F0F4F5", border = NA)
    text(0.055,y,value,adj = 0, font = 2, cex = 1.35, col = "#214352")
    text(0.30,y,label,adj = 0, col = "#30454F")
  }
  tile(0.60, sprintf("%.1f %%", 100 * safe_median(students$success_rate)), "Réussite médiane des élèves parmi leurs réponses saisies")
  tile(0.49, sprintf("%.2f s", safe_median(students$median_correct_time_ms) / 1000), "Médiane des temps médians individuels sur les réponses justes")
  tile(0.38, sprintf("%.1f / min", safe_median(students$correct_per_minute)), "Débit médian de réponses justes")
  text(0.055, 0.23, "Lire les pages suivantes", adj = 0, font = 2, cex = 1.2)
  text(0.055, 0.15, "2   Vitesse et exactitude des élèves\n3   Performance par groupe de calculs\n4   Déroulement selon la position de l’item", adj = c(0,0.5))
  draw_student_scatter(data_list$students, focus_id)
  draw_family_performance(data_list$families, focus_id)
  draw_position_effects(data_list$responses, focus_id)
}

write_individual_reports <- function(students, output_dir) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  data <- add_session_number(students)
  for (student in unique(data$student_export_id)) {
    block <- data[data$student_export_id == student, , drop = FALSE]
    block <- block[order(block$session_number), ]
    label <- student_labels(student)
    filename <- if (is_teacher_view()) paste(substr(gsub("[^[:alnum:] -]", "_", label), 1, 56), student) else student
    path <- file.path(output_dir, paste0(filename, ".pdf"))
    pdf(path, width = 8.27, height = 11.69, useDingbats = FALSE)
    plot.new(); title(main = paste("Rapport individuel -", label), cex.main = 1.4)
    latest <- block[nrow(block), ]
    lines_text <- c(
      sprintf("Évaluations disponibles : %d", nrow(block)),
      sprintf("Dernière réussite : %.1f %%", 100 * latest$success_rate),
      sprintf("Dernier temps médian exact : %.2f s", latest$median_correct_time_ms / 1000),
      sprintf("Dernier débit exact : %.1f réponses/min", latest$correct_per_minute),
      sprintf("Dernier taux d’omission : %.1f %%", 100 * latest$omission_rate),
      "Comparer prioritairement l’élève à sa propre trajectoire.",
      "Ce rapport n’attribue aucune étiquette définitive."
    )
    text(0.08, seq(0.82, 0.42, length.out = length(lines_text)), labels = lines_text, adj = 0, cex = 0.95)
    par(mfrow = c(2, 1), pty = "s", mar = c(4, 5, 3, 2))
    session_range <- if (nrow(block) == 1) block$session_number + c(-0.2, 0.2) else range(block$session_number)
    plot(block$session_number, 100 * block$success_rate, type = "b", pch = 19, col = PALETTE[3], ylim = c(0, 100),
         xlim = session_range, xaxt = "n", panel.first = panel_grid(), xlab = "Session", ylab = "Réussite (%)", main = "Trajectoire d’exactitude")
    axis(1, at = block$session_number)
    if (any(is.finite(block$median_correct_time_ms))) {
      plot(block$session_number, block$median_correct_time_ms / 1000, type = "b", pch = 19, col = PALETTE[1],
           xlim = session_range, xaxt = "n", panel.first = panel_grid(), xlab = "Session", ylab = "Temps médian exact (s)", main = "Trajectoire temporelle")
      axis(1, at = block$session_number)
    } else {
      empty_plot("Aucun temps mesurable pour les réponses justes.", "Trajectoire temporelle")
    }
    par(mfrow = c(1, 1))
    dev.off()
  }
}
