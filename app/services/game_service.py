from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Game, GameEvent, GamePlayerStat, GameTeamStat
from app.models.enums import GameEventType, GameStatus
from app.models.game import MAX_EVENT_SECONDS
from app.schemas.game import GameCreate, GameUpdate, PlayerGoalMoment, ProtocolRequest
from app.services.clock import video_url_at
from app.services.competition_service import ValidationError


def _maybe_finish(game: Game) -> None:
    """Игра считается сыгранной, как только проставлен счёт обеих команд."""
    if game.score_team_a is not None and game.score_team_b is not None:
        game.status = GameStatus.finished


async def list_games(
    db: AsyncSession, *, competition_id: int | None = None, team_id: int | None = None
) -> Sequence[Game]:
    q = select(Game)
    if competition_id is not None:
        q = q.where(Game.competition_id == competition_id)
    if team_id is not None:
        q = q.where((Game.team_a_id == team_id) | (Game.team_b_id == team_id))
    q = q.order_by(Game.date, Game.time, Game.id)
    return (await db.execute(q)).scalars().all()


async def get(db: AsyncSession, game_id: int) -> Game | None:
    return await db.get(Game, game_id)


async def games_for_player(db: AsyncSession, player_id: int) -> Sequence[Game]:
    res = await db.execute(
        select(Game)
        .join(GamePlayerStat, GamePlayerStat.game_id == Game.id)
        .where(GamePlayerStat.player_id == player_id)
        .order_by(Game.date, Game.time)
    )
    return res.scalars().unique().all()


async def get_with_protocol(db: AsyncSession, game_id: int) -> Game | None:
    res = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.player_stats).selectinload(GamePlayerStat.player),
            selectinload(Game.events).selectinload(GameEvent.player),
            selectinload(Game.events).selectinload(GameEvent.assist1),
            selectinload(Game.events).selectinload(GameEvent.assist2),
            selectinload(Game.team_stats),
        )
    )
    return res.scalar_one_or_none()


async def create(db: AsyncSession, data: GameCreate) -> Game:
    game = Game(**data.model_dump())
    _maybe_finish(game)
    db.add(game)
    await db.flush()
    return game


async def update(db: AsyncSession, game: Game, data: GameUpdate) -> Game:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(game, key, value)
    _maybe_finish(game)
    await db.flush()
    return game


async def delete(db: AsyncSession, game: Game) -> None:
    await db.delete(game)
    await db.flush()


# Верхняя граница игрового времени берётся из модели
GOAL_TYPES = frozenset({GameEventType.goal, GameEventType.shootout_goal})
# У обоих событий player_id — вратарь: в goalie_change тот, кто вышел,
# в empty_net тот, кто ушёл с площадки.
GOALIE_TYPES = frozenset({GameEventType.goalie_change, GameEventType.empty_net})


def _goal_moment(ev: GameEvent) -> PlayerGoalMoment:
    """Событие + матч -> запись для карточки игрока, со стороны его команды."""
    game = ev.game
    home = ev.team_id == game.team_a_id
    opponent = game.team_b if home else game.team_a
    return PlayerGoalMoment(
        event_id=ev.id,
        game_id=game.id,
        type=ev.type,
        period=ev.period,
        time_seconds=ev.time_seconds,
        video_seconds=ev.video_seconds,
        video_url=game.video_url,
        video_at_url=video_url_at(game.video_url, ev.video_seconds),
        date=game.date,
        competition_id=game.competition_id,
        competition_name=game.competition.name,
        team=ev.team,
        opponent=opponent,
        score_for=game.score_team_a if home else game.score_team_b,
        score_against=game.score_team_b if home else game.score_team_a,
        assist1=ev.assist1,
        assist2=ev.assist2,
    )


async def goal_moments_for_player(db: AsyncSession, player_id: int) -> list[PlayerGoalMoment]:
    """Голы игрока, у которых есть и таймкод, и видео матча. Свежие матчи сверху.

    Идём от событий к матчу, а не через строки состава (как games_for_player):
    если игрока потом убрали из протокола, гол в game_events остаётся, и джойн
    через состав молча спрятал бы момент.
    """
    res = await db.execute(
        select(GameEvent)
        .join(Game, Game.id == GameEvent.game_id)
        .where(
            GameEvent.player_id == player_id,
            GameEvent.type.in_(GOAL_TYPES),
            GameEvent.video_seconds.isnot(None),
            Game.video_url.isnot(None),
            # через API в video_url можно записать пустую строку — тогда
            # ссылка на момент получилась бы без домена
            Game.video_url != "",
        )
        # Games.time не годится для сортировки: поле nullable, а SQLite и
        # PostgreSQL кладут NULL в DESC по-разному. Порядок внутри матча
        # повторяет связь Game.events — на select(GameEvent) он не применяется.
        .order_by(
            Game.date.desc(),
            Game.id.desc(),
            GameEvent.time_seconds,
            GameEvent.sort_order,
            GameEvent.id,
        )
        .options(
            # без этого ev.game.competition.name уронит запрос с MissingGreenlet
            selectinload(GameEvent.game).selectinload(Game.competition),
            selectinload(GameEvent.game).selectinload(Game.team_a),
            selectinload(GameEvent.game).selectinload(Game.team_b),
            selectinload(GameEvent.team),
            selectinload(GameEvent.assist1),
            selectinload(GameEvent.assist2),
        )
    )
    return [_goal_moment(ev) for ev in res.scalars().all()]



def _derive_totals(events: Iterable) -> dict[int, dict[str, int]]:
    """Голы, передачи и штрафные минуты по игрокам, посчитанные из событий.

    Работает и со схемами GameEventIn, и с ORM-объектами GameEvent — у них
    одинаковые имена полей.
    """
    totals: dict[int, dict[str, int]] = {}

    def bucket(pid: int) -> dict[str, int]:
        return totals.setdefault(pid, {"goals": 0, "assists": 0, "penalties": 0})

    for ev in events:
        if ev.type in GOAL_TYPES:
            # Гол в буллитах в счёт матча не идёт, а в личную статистику — идёт
            bucket(ev.player_id)["goals"] += 1
            for aid in (ev.assist1_player_id, ev.assist2_player_id):
                if aid is not None:
                    bucket(aid)["assists"] += 1
        elif ev.type is GameEventType.penalty:
            bucket(ev.player_id)["penalties"] += ev.penalty_minutes or 0
    return totals


def _validate_events(
    events: Iterable, *, game: Game, participation: dict[int, GamePlayerStat]
) -> None:
    """Проверяет набор событий против состава матча.

    Проверяется весь действующий набор, включая уже лежащие в базе события:
    состав могли переписать и оставить событие без игрока.
    """
    valid_teams = {game.team_a_id, game.team_b_id}

    for idx, ev in enumerate(events, start=1):
        where = f"Событие #{idx} ({ev.type})"

        if ev.team_id not in valid_teams:
            raise ValidationError(f"{where}: команда {ev.team_id} не участвует в этом матче")
        if not 0 <= ev.time_seconds <= MAX_EVENT_SECONDS:
            raise ValidationError(
                f"{where}: время {ev.time_seconds} с вне диапазона 0..{MAX_EVENT_SECONDS}"
            )

        def line_of(pid: int, role: str) -> GamePlayerStat:
            row = participation.get(pid)
            if row is None:
                raise ValidationError(f"{where}: {role} {pid} отсутствует в протоколе матча")
            if row.team_id != ev.team_id:
                raise ValidationError(f"{where}: {role} {pid} заявлен за другую команду")
            return row

        main = line_of(ev.player_id, "игрок")

        if ev.type in GOAL_TYPES:
            if ev.penalty_minutes is not None:
                raise ValidationError(f"{where}: штрафные минуты не относятся к голу")
            if ev.assist2_player_id is not None and ev.assist1_player_id is None:
                raise ValidationError(f"{where}: вторая передача указана без первой")
            assists = [a for a in (ev.assist1_player_id, ev.assist2_player_id) if a is not None]
            if ev.type is GameEventType.shootout_goal and assists:
                raise ValidationError(f"{where}: у гола в буллитах не бывает передач")
            if len(set(assists)) != len(assists):
                raise ValidationError(f"{where}: обе передачи записаны на одного игрока")
            if ev.player_id in assists:
                raise ValidationError(f"{where}: автор гола не может быть своим же ассистентом")
            for aid in assists:
                line_of(aid, "ассистент")
        else:
            if ev.assist1_player_id is not None or ev.assist2_player_id is not None:
                raise ValidationError(f"{where}: передачи бывают только у голов")
            if ev.video_seconds is not None:
                raise ValidationError(f"{where}: момент видео задаётся только для голов")
            if ev.type is GameEventType.penalty:
                if not ev.penalty_minutes:
                    raise ValidationError(f"{where}: укажите штрафные минуты")
            elif ev.type in GOALIE_TYPES:
                if ev.penalty_minutes is not None:
                    raise ValidationError(
                        f"{where}: штрафные минуты не относятся к событиям вратаря"
                    )
                if not main.is_goalie:
                    raise ValidationError(
                        f"{where}: игрок {ev.player_id} не отмечен вратарём в протоколе"
                    )


def team_penalty_minutes(events: Iterable[GameEvent]) -> dict[int, int]:
    """Штрафные минуты по командам — из событий, отдельным полем не хранятся."""
    totals: dict[int, int] = {}
    for ev in events:
        if ev.type is GameEventType.penalty and ev.penalty_minutes:
            totals[ev.team_id] = totals.get(ev.team_id, 0) + ev.penalty_minutes
    return totals


def _validate_team_stats(rows, *, game: Game) -> None:
    valid_teams = {game.team_a_id, game.team_b_id}
    seen: set[int] = set()
    for row in rows:
        if row.team_id not in valid_teams:
            raise ValidationError(f"Команда {row.team_id} не участвует в этом матче")
        if row.team_id in seen:
            raise ValidationError(f"Командные итоги для команды {row.team_id} указаны дважды")
        seen.add(row.team_id)
        if (
            row.shots is not None
            and row.shots_on_goal is not None
            and row.shots_on_goal > row.shots
        ):
            raise ValidationError(
                f"Команда {row.team_id}: бросков в створ ({row.shots_on_goal}) "
                f"больше, чем бросков всего ({row.shots})"
            )


async def save_protocol(db: AsyncSession, game: Game, data: ProtocolRequest) -> Game:
    """Полностью заменяет протокол матча: счёт, состав и таймлайн.

    Голы, передачи и штрафные минуты по игрокам не приходят извне — они
    выводятся из событий. Вратарские цифры остаются ручными.

    data.events == None означает «таймлайн не трогать»: события остаются как
    были, а производные цифры пересчитываются по ним. Пустой список очищает
    таймлайн и обнуляет цифры.
    """
    valid_teams = {game.team_a_id, game.team_b_id}

    seen: set[int] = set()
    for line in data.stat_lines:
        if line.team_id not in valid_teams:
            raise ValidationError(
                f"Игрок {line.player_id}: команда {line.team_id} не участвует в этом матче"
            )
        if line.player_id in seen:
            raise ValidationError(f"Игрок {line.player_id} указан в протоколе дважды")
        seen.add(line.player_id)

    if data.score_team_a is not None:
        game.score_team_a = data.score_team_a
    if data.score_team_b is not None:
        game.score_team_b = data.score_team_b
    if data.bullet_win_team_id is not None:
        game.bullet_win_team_id = data.bullet_win_team_id
    _maybe_finish(game)

    old_lines = (
        await db.execute(select(GamePlayerStat).where(GamePlayerStat.game_id == game.id))
    ).scalars().all()
    old_events = (
        await db.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalars().all()

    replace_events = data.events is not None
    effective_events: list = list(data.events) if replace_events else list(old_events)

    # Сначала удаляем и флашим: uq_game_player не даст вставить новые строки
    # поверх старых.
    for row in old_lines:
        await db.delete(row)
    if replace_events:
        for row in old_events:
            await db.delete(row)
    await db.flush()

    new_lines: dict[int, GamePlayerStat] = {}
    for line in data.stat_lines:
        row = GamePlayerStat(game_id=game.id, **line.model_dump())
        new_lines[line.player_id] = row
        db.add(row)

    _validate_events(effective_events, game=game, participation=new_lines)

    if replace_events:
        # sorted устойчив, поэтому события с одинаковым временем сохраняют
        # порядок присланного массива
        ordered = sorted(data.events, key=lambda e: e.time_seconds)
        for order, ev in enumerate(ordered):
            db.add(GameEvent(game_id=game.id, sort_order=order, **ev.model_dump()))

    totals = _derive_totals(effective_events)
    for pid, row in new_lines.items():
        t = totals.get(pid)
        row.goals = t["goals"] if t else 0
        row.assists = t["assists"] if t else 0
        row.penalties = t["penalties"] if t else 0

    if data.team_stats is not None:
        _validate_team_stats(data.team_stats, game=game)
        old_team_stats = (
            await db.execute(select(GameTeamStat).where(GameTeamStat.game_id == game.id))
        ).scalars().all()
        # Как и со строками участия: сначала удалить и сбросить, иначе uq_game_team
        # не даст вставить новые строки поверх старых.
        for row in old_team_stats:
            await db.delete(row)
        await db.flush()
        for row in data.team_stats:
            db.add(GameTeamStat(game_id=game.id, **row.model_dump()))

    await db.flush()
    return game
