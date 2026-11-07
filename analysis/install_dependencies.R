# Vérifie les paquets R. Le calcul peut utiliser robustbase quand il est installé.
required <- c("stats", "graphics", "grDevices", "utils")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) stop(paste("Paquets R manquants :", paste(missing, collapse = ", ")))
cat("Toutes les dépendances R sont disponibles.\n")
if (requireNamespace("robustbase", quietly = TRUE)) {
  cat("Le paquet facultatif robustbase est installé. Le calcul utilisera covMcd.\n")
} else {
  cat("Le paquet facultatif robustbase est absent. Le calcul utilisera les médianes et la covariance classique.\n")
}
cat(R.version.string, "\n")
