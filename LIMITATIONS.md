# Limites et précautions

## Portée scientifique

- Une classe d’environ 25 élèves permet une description locale, pas une norme populationnelle.
- Trois sessions ne suffisent pas à estimer une trajectoire individuelle stable.
- Les corrélations et évolutions ne prouvent aucune causalité pédagogique.
- Les seuils de difficulté, dont 80 %, sont des repères de travail non validés diagnostiquement.
- PyStats ne remplace ni une évaluation clinique, ni le jugement professionnel, ni l’observation qualitative.

## Mesure

- Le premier appui inclut attention, posture et interaction avec le clavier, pas seulement la récupération mentale.
- La précision dépend de la plateforme et de sa charge, même si l’horloge monotone évite les sauts de l’heure système.
- Le matériel, le pavé numérique et les conditions de passation doivent rester aussi constants que possible.
- Les données historiques migrées ne peuvent retrouver les événements ou statuts qui n’étaient pas enregistrés.
- Une limite temporelle modifie le construit observé et ne doit pas être comparée naïvement à une passation sans limite.

## Analyses

- Le bootstrap par grappes reste instable si très peu d’élèves possèdent plusieurs mesures.
- La corrélation répétée par rangs centrés est exploratoire ; une étude confirmatoire requiert un modèle préspécifié.
- Les pentes utilisent le numéro de session, pas l’intervalle calendaire exact.
- Les effets d’item, d’ordre et d’élève ne sont pas estimés simultanément par un modèle mixte automatisé.
- `correct_per_minute` combine vitesse et exactitude et ne doit pas remplacer leurs deux mesures séparées.
- Les multiples graphiques augmentent le risque de repérer des motifs fortuits ; leur cohérence doit être vérifiée.

## Comparabilité

- Les items d’ancrage soutiennent une comparaison descriptive, pas un équating formel.
- Un changement d’opération, de plage, d’ordre, d’interface ou de limite rompt partiellement la comparabilité.
- La mémorisation d’ancres réutilisées peut simuler une amélioration.
- Les catégories de difficulté sont heuristiques et ne proviennent pas d’un étalonnage externe.

## Confidentialité et sécurité

- Les pseudonymes stables restent des données personnelles.
- Le fichier public agrégé n’est pas garanti anonyme dans tous les contextes.
- SQLite n’est pas chiffré par l’application ; le chiffrement du disque et les droits du poste sont indispensables.
- Une personne ayant accès simultanément aux deux bases peut réidentifier tous les élèves.
- Il n’existe pas de gestion multi-utilisateur, de serveur de droits ou d’effacement à distance.

## Exploitation et portabilité

- L’interface a été conçue et testée comme application de bureau ; tablette/tactile et accessibilité complète demandent une validation dédiée.
- R et ses paquets doivent être installés pour produire les graphiques.
- Les rendus peuvent varier légèrement avec les polices et versions de R.
- Sans le paquet facultatif `robustbase`, le graphique final annonce et utilise le repli par médianes marginales et covariance classique ; ce repli est moins robuste qu’un MCD.
- La sauvegarde locale ne remplace pas une stratégie institutionnelle externalisée et testée.
- La restauration de la partie nominative exige de conserver ensemble la base analytique et la base d’identités correspondante.

## Améliorations possibles

Priorités futures raisonnables : chiffrement institutionnel avec gestion de clés, réglage du seuil pédagogique dans l’interface, contrôles d’accessibilité, import/export d’une configuration JSON, analyses mixtes optionnelles pour des cohortes plus larges, et validation ergonomique auprès d’élèves.
