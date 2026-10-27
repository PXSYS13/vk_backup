"""Разбор страниц архива ВК: даты, текст, вложения, все разделы."""

import time

import fake_archive
import pytest

from vkbackup import parse
from vkbackup.archive import Archive, NotAnArchive, decode


def _ts(y, mo, d, h=0, mi=0, s=0):
    return int(time.mktime((y, mo, d, h, mi, s, 0, 0, -1)))


@pytest.mark.parametrize("text, expected", [
    ("28 мая 2013 в 9:05:48", _ts(2013, 5, 28, 9, 5, 48)),
    ("Вы 7 мая 2026 в 21:15", _ts(2026, 5, 7, 21, 15)),
    ("27 мая 2008", _ts(2008, 5, 27)),
    ("1 сентября 2020 в 10:00", _ts(2020, 9, 1, 10, 0)),
    ("31 дек 2014 в 23:59:59", _ts(2014, 12, 31, 23, 59, 59)),
    ("вчера", None),
])
def test_parse_date(text, expected):
    assert parse.parse_date(text) == expected


def test_text_of_keeps_lines_and_entities():
    assert parse.text_of("Смотри &#128049;<br>вторая  строка &amp; <b>жирно</b>") == "Смотри 🐱\nвторая строка & жирно"


def test_owner_from_link():
    assert parse.owner_from_link("https://vk.com/id2002") == 2002
    assert parse.owner_from_link("https://vk.com/club77") == -77
    assert parse.owner_from_link("https://vk.ru/public5") == -5
    assert parse.owner_from_link("https://vk.com/durov") is None
    assert parse.owner_from_link("https://evil.com/vk.com/id1x") is None


def test_file_urls_only_from_vk_storage():
    assert parse.is_file_url(fake_archive.PHOTO_URL)
    assert parse.is_file_url(fake_archive.VOICE_URL)
    assert parse.is_file_url(fake_archive.THUMB_URL)
    assert not parse.is_file_url("https://vk.com/doc1_2")          # страница ВК — нужен вход
    assert not parse.is_file_url("https://userapi.com.evil.ru/x.jpg")
    assert not parse.is_file_url("https://example.org/x.jpg")
    assert not parse.is_file_url("javascript:alert(1)")


def test_decode_detects_encoding():
    text = "Привет, ёжик"
    assert decode(text.encode("cp1251")) == text
    assert decode(text.encode("utf-8")) == text
    assert decode(b"\xef\xbb\xbf" + text.encode("utf-8")) == text


@pytest.fixture
def archive(archive_zip):
    with Archive(archive_zip) as a:
        yield a


def test_archive_owner_and_names(archive):
    assert archive.owner_id() == fake_archive.OWNER_ID
    assert archive.names(r"messages/-?\d+/messages\d+\.html") == [
        "messages/2000000001/messages0.html", "messages/2002/messages0.html", "messages/2002/messages50.html"]


def test_archive_zip_with_top_folder_and_plain_folder(tmp_path):
    z = fake_archive.build(tmp_path / "a.zip", top_folder="Archive/")
    with Archive(z) as a:
        assert a.exists("messages/index-messages.html")
    d = fake_archive.build(tmp_path / "unpacked", as_zip=False, top_folder="Archive/", encoding="utf-8")
    with Archive(d) as a:
        assert a.owner_id() == fake_archive.OWNER_ID


def test_not_an_archive(tmp_path):
    (tmp_path / "x.zip").write_bytes(b"not a zip")
    with pytest.raises(NotAnArchive):
        Archive(tmp_path / "x.zip")
    (tmp_path / "empty").mkdir()
    with pytest.raises(NotAnArchive):
        Archive(tmp_path / "empty")
    with pytest.raises(NotAnArchive):
        Archive(tmp_path / "missing.zip")


def test_read_refuses_paths_outside_list(archive):
    with pytest.raises(FileNotFoundError):
        archive.read("../../etc/passwd")


def test_messages_page(archive):
    msgs = parse.messages_page(archive.read("messages/2002/messages0.html"))
    by_id = {m["id"]: m for m in msgs}
    assert sorted(by_id) == [102, 103, 104, 105]
    m = by_id[105]
    assert m["from_id"] == 2002 and m["from_name"] == "Пётр Тестов" and not m["out"]
    assert m["text"] == "Смотри 🐱\nвторая строка"
    assert m["date"] == _ts(2015, 1, 2, 10, 0, 5)
    assert m["attachments"] == [{"kind": "photo", "label": "Фотография", "url": fake_archive.PHOTO_URL}]
    assert by_id[104]["out"] and by_id[104]["edited"] and by_id[104]["text"] == "исправленное"
    kinds = [a["kind"] for a in by_id[103]["attachments"]]
    assert kinds == ["voice", "fwd", "deleted"]
    assert by_id[103]["attachments"][0]["link"] == "https://vk.com/doc2002_1"
    files = by_id[102]["attachments"]
    assert [a["kind"] for a in files] == ["file", "file", "video", "sticker", "link"]
    assert files[0]["url"] == fake_archive.DOC_URL
    assert "url" not in files[1] and files[1]["link"] == "https://vk.com/doc1001_8"
    assert files[4]["link"] == "https://example.org/x?a=1&b=2"
    # Пагинацию внизу страницы не принимаем за текст сообщения
    assert "service" not in by_id[102]


def test_message_without_kludges_and_service(archive):
    older = {m["id"]: m for m in parse.messages_page(archive.read("messages/2002/messages50.html"))}
    assert older[101]["text"] == "С наступающим!"
    assert older[100]["text"] == "Привет & пока <b>"
    chat = {m["id"]: m for m in parse.messages_page(archive.read("messages/2000000001/messages0.html"))}
    assert chat[201]["service"] == "Анна Пример вышла из чата" and chat[201]["text"] == ""
    assert chat[200]["from_id"] == -77


def test_chat_list_and_crumbs(archive):
    assert parse.chat_list(archive.read("messages/index-messages.html")) == [
        ("2002", "Пётр Тестов"), ("2000000001", 'Беседа "Друзья"')]
    assert parse.crumbs(archive.read("messages/2002/messages0.html"))[-1] == "Пётр Тестов"


def test_profile_friends_photos(archive):
    info = parse.page_info(archive.read("profile/page-info.html"))
    assert info["name"] == "Иван Проверкин"
    assert info["avatar_url"] == fake_archive.AVATAR_URL
    assert ("Дата рождения", "01.02.1990") in info["info"]
    friends = parse.friends_page(archive.read("profile/friends0.html"))
    assert friends[0] == {"id": 2002, "name": "Пётр Тестов", "link": "https://vk.com/id2002",
                          "added": _ts(2026, 3, 26, 13, 23)}
    albums = parse.album_list(archive.read("photos/photo-albums.html"))
    assert [a["key"] for a in albums] == ["555", "-7"]
    photos = parse.photos_page(archive.read("photos/photo-albums/555.html"))
    assert photos == [{"key": "1001_9001", "url": fake_archive.PHOTO_URL,
                       "link": "https://vk.com/photo1001_9001", "text": "Закат",
                       "date": _ts(2014, 5, 6, 23, 5)}]


def test_videos_music_docs_wall(archive):
    videos = parse.videos_page(archive.read("video/video-albums/-1.html"))
    assert videos[0]["key"] == "1001_5" and videos[0]["title"] == "Мой ролик"
    assert videos[0]["duration"] == "1:17:36" and videos[0]["views"] == 30
    assert videos[0]["thumb_url"] == fake_archive.THUMB_URL
    tracks = parse.audios_page(archive.read("audio/audio-albums/1/audios0.html"))
    assert tracks == [{"artist": "Кино", "title": "Группа крови", "duration": "4:45"},
                      {"artist": "", "title": "Без исполнителя", "duration": "0:30"}]
    docs = parse.documents_page(archive.read("profile/documents.html"))
    assert docs[0]["title"] == "report.pdf" and docs[0]["url"] is None
    posts = parse.wall_page(archive.read("wall/wall0.html"))
    assert posts[0]["id"] == 10 and posts[0]["out"] and posts[0]["text"] == "Первая запись"
    assert posts[0]["comments_page"] == "10/comments0.html" and posts[0]["comments_count"] == 1
    assert posts[0]["attachments"][0]["link"] == "https://vk.com/photo1001_9002"
    assert posts[1]["author"] == "Пётр Тестов" and posts[1]["author_id"] == 2002
    comments = parse.wall_page(archive.read("wall/10/comments0.html"))
    assert comments[0]["id"] == 12 and comments[0]["post_id"] == 10 and comments[0]["author"] == "Анна Пример"
