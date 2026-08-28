from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    manager = "manager"


class PlayerPosition(StrEnum):
    goalie = "вратарь"
    defender = "защитник"
    forward = "нападающий"


class CompetitionType(StrEnum):
    championship = "championship"
    tournament = "tournament"


class GameStage(StrEnum):
    matches = "matches"          # регулярка — участвует в турнирной таблице
    quarterfinal = "quarterfinal"
    semifinal = "semifinal"
    final = "final"


class GameStatus(StrEnum):
    scheduled = "scheduled"
    finished = "finished"


class GameEventType(StrEnum):
    """Событие матча для таймлайна."""

    goal = "goal"
    # Гол в серии буллитов: в счёт основного времени не входит, но в личную
    # статистику игрока идёт. Отдельный тип нужен, чтобы сумма голевых событий
    # не противоречила score_team_a/score_team_b.
    shootout_goal = "shootout_goal"
    penalty = "penalty"
    goalie_change = "goalie_change"
    # Вратарь снят с площадки. player_id — тот, кто УШЁЛ (в goalie_change,
    # наоборот, тот, кто вышел). Хранится как обычное событие со временем.
    empty_net = "empty_net"


class HomepageBlockType(StrEnum):
    """Что показывает блок главной: турнирную таблицу или сетку плей-офф."""

    standings = "standings"
    bracket = "bracket"


class MediaKind(StrEnum):
    player_photo = "player_photo"
    team_logo = "team_logo"
    competition_logo = "competition_logo"
    game_scan = "game_scan"
    other = "other"
