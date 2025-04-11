#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script d'automatisation pour mettre à jour la liste des participants des Dev Side Quests.
Ce script:
1. Récupère la liste de tous les forks du repo DSQ
2. Extrait les informations des utilisateurs
3. Génère un nouveau fichier PARTICIPANTS.md formaté
"""

import os
import requests
import json
from datetime import datetime, timedelta
from github import Github
from dateutil import parser

# Configuration
REPO_OWNER = "RaphyStoll"
REPO_NAME = "devSideQuests"

# Initialisation de l'API GitHub avec le token fourni par les Actions GitHub
token = os.environ.get("GITHUB_TOKEN")  # ou TOKEN, selon ton choix
if not token:
    print("ERREUR: Variable d'environnement TOKEN non définie ou vide")
    print(
        "Assurez-vous que le token est correctement configuré dans le workflow GitHub Actions"
    )
    sys.exit(1)

g = Github(token)


def determine_main_language(user_login):
    """Détermine le langage principal utilisé par un utilisateur sur l'ensemble de son profil"""
    try:
        user_obj = g.get_user(user_login)

        # Étape 1: Vérifier si l'utilisateur a un profil WakaTime
        if user_obj.bio and (
            "wakatime.com" in user_obj.bio.lower()
            or "waka time" in user_obj.bio.lower()
        ):
            wakatime_lang = extract_wakatime_data(user_obj.bio)
            if wakatime_lang:
                return wakatime_lang

        # Étape 2: Récupérer tous les repos publics de l'utilisateur
        repos = list(user_obj.get_repos())

        # Si l'utilisateur n'a pas de repos, vérifier la bio
        if not repos:
            bio_lang = extract_language_from_bio(user_obj)
            return bio_lang if bio_lang else "Aucune"

        # Étape 3: Collecter les langages de tous ses repos
        languages = []
        for repo in repos:
            if repo.language:
                # Donner plus de poids aux repos les plus récents (coefficient ×2)
                # et aux repos non forkés (coefficient ×3)
                weight = 1
                if not repo.fork:
                    weight *= 3
                # Vérifier si le repo a été mis à jour récemment (moins de 6 mois)
                six_months_ago = datetime.now() - timedelta(days=180)
                if repo.updated_at > six_months_ago:
                    weight *= 2

                # Ajouter le langage plusieurs fois selon son poids
                languages.extend([repo.language] * weight)

        # Étape 4: Déterminer le langage le plus fréquent avec pourcentage
        if languages:
            from collections import Counter

            counter = Counter(languages)
            total = sum(counter.values())
            most_common = counter.most_common(1)[0]
            language_name = most_common[0]
            percentage = (most_common[1] / total) * 100

            # Si le pourcentage est supérieur à 15%, ajouter le pourcentage
            if percentage > 15:
                return f"{language_name} {int(percentage)}%"
            return language_name

        # Étape 5: Si aucun langage n'est trouvé, vérifier la bio
        bio_lang = extract_language_from_bio(user_obj)
        return bio_lang if bio_lang else "Aucune"

    except Exception as e:
        print(f"Erreur lors de la détermination du langage pour {user_login}: {e}")
        return "Aucune"


def extract_wakatime_data(bio_text):
    """Tente d'extraire les données WakaTime de la bio de l'utilisateur"""
    try:
        # Rechercher les liens WakaTime dans la bio
        import re

        wakatime_urls = re.findall(r"https?://wakatime.com/[@\w\d\-\.]+", bio_text)

        if not wakatime_urls:
            return None

        # Prendre le premier lien trouvé
        wakatime_url = wakatime_urls[0]

        # Essayer d'accéder à la page WakaTime (peut nécessiter des ajustements)
        # Note: Cette partie peut être limitée par les restrictions de WakaTime
        # Pour une implémentation complète, l'API WakaTime serait nécessaire

        # Simulation d'extraction à partir du nom d'utilisateur WakaTime
        # (en réalité, il faudrait une méthode plus robuste)
        match = re.search(r"wakatime.com/(@[\w\d\-\.]+)", wakatime_url)
        if match:
            username = match.group(1)
            # Ici, on pourrait utiliser l'API WakaTime si disponible
            # Pour l'instant, on retourne simplement qu'on a détecté un profil WakaTime
            return "WakaTime"

        return None
    except Exception as e:
        print(f"Erreur lors de l'extraction des données WakaTime: {e}")
        return None


def extract_language_from_bio(user_obj):
    """Extrait un langage de programmation potentiel de la bio de l'utilisateur"""
    if not user_obj.bio:
        return None

    # Liste des langages communs à rechercher dans la bio
    common_langs = [
        "Python",
        "JavaScript",
        "Java",
        "C",
        "C++",
        "C#",
        "Go",
        "Ruby",
        "PHP",
        "Swift",
        "Kotlin",
        "Rust",
        "TypeScript",
        "Scala",
        "R",
        "Perl",
        "Haskell",
        "Lua",
        "Shell",
        "Objective-C",
        "Assembly",
    ]

    bio_text = user_obj.bio.lower()

    # Rechercher les mentions explicites comme "I code in X" or "X developer"
    for lang in common_langs:
        patterns = [
            f"{lang.lower()} developer",
            f"développeur {lang.lower()}",
            f"code in {lang.lower()}",
            f"code avec {lang.lower()}",
            f"programme en {lang.lower()}",
            f"{lang.lower()} programmer",
            f"using {lang.lower()}",
            f"specializing in {lang.lower()}",
        ]

        if any(pattern in bio_text for pattern in patterns) or lang.lower() in bio_text:
            return lang

    # Si aucun langage n'est trouvé avec les patterns
    for lang in common_langs:
        if lang.lower() in bio_text:
            return lang

    return None


def get_forks():
    """Récupère tous les forks du repo principal"""
    repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
    forks = repo.get_forks()

    fork_data = []
    for fork in forks:
        # Récupère la date de création du fork
        created_at = fork.created_at

        # Récupère les informations de l'utilisateur
        user = fork.owner

        # Recherche les repos DSQ de l'utilisateur avec les topics appropriés
        dsq_repos = []
        try:
            user_repos = g.search_repositories(f"user:{user.login} topic:devsidequests")
            for repo in user_repos:
                dsq_repos.append(
                    {
                        "name": repo.name,
                        "url": repo.html_url,
                        "topics": repo.get_topics(),
                    }
                )
        except Exception as e:
            print(f"Erreur lors de la recherche des repos pour {user.login}: {e}")

        # Déterminer la principale technologie utilisée
        main_language = determine_main_language(user.login)

        fork_data.append(
            {
                "username": user.login,
                "avatar_url": user.avatar_url,
                "profile_url": user.html_url,
                "fork_date": created_at,
                "dsq_repos": dsq_repos,
                "main_language": main_language,
            }
        )

    # Trier par date de fork (plus récent en premier)
    fork_data.sort(key=lambda x: x["fork_date"], reverse=True)
    return fork_data


def count_active_quests():
    """Détermine le nombre de quêtes actives en comptant les fichiers .md dans le répertoire quests"""
    try:
        repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
        quests_files = []

        # Récupérer les fichiers .md dans le répertoire quests
        try:
            quests_dir_contents = repo.get_contents("quests")
            for content in quests_dir_contents:
                if content.name.endswith(".md"):
                    quests_files.append(content)

            # Retourner le nombre de fichiers .md trouvés
            if quests_files:
                return len(quests_files)
        except Exception as e:
            print(f"Erreur lors de l'accès au répertoire quests: {e}")

        # Valeur par défaut en cas d'erreur ou si aucun fichier n'est trouvé
        return 1
    except Exception as e:
        print(f"Erreur lors du comptage des quêtes actives: {e}")
        return 1  # Valeur par défaut en cas d'erreur


def get_completed_quests(fork_data):
    """Détermine les quêtes complétées en analysant les dates de création des repos"""
    completed_quests = []
    quest_completion_times = {}  # Pour stocker les temps de complétion par quête

    for user in fork_data:
        for repo in user["dsq_repos"]:
            # Vérifier si le repo a plus de 7 jours (considéré comme complété)
            repo_obj = g.get_repo(f"{user['username']}/{repo['name']}")
            creation_date = repo_obj.created_at
            current_date = datetime.now()
            days_difference = (current_date - creation_date).days

            if days_difference >= 7:
                # Extraire l'ID de la quête à partir des topics
                quest_id = None
                for topic in repo["topics"]:
                    if topic.startswith("dsq") and topic != "devsidequests":
                        quest_id = topic
                        break

                if quest_id:
                    completed_quests.append(
                        {
                            "quest_id": quest_id,
                            "repo_name": repo["name"],
                            "repo_url": repo["url"],
                            "user": user["username"],
                            "completion_days": days_difference,
                        }
                    )

                    # Ajouter à notre dictionnaire de temps de complétion
                    if quest_id not in quest_completion_times:
                        quest_completion_times[quest_id] = []
                    quest_completion_times[quest_id].append(days_difference)

    # Calculer le temps moyen de complétion pour chaque quête
    average_completion_times = {}
    for quest_id, times in quest_completion_times.items():
        if times:
            average_completion_times[quest_id] = sum(times) / len(times)

    return completed_quests, average_completion_times


def generate_community_stats(fork_data):
    """Génère des statistiques détaillées sur la communauté DSQ"""
    # Préparer les données
    completion_data, avg_times = get_completed_quests(fork_data)

    # Calculer les statistiques mensuelles de croissance
    monthly_growth = calculate_monthly_growth(fork_data)

    # Calculer les statistiques de langages
    language_stats = calculate_language_stats(fork_data)

    # Formatter les données pour l'affichage
    stats = {
        "monthly_growth": monthly_growth,
        "language_stats": language_stats,
        "avg_completion_times": avg_times,
        "total_projects": len(completion_data),
    }

    return stats


def calculate_monthly_growth(fork_data):
    """Calcule la croissance mensuelle de la communauté"""
    # Grouper les forks par mois
    monthly_counts = {}

    for user in fork_data:
        fork_date = user["fork_date"]
        month_key = fork_date.strftime("%Y-%m")

        if month_key not in monthly_counts:
            monthly_counts[month_key] = 0
        monthly_counts[month_key] += 1

    # Trier les mois chronologiquement
    sorted_months = sorted(monthly_counts.keys())
    monthly_growth = []

    for month in sorted_months:
        monthly_growth.append(
            {
                "month": month,
                "count": monthly_counts[month],
                "display_name": datetime.strptime(month, "%Y-%m").strftime("%b %Y"),
            }
        )

    return monthly_growth


def calculate_language_stats(fork_data):
    """Calcule la distribution des langages dans la communauté"""
    language_counts = {}

    for user in fork_data:
        lang = user["main_language"]
        # Extraire seulement le nom du langage si un pourcentage est présent
        if "%" in lang:
            lang = lang.split()[0]

        if lang not in language_counts:
            language_counts[lang] = 0
        language_counts[lang] += 1

    # Trier par popularité
    sorted_langs = sorted(language_counts.items(), key=lambda x: x[1], reverse=True)

    # Calculer les pourcentages
    total_users = len(fork_data)
    language_stats = []

    for lang, count in sorted_langs:
        percentage = (count / total_users) * 100
        language_stats.append(
            {"language": lang, "count": count, "percentage": round(percentage, 1)}
        )

    return language_stats


def count_completed_projects(fork_data):
    """Compte le nombre total de projets DSQ complétés"""
    total = 0
    for user in fork_data:
        total += len(user["dsq_repos"])
    return total


def generate_markdown(fork_data):
    """Génère le contenu markdown du fichier PARTICIPANTS.md"""
    # Calcul des statistiques
    participants_count = len(fork_data)
    projects_count = count_completed_projects(fork_data)
    quests_count = count_active_quests()  # Utilise notre nouvelle fonction
    newest_user = fork_data[0]["username"] if fork_data else "Aucun participant"

    # Générer les statistiques avancées
    community_stats = generate_community_stats(fork_data)

    markdown = f"""# 🎮 Aventuriers des Dev Side Quests

<div align="center">
  
*Liste auto-générée le {datetime.now().strftime('%d/%m/%Y')} · Mise à jour quotidienne*

</div>

> _"Dans le monde des Dev Side Quests, ce n'est pas la destination qui compte, c'est le code que
> vous écrivez en chemin."_

Bien que les DSQ soient nées à l'école 42, cette aventure est ouverte à tous les développeurs qui
souhaitent relever des défis de code en temps limité. Étudiants de 42 ou développeurs indépendants,
rejoignez-nous !

## 🌟 Rejoindre l'aventure

Pour apparaître dans cette liste d'aventuriers :

1. **Forkez** ce repository
2. **Développez** vos propres DSQ
3. **Partagez** vos créations (ajoutez les topics `devsidequests` et `dsqX` à vos repos)

## 📊 Statistiques de la communauté

<div align="center">
  
| 🧙‍♂️ Participants | 🗺️ Quêtes actives | 🏆 Projets complétés | 🔥 Dernier arrivé |
|:----------------:|:---------------:|:--------------------:|:------------------:|
| {participants_count} | {quests_count} | {projects_count} | {newest_user} |

</div>

"""

    # Ajouter les statistiques de progression de la communauté
    if community_stats["monthly_growth"]:
        markdown += """
### 📈 Progression de la communauté

```
"""
        # Créer un graphique ASCII simple pour la progression mensuelle
        monthly_data = community_stats["monthly_growth"]
        max_count = (
            max([month["count"] for month in monthly_data]) if monthly_data else 0
        )

        if max_count > 0:
            for month in monthly_data:
                bar_length = int((month["count"] / max_count) * 30)
                bar = "█" * bar_length
                markdown += (
                    f"{month['display_name']}: {bar} ({month['count']} nouveaux)\n"
                )

        markdown += "```\n"

    # Ajouter les statistiques des langages si disponibles
    if community_stats["language_stats"]:
        markdown += """
### 💻 Langages préférés de la communauté

```
"""
        # Limiter aux 8 langages les plus populaires
        top_languages = community_stats["language_stats"][:8]
        for lang in top_languages:
            bar_length = int((lang["percentage"] / 100) * 30)
            bar = "█" * bar_length
            markdown += f"{lang['language']:10}: {bar} {lang['percentage']}%\n"

        markdown += "```\n"

    # Ajouter les temps moyens de complétion si disponibles
    if community_stats["avg_completion_times"]:
        markdown += """
### ⏱️ Temps moyen de complétion

| Quête | Temps moyen |
|:-----:|:-----------:|
"""
        for quest_id, avg_time in community_stats["avg_completion_times"].items():
            markdown += f"| {quest_id} | {avg_time:.1f} jours |\n"

        markdown += "\n"

    markdown += """
## 🔍 Guides de la communauté

<details>
<summary>💡 Comment organiser votre repo DSQ ?</summary>

Nous recommandons la structure suivante :

```
votre-projet-dsq/
├── README.md       # Présentation de votre quête
├── DEVLOG.md       # Journal de développement
├── screenshots/    # Captures de votre projet
└── src/            # Votre code source
```

</details>

<details>
<summary>📣 Comment partager efficacement votre projet ?</summary>

1. Ajoutez des screenshots dans votre README
2. Documentez votre processus dans un DEVLOG
3. Expliquez vos choix techniques et les difficultés rencontrées
4. Ajoutez les topics GitHub appropriés : `devsidequests`, `dsq1`, etc.

</details>

## 🏆 Les Nouveaux Héros (Derniers arrivés)

|                                                     Avatar                                                      |                   Aventurier                    | Classe principale |                     Repos DSQ                     | Date d'arrivée |
| :-------------------------------------------------------------------------------------------------------------: | :---------------------------------------------: | :---------------: | :-----------------------------------------------: | :------------: |
"""

    # Ajouter les 5 derniers arrivés
    for user in fork_data[:5]:
        date_formatted = user["fork_date"].strftime("%d/%m/%Y")
        repo_link = ""
        if user["dsq_repos"]:
            main_repo = user["dsq_repos"][0]
            repo_link = f"[🔗]({main_repo['url']})"

        markdown += f"| <img src=\"{user['avatar_url']}\" width=\"60\" height=\"60\" style=\"border-radius:50%\" /> "
        markdown += f"| [{user['username']}]({user['profile_url']}) "
        markdown += f"| {user['main_language']} "
        markdown += f"| {repo_link} "
        markdown += f"| {date_formatted} |\n"

    # Ajouter la section des tous les participants
    markdown += """
## 🌍 Guilde des Aventuriers (Tous les participants)

<div align="center">
<table>
"""

    # Génération de la table des utilisateurs (par groupes de 5)
    for i in range(0, len(fork_data), 5):
        markdown += "  <tr>\n"
        for user in fork_data[i : i + 5]:
            markdown += f"""    <td align="center">
      <a href="{user['profile_url']}">
        <img src="{user['avatar_url']}" width="70" /><br />
        <sub><b>{user['username']}</b></sub>
      </a>
    </td>
"""
        markdown += "  </tr>\n"

    markdown += """</table>
</div>
"""

    # Si plus de 30 participants, ajouter cette mention
    if participants_count > 30:
        markdown += f"\n_Et plus de {participants_count - 30} autres aventuriers..._\n"

    # Ajouter la section galerie des quêtes
    markdown += """
## 🎭 Galerie des Quêtes Accomplies

### DSQ #1 - Mini Weather Dashboard

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://github.com/RaphyStoll/miniWeather">
          <img src="https://via.placeholder.com/250x150?text=Mini+Weather" /><br />
          <sub><b>Python App par RaphyStoll</b></sub>
        </a>
      </td>
      <td align="center">
        <a href="https://github.com/user2/meteo-vue">
          <img src="https://via.placeholder.com/250x150?text=Meteo+Vue" /><br />
          <sub><b>Vue.js App par user2</b></sub>
        </a>
      </td>
      <td align="center">
        <a href="https://github.com/user3/react-weather">
          <img src="https://via.placeholder.com/250x150?text=React+Weather" /><br />
          <sub><b>React App par user3</b></sub>
        </a>
      </td>
    </tr>
  </table>
</div>

## 🔍 Explorer plus de projets

Découvrez les projets DSQ en explorant ces GitHub Topics :

<div align="center">
  
[🌐 Tous les projets DSQ](https://github.com/topics/devsidequests)

</div>

---

<div align="center">
  
*Cette page est générée automatiquement par un workflow GitHub Actions.*  
*Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y à %H:%M')}*

</div>
"""
    return markdown


def main():
    """Fonction principale"""
    print("Récupération des forks...")
    fork_data = get_forks()

    print(f"Nombre de participants trouvés: {len(fork_data)}")

    print("Génération des statistiques avancées...")
    # Les statistiques sont maintenant générées dans la fonction generate_markdown

    print("Génération du markdown...")
    markdown_content = generate_markdown(fork_data)

    print("Écriture dans le fichier PARTICIPANTS.md...")
    with open("PARTICIPANTS.md", "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print("Mise à jour terminée avec succès!")

    # Afficher un récapitulatif
    print("\nRécapitulatif:")
    print(f"- {len(fork_data)} participants")
    print(f"- {count_completed_projects(fork_data)} projets complétés")
    print(f"- {count_active_quests()} quêtes actives")

    # Suggestions pour des optimisations futures
    if len(fork_data) > 50:
        print(
            "\nSuggestion: Beaucoup de participants détectés, vous pourriez optimiser les appels API GitHub"
        )

    if count_completed_projects(fork_data) > 100:
        print(
            "\nSuggestion: Beaucoup de projets complétés, vous pourriez ajouter un système de filtrage par quête"
        )


if __name__ == "__main__":
    main()
