# PROD3 Hypercycle Stable Context

Дата фиксации: 2026-06-01.

Этот файл описывает текущую стабильную PROD3-версию мода Hypercycle для DuckStation:

```text
PROD 3 версия. DuckStation. Need for Speed - High Stakes (USA) — Мод Hypercycle
```

## Стабильная версия

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
