"""OLX scraper va /olx buyrug'i testlari (OLX'ning o'ziga so'rov yuborilmaydi — lokal soxta server)."""
from __future__ import annotations

from aiohttp import web

from bot.scrapers.olx import OLXBlocked, OLXScraper, parse_offer, parse_proxy
from tests.conftest import free_port, run

SAMPLE = {"data": [{
    "title": "2 xonali kvartira <ijara>",
    "url": "https://www.olx.uz/d/obyavlenie/test-ID1.html",
    "params": [{"key": "price", "value": {"label": "3 000 000 so'm"}}],
    "location": {"city": {"name": "Chirchiq"}, "district": {"name": "Roshi"}},
    "photos": [{"link": "https://img.example/{width}x{height}.jpg"}],
}]}


def test_parse_proxy():
    assert parse_proxy("1.2.3.4:6014:user:pass") == "http://user:pass@1.2.3.4:6014"
    assert parse_proxy("1.2.3.4:8080") == "http://1.2.3.4:8080"
    assert parse_proxy("") is None and parse_proxy("# izoh") is None


def test_parse_offer():
    o = parse_offer(SAMPLE["data"][0])
    assert o.price == "3 000 000 so'm"
    assert o.location == "Chirchiq, Roshi"
    assert o.photo == "https://img.example/640x480.jpg"
    assert parse_offer({}).price == "—"


async def _with_server(status_ref: dict, fn):
    async def handler(_req):
        if status_ref["status"] != 200:
            return web.Response(status=status_ref["status"], text="blocked")
        return web.json_response(SAMPLE)

    app = web.Application()
    app.router.add_get("/api", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = free_port()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    try:
        return await fn(f"http://127.0.0.1:{port}/api")
    finally:
        await runner.cleanup()


def test_blocked_then_ok_and_cache():
    state = {"status": 403}

    async def scenario(url):
        sc = OLXScraper(proxies=[], api_url=url)
        try:
            await sc.latest()
            raise AssertionError("OLXBlocked kutilgan edi")
        except OLXBlocked:
            pass
        state["status"] = 200
        first = await sc.latest(5)
        state["status"] = 403  # kesh ishlashi kerak
        cached = await sc.latest(5)
        return first, cached

    first, cached = run(_with_server(state, scenario))
    assert len(first) == 1 and first == cached
    assert first[0].title == "2 xonali kvartira <ijara>"


def test_olx_handler_fallback_and_list(monkeypatch):
    from bot.handlers import user

    class Msg:
        def __init__(self):
            self.out = []

        async def answer(self, text, **kw):
            self.out.append(("answer", text, kw.get("reply_markup")))
            return self

        async def edit_text(self, text, **kw):
            self.out.append(("edit", text, kw.get("reply_markup")))
            return self

    state = {"status": 403}

    async def scenario(url):
        sc = OLXScraper(proxies=[], api_url=url)
        monkeypatch.setattr(user, "get_scraper", lambda: sc)
        blocked = Msg()
        await user.olx_offers(blocked, lang="uz")
        state["status"] = 200
        ok = Msg()
        await user.olx_offers(ok, lang="uz")
        return blocked, ok

    blocked, ok = run(_with_server(state, scenario))
    _, text, markup = blocked.out[-1]
    assert "OLX" in text
    btn = markup.inline_keyboard[0][0]
    assert btn.text == "🛒 OLXda" and btn.url.startswith("https://www.olx.uz/")
    _, text, _ = ok.out[-1]
    assert "&lt;ijara&gt;" in text and "3 000 000" in text


def test_menu_has_olx_button():
    from bot import keyboards as kb

    texts = [b.text for row in kb.user_menu("uz").keyboard for b in row]
    assert "📢 OLX e'lonlari" in texts


