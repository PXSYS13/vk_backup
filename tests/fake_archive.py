"""Поддельный архив данных ВК для тестов: та же разметка, что у настоящего (2026), но выдуманные люди.

Разметка повторяет страницы, которые ВК кладёт в архив: шапка с ui_crumb, записи
<div class="item">, сообщения с message__header и kludges, вложения attachment__description.
Кодировка — windows-1251, как у ВК.
"""

from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

OWNER_ID = 1001
PHOTO_URL = "https://sun9-11.userapi.com/impg/AAA/photo.jpg?size=800x600&quality=95&sign=abc&type=album"
VOICE_URL = "https://psv4.userapi.com/s/v1/amsg2/voice_abc.ogg"
DOC_URL = "https://psv4.userapi.com/s/v1/d/doc_abc/report.pdf"
THUMB_URL = "https://iv.okcdn.ru/getVideoPreview?id=1&idx=1&type=39&tkn=x&fn=vid_l"
AVATAR_URL = "https://sun9-12.userapi.com/s/v1/ig2/avatar.jpg?quality=95&ava=1"


def _jd() -> str:
    raw = json.dumps({"user_id": OWNER_ID, "time_current": 1778180891}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def page(crumbs: list[str], body: str, depth: int) -> str:
    up = "../" * depth
    trail = "".join(
        f'<a class="ui_crumb" href="{up}index.html" data-testid="header_link_crumb">{c}</a><div class="ui_crumb_sep"></div>'
        for c in crumbs[:-1])
    if crumbs:
        trail += f'<div class="ui_crumb" >{crumbs[-1]}</div>'
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="windows-1251">
  <meta name="jd" content="{_jd()}">
  <title>VK</title>
  <link rel="stylesheet" type="text/css" href="{up}style.css">
</head>
<body>
  <div class="wrap">
    <div class="page_content page_block">
      <h2 class="page_block_h2">
<div class="page_block_header clear_fix">
  <div class="page_block_header_inner _header_inner" data-testid="header">{trail}</div>
</div>
</h2>
      <div class="wrap_page_content">{body}</div>
    </div>
  </div>
</body>
</html>
"""


def msg(mid: int, header: str, text: str, kludges: str | None = "") -> str:
    tail = f'<div class="kludges">{kludges}</div>' if kludges is not None else ""
    return f"""<div class="item">
  <div class='item__main'><div class="message" data-id="{mid}">
  <div class="message__header">{header}</div>
  <div>{text}{tail}</div>
</div></div>


</div>"""


def att(description: str, href: str | None = None, text: str | None = None) -> str:
    link = f"\n  <a class='attachment__link' href='{href}'>{text or href}</a>" if href else ""
    return f'<div class="attachment">\n  <div class="attachment__description">{description}</div>{link}\n</div>'


PETR = '<a href="https://vk.com/id2002">Пётр Тестов</a>'


def files() -> dict[str, str]:
    f: dict[str, str] = {}
    f["index.html"] = page([], '<div class="item"><a class="menu__page-link" href="profile/page-info.html">Информация</a></div>', 0)
    f["messages/index-messages.html"] = page(["Профиль", "Сообщения"], """
  <div class="item">
  <div class='item__main'><div class="message-peer">
  <div class="message-peer--id">
    <a href="2002/messages0.html">Пётр Тестов</a>
  </div>
</div></div>
</div><div class="item">
  <div class='item__main'><div class="message-peer">
  <div class="message-peer--id">
    <a href="2000000001/messages0.html">Беседа &quot;Друзья&quot;</a>
  </div>
</div></div>
</div>""", 1)
    # Новые сообщения — на первой странице, как у ВК
    newest = "".join([
        msg(105, f"{PETR}, 2 янв 2015 в 10:00:05", "Смотри &#128049;<br>вторая строка", att("Фотография", PHOTO_URL)),
        msg(104, "Вы, 2 янв 2015 в 9:59:00<span class='message-edited' title='2 янв 2015 в 10:01:00'> (ред.)</span>",
            "исправленное", ""),
        msg(103, f"{PETR}, 1 янв 2015 в 23:00:00", "",
            att("Файл", VOICE_URL, "https://vk.com/doc2002_1") + att("1 прикреплённое сообщение")
            + att("Сообщение удалено")),
        msg(102, "Вы, 1 янв 2015 в 22:59:59", "держи файл",
            att("Файл", DOC_URL, "https://vk.com/doc1001_7") + att("Файл", "https://vk.com/doc1001_8")
            + att("Видеозапись", "https://vk.com/video1001_5", "https://vk.com/video1001_5")
            + att("Стикер") + att("Ссылка", "https://example.org/x?a=1&amp;b=2")),
    ]) + """<div class="pagination clear_fix">
  <div class="fl_r">
    <a class="pg_lnk_sel fl_l" href="messages0.html".html><div class="pg_in">1</div></a><a class="pg_lnk fl_l" href="messages50.html".html><div class="pg_in">2</div></a>
  </div>
</div>"""
    f["messages/2002/messages0.html"] = page(["Профиль", "Сообщения", "Пётр Тестов"], newest, 2)
    f["messages/2002/messages50.html"] = page(["Профиль", "Сообщения", "Пётр Тестов"], "".join([
        msg(101, f"{PETR}, 31 дек 2014 в 12:00:00", "С наступающим!", None),
        msg(100, "Вы, 30 дек 2014 в 8:05:00", "Привет &amp; пока &lt;b&gt;", ""),
    ]), 2)
    f["messages/2000000001/messages0.html"] = page(["Профиль", "Сообщения", "Беседа &quot;Друзья&quot;"], "".join([
        msg(201, '<a href="https://vk.com/id3003">Анна Пример</a>, 5 мар 2016 в 18:00:00', "",
            '<a class="im_srv_lnk " target="_blank" href="https://vk.com/id3003">Анна Пример</a> вышла из чата'),
        msg(200, '<a href="https://vk.com/club77">Сообщество</a>, 5 мар 2016 в 17:00:00', "Всем привет", ""),
    ]), 2)
    f["profile/page-info.html"] = page(["Профиль", "Информация о странице"], f"""
  <div class="item">
  <div class="item__tertiary">Фотография</div>
  <img class="fans_fan_img" src="{AVATAR_URL}">
</div>
<div class="item">
  <div class="item__tertiary">Полное имя</div>
  <div>Иван  Проверкин</div>
</div>
<div class="item">
  <div class="item__tertiary">Дата рождения</div>
  <div>01.02.1990</div>
</div>
<div class="item">
  <div class="item__tertiary">Дата регистрации</div>
  <div>27 мая 2008</div>
</div>""", 1)
    f["profile/friends0.html"] = page(["Профиль", "Друзья"], """<div class="item">
  <div class='item__main'><a href="https://vk.com/id2002">Пётр Тестов</a></div>
  <div class='item__tertiary'>26 мар 2026 в 13:23</div>
</div><div class="item">
  <div class='item__main'><a href="https://vk.com/id3003">Анна Пример</a></div>
  <div class='item__tertiary'>19 мар 2026 в 22:46</div>
</div>""", 1)
    f["photos/photo-albums.html"] = page(["Профиль", "Фотографии"], """
  <div class="item">
  <div class='item__main'><a href="photo-albums/555.html">Море: 2014?</a></div>
  <div class='item__tertiary'>Создан 29 окт 2025 в 13:09</div>
</div> <div class="item">
  <div class='item__main'><a href="photo-albums/-7.html">Фото на стене</a></div>
</div>""", 1)
    f["photos/photo-albums/555.html"] = page(["Профиль", "Фотографии", "Море: 2014?"], f"""<div class="item">
  <div class='item__main'><a href="https://vk.com/photo1001_9001"><img src="{PHOTO_URL}" alt="1001_9001"></a></div><div class='item__main'>Закат</div><div class='item__main'><a href="https://vk.com/photo1001_9001">vk.com/photo1001_9001</a></div>
  <div class='item__tertiary'></div><div class='item__tertiary'><div class="clear_fix">6 мая 2014 в 23:05 </div></div>
</div>""", 2)
    f["photos/photo-albums/-7.html"] = page(["Профиль", "Фотографии", "Фото на стене"], f"""<div class="item">
  <div class='item__main'><a href="https://vk.com/photo1001_9002"><img src="{PHOTO_URL}&n=2" alt="1001_9002"></a></div><div class='item__main'></div><div class='item__main'><a href="https://vk.com/photo1001_9002">vk.com/photo1001_9002</a></div>
  <div class='item__tertiary'></div><div class='item__tertiary'><div class="clear_fix">7 мая 2014 в 10:00 </div></div>
</div>""", 2)
    f["video/video-albums.html"] = page(["Профиль", "Видео"], """
  <div class="item">
  <div class='item__main'><a href="video-albums/-1.html">Загруженные</a></div>
</div>""", 1)
    f["video/video-albums/-1.html"] = page(["Профиль", "Видео", "Загруженные"], f"""<div class="item">
  <div class='item__main'><a href="https://vk.com/video1001_5">
  <div class="video-thumb">
      <div class="video-thumb__image" style="background-image: url({THUMB_URL});"></div>
  </div>
</a></div><div class='item__main'>Мой ролик</div><div class='item__main'>1:17:36 <span class="divider">|</span> 30 просмотров</div><div class='item__main'><a href="https://vk.com/video1001_5">vk.com/video1001_5</a></div>
  <div class='item__tertiary'><div class="clear_fix">1 мая 2016 в 17:49 <div class="fl_r"></div> </div></div>
</div>""", 2)
    f["audio/audio-albums/1/audios0.html"] = page(["Профиль", "Музыка", "Мне нравится"], """<div class="albums">
  <div class="item">
  <div class='item__main'><div class="clear_fix audio">
  <div class="fl_l audio__title">Кино &mdash; Группа крови</div><span class="fl_r audio__duration">4:45</span>
</div></div>
</div><div class="item">
  <div class='item__main'><div class="clear_fix audio">
  <div class="fl_l audio__title">Без исполнителя</div><span class="fl_r audio__duration">0:30</span>
</div></div>
</div></div>""", 4)
    f["wall/wall0.html"] = page(["Профиль", "Стена"], """<div class="item">
  <div class='item__main'><div>
  Первая запись
  <div class="kludges"><div class="attachment">
  <div class="attachment__description">Фотография</div>
  <a class='attachment__link' href='https://vk.com/photo1001_9002'>https://vk.com/photo1001_9002</a>
</div></div>
</div></div><div class='item__main'><div class='clear_fix'><a class="post__link fl_l" href="https://vk.com/wall1001_10">https://vk.com/wall1001_10</a></div></div>
  <div class='item__tertiary'><div class="clear_fix">
    <span>Вы 7 мая 2014 в 10:34</span>
    <div class="fl_r"><a href="10/comments0.html">Комментарии (1)</a></div>
</div></div>
</div><div class="item">
  <div class='item__main'><div>
  Запись от друга
  <div class="kludges"></div>
</div></div><div class='item__main'><div class='clear_fix'><a class="post__link fl_l" href="https://vk.com/wall1001_11">https://vk.com/wall1001_11</a></div></div>
  <div class='item__tertiary'><div class="clear_fix">
    <span><a href="https://vk.com/id2002">Пётр Тестов</a> 8 мая 2014 в 11:00</span>
    <div class="fl_r"></div>
</div></div>
</div>""", 1)
    f["wall/10/comments0.html"] = page(["Профиль", "Стена", "Комментарии"], """<div class="item">
  <div class='item__main'><div>
  Классное фото
  <div class="kludges"></div>
</div></div><div class='item__main'><div class='clear_fix'><a class="post__link fl_l" href="https://vk.com/wall1001_10?reply=12">https://vk.com/wall1001_10?reply=12</a></div></div>
  <div class='item__tertiary'><div class="clear_fix">
    <span><a href="https://vk.com/id3003">Анна Пример</a> 7 мая 2014 в 12:00</span>
    <div class="fl_r"></div>
</div></div>
</div>""", 2)
    f["profile/documents.html"] = page(["Профиль", "Файлы"], """
  <div class="item">
  <div class='item__main'><a href="https://vk.com/doc1001_7">report.pdf</a></div>
  <div class='item__tertiary'>19 апр 2016 в 10:06</div>
</div>""", 1)
    return f


def build(dest: Path, *, as_zip: bool = True, encoding: str = "cp1251", top_folder: str = "") -> Path:
    """Собирает архив: ZIP (как присылает ВК) или папку. top_folder — папка верхнего уровня внутри ZIP."""
    content = files()
    if as_zip:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as z:
            for name, text in content.items():
                z.writestr(top_folder + name, text.encode(encoding))
        return dest
    for name, text in content.items():
        p = dest / top_folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode(encoding))
    return dest
