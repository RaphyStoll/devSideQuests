#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script d'automatisation pour mettre à jour la liste des participants des Dev Side Quests.
Intégration d'un mécanisme de cache pour éviter les appels répétés à l'API GitHub.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from github import Github

# --------------------------------------------------------
# CONFIGURATION GLOBALE
# --------------------------------------------------------
REPO_OWNER = "RaphyStoll"
REPO_NAME = "devSideQuests"

# Fichier de cache
CACHE_FILE = "cache.json"

# Tableau de noms d'utilisateur à ajouter manuellement
ADDITIONAL_USERNAMES = [
    "RaphyStoll",
    # "AutreAventurier",
]

# On récupère le token GitHub
token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERREUR: Variable d'environnement GITHUB_TOKEN non définie ou vide.")
    sys.exit(1)

g = Github(token)

# --------------------------------------------------------
# GESTION DU CACHE
# --------------------------------------------------------


def load_cache():
    """Charge le cache depuis le fichier CACHE_FILE,
    s'il n'existe pas, le crée et renvoie un dict vide."""
    if not os.path.exists(CACHE_FILE):
        # On crée un nouveau fichier de cache vide
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write("{}")  # on met simplement un JSON vide
        return {}

    # Sinon, on lit son contenu
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_data):
    """Sauvegarde le cache dans le fichier CACHE_FILE."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print("Chemin d'exécution :", os.getcwd())


# --------------------------------------------------------
# FONCTIONS POUR RÉCUPÉRER / STOCKER LES INFOS UTILISATEUR
# --------------------------------------------------------


def fetch_user_data(user_login, fork_date=None):
    """
    Récupère toutes les infos pour un utilisateur donné (avatar, URL, date "fork"/arrivée,
    repos DSQ, langage principal) via l'API GitHub, et renvoie un dict.
    """
    user_obj = g.get_user(user_login)

    # Si fork_date n'est pas fourni, on prend la date de création de son compte
    # (utile pour les "ADDITIONAL_USERNAMES" qui n'ont pas forké).
    if not fork_date:
        fork_date = user_obj.created_at

    # Récupération des dépôts DSQ
    dsq_repos = []
    try:
        user_repos = g.search_repositories(f"user:{user_login} topic:devsidequests")
        for r in user_repos:
            dsq_repos.append(
                {"name": r.name, "url": r.html_url, "topics": r.get_topics()}
            )
    except Exception as e:
        print(f"Erreur lors de la recherche DSQ pour {user_login}: {e}")

    main_language = determine_main_language(user_login)

    # On stocke la date au format ISO8601 (string) pour plus de facilité au JSON
    return {
        "username": user_login,
        "avatar_url": user_obj.avatar_url,
        "profile_url": user_obj.html_url,
        "fork_date": fork_date.isoformat(),
        "dsq_repos": dsq_repos,
        "main_language": main_language,
    }


def get_or_cache_user(user_login, cache_data, fork_date=None):
    if user_login in cache_data:
        user_info = cache_data[user_login]
        # user_info["fork_date"] est une string iso
        if fork_date:
            # si on a un "fork_date" plus récent, on écrase
            user_info["fork_date"] = fork_date.isoformat()
    else:
        # On fetch
        user_info = fetch_user_data(user_login, fork_date)
        cache_data[user_login] = user_info

    # Convertir en datetime directement
    # => dans le dictionnaire Python, on garde un champ datetime
    # => dans le cache JSON, on garde la chaîne iso
    fd_str = user_info["fork_date"]

    return user_info


# --------------------------------------------------------
# DÉTERMINATION DU LANGAGE PRINCIPAL
# --------------------------------------------------------


def determine_main_language(user_login):
    try:
        user_obj = g.get_user(user_login)
        repos = list(user_obj.get_repos())

        if not repos:
            return "Aucune"

        from collections import Counter

        languages = []

        for repo in repos:
            if repo.language:
                weight = 1

                # On s'assure d'un offset-aware "six_months_ago"
                # en prenant la timezone du repo si elle existe :
                repo_tz = repo.updated_at.tzinfo
                six_months_ago = datetime.now(tz=repo_tz) - timedelta(days=180)

                if not repo.fork:
                    weight *= 3
                if repo.updated_at > six_months_ago:
                    weight *= 2

                languages.extend([repo.language] * weight)

        if not languages:
            return "Aucune"

        counter = Counter(languages)
        lang, count = counter.most_common(1)[0]
        total = sum(counter.values())
        percentage = (count / total) * 100
        if percentage > 15:
            return f"{lang} {int(percentage)}%"
        return lang

    except Exception as e:
        print(f"Erreur determine_main_language({user_login}): {e}")
        return "Aucune"


# --------------------------------------------------------
# RÉCUPÉRATION DES DONNÉES : FORKS + PARTICIPANTS ADDITIONNELS
# --------------------------------------------------------


def get_forks(cache_data):
    """
    Récupère la liste des forks du repo principal,
    utilise le cache pour chaque user,
    et retourne une liste de dict participants.
    """
    repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
    forks = repo.get_forks()

    participants = []
    for fork in forks:
        user_login = fork.owner.login
        fork_date = fork.created_at
        # On récupère l'utilisateur depuis le cache ou via l'API
        user_data = get_or_cache_user(user_login, cache_data, fork_date)
        participants.append(user_data)

    # On ne convertit pas encore la date en datetime,
    # mais on va le faire plus tard, avant le tri final.
    return participants


def get_additional_participants_data(usernames_list, cache_data):
    """
    Pour chaque username additionnel, on récupère les infos
    via le cache ou l'API GitHub.
    On renvoie une liste (même format que get_forks).
    """
    participants_data = []
    for username in usernames_list:
        user_data = get_or_cache_user(username, cache_data, None)
        participants_data.append(user_data)
    return participants_data


# --------------------------------------------------------
# STATISTIQUES : QUÊTES ACTIVES, PROJETS COMPLÉTÉS, ETC.
# --------------------------------------------------------


def count_active_quests():
    """Détermine le nombre de quêtes actives via le topic 'dsqX'."""
    try:
        dsq_repos = g.search_repositories("topic:devsidequests")
        quest_topics = set()
        for repo in dsq_repos:
            topics = repo.get_topics()
            for topic in topics:
                if topic.startswith("dsq") and topic != "devsidequests":
                    quest_topics.add(topic)
        return len(quest_topics) if quest_topics else 1
    except Exception as e:
        print(f"Erreur lors du comptage des quêtes actives: {e}")
        return 1


def count_completed_projects(fork_data):
    """Compte le nombre total de projets DSQ (tous repos DSQ, terminés ou non)."""
    total = 0
    for user in fork_data:
        total += len(user["dsq_repos"])
    return total


def calculate_monthly_growth(fork_data):
    """Calcule la croissance mensuelle (groupement par YYYY-MM)."""
    monthly_counts = {}
    for user in fork_data:
        # On re-convertit la date iso en datetime
        dt = datetime.fromisoformat(user["fork_date"])
        month_key = dt.strftime("%Y-%m")
        monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1

    sorted_months = sorted(monthly_counts.keys())
    monthly_growth = []
    for month in sorted_months:
        dt_obj = datetime.strptime(month, "%Y-%m")
        monthly_growth.append(
            {
                "month": month,
                "count": monthly_counts[month],
                "display_name": dt_obj.strftime("%b %Y"),
            }
        )
    return monthly_growth


def calculate_language_stats(fork_data):
    """Classement des langages principaux dans la communauté."""
    from collections import Counter

    lang_counter = Counter()

    for user in fork_data:
        lang = user["main_language"]
        # Si on a un pourcentage, on ne garde que le nom du langage
        if "%" in lang:
            lang = lang.split()[0]
        lang_counter[lang] += 1

    total_users = len(fork_data)
    stats = []
    for lang, count in lang_counter.most_common():
        percentage = round((count / total_users) * 100, 1)
        stats.append({"language": lang, "count": count, "percentage": percentage})
    return stats


def get_completed_quests(fork_data):
    """
    Retourne la liste des quêtes "terminées" (repos DSQ de plus de 7 jours)
    et calcule le temps moyen de complétion.
    """
    completed_quests = []
    quest_completion_times = {}

    for user in fork_data:
        username = user["username"]
        for repo_info in user["dsq_repos"]:
            repo_name = repo_info["name"]
            # On essaye d'aller voir la date de création du repo
            try:
                repo_obj = g.get_repo(f"{username}/{repo_name}")
                creation_date = repo_obj.created_at
                days_diff = (datetime.now() - creation_date).days
                if days_diff >= 7:
                    # la quête est considérée comme "complétée"
                    quest_id = None
                    for t in repo_info["topics"]:
                        if t.startswith("dsq") and t != "devsidequests":
                            quest_id = t
                            break
                    if quest_id:
                        completed_quests.append(
                            {
                                "quest_id": quest_id,
                                "repo_name": repo_info["name"],
                                "repo_url": repo_info["url"],
                                "user": username,
                                "completion_days": days_diff,
                            }
                        )
                        if quest_id not in quest_completion_times:
                            quest_completion_times[quest_id] = []
                        quest_completion_times[quest_id].append(days_diff)
            except Exception as e:
                print(
                    f"Skipping repo {repo_name} for user {username} due to error: {e}"
                )
                continue

    # On calcule la moyenne de complétion pour chaque quête
    average_times = {}
    for qid, times in quest_completion_times.items():
        if times:
            average_times[qid] = sum(times) / len(times)

    return completed_quests, average_times


def generate_community_stats(fork_data):
    """
    Construit un dict de stats (progression, langages, temps moyen...).
    """
    # Quêtes terminées et moyenne
    completion_data, avg_times = get_completed_quests(fork_data)
    monthly_growth = calculate_monthly_growth(fork_data)
    language_stats = calculate_language_stats(fork_data)

    stats = {
        "monthly_growth": monthly_growth,
        "language_stats": language_stats,
        "avg_completion_times": avg_times,
        "total_projects": len(completion_data),
    }
    return stats


# --------------------------------------------------------
# GÉNÉRATION DU MARKDOWN
# --------------------------------------------------------


def generate_markdown(fork_data):
    """
    Gère la construction de PARTICIPANTS.md (sans la "Galerie des Quêtes").
    """
    # Tri final du plus récent au plus ancien
    fork_data.sort(key=lambda x: datetime.fromisoformat(x["fork_date"]), reverse=True)

    participants_count = len(fork_data)
    projects_count = count_completed_projects(fork_data)
    quests_count = count_active_quests()
    newest_user = fork_data[0]["username"] if fork_data else "Aucun participant"

    # Stats avancées
    community_stats = generate_community_stats(fork_data)

    date_now = datetime.now()
    date_now_str = date_now.strftime("%d/%m/%Y")
    date_hour_str = date_now.strftime("%d/%m/%Y à %H:%M")

    markdown = f"""# 🎮 Aventuriers des Dev Side Quests

<div align="center">
  
*Liste auto-générée le {date_now_str} · Mise à jour quotidienne*

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

    # Progression mensuelle
    monthly_data = community_stats["monthly_growth"]
    if monthly_data:
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
        date_formatted = datetime.fromisoformat(user["fork_date"]).strftime("%d/%m/%Y")
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

    # Ajouter la section footer
    markdown += """
    
---

<div align="center">

*Cette page est générée automatiquement par un workflow GitHub Actions.*  
*Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y à %H:%M')}*

</div>
""".format(
        date_heure=datetime.now().strftime("%d/%m/%Y à %H:%M")
    )
    return markdown


def main():
    print("Récupération du cache...")
    cache_data = load_cache()

    print("Récupération des forks...")
    fork_data = get_forks(cache_data)
    print(f"Nombre de participants trouvés: {len(fork_data)}")

    print("Participants additionnels...")
    additional_data = get_additional_participants_data(ADDITIONAL_USERNAMES, cache_data)
    print(f"Participants additionnels : {len(additional_data)}")

    # Correction du NameError : renommer 'forks_data' en 'fork_data'
    combined = fork_data + additional_data
    print(f"Nombre total de participants après fusion : {len(combined)}")

    print("Génération du markdown...")
    markdown_content = generate_markdown(combined)

    print("Écriture dans PARTICIPANTS.md...")
    with open("PARTICIPANTS.md", "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print("Mise à jour du cache...")
    save_cache(cache_data)
    print("Mise à jour terminée.")

    # Récap
    print("\nRécapitulatif:")
    print(f"- {len(fork_data)} participants (via forks)")
    print(f"- {count_completed_projects(fork_data)} projets complétés")
    print(f"- {count_active_quests()} quêtes actives")


if __name__ == "__main__":
    main()
