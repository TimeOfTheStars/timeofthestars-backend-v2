# TIME OF THE STARS — данные для фронтенда

Справочник по читающим ручкам API: что можно получить и как из этого собрать страницы сайта.

Наполнение контента идёт через серверную админку (`/admin`, Jinja2 + HTMX), которая поднимается
вместе с API. **Фронтенду ничего писать не нужно** — здесь только `GET`-ручки.

- **Base URL:** `http://localhost:8002` (dev), ручки под префиксом `/api/v1`
- **Токен не нужен: все `GET`-ручки публичные.** Ни заголовков, ни куки.
- **Файлы (логотипы, фото, сканы):** `GET /media/<filename>` — публичная статика
- **Swagger:** `/docs` · **OpenAPI JSON:** `/openapi.json` (можно генерировать типы автоматически)
- CORS: по умолчанию `*` (переменная `CORS_ORIGINS`)

Составлено по коду ([app/api/v1/](app/api/v1/), [app/schemas/](app/schemas/), [app/services/](app/services/))
и проверено запросами к живому приложению — все примеры ответов ниже фактические.

---

## Содержание

1. [Модель данных на пальцах](#1-модель-данных-на-пальцах)
2. [Общие соглашения](#2-общие-соглашения)
3. [Перечисления (enum)](#3-перечисления-enum)
4. [Экран → какие запросы делать](#4-экран--какие-запросы-делать)
5. [Справочник ручек](#5-справочник-ручек)
6. [TypeScript-типы](#6-typescript-типы)
7. [Подводные камни](#7-подводные-камни-важно)
8. [Чего в API нет](#8-чего-в-api-нет)

---

## 1. Модель данных на пальцах

```
Competition (соревнование: чемпионат ИЛИ турнир — различаются полем type)
├── состав команд         → GET /competitions/{id}/teams
├── заявки игроков        → те же teams (вложенно) + /competitions/{id}/players (со статистикой)
├── матчи                 → GET /competitions/{id}/games
│   └── протокол матча    → GET /games/{id}   (счёт + строки по игрокам)
├── турнирная таблица     → GET /competitions/{id}/standings     (считается на лету)
└── лучшие игроки         → GET /competitions/{id}/best-players  (считается на лету)

Team   ── справочник, GET /teams
Player ── справочник, GET /players (+ /players/{id}/stats — карьера)
```

Ключевое: **никаких хранимых счётчиков нет**. Турнирная таблица и вся статистика игроков
вычисляются SQL-агрегацией из матчей и протоколов при каждом запросе. Единственный источник
истины — `games` + строки протокола. Поэтому:

- нет расхождений между таблицей и матчами;
- **но нет и способа «переопределить» таблицу вручную** — она всегда следствие протоколов;
- заявка игрока в составе (`number`, `contract`) и его статистика — независимые вещи.

---

## 2. Общие соглашения

### Пагинация

Списки **команд, игроков и соревнований** возвращают конверт `Page<T>`:

```json
{ "items": [], "total": 0, "page": 1, "size": 50 }
```

Query: `page` (≥1, по умолчанию 1), `size` (1…200, по умолчанию 50).

Списки **матчей, составов и статистики — простые массивы без пагинации** (они и так в рамках
одного соревнования). Не ищите там `items`.

### Формат ошибок

| Код | Когда | Тело |
|---|---|---|
| 404 | объекта нет | `{"detail": "Команда не найдена"}` |
| 422 | плохой тип параметра (например `?type=xxx`) | `{"detail": [{"type": "...", "loc": ["query", "type"], "msg": "...", "input": "xxx"}]}` |
| 500 | внутренняя ошибка | `{"detail": "Внутренняя ошибка сервера", "code": "internal_error"}` |

> `detail` — **строка** для `404` и **массив объектов** для `422`. Обрабатывайте оба варианта.

Для читающих ручек `401`/`403` не бывает — авторизация не требуется.

### Форматы значений

| Тип | Формат | Пример |
|---|---|---|
| дата | `YYYY-MM-DD` | `"2026-01-05"` |
| время | `HH:MM:SS` | `"19:30:00"` |
| нет значения | `null` (поля не пропадают из JSON) | `"end_date": null` |

`created_at` / `updated_at` есть в БД, но **не отдаются** ни одной ручкой — «дата обновления»
на фронте недоступна.

### Пути без завершающего слэша

Коллекции — это `/api/v1/teams`, а не `/api/v1/teams/`. Со слэшем прилетит
**307 Location: /api/v1/teams**: лишний round-trip, а часть fetch-обёрток теряет на редиректе
параметры. Всегда без слэша.

### Ссылки на файлы — относительные

`logo_url`, `photo_url`, `scan`, а также `url` у медиа — это строки вида `/media/ab12….webp`.
Склеивайте с базовым URL API:

```ts
const mediaUrl = (path: string | null) => (path ? `${API}${path}` : null);
```

Картинки на бэкенде уже приведены к WebP и уменьшены (логотипы ≤512 px, фото игроков ≤700 px,
сканы ≤1800 px) — на фронте досжимать не нужно, но и большего разрешения не будет.

---

## 3. Перечисления (enum)

```ts
type CompetitionType = "championship" | "tournament";
type GameStage       = "matches" | "quarterfinal" | "semifinal" | "final";
type GameStatus      = "scheduled" | "finished";
// ⚠️ значения на русском — они приходят в JSON именно так
type PlayerPosition  = "вратарь" | "защитник" | "нападающий";
```

- `stage: "matches"` = регулярка (**только она идёт в турнирную таблицу**),
  `quarterfinal` / `semifinal` / `final` = плей-офф.
- `status: "finished"` выставляется автоматически, когда у матча заполнены оба счёта.
  Матч без счёта — `scheduled`, для него `score_team_a` / `score_team_b` будут `null`.

Подписи для UI придётся держать у себя — API отдаёт только сырые значения:

```ts
const STAGE_LABEL: Record<GameStage, string> = {
  matches: "Регулярный сезон",
  quarterfinal: "1/4 финала",
  semifinal: "1/2 финала",
  final: "Финал",
};
```

---

## 4. Экран → какие запросы делать

### Главная

```
GET /api/v1/homepage
```

```json
{ "show_bracket": false, "bracket_competition_id": null,
  "show_standings": false, "standings_competition_id": null }
```

Это переключатели из админки — какие блоки показывать и по какому соревнованию:

```ts
const hp = await get<Homepage>("/api/v1/homepage");

if (hp.show_standings && hp.standings_competition_id) {
  const standings = await get<StandingRow[]>(
    `/api/v1/competitions/${hp.standings_competition_id}/standings`);
}
if (hp.show_bracket && hp.bracket_competition_id) {
  const games = await get<Game[]>(
    `/api/v1/competitions/${hp.bracket_competition_id}/games`);
  const bracket = games.filter(g => g.stage !== "matches");
}
```

Проверяйте **и флаг, и id** — флаг может быть `true` при `null` в id (админка это допускает).
Название соревнования для заголовка блока — отдельным `GET /api/v1/competitions/{id}`.

### Список соревнований

```
GET /api/v1/competitions?type=championship&page=1&size=50
```

`type` опционален. Отсортировано сервером: `start_date` ↓, затем `id` ↓ — сначала свежие,
дополнительная сортировка не нужна. Поиска по названию здесь нет.

### Страница соревнования

Четыре независимых запроса, можно параллельно:

```ts
const [comp, standings, players, games] = await Promise.all([
  get<Competition>(`/api/v1/competitions/${id}`),
  get<StandingRow[]>(`/api/v1/competitions/${id}/standings`),
  get<CompetitionPlayerWithStats[]>(`/api/v1/competitions/${id}/players`),
  get<Game[]>(`/api/v1/competitions/${id}/games`),
]);
```

Что рисовать, подсказывают флаги самого соревнования:

| Флаг | Блок | Запрос |
|---|---|---|
| `show_best_players` | «Лучшие игроки» | `GET /competitions/{id}/best-players?limit=10` |
| `show_playoff_bracket` | Сетка плей-офф | из `games`, где `stage !== "matches"` |
| `winner_team_id` | Плашка «Победитель» | id из `comp`, название — из справочника команд |

**Календарь / результаты** — из `games`, уже отсортированных по дате → времени → id:

```ts
const played   = games.filter(g => g.status === "finished");
const upcoming = games.filter(g => g.status === "scheduled");
```

**Состав по командам** — сгруппируйте `players` по `team_id` (сервер уже отдал их в порядке
`team_id`, затем `number`); эта же ручка содержит статистику каждого игрока в этом соревновании.
Если статистика не нужна, а нужны только заявки с объектами команд — `GET /competitions/{id}/teams`.

### Страница команды

Отдельной ручки «всё о команде» нет, собирается из двух:

```ts
const [team, games] = await Promise.all([
  get<Team>(`/api/v1/teams/${teamId}`),
  get<Game[]>(`/api/v1/games?team_id=${teamId}`),   // все матчи, где команда — любая из сторон
]);
// в каких соревнованиях играет — вывести из матчей:
const competitionIds = [...new Set(games.map(g => g.competition_id))];
```

Состав команды существует только в контексте соревнования — берите из
`GET /competitions/{competitionId}/players` и фильтруйте по `team_id`.

### Страница игрока

```ts
const [player, stats, games] = await Promise.all([
  get<Player>(`/api/v1/players/${playerId}`),
  get<PlayerStatsBreakdown>(`/api/v1/players/${playerId}/stats`),
  get<Game[]>(`/api/v1/players/${playerId}/games`),
]);
```

`stats` сразу даёт всё для карточки: `career` (итоги за карьеру), `by_competition`
(разбивка по соревнованиям, с названиями) и `by_team` (по командам, с названиями) —
дополнительные запросы за названиями не нужны.

`games` — матчи, где у игрока **есть строка протокола** (не все матчи его команды).

Игровой номер игрока хранится в заявке, не в самом игроке: `GET /competitions/{id}/players` → `number`.

### Страница матча

```
GET /api/v1/games/{id}
```

Один запрос отдаёт матч **вместе с протоколом** (`player_stats`) и **таймлайном** (`events`),
причём в каждой строке и в каждом событии вложен объект `player` — за именами игроков ходить
не надо. Названия команд придётся подставить из справочника (см. следующий пункт).

### Справочник команд — заведите один раз

Объекты матчей не содержат названий команд — только `team_a_id` / `team_b_id`.
Загрузите справочник один раз и держите в стейте:

```ts
const { items } = await get<Page<Team>>("/api/v1/teams?size=200");
const teamById = new Map(items.map(t => [t.id, t]));
```

(`size` максимум 200. Если команд станет больше — листайте по `total`.)
Исключение: в `standings` объект `team` уже вложен целиком.

---

## 5. Справочник ручек

Все перечисленные ручки — `GET`, публичные, без заголовков.

### Соревнования

| Путь | Query | Ответ |
|---|---|---|
| `/api/v1/competitions` | `type`, `page`, `size` | `Page<Competition>` |
| `/api/v1/competitions/{id}` | — | `Competition` · `404` |
| `/api/v1/competitions/{id}/teams` | — | `RosterTeam[]` |
| `/api/v1/competitions/{id}/players` | — | `CompetitionPlayerWithStats[]` |
| `/api/v1/competitions/{id}/standings` | — | `StandingRow[]` |
| `/api/v1/competitions/{id}/best-players` | `limit` (1…100, деф. 10) | `BestPlayer[]` |
| `/api/v1/competitions/{id}/games` | — | `Game[]` |

```json
{
  "id": 1, "type": "championship", "name": "Кубок Звёзд 2026",
  "start_date": "2026-01-01", "end_date": "2026-05-30",
  "location": "Москва, ЛД «Арена»", "logo_url": "/media/ef56….webp",
  "show_playoff_bracket": false, "show_best_players": false,
  "winner_team_id": null
}
```

### Турнирная таблица

`GET /api/v1/competitions/{id}/standings`

```json
[
  { "team": { "id": 1, "name": "Сокол", "slug": "sokol", "city": "Москва", "logo_url": null },
    "games": 1, "wins": 1, "losses": 0, "draws": 0,
    "goals_scored": 3, "goals_conceded": 2, "extra_points": 0, "points": 2 }
]
```

Правила ([stats_service.py:25](app/services/stats_service.py#L25)):

- Строки — **только для команд, добавленных в состав** соревнования (в админке).
- Учитываются матчи со `stage == "matches"` **и** обоими заполненными счетами.
  Плей-офф и матчи без счёта в таблицу не попадают.
- Очки: **победа 2**, **ничья 1**, **+1** победителю серии буллитов (`extra_points`).
  То есть ничья с буллитами: победитель 2 очка, проигравший 1.
- **Уже отсортировано:** очки ↓ → разница мячей ↓ → заброшенные ↓.
  Место в таблице = индекс + 1, пересортировывать не нужно.
- Разницу мячей считайте сами: `goals_scored - goals_conceded`.

### Игроки соревнования (состав + статистика)

`GET /api/v1/competitions/{id}/players` — основная ручка для таблицы «состав со статистикой»:

```json
[
  { "player": { "id": 7, "full_name": "Иван Петров", "birth_date": null,
                "position": "нападающий", "grip": null, "photo_url": null },
    "team_id": 1, "number": 9, "contract": true,
    "goals": 2, "assists": 1, "points": 3, "penalties": 0, "games": 1 }
]
```

Возвращаются **все заявленные** игроки, у не игравших — нули. `points` = `goals + assists`.
Порядок: `team_id`, затем `number`. `contract` — признак контракта из заявки.

### Состав соревнования (без статистики)

`GET /api/v1/competitions/{id}/teams` — команды с вложенными заявками:

```json
[
  { "team": { "id": 1, "name": "Сокол", "slug": "sokol", "city": "Москва", "logo_url": null },
    "players": [
      { "player": { "id": 7, "full_name": "Иван Петров", "birth_date": null,
                    "position": "нападающий", "grip": null, "photo_url": null },
        "team_id": 1, "number": 9, "contract": true }
    ] }
]
```

Команда без заявленных игроков придёт с `players: []`.

### Лучшие игроки

`GET /api/v1/competitions/{id}/best-players?limit=10`

```json
[
  { "player": { "id": 7, "full_name": "Иван Петров", "…": "" },
    "team_id": null, "goals": 2, "assists": 1, "points": 3, "penalties": 0 }
]
```

Сортировка по `points` ↓. В отличие от таблицы, учитываются **все** стадии, включая плей-офф.

> ⚠️ `team_id` здесь **всегда `null`** — сервер его не заполняет. Нужна команда игрока —
> ищите его в `GET /competitions/{id}/players`.

### Матчи

| Путь | Query | Ответ |
|---|---|---|
| `/api/v1/games` | `competition_id`, `team_id` | `Game[]` (без протокола) |
| `/api/v1/games/{id}` | — | `GameWithProtocol` · `404` |

Сортировка: дата → время → id. Пагинации нет. `team_id` матчит команду с любой стороны.

```json
{
  "id": 1, "competition_id": 1, "team_a_id": 1, "team_b_id": 3,
  "score_team_a": 3, "score_team_b": 2,
  "date": "2026-01-05", "time": "19:30:00", "location": "ЛД «Арена»",
  "scan": "/media/ab12….pdf", "video_url": "https://youtu.be/…",
  "stage": "matches", "status": "finished", "bullet_win_team_id": null,
  "round_no": null, "bracket_slot": null, "next_game_id": null
}
```

- `bullet_win_team_id` — победитель серии буллитов; осмыслен только при равном счёте.
- `scan` — URL сканa бумажного протокола (PDF или картинка), `video_url` — внешняя ссылка.
- `round_no`, `bracket_slot`, `next_game_id` — служебные поля сетки плей-офф; заполняются
  вручную в админке, **сервер их не валидирует и связи не строит** — могут быть `null`
  даже у плей-офф-матчей.

`GET /api/v1/games/{id}` добавляет протокол:

```json
{
  "id": 1, "…": "все поля Game",
  "player_stats": [
    { "player_id": 7, "team_id": 1, "goals": 2, "assists": 1, "penalties": 2,
      "is_goalie": false, "goals_against": null, "saves": null, "minutes_played": null,
      "player": { "id": 7, "full_name": "Иван Петров", "birth_date": null,
                  "position": "нападающий", "grip": null, "photo_url": null } }
  ],
  "events": [
    { "id": 11, "type": "goalie_change", "team_id": 1, "time_seconds": 0, "period": 1,
      "sort_order": 0, "player_id": 30, "assist1_player_id": null, "assist2_player_id": null,
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": null,
      "player": { "id": 30, "full_name": "Пётр Голкипер", "…": "" },
      "assist1": null, "assist2": null },
    { "id": 12, "type": "goal", "team_id": 1, "time_seconds": 960, "period": 1,
      "sort_order": 1, "player_id": 7, "assist1_player_id": 4, "assist2_player_id": null,
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": 2705,
      "player": { "id": 7, "full_name": "Иван Петров", "…": "" },
      "assist1": { "id": 4, "full_name": "Олег Крайний", "…": "" }, "assist2": null },
    { "id": 13, "type": "penalty", "team_id": 1, "time_seconds": 757, "period": 1,
      "sort_order": 2, "player_id": 7, "assist1_player_id": null, "assist2_player_id": null,
      "penalty_minutes": 2, "penalty_end_seconds": 877, "video_seconds": null,
      "player": { "id": 7, "full_name": "Иван Петров", "…": "" },
      "assist1": null, "assist2": null },
    { "id": 14, "type": "shootout_goal", "team_id": 1, "time_seconds": 3600, "period": null,
      "sort_order": 3, "player_id": 7, "assist1_player_id": null, "assist2_player_id": null,
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": null,
      "player": { "id": 7, "full_name": "Иван Петров", "…": "" },
      "assist1": null, "assist2": null }
  ]
}
```

Разделите `player_stats` по `team_id` — получите box-score по сторонам. Вратарские поля
(`goals_against`, `saves`, `minutes_played`) заполнены только у строк с `is_goalie: true`,
у остальных `null`. `player` теоретически может быть `null` — подстрахуйтесь.
Протокол может быть пустым (`[]`) даже у сыгранного матча со счётом.

**Таймлайн (`events`).** Массив **уже отсортирован сервером**: время → `sort_order` → `id`.

| Поле | Смысл |
|---|---|
| `type` | `goal` · `shootout_goal` · `penalty` · `goalie_change` |
| `time_seconds` | сквозное игровое время от начала матча (`960` = 16:00) |
| `period` | 1–3 по двадцать минут, `4` — овертайм, `null` у буллита. Границы относятся к завершившемуся периоду: 1200 → 1, 3600 → 3 |
| `player_id` | гол — автор, удаление — оштрафованный, смена вратаря — кто **вышел** на лёд |
| `assist1_player_id`, `assist2_player_id` | только у голов |
| `penalty_minutes` | только у удалений, в минутах |
| `penalty_end_seconds` | конец удаления, считает сервер: начало + минуты |
| `video_seconds` | момент в `Game.video_url`, только у голов |

`goals`, `assists` и `penalties` в `player_stats` сервер **считает из `events`** —
вручную их больше не вводят. `penalties` — это минуты штрафа, а не число удалений.

Гол в серии буллитов (`shootout_goal`) в счёт матча **не входит**: сумма событий типа
`goal` по команде равна её `score_team_*`. В личную статистику игрока такой гол идёт,
поэтому «сумма голов игроков больше счёта» при буллитной победе — это норма, а не баг.

**Ссылка на момент в видео.** Бэкенд хранит только секунды, URL собирает фронт:

```ts
// 2705 -> "45m5s"  =>  https://vk.ru/live-227828023_456239234?t=45m5s
export function videoAt(videoUrl: string | null, seconds: number | null): string | null {
  if (!videoUrl || seconds == null) return null;
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  const t = `${h ? `${h}h` : ""}${m ? `${m}m` : ""}${s}s`;
  return `${videoUrl}${videoUrl.includes("?") ? "&" : "?"}t=${t}`;
}
```

Видео одно на матч; если `video_url === null`, кнопку «смотреть» не показываем.

### Сетка плей-офф

Отдельной ручки нет — строится из `GET /competitions/{id}/games`:

```ts
const playoff = games.filter(g => g.stage !== "matches");

// вариант А (надёжный): по стадии
const byStage = {
  quarterfinal: playoff.filter(g => g.stage === "quarterfinal"),
  semifinal:    playoff.filter(g => g.stage === "semifinal"),
  final:        playoff.filter(g => g.stage === "final"),
};

// вариант Б (если админ заполнил поля сетки): по раундам
const byRound = new Map<number, Game[]>();
for (const g of playoff.filter(g => g.round_no != null)) {
  byRound.set(g.round_no!, [...(byRound.get(g.round_no!) ?? []), g]);
}
for (const list of byRound.values()) list.sort((x, y) => (x.bracket_slot ?? 0) - (y.bracket_slot ?? 0));
// связь «кто куда проходит» — через next_game_id
```

Опирайтесь на `stage` как на основу и используйте `round_no` / `bracket_slot` / `next_game_id`
только если они заполнены — гарантий по ним нет.

### Команды

| Путь | Query | Ответ |
|---|---|---|
| `/api/v1/teams` | `page`, `size`, `search` | `Page<Team>` |
| `/api/v1/teams/{id}` | — | `Team` · `404` |

`search` — регистронезависимая подстрока по **названию и городу**. Сортировка по названию.

```json
{ "id": 1, "name": "Сокол", "slug": "sokol", "city": "Москва", "logo_url": "/media/ab12….webp" }
```

`slug` всегда заполнен (генерируется из названия с транслитерацией, уникален) — годится
для человекочитаемых URL, но **все ручки принимают только числовой `id`**, не slug.

### Игроки

| Путь | Query | Ответ |
|---|---|---|
| `/api/v1/players` | `page`, `size`, `search` | `Page<Player>` |
| `/api/v1/players/{id}` | — | `Player` · `404` |
| `/api/v1/players/{id}/stats` | `competition_id`, `team_id` | `PlayerStatsBreakdown` · `404` |
| `/api/v1/players/{id}/games` | — | `Game[]` |

`search` — подстрока по ФИО. Сортировка по ФИО.

```json
{ "id": 7, "full_name": "Иван Петров", "birth_date": "2000-05-01",
  "position": "нападающий", "grip": "левый", "photo_url": "/media/cd34….webp" }
```

`grip` (хват) — свободная строка, не enum. Возраст считайте из `birth_date` сами.

### Статистика игрока

`GET /api/v1/players/{id}/stats`

```json
{
  "player_id": 7,
  "career": { "games": 12, "goals": 8, "assists": 5, "points": 13, "penalties": 4,
              "goals_against": 0, "saves": 0, "minutes_played": 0 },
  "by_competition": [
    { "competition_id": 1, "competition_name": "Кубок Звёзд 2026",
      "totals": { "…": "те же поля" } }
  ],
  "by_team": [
    { "team_id": 1, "team_name": "Сокол", "totals": { "…": "те же поля" } }
  ]
}
```

- `points` = `goals + assists`; вратарские поля у не-вратарей всегда `0`.
- `games` = число матчей, где игрок есть в протоколе.
- Учитываются **все** стадии всех соревнований.
- ⚠️ Query-фильтры `competition_id` / `team_id` меняют **только `career`**;
  `by_competition` и `by_team` всегда по всей карьере. Для «статистики в этом соревновании»
  достаточно взять нужный элемент `by_competition` — лишний запрос не нужен.

### Служебные

| Путь | Ответ |
|---|---|
| `/api/v1/homepage` | `Homepage` (создаётся при первом обращении, `404` не бывает) |
| `/media/{filename}` | сам файл |
| `/health` | `{"status": "ok"}` |
| `/` | `{"service": "Time Of The Stars API", "version": "2.0.0", "docs": "/docs"}` |

---

## 6. TypeScript-типы

Только читающая часть — соответствует ответам один в один.

```ts
// ---------- enums ----------
export type CompetitionType = "championship" | "tournament";
export type GameStage       = "matches" | "quarterfinal" | "semifinal" | "final";
export type GameStatus      = "scheduled" | "finished";
export type PlayerPosition  = "вратарь" | "защитник" | "нападающий";

// ---------- общее ----------
export interface Page<T> { items: T[]; total: number; page: number; size: number }

/** detail — строка для 404, массив для 422 */
export interface ApiError {
  detail: string | { type: string; loc: (string | number)[]; msg: string; input?: unknown }[];
  code?: string;
}

// ---------- справочники ----------
export interface Team {
  id: number; name: string; slug: string;
  city: string | null;
  logo_url: string | null;        // относительный: /media/…
}

export interface Player {
  id: number; full_name: string;
  birth_date: string | null;      // YYYY-MM-DD
  position: PlayerPosition | null;
  grip: string | null;            // хват, свободная строка
  photo_url: string | null;       // относительный: /media/…
}

// ---------- соревнования ----------
export interface Competition {
  id: number; type: CompetitionType; name: string;
  start_date: string; end_date: string | null;
  location: string | null; logo_url: string | null;
  show_playoff_bracket: boolean;  // показывать сетку
  show_best_players: boolean;     // показывать блок лучших
  winner_team_id: number | null;
}

/** заявка игрока в соревновании */
export interface RosterPlayer {
  player: Player;
  team_id: number;
  number: number | null;          // игровой номер
  contract: boolean;
}
export interface RosterTeam { team: Team; players: RosterPlayer[] }

/** заявка + статистика игрока в этом соревновании */
export interface CompetitionPlayerWithStats extends RosterPlayer {
  goals: number; assists: number; points: number; penalties: number; games: number;
}

// ---------- статистика ----------
export interface StandingRow {
  team: Team;                     // объект команды вложен целиком
  games: number; wins: number; losses: number; draws: number;
  goals_scored: number; goals_conceded: number;
  extra_points: number;           // очки за победу по буллитам
  points: number;                 // wins*2 + draws*1 + extra_points
}

export interface PlayerStatTotals {
  games: number; goals: number; assists: number; points: number; penalties: number;
  goals_against: number; saves: number; minutes_played: number;   // вратарские
}
export interface PlayerStatsBreakdown {
  player_id: number;
  career: PlayerStatTotals;
  by_competition: { competition_id: number; competition_name: string; totals: PlayerStatTotals }[];
  by_team: { team_id: number; team_name: string; totals: PlayerStatTotals }[];
}

export interface BestPlayer {
  player: Player;
  team_id: number | null;         // ⚠️ сервер всегда отдаёт null
  goals: number; assists: number; points: number; penalties: number;
}

// ---------- матчи ----------
export interface Game {
  id: number; competition_id: number;
  team_a_id: number; team_b_id: number;          // названий команд нет — нужен справочник
  score_team_a: number | null; score_team_b: number | null;
  date: string;                                  // YYYY-MM-DD
  time: string | null;                           // HH:MM:SS
  location: string | null;
  scan: string | null;                           // URL сканa протокола
  video_url: string | null;                      // внешняя ссылка
  stage: GameStage; status: GameStatus;
  bullet_win_team_id: number | null;             // осмыслен только при ничьей
  round_no: number | null;                       // поля сетки плей-офф,
  bracket_slot: number | null;                   // заполняются вручную,
  next_game_id: number | null;                   // могут быть null
}

/** строка протокола */
export interface PlayerStatLine {
  player_id: number; team_id: number;
  goals: number; assists: number; penalties: number;  // считает сервер из events; penalties = МИНУТЫ
  is_goalie: boolean;
  goals_against: number | null;                  // заполнены только у вратарей
  saves: number | null;
  minutes_played: number | null;
  player: Player | null;
}

export type GameEventType = "goal" | "shootout_goal" | "penalty" | "goalie_change";

/** событие таймлайна; массив приходит уже отсортированным */
export interface GameEvent {
  id: number;
  type: GameEventType;
  team_id: number;
  time_seconds: number;              // сквозное игровое время от начала матча
  period: number | null;             // 1–3, 4 = овертайм, null у shootout_goal
  sort_order: number;                // разводит события с одинаковым временем
  player_id: number;                 // автор гола / оштрафованный / вышедший вратарь
  assist1_player_id: number | null;
  assist2_player_id: number | null;
  penalty_minutes: number | null;    // только penalty
  penalty_end_seconds: number | null; // только penalty, считает сервер
  video_seconds: number | null;      // только голы; смещение в Game.video_url
  player: Player | null;
  assist1: Player | null;
  assist2: Player | null;
}

export interface GameWithProtocol extends Game {
  player_stats: PlayerStatLine[];
  events: GameEvent[];
}

// ---------- главная ----------
export interface Homepage {
  show_bracket: boolean;   bracket_competition_id: number | null;
  show_standings: boolean; standings_competition_id: number | null;
}
```

Минимальный клиент:

```ts
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

export async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);          // без слэша на конце!
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null;
    const msg = typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const mediaUrl = (p: string | null) => (p ? `${API}${p}` : null);
```

---

## 7. Подводные камни (важно)

1. **Названий команд в матчах нет** — только `team_a_id` / `team_b_id`. Держите справочник
   `GET /api/v1/teams?size=200` в стейте. В `standings` объект `team` вложен целиком.
2. **Никаких завершающих слэшей** — `/api/v1/teams/` отдаст `307` на `/api/v1/teams`.
3. **Все `*_url` относительные** (`/media/…`) — склеивайте с базовым URL API.
4. **Турнирная таблица — только регулярка** (`stage: "matches"`) и только матчи с обоими
   заполненными счетами. Плей-офф в ней не участвует, а `best-players` — наоборот,
   считает все стадии. Числа в двух блоках закономерно не сходятся, это не баг.
5. **Таблица может быть пустой при наличии матчей** — строки создаются только для команд,
   добавленных в состав соревнования. Если в админке команду не заявили, её в таблице
   не будет даже при сыгранных матчах.
6. **Таблица уже отсортирована сервером** (очки → разница → заброшенные). Место = индекс + 1.
   Своя сортировка сломает согласованность с админкой.
7. **`BestPlayer.team_id` всегда `null`** — команду ищите в `GET /competitions/{id}/players`.
8. **Фильтры `/players/{id}/stats`** влияют только на `career`; `by_competition` / `by_team`
   всегда по всей карьере. Разбивку по соревнованию берите из `by_competition` без доп. запроса.
9. **`/players/{id}/games` — матчи с протоколом игрока**, а не все матчи его команды.
   Игрок в заявке, но не выпущенный на лёд, здесь не появится.
10. **`GET /games` не отдаёт протокол** — он только в `GET /games/{id}`.
11. **Протокол может быть пустым** даже у матча со счётом, а `player` в строке — теоретически
    `null`. Не считайте `player_stats` гарантированно непустым.
12. **Игровой номер живёт в заявке, а не в игроке** — `number` есть только в
    `/competitions/{id}/players` и `/competitions/{id}/teams`. Один игрок в разных
    соревнованиях может иметь разные номера.
13. **Поля сетки (`round_no`, `bracket_slot`, `next_game_id`) не гарантированы** — заполняются
    руками в админке и не валидируются. Стройте сетку от `stage`, а эти поля используйте
    как уточнение, если они есть.
14. **Флаг главной может быть `true` при `null` в id** — проверяйте оба условия.
15. **`PlayerPosition` — русские строки** (`"вратарь"`, `"защитник"`, `"нападающий"`), не латиница.
16. **Матчи, составы и статистика — массивы без `items`**; `Page<T>` только у команд,
    игроков и соревнований (`size` максимум 200).
17. **`slug` есть только у команды** и в API нигде не принимается — все ручки только по `id`.
    Для красивых URL используйте схему `/teams/{slug}-{id}` и запрашивайте по `id`.
18. **`created_at` / `updated_at` не отдаются** — «обновлено N минут назад» показать нечем.
19. **`events` — источник истины по голам, передачам и штрафу.** Числа в `player_stats`
    сервер считает из таймлайна; расходиться они не могут. У матчей, внесённых до появления
    таймлайна, `events` пустой, а числа остались от прежнего ручного ввода.
20. **`penalties` и `penalty_minutes` — это МИНУТЫ**, а не количество удалений. Два
    двухминутных дают `4`.
21. **`shootout_goal` не входит в счёт матча.** `count(events, type="goal", team_id=X)`
    равно `score_team_X`, а буллит учтён отдельно через `bullet_win_team_id`. В личных
    голах игрока буллит есть — поэтому сумма голов игроков может быть больше счёта.
22. **`events` уже отсортирован сервером** (время → `sort_order` → `id`). Своя сортировка
    по одному `time_seconds` перемешает события одной секунды.
23. **`period` — производное поле**, сервер его не хранит и вычисляет из `time_seconds`.
    Ровные границы относятся к завершившемуся периоду: 20:00 — конец первого, 60:00 — конец
    третьего. У буллита `period: null`.
24. **`goalie_change.player_id` — тот, кто вышел** на лёд, а не тот, кого заменили. Кто
    ушёл, выводится из предыдущей смены той же команды.
19. **Соревнований может быть много страниц** — у `/competitions` нет поиска по названию,
    только фильтр `type` и пагинация.
20. **Всё считается на лету** — кешировать `standings` и статистику на фронте можно смело,
    но помните, что после правки протокола в админке цифры меняются сразу, без инвалидации.

---

## 8. Чего в API нет

Чтобы не искать. Если что-то из этого нужно — это доработка бэкенда, скажите.

| Нет | Обходной путь |
|---|---|
| Поиска по названию соревнования | только фильтр `type` + пагинация |
| Ручки «соревнования команды» | вывести из `GET /games?team_id=X` → `competition_id` |
| Ручки «текущий состав команды» вне соревнования | `GET /competitions/{id}/players` + фильтр по `team_id` |
| Готовой сетки плей-офф | собрать из `games` по `stage` / `round_no` |
| Сводной статистики игрока по стадиям (регулярка vs плей-офф) | нет — `stats` не разделяет стадии |
| Общего лидерборда по всем соревнованиям | `best-players` только в рамках одного |
| Личных встреч (head-to-head) | отфильтровать `GET /games?team_id=X` по второй команде |
| Доступа по `slug` | только по числовому `id` |
| `created_at` / `updated_at` в ответах | — |
| Вебхуков / SSE / long-polling | обычный polling |
| Списка загруженных медиа | ссылки приходят внутри объектов |
