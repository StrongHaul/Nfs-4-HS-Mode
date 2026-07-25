# PROD3 Hypercycle Stable Context

Дата фиксации: 2026-06-01.

Этот файл описывает текущую стабильную PROD3-версию мода Hypercycle для DuckStation:

```text
PROD 3 версия. DuckStation. Need for Speed - High Stakes (USA) — Мод Hypercycle
```

## Стабильная версия

Stable point confirmed by user on 2026-07-06 (traffic yield converted to toggle cheat):

```text
NFS4.EXE  D20593943A2C3F25F1EE364DFB3FE014
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

Traffic yield toggle notes:

- Traffic yield-to-non-traffic-units is off by default in `NFS4.EXE`.
- DuckStation traffic-yield cheat / flag `8011F220` toggles the feature:
  - Off restores stock `CheckForCops` / `CopCheck` behavior;
  - On scans all cars and accepts the selected non-traffic candidate, matching the previously stable always-on behavior.
- Local cheat fragment: `PROD3_traffic_yield_toggle.cht`; generator: `patch_prod3_traffic_yield_toggle.py`.


Stable point confirmed by user on 2026-07-05 (player collision mass toggle added):

```text
NFS4.EXE  D56214BFA980EAC29D2346E889AC5025
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

Collision mass toggle notes:

- Player collision mass is off by default in `NFS4.EXE`: `data_801144DC = 0008`.
- DuckStation collision-mass cheat / flag `8011F21C` toggles the mass bit:
  - Off writes `801144DC 0008`;
  - On writes `801144DC 000A`.
- Existing stable mass hook/multiplier is retained; the cheat only controls bit `0x0002`.
- Local cheat fragment: `PROD3_player_collision_mass_toggle.cht`; generator: `patch_prod3_player_collision_mass_toggle.py`.


Stable point confirmed by user on 2026-07-05 (power/speed toggle added; current replay camera experiment accepted as a temporary stable checkpoint):

```text
NFS4.EXE  C5504C22589352A329839FCCD420AD75
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

Current accepted notes:

- Player acceleration/speed/torque is stock by default and is controlled by DuckStation power/speed cheat / flag `8011F218`.
- This cheat only controls power/speed/torque patch points; steering and collision mass are not controlled by it.
- Local cheat fragment: `PROD3_player_power_speed_toggle.cht`; generator: `patch_prod3_player_power_speed_toggle.py`.
- Replay camera work is accepted as a temporary stable checkpoint, but the far camera still may be revisited later.
- Replay camera cheat / `PROD3_replay_chase_cameras_clean_ui.cht` currently switches On replay camera table to `3,4,3,4,3,4,3,4,3` to avoid the more dynamic `HeliCam` mode 6 behavior.
- Near TailCam uses `80081830 2000` when the replay cheat is On.
- Far camera experiments currently leave aggressive HeliCam smoothing lines in the cheat fragment, but the active far replay slots use mode `4`; these lines are retained for now and can be cleaned when the camera pass resumes.


Последняя подтвержденная пользователем стабильная точка:

```text
NFS4.EXE  0CFB1D2302D9042A2D165EC7403DA3C3
FRONT.BIN 5062835E2B00A6F7F96E8B4C5A38AF1C
git       d6f8cad Restore requested stable civilian siren state
```

Stable point confirmed by user on 2026-06-29 (tournament traffic restored; replay camera behavior=1.5; HP starts first try; HP night has 2 traffic cars):

```text
NFS4.EXE  425AEC740D015EA47EDC8AA36B8FFD78
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
Replay chase cameras / clean replay UI, replay camera behavior=1.5, HP night traffic, and Tournament traffic state accepted as stable.
```

Replay notes carried over from the stable point:

- `NFS4.EXE` contains a permanent replay HUD auto-hide hook.
- The hook checks `8011F20C`; in testing the HUD auto-hide works both with the cheat off and on, and this behavior is accepted.
- DuckStation cheat `[My\Replay chase cameras and clean UI]` still uses `8011F20C 000?`.
- `On` switches replay camera table to alternating tuned chase cameras: `3,6,3,6,3,6,3,6,3`.
- `Off` restores stock replay camera table: `19,10,11,8,9,6,4,15,0`.
- The active cheat fragment is `PROD3_replay_chase_cameras_clean_ui.cht`.
- Replay position 5 tuned fixedness uses `behavior=1.5` (`80081830 1800` when the replay cheat is On).

- Tournament traffic is enabled through `ZTOURN*.TRN` data, not through the reverted risky `FRONT.BIN` force-hook.
- Confirmed by user: starting Tournament immediately after boot no longer hangs, and Tournament has 1 traffic car.
- `ZTOURN.TRN  06CC06F5C85FEF4C2F66627F4CBAFCDD`
- `ZTOURNB.TRN A54BBFE9D8E1BC2E9CEB75D73CF615A1`
- `ZTOURNC.TRN FB8C7F80571CB5241DD8A13879234E75`


Проверено пользователем после отката к стабильному EXE `0CFB1D2302D9042A2D165EC7403DA3C3` и старой объединенной схеме DuckStation-чита для мигалок/сирены гражданской машины. Это состояние принято как стабильное.

Состояние на момент фиксации:

- Игра не зависает при старте гонки, загрузке карты и в погоне.
- Фары, поворотники, ночная подсветка мигалок и белые задние огни работают.
- Кастомное моргание световых элементов обычных машин по умолчанию выключено и включается объединенным читом мигалок/сирены.
- Damage-only-visual по умолчанию выключен и включается одним переключаемым читом `0/1`.
- Звук сирены на обычной/неполицейской машине игрока включается тем же объединенным `0/1` читом, что и мигалки.
- Полицейские машины не имеют постоянного некорректного белого свечения задних огней.
- Чит ареста ИИ гонщиков снова работает без видимых проблем.

## Главные файлы

- `PROD 3 версия. DuckStation. Need for Speed - High Stakes (USA) — Мод Hypercycle/NFS4.EXE`
- `PROD 3 версия. DuckStation. Need for Speed - High Stakes (USA) — Мод Hypercycle/FRONT.BIN`
- `patch_prod3_reverse_lights_blink.py`
- `patch_prod3_player_can_bust_ai_racers.py`
- `patch_prod3_player_bust_sr_pullover_hud_guard.py`
- `patch_prod3_player_car_cheat_30114878_sync.py`
- `patch_prod3_police_ai_only_mode_cheat.py`
- `patch_prod3_player_civilian_strobe_lights.py`
- `patch_prod3_player_civilian_blink_cheat_gate.py`
- `patch_prod3_all_cop_siren_night_glow.py`
- `patch_prod3_visual_damage_only.py`
- `patch_prod3_player_civilian_siren_sound.py`

## Игрок

- Машина игрока использует low LOD, как машины ботов.
- Улучшена физика игрока под DuckStation: масса коллизии, ускорение/крутящий момент, управляемость.
- Визуальный поворот колес игрока отключен.
- Добавлена синхронизация чита замены машины игрока `30114878`, чтобы SR/HP не ломали `carData`/mirror setup при замене машины.
- Игрок может арестовывать ИИ гонщиков в HP/SR через чит:

```text
800F7A00 0001
800F7B00 0001
```

Выключение:

```text
800F7A00 0000
800F7B00 0000
```

Технически это не глобально превращает игрока в human cop через `carFlags & 0x200`, потому что такой путь ломал HUD/AI в SR/HP. Вместо этого добавлены отдельные hook'и в кандидатный тест ареста и проверку управления.

## Арест ИИ гонщиков

Итоговая рабочая схема:

- Игрок может завершать арест ИИ гонщика без глобального флага human cop.
- Для SR добавлена защита HUD/pullover пути, чтобы игра не читала мусорный указатель после ареста ИИ.
- Ошибка DuckStation вида `Invalid word read ... pc 0x80062DDC` была устранена guard'ом в `patch_prod3_player_bust_sr_pullover_hud_guard.py`.
- Более ранние попытки guard'ов `no-cops bypass` и `assigned target` были экспериментальными и не считаются основной стабильной причиной фикса.

Важные cave/адреса текущей схемы:

```text
0x800F7A00  candidate cave / внешний чит ареста
0x800F7B00  controls cave / внешний чит ареста
0x800F7A44  SR pullover HUD guard
0x800F7B50  reverse-light object cave
0x800F7D00  player car cheat sync cave
```

Важно: reverse-light object cave специально перенесен с `0x800F7A40/0x800F7A44` и `0x800F7B00`-области, потому что старое размещение попадало рядом с delay slot/читовыми cave ареста и вызывало зависания.

## Полиция

Чит поведения полиции:

```text
800F7980 0001
800F7900 0001
```

Режим `0001`: копы преследуют только ИИ гонщиков.

```text
800F7980 0000
800F7900 0000
```

Режим `0000`: дефолтное поведение, копы преследуют всех.

## Полицейская расцветка игрока

Чит режима расцветки:

```text
800553F4 0000  выкл
800553F4 0001  расцветка по стране карты
800553F4 0002  кастомная расцветка
```

Для Raceway:

- Raceway: французская.
- Raceway 2: американская.
- Raceway 3: немецкая.

Цвет света мигалок соответствует расцветке машины:

- немецкая/английская: синий;
- французская: красный;
- американская/австралийская: красно-синий.

## Поворотники, мигалки и стробоскопы

- На гражданской машине игрока доступен режим двойного моргания полицейских/аварийных огней.
- По умолчанию этот режим выключен.
- Переключатель сделан через code-immediate cheat, чтобы не зависеть от чтения отдельного RAM-флага:

```text
80055148 000?  основной strobe gate
8005517C 000?  reverse-light object gate
800551B0 000?  reverse-light DrawC mask gate
```

Значения:

```text
0000  выкл
0001  вкл
```

- Поворотники сохранены в рабочей попеременной схеме.
- Ночная подсветка машин от мигалок доработана и работает не только в первом лице.
- Для ночной подсветки добавлена защита от мусорных указателей машины: перед чтением `car+0x8B4/0x8B6` проверяется, что указатель похож на нормальный PS1-адрес `0x80xxxxxx`. Это убрало ошибки вроде:

```text
Invalid halfword read ... pc 0x800552AC
```

## Сирена игрока

В текущей стабильной версии оставлен штатный чит выбора типа полицейской сирены:

```text
[Мои\Полицейская сирена]
Option = Обычная:0
Option = Особая:1
80055204 000?
80055258 000?
```

Этот пункт выбирает тип/режим уже установленного siren-cave.

Для гражданской машины игрока используется один общий DuckStation/GameShark-чит, объединяющий мигалки и сирену:

```text
[My\Civilian strobes and siren]
Option = Off:0
Option = On:1
8011F208 000?
80055148 000?
8005517C 000?
800551B0 000?
```

Внутри этого же пункта условными `D0`-кодами восстанавливаются или NOP'аются ветки сирены `80076554` и `80076568`.

Этот пункт включает звук сирены на обычной/неполицейской машине игрока старым стабильным способом, без новой встроенной логики в `NFS4.EXE`: DuckStation/GameShark-чит временно отключает две проверки в `AudioClc_SoundPlayersCar`:

- проверку, что `carInfo->carType` находится в диапазоне полицейских машин `0x16..0x1B`;
- проверку siren-bit'а `car+0x570 & 0x2`.

Значения:

```text
0  выкл, штатные мигалки/сирена
1  вкл, мигалки и звук сирены работают на обычной машине игрока
```

## Белые задние огни

Итоговая стабильная схема:

- При включенном cheat-gate белые задние огни гражданской машины игрока мигают двойным ритмом всегда, а не только при движении назад.
- При выключенном cheat-gate белые задние огни остаются в штатном режиме.
- Ритм синхронизирован с уже рабочим счетчиком мигалок `0x800550FC`.
- Полиция и copbot'ы не должны получать постоянное белое свечение.
- Штатное поведение полиции сохранено через проверку `carInfo->carType`, а не через `carFlags`.

Ключевые технические точки:

```text
R3DCar_InsertCarFacet case 0x11 hook:
  hook off      0xA1974
  cave off      0xE8350
  runtime cave  0x800F7B50

DrawC reverse mask hook:
  hook off      0xB0778
  cave off      0xE803C
  runtime cave  0x800F783C
```

Почему текущий фильтр именно такой:

- Маска `carFlags & 0x0220` оказалась слишком широкой: бит `0x20` цеплял гражданских/обычных участников, и белые задние у гражданских снова работали только при заднем ходе.
- Маска `carFlags & 0x0200` тоже была неправильной для этой задачи: она отсекала human/player car.
- Текущая стабильная версия проверяет `carInfo->carType` и считает полицейскими типы `0x16..0x1B`. Это не должно отсекать гражданскую машину игрока.

## ИИ гонщики

- В HP стабильно используется схема `2 ИИ гонщика + 4 копа`.
- Машину второго ИИ гонщика можно менять читом:

```text
801149E0 00??
80118960 00??
```

- Масса коллизии ИИ гонщиков регулируется параметризованным читом; дефолтная настроенная величина около `1.20M`.

## Трафик

Чит traffic/Raceway-фич:

```text
80054B7C 0001  вкл
80054B7C 0000  выкл
```

Итоговые изменения:

- В HP может добавляться третья traffic-машина.
- Замена третьей traffic-машины:

```text
80118CE4 00??
80114D64 00??
```

- В Raceway-картах traffic-модель заменена на `2C`.
- В Raceway-картах добавлен стабильный traffic:
  - HP: 1 traffic + копы сохранены;
  - Single Race: traffic тоже работает.
- При включенном `80054B7C 0001` `FRONT.BIN` держит HP night `maxTraffic = 2`, а hook на roving-traffic release check поднимает минимальный лимит активного traffic: до `5` машин в SR и до `2` машин в HP. Подтверждено пользователем: HP стартует с первого раза, ночью в HP 2 traffic-машины.
- В Tournament чит `80054B7C 0001` принудительно включает frontend traffic даже для турниров, где `fTraffic == 0`:
  - обычный Tournament: до 3 traffic-машин;
  - HP/special-event Tournament (`frontEnd.tier == 1`): 1 traffic-машина, чтобы итоговый состав `игрок + 3 ИИ + 4 копа + 1 traffic` не превышал лимит 9 машин.
- Для Tournament этот же release-check сокращает порог выпуска traffic до `2` кадров.
- Трафик уступает/тормозит для не-traffic машин.

## Damage только визуальный

Фича позволяет оставить `Damage` включенным в настройках игры, но убрать ослабление машин от повреждений. Визуальные повреждения и накопление damage остаются, а просадка ускорения/управления/торможения отключается.

Итоговый стабильный вариант сделан без изменения `NFS4.EXE`: используется один переключаемый DuckStation/GameShark-чит с условными `D0`-кодами.

```text
[Мои\Damage только визуальный]
Type = Gameshark
Activation = EndFrame
Option = Выкл:0
Option = Вкл:1
8011F204 000?
```

Значения:

```text
0  выкл, штатный damage ослабляет машины
1  вкл, damage остается только визуальным
```

Техническая схема:

- строка `8011F204 000?` задает значение опции;
- строки `D011F204 0000` условно восстанавливают штатные инструкции damage;
- строки `D011F204 0001` условно применяют visual-only инструкции;
- встроенный EXE-hook для этой фичи не используется, потому что варианты с hook'ом в `Physics_CalculateCarAcceleration` приводили к зависанию при завершении загрузки карты даже при выключенном чите.

## FRONT.BIN

`FRONT.BIN` текущей стабильной версии:

```text
5062835E2B00A6F7F96E8B4C5A38AF1C
```

В нем сохранены предыдущие PROD3-изменения фронтенда:

- настройки HP/SR состава гонки;
- поддержка второго ИИ гонщика;
- Raceway/traffic-связанные режимы;
- сохраненные правки, нужные для текущей схемы PROD3.

## Дополнительно

- Игрок и ИИ гонщики неуязвимы к полицейским шипам.
- Дополнительные cheat-коды машин PROD2/PROD3 были добавлены в список.
- Кодировка русского файла `Читы.txt` была исправлена ранее.
- В рабочей версии не используется HUD-overlay ареста и отдельный SFX ареста: эти эксперименты были признаны неудачными/отложенными.

## Поздние стабильные коммиты

Последняя серия правок после старого списка:

```text
d6f8cad Restore requested stable civilian siren state
13b515f Restore stable civilian siren build
30b7145 Add civilian player siren sound cheat
ca7c93b Emit conditional visual damage cheat toggle
4e255ac Revert "Add visual damage only cheat toggle"
e27c408 Revert "Use data flag for visual damage toggle"
2562023 Use car type for reverse light police filter
42e7ad6 Narrow reverse light police flag filter
239dbb3 Exclude police flags from reverse light mask blink
a7d30a0 Guard SR bust pullover HUD index
d2e28f2 Place reverse light cave after bust controls delay slot
42eee2a Move reverse light object cave away from bust cheat
90d8e0c Gate player bust controls to assigned target
f832e7d Guard player bust no-cops bypass
7f2939e Track PROD3 reverse blink and car cheat sync
```

Практический вывод из этой серии:

- Самая важная стабильная точка по белым задним огням: `2562023`.
- Самая важная стабильная точка по SR HUD/log error после ареста ИИ: `a7d30a0`.
- Самая важная стабильная точка по зависаниям от пересечения cave ареста и белых задних огней: `d2e28f2`.
- Самая важная стабильная точка по visual-only damage: `ca7c93b`.
- Самая важная стабильная точка по восстановленной объединенной схеме мигалок/сирены: `d6f8cad`.

## Что не повторять

- Не возвращать reverse-light object cave в `0x800F7A40/0x800F7A44`: это рядом с критичной областью чита ареста и уже приводило к зависаниям.
- Не использовать дальнюю cave-область `0x800FEA00`/`0xFF200` для reverse-light object hook: она давала зависания на загрузке карты.
- Не фильтровать белые задние огни полиции через `carFlags & 0x0220` или `carFlags & 0x0200`: оба варианта ломали гражданскую машину игрока.
- Не ставить глобально игроку `carFlags & 0x200` ради ареста ИИ: это ломает другие игровые пути SR/HP.
- Не возвращать эксперименты с HUD-overlay/SFX ареста без отдельного тестового бранча.
- Не возвращать встроенный `0/1` damage-toggle hook в `Physics_CalculateCarAcceleration`: он давал зависание на завершении загрузки карты с читами и без.

## Быстрая проверка после будущих изменений

Минимальный smoke test:

1. Test Race: старт гонки, машина игрока появилась, зависания нет.
2. Single Race: старт с ИИ, белые задние гражданской машины игрока мигают двойным ритмом при движении вперед.
3. HP/SR: старт с ИИ и копами, зависания нет.
4. HP/SR с читом ареста ИИ:

```text
800F7A00 0001
800F7B00 0001
```

5. Арестовать ИИ гонщика: видимых проблем и ошибок DuckStation быть не должно.
6. Проверить полицейскую машину/копов: белые задние не должны гореть постоянно.
7. Проверить поворотники: они должны оставаться попеременными, а не синхронными.
8. Проверить cheat-gate стробоскопов:

```text
80055148 0001
8005517C 0001
800551B0 0001
```

При `0001` моргание обычных машин должно включаться, при `0000` - выключаться.
9. Проверить `Damage только визуальный`: при `Выкл:0` damage должен ослаблять машину штатно, при `Вкл:1` повреждения должны оставаться визуальными без ослабления.
10. Проверить `Сирена на обычной машине игрока`: при `Вкл:1` на неполицейской машине игрока должен появиться звук сирены; тип сирены выбирается соседним читом `Полицейская сирена`.

Stable point confirmed by user on 2026-07-05 (player low LOD and player wheel visual steering are now cheat toggles):

```text
NFS4.EXE  22CD7C1CAD63E53210B64816E9D17497
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

Player visual toggles added after the tournament traffic stable point:

- Player low polygon LOD is stock/high by default and can be enabled with DuckStation cheat `[My\Player car low polygon LOD]` / flag `8011F210`.
- Player wheel steering animation is stock by default and can be disabled with DuckStation cheat `[My\Анимация поворота колес игрока]` / flag `8011F214`.
- Cheat fragments: `PROD3_player_low_lod_toggle.cht`, `PROD3_player_wheel_steer_toggle.cht`.

## Stable point: second HP AI model cheat

Confirmed by user on 2026-07-11:

```text
NFS4.EXE  33ADA99664FFBCE318A2007E9BEF41BC
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

`[???\???? X. ?????? ?? ?????? ? HP]` is handled by the player car-data sync cave at `0x800F7D00`:

```text
80054800 0000  same model as the first AI racer
80054800 00??  force a model ID for the second AI racer
```

The override is applied before the second AI car resources are loaded. It shares the previous stable behavior at `0000` and does not modify the working cop replacement cheats.

## Stable point: Snowy Ridge player cop livery

Confirmed by user on 2026-07-13:

```text
NFS4.EXE  E0AF4BD358694ED30DAE64375B9A9427
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

With player cop livery mode `800553F4 0001`, Snowy Ridge now uses the US/Canada country slot (`04`) instead of the German slot (`02`). The existing Raceway country mapping remains unchanged.

## Stable point: player-relative traffic respawn

Confirmed by user on 2026-07-13:

```text
NFS4.EXE  B4986CA7737FCBFEB6B8AFD87DE74ED4
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
```

Traffic reincarnation now uses the player as its only life-basis car:

- a new traffic position is chosen relative to the player;
- AI racers and cops cannot keep distant traffic active;
- traffic counts, release timing, and density remain unchanged.

Implementation: `patch_prod3_traffic_respawn_player_only.py`.

## Stable point: random HP night cop beacon source

Confirmed by user on 2026-07-14:

~~~text
NFS4.EXE  9790E6B86C5D4C12773D61DF7B2A25C4
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
~~~

At night in HP, an optional feature changes the environmental beacon-light
source between the player cop and active AI cops. The selected source is held
for about 171 simulation ticks, producing an observed interval of roughly
4-5 seconds. The player participates only while the player cop strobes are on.

The feature is disabled by default and controlled by:

~~~text
[Мои\Случайное переключение света мигалок в HP]
Option = Выкл:0
Option = Вкл:1
8011F224 000?
~~~

The DuckStation option synchronizes both code-immediate gates:

~~~text
800F7A64 0000  off
800F7AD4 0000  off
800F7A64 0004  on
800F7AD4 0004  on
~~~

Both gates must always use matching values. The timing code includes the PS1
load-delay NOP after reading simGlobal.gameTicks; removing it makes the source
effectively constant. Outside four-cop HP, selection remains stock.

Implementation files:

- patch_prod3_hp_random_cop_beacon.py
- PROD3_hp_random_cop_beacon_toggle.cht

## Stable point: second HP AI model selector options

Confirmed by user on 2026-07-16:

~~~text
NFS4.EXE  9790E6B86C5D4C12773D61DF7B2A25C4
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
~~~

`[Мои\Юнит X. Второй ИИ гонщик в HP]` now provides named model options for
the existing `80054800` override:

~~~text
80054800 0000       stock behavior: same model as the first AI racer
80054800 0001-0032  force the selected model ID
~~~

Model ID `00` (Mercedes SLK 230) is intentionally omitted from this selector,
because `0000` is reserved by the stable runtime hook for stock/shared behavior.
All IDs `01` through `32` remain available. The option list is stored in
`PROD3_unit_car_model_selectors.cht` and is mirrored in the active DuckStation
`NFS 4.cht` file.
## Stable point: configurable HP cop beacon-light distribution

Confirmed by user on 2026-07-24:

~~~text
NFS4.EXE  081501F9E01FE33C456AD826232254FA
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 91F0F5FC04132BB1C013F182398C4B57
~~~

The HP night beacon-light selector now provides four modes:

~~~text
0  stock/off
1  one held pseudo-random source
2  rapid distribution across all active AI cops
3  a held pseudo-random pair of eligible cop cars
~~~

Pair mode scans the player slot and four AI-cop slots. It excludes inactive
cars and cars whose beacon damage bit `car+0x87E & 4` is set. The player
participates when driving a cop car with active, working strobes. If only two
eligible sources remain, that pair stays selected.

The extended selector runs at `0x80054D00`. It preserves the stock loop
registers `t0-t4`; clobbering `t0` corrupts the cop-list pointer and causes
invalid reads at `0x8007E468`, `0x8007E480`, and `0x8007E494`.

The abandoned close-camera cheat and its `Camera_SetMode` hook were removed.
The map-selection cheat at `801158DA` was also removed from `NFS 4.cht`.
## Stable point: Australian police livery in Scotland

Confirmed by user on 2026-07-24:

~~~text
NFS4.EXE  821353C9879AE259B395BD953F436CF2
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 91F0F5FC04132BB1C013F182398C4B57
~~~

With player cop-livery mode `800553F4 0001`, Scotland/Celtic now selects
country slot `03` (Australian). Snowy Ridge remains US/Canada, while the
Raceway mappings remain French, US/Canada, and German respectively.
## Stable point: stock far camera and adjusted near camera

Confirmed by user on 2026-07-25:

~~~text
NFS4.EXE  5F9831602BE3B268C487AF78F2F996F2
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 12AA6F7F3865D50EF52D88E48F2CB0A8
~~~

When `[Мои\Изменение камер]` is enabled, the near gameplay camera remains
the custom mode `2` and uses a slightly increased distance of `-5.2`
(`8011083C/3E = CCCD/FFFA`). The gameplay far-camera assignment at
`80114924/26` is no longer overwritten, so the game retains its stock far
camera. The permanent shared camera constants in `NFS4.EXE` were restored
to their pre-camera values.

The active DuckStation cheat file and the project copy of `NFS 4.cht` have
the same MD5.
## Stable point: stock replay cameras

Confirmed by user on 2026-07-25:

~~~text
NFS4.EXE  572B1D32967A0976BED280B84257296E
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 2B46747E56E852C7D7C81B372E14E418
~~~

Replay camera switching and its camera table are restored to stock:

~~~text
19, 10, 11, 8, 9, 6, 4, 15, 0
~~~

The replay path no longer substitutes the player's gameplay camera modes.
The adjusted near gameplay camera, stock far gameplay camera, and permanent
replay HUD auto-hide behavior remain unchanged.
## Stable point: minimal near-camera cheat

Confirmed by user on 2026-07-25:

~~~text
NFS4.EXE  572B1D32967A0976BED280B84257296E
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 6636426D8A4905579498CFE23FB1AEB1
~~~

`[Мои\Изменение камер]` now has short Russian options:

~~~text
Выкл
Фикс. камера 2
~~~

The legacy replay, far-camera, camera-dispatch, and smoothing writes were
removed from this cheat. Its enabled branch changes only the near gameplay
camera and sets its distance to approximately `-5.4`
(`8011083C/3E = 999A/FFFA`). The stock far and replay cameras are untouched.
## Stable point: HP-only AI racer count cheat

Confirmed by user on 2026-07-25:

~~~text
NFS4.EXE  572B1D32967A0976BED280B84257296E
FRONT.BIN 83ECFCE7A1656659A6A2E8338F50BA6B
NFS 4.cht 6C0A219B9D1406D48CB43AF1786243B5
~~~

Every patch/write in `[Мои\HP. Количество ИИ гонщиков]` is now guarded by:

~~~text
D01158BC 0001
~~~

`801158BC = 1` identifies Hot Pursuit. The cheat therefore does not patch
the opponent-roster initialization while Test Drive or another race type is
active, preventing the Test Drive load failure at `PC=0xA0010000`.