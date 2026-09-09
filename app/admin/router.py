import datetime as dt
import logging
import re

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import current_admin, flash, is_admin, render
from app.db.session import get_session
from app.models.enums import (
    CompetitionType,
    GameEventType,
    GameStage,
    HomepageBlockType,
    MediaKind,
    PlayerPosition,
    UserRole,
)
from app.models.homepage import MAX_HOMEPAGE_BLOCKS
from app.schemas.auth import UserCreate, UserUpdate
from app.schemas.competition import CompetitionCreate, CompetitionUpdate
from app.schemas.game import (
    GameCreate,
    GameEventIn,
    GameTeamStatIn,
    GameUpdate,
    PlayerStatLine,
    ProtocolRequest,
)
from app.schemas.homepage import HomepageBlockIn
from app.schemas.player import PlayerCreate, PlayerUpdate
from app.schemas.team import TeamCreate, TeamUpdate
from app.services import (
    competition_service,
    game_service,
    homepage_service,
    media_service,
    player_service,
    stats_service,
    team_service,
    user_service,
)
from app.services.clock import ClockParseError, format_clock, parse_clock, parse_video_time
from app.services.competition_service import ValidationError

logger = logging.getLogger("tots.admin")

router = APIRouter(prefix="/admin", include_in_schema=False)

LOGIN_URL = "/admin/login"


def _guard(request: Request) -> RedirectResponse | None:
    if current_admin(request) is None:
        return RedirectResponse(LOGIN_URL, status_code=303)
    return None


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# --- Аутентификация ---
@router.get("/login")
async def login_page(request: Request):
    if current_admin(request):
        return _redirect("/admin")
    return render(request, "login.html", error=None)


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    user = await user_service.authenticate(db, username, password)
    if user is None:
        return render(request, "login.html", error="Неверный логин или пароль")
    request.session["admin_user_id"] = user.id
    request.session["admin_username"] = user.username
    request.session["admin_role"] = user.role.value
    return _redirect("/admin")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return _redirect(LOGIN_URL)


# --- Дашборд ---
@router.get("")
@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    comps, comp_total = await competition_service.list_competitions(db, page=1, size=100)
    teams_items, team_total = await team_service.list_teams(db, page=1, size=1000)
    _, player_total = await player_service.list_players(db, page=1, size=1)
    all_games = await game_service.list_games(db)
    upcoming = [g for g in all_games if g.score_team_a is None][:10]

    team_names = {t.id: t.name for t in teams_items}
    comp_names = {c.id: c.name for c in comps}

    today = dt.date.today()
    week_start = today - dt.timedelta(days=today.weekday())
    week_end = week_start + dt.timedelta(days=6)
    this_week = sorted(
        (g for g in all_games if week_start <= g.date <= week_end),
        key=lambda g: (g.date, g.time or dt.time.min),
    )

    counts = {
        "competitions": comp_total,
        "teams": team_total,
        "players": player_total,
        "games": len(all_games),
    }
    return render(
        request,
        "dashboard.html",
        competitions=comps,
        upcoming=upcoming,
        counts=counts,
        this_week=this_week,
        team_names=team_names,
        comp_names=comp_names,
        week_start=week_start,
        week_end=week_end,
        today=today,
    )


# --- Команды ---
@router.get("/teams")
async def teams_page(request: Request, q: str | None = None, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    items, total = await team_service.list_teams(db, page=1, size=500, search=q)
    return render(request, "teams.html", teams=items, q=q or "", total=total)


@router.get("/teams/new")
async def teams_new(request: Request):
    if r := _guard(request):
        return r
    return render(request, "team_form.html", team=None)


@router.get("/teams/{team_id}/edit")
async def teams_edit_page(request: Request, team_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    team = await team_service.get(db, team_id)
    if team is None:
        return _redirect("/admin/teams")
    return render(request, "team_form.html", team=team)


@router.post("/teams")
async def teams_create(
    request: Request,
    name: str = Form(...),
    city: str = Form(""),
    logo_url: str = Form(""),
    logo: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    uploaded = await _maybe_upload_photo(db, logo, MediaKind.team_logo, request)
    await team_service.create(
        db, TeamCreate(name=name, city=city or None, logo_url=uploaded or logo_url or None)
    )
    return _redirect("/admin/teams")


@router.post("/teams/{team_id}/edit")
async def teams_edit(
    request: Request,
    team_id: int,
    name: str = Form(...),
    city: str = Form(""),
    logo_url: str = Form(""),
    logo: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    team = await team_service.get(db, team_id)
    if team:
        uploaded = await _maybe_upload_photo(db, logo, MediaKind.team_logo, request)
        data = TeamUpdate(name=name, city=city or None)
        new_logo = uploaded or (logo_url or None)
        if new_logo:
            data.logo_url = new_logo
        await team_service.update(db, team, data)
    return _redirect("/admin/teams")


@router.post("/teams/{team_id}/delete")
async def teams_delete(request: Request, team_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    team = await team_service.get(db, team_id)
    if team:
        await team_service.delete(db, team)
    return _redirect("/admin/teams")


# --- Игроки ---
PLAYER_PAGE_SIZES = [10, 50, 100, 150, 200]


@router.get("/players")
async def players_page(
    request: Request,
    q: str | None = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    if size not in PLAYER_PAGE_SIZES:
        size = 50
    if page < 1:
        page = 1
    items, total = await player_service.list_players(db, page=page, size=size, search=q)
    total_pages = max(1, (total + size - 1) // size)
    if page > total_pages:
        page = total_pages
        items, total = await player_service.list_players(db, page=page, size=size, search=q)
    return render(
        request,
        "players.html",
        players=items,
        q=q or "",
        total=total,
        page=page,
        size=size,
        total_pages=total_pages,
        page_sizes=PLAYER_PAGE_SIZES,
    )


async def _maybe_upload_photo(
    db: AsyncSession,
    photo: UploadFile | None,
    kind: MediaKind,
    request: Request | None = None,
) -> str | None:
    """Загружает файл, если он выбран. Отказ не теряется: причина уходит
    в flash и показывается на следующей странице, иначе форма молча
    сохранялась бы без картинки."""
    if photo is None or not photo.filename:
        return None
    content = await photo.read()
    try:
        rec = await media_service.save_upload(
            db, content=content, content_type=photo.content_type, kind=kind
        )
    except media_service.MediaError as exc:
        logger.warning(
            "Файл «%s» (%s, %.1f МБ) не принят: %s",
            photo.filename, photo.content_type, len(content) / 1024 / 1024, exc,
        )
        if request is not None:
            flash(request, f"Файл «{photo.filename}» не загружен: {exc}")
        return None
    return media_service.file_url(rec.filename)


@router.get("/players/new")
async def players_new(request: Request):
    if r := _guard(request):
        return r
    return render(request, "player_form.html", player=None, positions=list(PlayerPosition))


@router.get("/players/{player_id}/edit")
async def players_edit_page(request: Request, player_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    player = await player_service.get(db, player_id)
    if player is None:
        return _redirect("/admin/players")
    return render(request, "player_form.html", player=player, positions=list(PlayerPosition))


@router.post("/players")
async def players_create(
    request: Request,
    full_name: str = Form(...),
    birth_date: str = Form(""),
    position: str = Form(""),
    grip: str = Form(""),
    photo: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    photo_url = await _maybe_upload_photo(db, photo, MediaKind.player_photo, request)
    await player_service.create(
        db,
        PlayerCreate(
            full_name=full_name,
            birth_date=dt.date.fromisoformat(birth_date) if birth_date else None,
            position=position or None,
            grip=grip or None,
            photo_url=photo_url,
        ),
    )
    return _redirect("/admin/players")


@router.post("/players/{player_id}/edit")
async def players_edit(
    request: Request,
    player_id: int,
    full_name: str = Form(...),
    birth_date: str = Form(""),
    position: str = Form(""),
    grip: str = Form(""),
    photo: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    player = await player_service.get(db, player_id)
    if player:
        photo_url = await _maybe_upload_photo(db, photo, MediaKind.player_photo, request)
        data = PlayerUpdate(
            full_name=full_name,
            birth_date=dt.date.fromisoformat(birth_date) if birth_date else None,
            position=position or None,
            grip=grip or None,
        )
        if photo_url:
            data.photo_url = photo_url
        await player_service.update(db, player, data)
    return _redirect("/admin/players")


@router.post("/players/{player_id}/delete")
async def players_delete(request: Request, player_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    player = await player_service.get(db, player_id)
    if player:
        await player_service.delete(db, player)
    return _redirect("/admin/players")


# --- Соревнования ---
@router.get("/competitions")
async def competitions_page(request: Request, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    items, _ = await competition_service.list_competitions(db, page=1, size=500)
    return render(request, "competitions.html", competitions=items, types=list(CompetitionType))


@router.get("/competitions/new")
async def competitions_new(request: Request):
    if r := _guard(request):
        return r
    return render(
        request, "competition_form.html", comp=None, roster=[], types=list(CompetitionType)
    )


@router.post("/competitions")
async def competitions_create(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(""),
    location: str = Form(""),
    logo_url: str = Form(""),
    logo: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    uploaded = await _maybe_upload_photo(db, logo, MediaKind.competition_logo, request)
    comp = await competition_service.create(
        db,
        CompetitionCreate(
            name=name,
            type=CompetitionType(type),
            start_date=dt.date.fromisoformat(start_date),
            end_date=dt.date.fromisoformat(end_date) if end_date else None,
            location=location or None,
            logo_url=uploaded or logo_url or None,
        ),
    )
    return _redirect(f"/admin/competitions/{comp.id}")


@router.get("/competitions/{competition_id}/edit")
async def competitions_edit_page(
    request: Request, competition_id: int, db: AsyncSession = Depends(get_session)
):
    if r := _guard(request):
        return r
    comp = await competition_service.get(db, competition_id)
    if comp is None:
        return _redirect("/admin/competitions")
    # победителя выбираем только из заявленных команд
    roster = await competition_service.get_roster(db, competition_id)
    return render(
        request,
        "competition_form.html",
        comp=comp,
        roster=roster,
        types=list(CompetitionType),
    )


@router.get("/competitions/{competition_id}")
async def competition_detail(
    request: Request, competition_id: int, db: AsyncSession = Depends(get_session)
):
    if r := _guard(request):
        return r
    comp = await competition_service.get(db, competition_id)
    if comp is None:
        return _redirect("/admin/competitions")
    roster = await competition_service.get_roster(db, competition_id)
    players = await competition_service.get_players(db, competition_id)
    all_teams, _ = await team_service.list_teams(db, page=1, size=500)
    all_players, _ = await player_service.list_players(db, page=1, size=1000)
    games = await game_service.list_games(db, competition_id=competition_id)
    standings = await stats_service.compute_standings(db, competition_id)
    return render(
        request,
        "competition.html",
        comp=comp,
        roster=roster,
        roster_players=players,
        all_teams=all_teams,
        all_players=all_players,
        games=games,
        standings=standings,
        stages=list(GameStage),
    )


@router.post("/competitions/{competition_id}/edit")
async def competition_edit(
    request: Request,
    competition_id: int,
    name: str = Form(...),
    type: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    location: str = Form(""),
    logo_url: str = Form(""),
    logo: UploadFile | None = None,
    show_playoff_bracket: bool = Form(False),
    show_best_players: bool = Form(False),
    winner_team_id: str = Form(""),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    comp = await competition_service.get(db, competition_id)
    if comp is None:
        return _redirect("/admin/competitions")

    uploaded = await _maybe_upload_photo(db, logo, MediaKind.competition_logo, request)
    # update() применяет только явно переданные поля (exclude_unset), поэтому
    # собираем набор целиком, а не доопределяем атрибуты после конструктора
    fields: dict = {
        "name": name,
        "location": location or None,
        "end_date": dt.date.fromisoformat(end_date) if end_date else None,
        "show_playoff_bracket": show_playoff_bracket,
        "show_best_players": show_best_players,
        "winner_team_id": int(winner_team_id) if winner_team_id else None,
    }
    if type:
        fields["type"] = CompetitionType(type)
    if start_date:
        fields["start_date"] = dt.date.fromisoformat(start_date)
    new_logo = uploaded or (logo_url or None)
    if new_logo:
        # пустое поле файла означает «оставить текущий логотип»
        fields["logo_url"] = new_logo

    try:
        await competition_service.update(db, comp, CompetitionUpdate(**fields))
    except ValidationError as exc:
        return render(request, "error.html", message=str(exc))
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/teams")
async def competition_add_team(
    request: Request,
    competition_id: int,
    team_id: int = Form(...),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    await competition_service.add_team(db, competition_id, team_id)
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/teams/bulk")
async def competition_add_teams_bulk(
    request: Request,
    competition_id: int,
    team_ids: list[int] = Form(default=[]),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    for tid in team_ids:
        await competition_service.add_team(db, competition_id, tid)
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/teams/{team_id}/delete")
async def competition_remove_team(
    request: Request, competition_id: int, team_id: int, db: AsyncSession = Depends(get_session)
):
    if r := _guard(request):
        return r
    await competition_service.remove_team(db, competition_id, team_id)
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/players")
async def competition_add_player(
    request: Request,
    competition_id: int,
    team_id: int = Form(...),
    player_id: int = Form(...),
    number: str = Form(""),
    contract: bool = Form(False),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    await competition_service.add_player(
        db, competition_id, team_id, player_id, int(number) if number else None, contract
    )
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/players/bulk")
async def competition_add_players_bulk(
    request: Request,
    competition_id: int,
    team_id: int = Form(...),
    player_ids: list[int] = Form(default=[]),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    for pid in player_ids:
        await competition_service.add_player(db, competition_id, team_id, pid, None, False)
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/players/{player_id}/number")
async def competition_set_number(
    request: Request,
    competition_id: int,
    player_id: int,
    team_id: int = Form(...),
    number: str = Form(""),
    contract: bool = Form(False),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    await competition_service.update_roster_player(
        db,
        competition_id,
        team_id,
        player_id,
        number=int(number) if number.strip() else None,
        contract=contract,
        set_number=True,
    )
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/players/{player_id}/delete")
async def competition_remove_player(
    request: Request,
    competition_id: int,
    player_id: int,
    team_id: int = Form(...),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    await competition_service.remove_player(db, competition_id, team_id, player_id)
    return _redirect(f"/admin/competitions/{competition_id}")


@router.post("/competitions/{competition_id}/delete")
async def competition_delete(
    request: Request, competition_id: int, db: AsyncSession = Depends(get_session)
):
    if r := _guard(request):
        return r
    comp = await competition_service.get(db, competition_id)
    if comp:
        await competition_service.delete(db, comp)
    return _redirect("/admin/competitions")


# --- Матчи ---
@router.post("/competitions/{competition_id}/games")
async def game_create(
    request: Request,
    competition_id: int,
    team_a_id: int = Form(...),
    team_b_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(""),
    location: str = Form(""),
    stage: str = Form(GameStage.matches.value),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    await game_service.create(
        db,
        GameCreate(
            competition_id=competition_id,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            date=dt.date.fromisoformat(date),
            time=dt.time.fromisoformat(time) if time else None,
            location=location or None,
            stage=GameStage(stage),
        ),
    )
    return _redirect(f"/admin/competitions/{competition_id}")


@router.get("/games/{game_id}/edit")
async def game_edit_page(request: Request, game_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    game = await game_service.get(db, game_id)
    if game is None:
        return _redirect("/admin/competitions")
    roster = await competition_service.get_roster(db, game.competition_id)
    return render(request, "game_form.html", game=game, roster=roster, stages=list(GameStage))


@router.post("/games/{game_id}/edit")
async def game_edit(
    request: Request,
    game_id: int,
    team_a_id: int = Form(...),
    team_b_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(""),
    location: str = Form(""),
    stage: str = Form(GameStage.matches.value),
    video_url: str = Form(""),
    scan: UploadFile | None = None,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    game = await game_service.get(db, game_id)
    if game is None:
        return _redirect("/admin/competitions")
    uploaded_scan = await _maybe_upload_photo(db, scan, MediaKind.game_scan, request)
    data = GameUpdate(
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        date=dt.date.fromisoformat(date),
        time=dt.time.fromisoformat(time) if time else None,
        location=location or None,
        stage=GameStage(stage),
        video_url=video_url or None,
    )
    if uploaded_scan:
        data.scan = uploaded_scan
    await game_service.update(db, game, data)
    return _redirect(f"/admin/competitions/{game.competition_id}")


@router.post("/games/{game_id}/delete")
async def game_delete(request: Request, game_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    game = await game_service.get(db, game_id)
    cid = game.competition_id if game else None
    if game:
        await game_service.delete(db, game)
    return _redirect(f"/admin/competitions/{cid}" if cid else "/admin/competitions")


# --- Протокол матча (ключевой экран) ---
_EV_KEY = re.compile(r"^ev-(\d+)-([a-z0-9_]+)$")
_PID_KEY = re.compile(r"^pid-(\d+)-(\d+)$")

# Поля события в форме; порядок важен только для читаемости шаблона
EVENT_FIELDS = (
    "time",
    "type",
    "team_id",
    "player_id",
    "assist1_player_id",
    "assist2_player_id",
    "penalty_minutes",
    "video_time",
)


def _indexed_rows(form, pattern: re.Pattern) -> list[dict[str, str]]:
    """'ev-0-type' -> [{'type': ...}] в порядке индекса.

    Пропуски в нумерации и произвольный порядок ключей в POST безопасны:
    индекс — просто метка строки, JS её не переиспользует.
    """
    buckets: dict[int, dict[str, str]] = {}
    for key in form.keys():
        m = pattern.match(key)
        if not m:
            continue
        value = form.get(key)
        buckets.setdefault(int(m.group(1)), {})[m.group(2)] = (
            value.strip() if isinstance(value, str) else ""
        )
    return [buckets[i] for i in sorted(buckets)]


def _events_from_form(form) -> tuple[list[GameEventIn], list[str], list[dict[str, str]]]:
    """Разбирает строки таймлайна.

    Возвращает события, список ошибок и сырые строки — последние нужны, чтобы
    при ошибке вернуть пользователю его же ввод, а не пустую форму.
    """
    events: list[GameEventIn] = []
    errors: list[str] = []
    raw_rows: list[dict[str, str]] = []

    for row in _indexed_rows(form, _EV_KEY):
        time_raw = row.get("time", "")
        # полностью пустая заготовка — молча выбрасываем
        if not time_raw and not row.get("player_id"):
            continue
        raw_rows.append(row)
        label = f"Событие {len(raw_rows)} ({time_raw or 'без времени'})"

        kind_raw = row.get("type") or GameEventType.goal.value
        try:
            kind = GameEventType(kind_raw)
        except ValueError:
            errors.append(f"{label}: неизвестный тип «{kind_raw}»")
            continue

        try:
            seconds = parse_clock(time_raw)
            video = parse_video_time(row.get("video_time"))
        except ClockParseError as exc:
            errors.append(f"{label}: время «{exc.args[0]}» непонятно, нужно ММ:СС")
            continue
        if seconds is None:
            errors.append(f"{label}: не указано время")
            continue
        if not row.get("player_id"):
            errors.append(f"{label}: не выбран игрок")
            continue

        def num(field: str) -> int | None:
            value = row.get(field)
            return int(value) if value and value.isdigit() else None

        is_goal = kind in (GameEventType.goal, GameEventType.shootout_goal)
        try:
            events.append(
                GameEventIn(
                    type=kind,
                    team_id=int(row["team_id"]),
                    time_seconds=seconds,
                    player_id=int(row["player_id"]),
                    assist1_player_id=num("assist1_player_id") if is_goal else None,
                    assist2_player_id=num("assist2_player_id") if is_goal else None,
                    penalty_minutes=(
                        num("penalty_minutes") if kind is GameEventType.penalty else None
                    ),
                    video_seconds=video if is_goal else None,
                )
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"{label}: {exc}")
    return events, errors, raw_rows


def _lines_from_form(form) -> list[PlayerStatLine]:
    """Строки участия. Голы/пас/штраф не читаем — они выводятся из событий."""

    def _int(name: str) -> int:
        value = form.get(name)
        try:
            return int(value) if value not in (None, "") else 0
        except ValueError:
            return 0

    lines: list[PlayerStatLine] = []
    for key in form.keys():
        m = _PID_KEY.match(key)
        if not m:
            continue
        pid, tid = int(m.group(1)), int(m.group(2))
        prefix = f"stat-{pid}-{tid}"
        is_goalie = form.get(f"{prefix}-is_goalie") is not None
        lines.append(
            PlayerStatLine(
                player_id=pid,
                team_id=tid,
                is_goalie=is_goalie,
                goals_against=_int(f"{prefix}-goals_against") if is_goalie else None,
                saves=_int(f"{prefix}-saves") if is_goalie else None,
                minutes_played=_int(f"{prefix}-minutes_played") if is_goalie else None,
            )
        )
    return lines


def _team_stats_from_form(form, game) -> tuple[list[GameTeamStatIn], list[str]]:
    """Командные итоги: по одной строке на команду. Пустая строка не сохраняется."""
    rows: list[GameTeamStatIn] = []
    errors: list[str] = []
    for team_id in (game.team_a_id, game.team_b_id):
        values = {}
        for field in ("shots", "shots_on_goal", "faceoffs_won", "conversion_percent"):
            raw = (form.get(f"ts-{team_id}-{field}") or "").strip()
            if raw == "":
                values[field] = None
                continue
            try:
                values[field] = int(raw)
            except ValueError:
                errors.append(f"Командные итоги: «{raw}» — не число")
                values[field] = None
        if any(v is not None for v in values.values()):
            try:
                rows.append(GameTeamStatIn(team_id=team_id, **values))
            except PydanticValidationError:
                errors.append(
                    "Командные итоги: броски и вбрасывания не могут быть отрицательными, "
                    "реализация — от 0 до 100"
                )
    return rows, errors


def _team_stats_rows(game) -> dict[int, dict[str, str]]:
    """Командные итоги из базы в строковом виде — как их отдаёт форма."""
    return {
        ts.team_id: {
            "shots": str(ts.shots if ts.shots is not None else ""),
            "shots_on_goal": str(ts.shots_on_goal if ts.shots_on_goal is not None else ""),
            "faceoffs_won": str(ts.faceoffs_won if ts.faceoffs_won is not None else ""),
            "conversion_percent": str(
                ts.conversion_percent if ts.conversion_percent is not None else ""
            ),
        }
        for ts in game.team_stats
    }


def _event_rows_from_db(game) -> list[dict[str, str]]:
    """События из базы в том же строковом виде, что приходит из формы."""
    rows = []
    for ev in game.events:
        rows.append(
            {
                "time": format_clock(ev.time_seconds),
                "type": ev.type.value,
                "team_id": str(ev.team_id),
                "player_id": str(ev.player_id),
                "assist1_player_id": str(ev.assist1_player_id or ""),
                "assist2_player_id": str(ev.assist2_player_id or ""),
                "penalty_minutes": str(ev.penalty_minutes or ""),
                "video_time": format_clock(ev.video_seconds),
            }
        )
    return rows


async def _protocol_context(
    db, request, game, *, event_rows, existing, derived, team_stats=None, errors=()
):
    roster_players = await competition_service.get_players(db, game.competition_id)
    team_players: dict[int, list] = {game.team_a_id: [], game.team_b_id: []}
    for cp in roster_players:
        if cp.team_id in team_players:
            team_players[cp.team_id].append(cp)
    # Для селектов в JS: {team_id: [{id, label}]}
    roster_json = {
        str(tid): [
            {
                "id": cp.player_id,
                "label": (f"#{cp.number} " if cp.number is not None else "") + cp.player.full_name,
            }
            for cp in players
        ]
        for tid, players in team_players.items()
    }
    return {
        "game": game,
        "team_a": await team_service.get(db, game.team_a_id),
        "team_b": await team_service.get(db, game.team_b_id),
        "team_players": team_players,
        "roster_json": roster_json,
        "event_rows": event_rows,
        "event_types": [
            (GameEventType.goal.value, "Гол"),
            (GameEventType.shootout_goal.value, "Буллит"),
            (GameEventType.penalty.value, "Штраф"),
            (GameEventType.goalie_change.value, "Вратарь вышел"),
            (GameEventType.empty_net.value, "Пустые ворота"),
        ],
        "existing": existing,
        # {player_id: {goals, assists, penalties}} — только для показа
        "derived": derived,
        "team_stats": team_stats or {},
        "errors": list(errors),
    }


@router.get("/games/{game_id}/protocol")
async def protocol_page(request: Request, game_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    game = await game_service.get_with_protocol(db, game_id)
    if game is None:
        return _redirect("/admin/competitions")
    ctx = await _protocol_context(
        db,
        request,
        game,
        event_rows=_event_rows_from_db(game),
        existing={(ps.player_id, ps.team_id): ps for ps in game.player_stats},
        derived={
            ps.player_id: {
                "goals": ps.goals,
                "assists": ps.assists,
                "penalties": ps.penalties,
            }
            for ps in game.player_stats
        },
        team_stats=_team_stats_rows(game),
    )
    return render(request, "protocol.html", **ctx)


@router.post("/games/{game_id}/protocol")
async def protocol_submit(request: Request, game_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    game = await game_service.get(db, game_id)
    if game is None:
        return _redirect("/admin/competitions")

    form = await request.form()
    events, errors, raw_event_rows = _events_from_form(form)
    lines = _lines_from_form(form)
    team_stats, team_stat_errors = _team_stats_from_form(form, game)
    errors += team_stat_errors

    def _opt_int(name: str) -> int | None:
        value = form.get(name)
        return int(value) if value not in (None, "") else None

    if not errors:
        payload = ProtocolRequest(
            score_team_a=_opt_int("score_team_a"),
            score_team_b=_opt_int("score_team_b"),
            bullet_win_team_id=_opt_int("bullet_win_team_id"),
            stat_lines=lines,
            events=events,
            team_stats=team_stats,
        )
        try:
            await game_service.save_protocol(db, game, payload)
        except ValidationError as exc:
            errors = [str(exc)]

    if errors:
        # get_session коммитит при обычном возврате, поэтому частично записанное
        # надо откатить руками, иначе оно уедет в базу.
        await db.rollback()
        game = await game_service.get_with_protocol(db, game_id)
        ctx = await _protocol_context(
            db,
            request,
            game,
            event_rows=raw_event_rows,
            existing={(line.player_id, line.team_id): line for line in lines},
            derived=game_service._derive_totals(events),
            team_stats={
                ts.team_id: {
                    "shots": str(ts.shots if ts.shots is not None else ""),
                    "shots_on_goal": str(ts.shots_on_goal if ts.shots_on_goal is not None else ""),
                    "faceoffs_won": str(ts.faceoffs_won if ts.faceoffs_won is not None else ""),
                    "conversion_percent": str(
                        ts.conversion_percent if ts.conversion_percent is not None else ""
                    ),
                }
                for ts in team_stats
            },
            errors=errors,
        )
        return render(request, "protocol.html", **ctx)

    return _redirect(f"/admin/competitions/{game.competition_id}")


# --- Главный экран ---
@router.get("/homepage")
async def homepage_page(request: Request, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    blocks = await homepage_service.get_blocks(db)
    comps, _ = await competition_service.list_competitions(db, page=1, size=500)
    # Форма всегда показывает MAX_HOMEPAGE_BLOCKS слотов: заполненные и пустые
    slots = [
        {
            "type": b.type.value,
            "competition_id": b.competition_id,
            "title": b.title or "",
        }
        for b in blocks
    ]
    slots += [{"type": "", "competition_id": None, "title": ""}] * (
        MAX_HOMEPAGE_BLOCKS - len(slots)
    )
    return render(request, "homepage.html", slots=slots, competitions=comps, error=None)


@router.post("/homepage")
async def homepage_submit(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    form = await request.form()

    blocks: list[HomepageBlockIn] = []
    for index in range(1, MAX_HOMEPAGE_BLOCKS + 1):
        block_type = (form.get(f"block-{index}-type") or "").strip()
        competition_id = (form.get(f"block-{index}-competition_id") or "").strip()
        if not block_type or not competition_id:
            continue  # пустой слот — просто пропускаем, дыры в нумерации не страшны
        blocks.append(
            HomepageBlockIn(
                type=HomepageBlockType(block_type),
                competition_id=int(competition_id),
                title=(form.get(f"block-{index}-title") or "").strip() or None,
            )
        )

    try:
        await homepage_service.replace_blocks(db, blocks)
    except ValidationError as exc:
        await db.rollback()
        comps, _ = await competition_service.list_competitions(db, page=1, size=500)
        slots = [
            {"type": b.type.value, "competition_id": b.competition_id, "title": b.title or ""}
            for b in blocks
        ]
        slots += [{"type": "", "competition_id": None, "title": ""}] * (
            MAX_HOMEPAGE_BLOCKS - len(slots)
        )
        return render(
            request, "homepage.html", slots=slots, competitions=comps, error=str(exc)
        )
    return _redirect("/admin/homepage")


# --- Пользователи (только admin) ---
@router.get("/users")
async def users_page(request: Request, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    if not is_admin(request):
        return render(request, "error.html", message="Доступно только администратору")
    users = await user_service.list_users(db)
    return render(request, "users.html", users=users, roles=list(UserRole))


@router.post("/users")
async def users_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(UserRole.manager.value),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    if not is_admin(request):
        return render(request, "error.html", message="Доступно только администратору")
    if not await user_service.get_by_username(db, username):
        await user_service.create(
            db, UserCreate(username=username, password=password, role=UserRole(role))
        )
    return _redirect("/admin/users")


@router.post("/users/{user_id}/delete")
async def users_delete(request: Request, user_id: int, db: AsyncSession = Depends(get_session)):
    if r := _guard(request):
        return r
    if not is_admin(request):
        return render(request, "error.html", message="Доступно только администратору")
    user = await user_service.get(db, user_id)
    if user:
        await user_service.delete(db, user)
    return _redirect("/admin/users")


@router.post("/users/{user_id}/password")
async def users_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    if r := _guard(request):
        return r
    if not is_admin(request):
        return render(request, "error.html", message="Доступно только администратору")
    user = await user_service.get(db, user_id)
    if user:
        await user_service.update(db, user, UserUpdate(password=password))
    return _redirect("/admin/users")
