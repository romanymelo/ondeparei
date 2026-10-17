"""Captura respostas reais da TMDB e grava versões enxugadas como fixtures de teste.

Uso (na raiz do projeto): uv run python -m tests.fixtures.capturar
"""

import json
from datetime import date
from pathlib import Path

import httpx

from app.config import load_settings
from app.filters import discover_params
from app.models import Filters
from app.tmdb.client import BASE_URL

FIXTURES = Path(__file__).parent
DETAIL_ID = 100088
SEASON_FIELDS = ("episode_number", "season_number", "name", "overview", "air_date", "runtime", "still_path")


def save(name: str, data: dict) -> None:
    (FIXTURES / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("gravado", name)


def only_region(results: dict, region: str) -> dict:
    return {region: results[region]} if region in results else {}


def main() -> None:
    settings = load_settings()
    region, language = settings.tmdb_region, settings.tmdb_language
    headers = {"Authorization": f"Bearer {settings.tmdb_token.get_secret_value()}"}

    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=10) as api:
        def get(path: str, **params) -> dict:
            response = api.get(path, params=params)
            response.raise_for_status()
            return response.json()

        providers = get("/watch/providers/tv", watch_region=region, language=language)
        providers["results"] = providers["results"][:15]
        for item in providers["results"]:
            item["display_priorities"] = only_region(item.get("display_priorities", {}), region)
        save("providers_tv.json", providers)

        save("genres_tv.json", get("/genre/tv/list", language=language))

        discover = get("/discover/tv", **discover_params(Filters(), region, language, date.today()))
        discover["results"] = discover["results"][:3]
        save("discover.json", discover)

        search = get("/search/tv", query="office", language=language)
        search["results"] = search["results"][:3]
        save("search_office.json", search)

        for series_id in [r["id"] for r in search["results"]] + [DETAIL_ID]:
            watch = get(f"/tv/{series_id}/watch/providers")
            watch["results"] = only_region(watch["results"], region)
            save(f"watch_providers_{series_id}.json", watch)

        detail = get(f"/tv/{DETAIL_ID}", language=language,
                     append_to_response="aggregate_credits,videos,watch/providers",
                     include_video_language="pt,en,null")
        detail["aggregate_credits"] = {"cast": detail["aggregate_credits"]["cast"][:12]}
        detail["videos"]["results"] = detail["videos"]["results"][:5]
        detail["watch/providers"]["results"] = only_region(detail["watch/providers"]["results"], region)
        save(f"tv_{DETAIL_ID}.json", detail)

        for number in (1, 2):
            season = get(f"/tv/{DETAIL_ID}/season/{number}", language=language)
            season["episodes"] = [{k: e.get(k) for k in SEASON_FIELDS} for e in season["episodes"]]
            save(f"season_{DETAIL_ID}_{number}.json", season)


if __name__ == "__main__":
    main()
