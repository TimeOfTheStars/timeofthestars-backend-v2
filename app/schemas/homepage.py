from pydantic import BaseModel, ConfigDict


class HomepageUpdate(BaseModel):
    show_bracket: bool | None = None
    bracket_competition_id: int | None = None
    show_standings: bool | None = None
    standings_competition_id: int | None = None


class HomepageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    show_bracket: bool
    bracket_competition_id: int | None = None
    show_standings: bool
    standings_competition_id: int | None = None
