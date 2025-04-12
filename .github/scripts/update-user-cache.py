#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from github import Github

CACHE_FILE = "cache.json"

# Nécessite un token GitHub
token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("ERREUR: Variable d'environnement GITHUB_TOKEN non définie ou vide.")
    sys.exit(1)

g = Github(token)


def load_cache():
    """Charge le cache depuis le fichier CACHE_FILE,
    s'il n'existe pas, le crée et renvoie un dict vide."""
    if not os.path.exists(CACHE_FILE):
        print(f"[ERROR] Cache file '{CACHE_FILE}' not found. Aborting.")
        sys.exit(1)
    else:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(
                f"[DEBUG] Cache file '{CACHE_FILE}' loaded successfully from {os.path.join(os.getcwd(), CACHE_FILE)}."
            )
            return data
        except json.JSONDecodeError:
            print(f"[WARN] {CACHE_FILE} semble vide ou invalide. On le réinitialise.")
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                f.write("{}")
            return {}


def save_cache(cache_data):
    """Sauvegarde le cache dans le fichier CACHE_FILE."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        print(
            f"[DEBUG] Saving cache file '{CACHE_FILE}' to {os.path.join(os.getcwd(), CACHE_FILE)}."
        )
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def determine_main_language(user_login):
    """
    Simplified version of your logic to find the main language.
    Only used to refresh if needed.
    """
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
                repo_tz = repo.updated_at.tzinfo or timezone.utc
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
        print(f"[ERROR] Could not determine main language for {user_login}: {e}")
        return "Aucune"


def refresh_user(user_login, user_info):
    """
    Fetch minimal info (avatar & main_language) from GitHub
    and update user_info if needed.
    We do NOT touch dsq_repos or fork_date.
    """
    user_obj = g.get_user(user_login)

    new_avatar = user_obj.avatar_url
    old_avatar = user_info.get("avatar_url", "")
    if not old_avatar or (old_avatar != new_avatar):
        user_info["avatar_url"] = new_avatar
        print(f"[INFO] Updated avatar for {user_login}.")

    new_main_lang = determine_main_language(user_login)
    old_main_lang = user_info.get("main_language", "")
    if not old_main_lang or (old_main_lang != new_main_lang):
        user_info["main_language"] = new_main_lang
        print(f"[INFO] Updated main_language for {user_login} => {new_main_lang}.")


def main():
    cache_data = load_cache()

    # Parcours des utilisateurs du cache
    for user_login, user_info in cache_data.items():
        try:
            refresh_user(user_login, user_info)
        except Exception as e:
            print(f"[WARN] Could not refresh user {user_login}: {e}")

    save_cache(cache_data)
    print("Cache updated successfully!")


if __name__ == "__main__":
    main()
