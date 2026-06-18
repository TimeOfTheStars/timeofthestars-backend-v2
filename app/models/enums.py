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


class MediaKind(StrEnum):
    player_photo = "player_photo"
    team_logo = "team_logo"
    competition_logo = "competition_logo"
    game_scan = "game_scan"
    other = "other"
