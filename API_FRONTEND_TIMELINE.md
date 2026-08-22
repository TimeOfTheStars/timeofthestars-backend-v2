# TIME OF THE STARS — таймлайн матча (дополнение к API_FRONTEND.md)

Этот документ — **только про то, что появилось после `API_FRONTEND.md`**. Всё, что описано в
той спецификации, уже реализовано и не менялось: ручки, пагинация, форматы, ошибки, ссылки на
медиа, турнирная таблица, статистика игроков — всё осталось как было. Читать её заново не нужно.

Изменение ровно одно: **`GET /api/v1/games/{id}` теперь отдаёт хронологию матча** — голы,
удаления и смены вратаря, каждое со временем по игровому секундомеру, а у голов ещё и момент
в видеозаписи. Всё остальное в этом ответе прежнее.

Токен не нужен, ручка публичная, как и все читающие.

---

## 1. Что именно добавилось

В ответе `GET /api/v1/games/{id}` появился массив `events`. Больше нигде ничего не изменилось:
`GET /api/v1/games` (список) по-прежнему отдаёт матчи **без** протокола и без хронологии.

```
GET /api/v1/games/{id}
  → { ...все прежние поля Game..., player_stats: [...], events: [...] }   ← events новый
```

**Массив уже отсортирован сервером**: время → `sort_order` → `id`. Своя сортировка только по
`time_seconds` перемешает события, случившиеся в одну и ту же секунду — сортировать не надо.

---

## 2. Поля события

| Поле | Тип | Смысл |
|---|---|---|
| `id` | `number` | идентификатор события |
| `type` | `"goal" \| "shootout_goal" \| "penalty" \| "goalie_change" \| "empty_net"` | вид события |
| `team_id` | `number` | команда, к которой относится событие |
| `time_seconds` | `number` | **сквозное** игровое время от начала матча: `960` = 16:00, `3600` = 60:00 |
| `period` | `number \| null` | 1–3 по двадцать минут, `4` — овертайм, **`null` у `shootout_goal`** |
| `sort_order` | `number` | разводит события с одинаковым временем; для сортировки уже применён |
| `player_id` | `number` | гол — автор, удаление — оштрафованный, `goalie_change` — **кто вышел** на лёд, `empty_net` — **кто ушёл** |
| `player` | `Player \| null` | тот же игрок объектом, с именем и фото — за именами ходить не надо |
| `assist1_player_id`, `assist2_player_id` | `number \| null` | только у голов |
| `assist1`, `assist2` | `Player \| null` | ассистенты объектами |
| `penalty_minutes` | `number \| null` | только у удалений, **в минутах** |
| `penalty_end_seconds` | `number \| null` | конец удаления, считает сервер: начало + минуты |
| `video_seconds` | `number \| null` | момент в `Game.video_url`, только у голов |

Вложенный `Player` — тот же объект, что и везде в API: `{ id, full_name, birth_date, position,
grip, photo_url }`. Теоретически может быть `null`, подстрахуйтесь.

### Границы периодов

Ровное время относится к **завершившемуся** периоду: `1200` (20:00) → период 1, `3600` (60:00)
→ период 3. Это сделано специально, чтобы гол на последней секунде не уезжал в следующий
период. Побочный эффект: смена вратаря ровно в 20:00 попадёт в конец первого периода, хотя по
смыслу это начало второго — на таймлайне позиция та же, отдельно обрабатывать не нужно.

---

## 3. TypeScript-типы

Дописать к типам из `API_FRONTEND.md`. `Game` и `PlayerStatLine` не изменились, кроме
комментария про производные цифры.

```ts
export type GameEventType =
  | "goal"
  | "shootout_goal"
  | "penalty"
  | "goalie_change"   // вратарь вышел на лёд
  | "empty_net";      // вратаря сняли, пустые ворота

export interface GameEvent {
  id: number;
  type: GameEventType;
  team_id: number;
  time_seconds: number;               // сквозное игровое время от начала матча
  period: number | null;              // 1–3, 4 = овертайм, null у shootout_goal
  sort_order: number;                 // сортировка уже применена сервером
  player_id: number;                  // автор гола / оштрафованный / вышедший или ушедший вратарь
  player: Player | null;
  assist1_player_id: number | null;
  assist2_player_id: number | null;
  assist1: Player | null;
  assist2: Player | null;
  penalty_minutes: number | null;     // только penalty, в минутах
  penalty_end_seconds: number | null; // только penalty, считает сервер
  video_seconds: number | null;       // только голы; смещение в Game.video_url
}

export interface GameWithProtocol extends Game {
  player_stats: PlayerStatLine[];
  events: GameEvent[];                // ← новое, уже отсортировано
}
```

---

## 4. Реальный пример

Это фактический ответ боевого сервера по матчу 18.08.2026 (Ярославич — Зубр, `team_a_id: 4`,
`team_b_id: 2`, `competition_id: 2`), сокращённый до четырёх событий из шестнадцати.

```json
{
  "id": 1,
  "competition_id": 2,
  "team_a_id": 4,
  "team_b_id": 2,
  "score_team_a": 4,
  "score_team_b": 4,
  "bullet_win_team_id": 4,
  "date": "2026-08-18",
  "time": "20:00:00",
  "status": "finished",
  "stage": "matches",
  "video_url": "https://vkvideo.ru/live-227828023_456239234",
  "player_stats": [ "…39 строк, форма не менялась…" ],
  "events": [
    {
      "id": 17, "type": "goalie_change", "team_id": 4,
      "time_seconds": 0, "period": 1, "sort_order": 0,
      "player_id": 517,
      "player": { "id": 517, "full_name": "Малых Арсений", "birth_date": null,
                  "position": "вратарь", "grip": null, "photo_url": null },
      "assist1_player_id": null, "assist2_player_id": null,
      "assist1": null, "assist2": null,
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": null
    },
    {
      "id": 19, "type": "goal", "team_id": 2,
      "time_seconds": 30, "period": 1, "sort_order": 2,
      "player_id": 96,
      "player": { "id": 96, "full_name": "Сорокин Артем", "birth_date": null,
                  "position": "нападающий", "grip": null,
                  "photo_url": "/media/a90d7cd6e977281a4a9f1ce79af632a9.webp" },
      "assist1_player_id": 95, "assist2_player_id": 87,
      "assist1": { "id": 95, "full_name": "Ардашев Кирилл", "…": "" },
      "assist2": { "id": 87, "full_name": "Пасынков Александр", "…": "" },
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": null
    },
    {
      "id": 22, "type": "penalty", "team_id": 4,
      "time_seconds": 757, "period": 1, "sort_order": 5,
      "player_id": 9,
      "player": { "id": 9, "full_name": "Клёмин Владимир", "…": "" },
      "assist1_player_id": null, "assist2_player_id": null,
      "assist1": null, "assist2": null,
      "penalty_minutes": 2, "penalty_end_seconds": 877, "video_seconds": null
    },
    {
      "id": 32, "type": "shootout_goal", "team_id": 4,
      "time_seconds": 3600, "period": null, "sort_order": 15,
      "player_id": 522,
      "player": { "id": 522, "full_name": "Бондарь Дмитрий", "…": "" },
      "assist1_player_id": null, "assist2_player_id": null,
      "assist1": null, "assist2": null,
      "penalty_minutes": null, "penalty_end_seconds": null, "video_seconds": null
    }
  ]
}
```

Состав этого матча по типам: 8 голов, 4 удаления, 3 смены вратаря, 1 буллит. По периодам:
8 событий в первом, 4 во втором, 3 в третьем, 1 без периода (буллит).

Посмотреть целиком:

```bash
curl -s https://api.timeofthestars.ru/api/v1/games/1 | jq '.events'
```

---

## 5. Рецепты

Все сниппеты ниже прогнаны на фактическом ответе боевого сервера по матчу `id: 1`.

### Время в человеческий вид

Секунды сквозные, часовой формы нет — конец третьего периода это `60:00`, а не `1:00:00`.

```ts
export const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
// 30 -> "0:30"   757 -> "12:37"   3600 -> "60:00"
```

### Ссылка на момент в видео

Бэкенд хранит только смещение в секундах, ссылку собирает фронт. У матча одно видео —
`Game.video_url`.

```ts
export function videoAt(videoUrl: string | null, seconds: number | null): string | null {
  if (!videoUrl || seconds == null) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const t = `${h ? `${h}h` : ""}${m ? `${m}m` : ""}${s}s`;
  return `${videoUrl}${videoUrl.includes("?") ? "&" : "?"}t=${t}`;
}
// videoAt("https://vkvideo.ru/live-227828023_456239234", 2705)
//   -> "https://vkvideo.ru/live-227828023_456239234?t=45m5s"
```

Кнопку «смотреть» показывайте только когда `video_url` и `video_seconds` оба непустые.
**Сейчас `video_seconds` у всех голов `null`** — моменты ещё не проставлены в админке, хотя
само видео у матча уже привязано. Верстайте так, чтобы отсутствие таймкода выглядело нормально.

### Группировка по периодам

```ts
const byPeriod = new Map<number | null, GameEvent[]>();
for (const e of game.events) {
  const key = e.period;              // null = серия буллитов, показывайте отдельным блоком
  if (!byPeriod.has(key)) byPeriod.set(key, []);
  byPeriod.get(key)!.push(e);
}
// по матчу 18.08 получится: 1 → 8 событий, 2 → 4, 3 → 3, null → 1
```

Порядок внутри группы уже правильный — массив отсортирован сервером.

### Счёт по ходу матча

Считайте только `type === "goal"`. Буллит в счёт не входит, его показывайте отдельно.

```ts
let a = 0, b = 0;
const withScore = game.events.map((e) => {
  if (e.type === "goal") {
    if (e.team_id === game.team_a_id) a += 1;
    else b += 1;
  }
  return { ...e, scoreA: a, scoreB: b };   // счёт ПОСЛЕ этого события
});
```

По этому матчу так и получится `4 : 4` к концу, а победа по буллитам берётся из
`bullet_win_team_id`.

### Удаление: до какой минуты

```ts
const from = clock(e.time_seconds);
const to = e.penalty_end_seconds != null ? clock(e.penalty_end_seconds) : null;
// "12:37 – 14:37, 2 мин"
```

### Кто в воротах в момент события

`goalie_change.player_id` — тот, кто **вышел**. Кто ушёл, выводится из предыдущей смены этой же
команды. В начале матча приходят две смены с `time_seconds: 0` — по одной на команду.

```ts
// null означает «пустые ворота»: либо до первой смены, либо после empty_net
function goalieAt(events: GameEvent[], teamId: number, at: number): Player | null {
  let current: Player | null = null;
  for (const e of events) {
    if (e.team_id !== teamId) continue;
    if (e.time_seconds > at) break;
    if (e.type === "goalie_change") current = e.player;
    else if (e.type === "empty_net") current = null;
  }
  return current;
}
```

---

## 6. Подводные камни (только новые)

1. **`events` уже отсортирован** сервером: время → `sort_order` → `id`. Сортировка по одному
   `time_seconds` перемешает события одной секунды — в этом матче их две пары.
2. **`shootout_goal` не входит в счёт матча.** Сумма событий `type: "goal"` по команде равна
   её `score_team_*`. Победа в серии — это `bullet_win_team_id`. При этом в личных голах
   игрока буллит **учтён**, поэтому «сумма голов игроков больше счёта» при буллитной победе
   закономерна и багом не является.
3. **`period: null` бывает** — только у `shootout_goal`. Не приводите к числу без проверки.
4. **`penalty_minutes` и `penalties` в протоколе — это МИНУТЫ**, а не количество удалений.
   Два двухминутных дают `4`.
5. **Числа в `player_stats` теперь производные**: `goals`, `assists`, `penalties` сервер
   считает из `events`, расходиться они не могут. Форма ответа не изменилась, пересчитывать
   их на фронте не нужно.
6. **У матчей без хронологии `events` пустой** (`[]`), а числа в `player_stats` при этом могут
   быть заполнены — они остались от прежнего ручного ввода. Пустой таймлайн у сыгранного
   матча со счётом — нормальная ситуация, обработайте её.
7. **`goalie_change.player_id` — вышедший**, а не заменённый. У `empty_net` наоборот — это
   вратарь, которого **сняли** с площадки; следующий `goalie_change` той же команды означает,
   что он (или другой) вернулся в ворота.
8. **`video_seconds` только у голов.** У удалений и смен вратаря он всегда `null`, даже если
   момент в видео существует.
9. **Время сквозное, а не внутри периода.** Гол во втором периоде на 5-й минуте — это
   `time_seconds: 1500`, то есть `25:00`, а не `5:00`. Если хотите показывать время внутри
   периода, вычитайте `(period - 1) * 1200` сами.

---

## 7. Чего в API по-прежнему нет

Чтобы не искать:

- **отдельной ручки событий** — таймлайн приходит только вместе с матчем, `GET /games/{id}`;
- **серии буллитов по попыткам** — хранится только победный гол одним событием
  `shootout_goal`;
- **кодов нарушений и «игровой ситуации»** у удаления — только минуты;
- **ссылки на видео у каждого события** — только смещение в секундах плюс одно
  `Game.video_url` на матч;
- **того, кто ушёл** при обычной смене вратаря — выводится из предыдущей смены (для снятия
  вратаря есть отдельный тип `empty_net`);
- **времени на льду у игроков** — `minutes_played` есть только у вратарей и только суммарно;
- **разбивки счёта по периодам отдельным полем** — считается из событий (см. рецепт выше);
- **зрителей, тренеров, лучших игроков матча** — в схеме этого нет. «Лучшие игроки» есть
  только как расчёт по соревнованию: `GET /api/v1/competitions/{id}/best-players`.

---

## 8. Как проверить

Боевой сервер, единственный сыгранный матч на сегодня — `id: 1` в соревновании
«Летний кубок» (`competition_id: 2`).

```bash
# таймлайн целиком
curl -s https://api.timeofthestars.ru/api/v1/games/1 | jq '.events'

# компактно: время, тип, кто
curl -s https://api.timeofthestars.ru/api/v1/games/1 \
  | jq -r '.events[] | "\(.time_seconds)\t\(.period // "ПБ")\t\(.type)\t\(.player.full_name)"'

# матчи соревнования (без хронологии — она только в /games/{id})
curl -s https://api.timeofthestars.ru/api/v1/competitions/2/games | jq '.[] | {id, date, status}'
```

Остальные пять матчей кубка ещё не сыграны: у них `status: "scheduled"`, пустой `events` и
`score_team_* = null`.
