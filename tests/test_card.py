"""Card loading: www copy, dashboard resource, versions (needs the homeassistant package)."""
import asyncio
import gzip
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

from custom_components.smart_heating import card  # noqa: E402
from custom_components.smart_heating.const import VERSION  # noqa: E402


def test_versions_match():
    manifest = json.loads((ROOT / "custom_components/smart_heating/manifest.json").read_text())["version"]
    js = re.search(r'const CARD_VERSION = "([^"]+)"', card.SOURCE.read_text()).group(1)
    readme = re.search(r"^Version (\S+)\. ", (ROOT / "README.md").read_text(), re.M).group(1)
    assert manifest == VERSION == js == readme


def test_copy_to_www(tmp_path):
    card.copy_to_www(tmp_path)
    js, gz = tmp_path / "smart_heating" / card.NAME, tmp_path / "smart_heating" / f"{card.NAME}.gz"
    data = card.SOURCE.read_bytes()
    assert js.read_bytes() == data and gzip.decompress(gz.read_bytes()) == data
    assert gz.stat().st_size < len(data) / 2
    stamp = (js.stat().st_mtime_ns, gz.stat().st_mtime_ns)
    card.copy_to_www(tmp_path)
    assert (js.stat().st_mtime_ns, gz.stat().st_mtime_ns) == stamp, "unchanged card is not rewritten"
    gz.write_bytes(gzip.compress(b"old card"))
    card.copy_to_www(tmp_path)
    assert gzip.decompress(gz.read_bytes()) == data, "a stale .gz is replaced"
    (tmp_path / "smart_heating" / "mine.txt").write_text("x")
    card.remove_from_www(tmp_path)
    assert not js.exists() and not gz.exists() and (tmp_path / "smart_heating" / "mine.txt").exists()


def test_local_served(tmp_path):
    router = web.UrlDispatcher()
    hass = SimpleNamespace(http=SimpleNamespace(app=SimpleNamespace(router=router)))
    assert not card.local_served(hass)
    router.register_resource(web.StaticResource("/local", str(tmp_path)))
    assert card.local_served(hass)


class Resources:
    """Stand-in for HA's dashboard resource storage collection."""

    def __init__(self, items=()):
        self.items = {str(i): dict(it, id=str(i)) for i, it in enumerate(items)}
        self.loaded = False

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self.items.values())

    async def async_create_item(self, data):
        rid = f"new{len(self.items)}"
        self.items[rid] = {"id": rid, "type": data["res_type"], "url": data["url"]}

    async def async_update_item(self, rid, data):
        self.items[rid].update(type=data["res_type"], url=data["url"])

    async def async_delete_item(self, rid):
        del self.items[rid]


def test_sync_resource():
    other = {"type": "module", "url": "/hacsfiles/button-card/button-card.js?hacstag=1"}
    res = Resources([other])
    asyncio.run(card.sync_resource(res, "/local/smart_heating/smart-heating-card.js?v=1"))
    assert res.loaded
    assert sorted(r["url"] for r in res.async_items()) == sorted([other["url"], "/local/smart_heating/smart-heating-card.js?v=1"])
    # An update moves it to the new version; duplicates (also hand-made ones) go.
    res = Resources([other, {"type": "module", "url": "/smart_heating/smart-heating-card.js?v=0.13.0"},
                     {"type": "js", "url": "/local/smart_heating/smart-heating-card.js"}])
    asyncio.run(card.sync_resource(res, "/local/smart_heating/smart-heating-card.js?v=2"))
    ours = [r for r in res.async_items() if "smart-heating" in r["url"]]
    assert ours == [{"id": "1", "type": "module", "url": "/local/smart_heating/smart-heating-card.js?v=2"}]
    assert other["url"] in [r["url"] for r in res.async_items()]


def _hass(tmp_path, resources, local=True):
    router = web.UrlDispatcher()
    if local:
        router.register_resource(web.StaticResource("/local", str(tmp_path)))
    extra = SimpleNamespace(urls=set())
    extra.add, extra.remove = extra.urls.add, extra.urls.discard

    async def register_static(paths):
        for p in paths:
            router.register_resource(web.StaticResource(p.url_path, str(Path(p.path).parent)))

    async def executor(func, *args):
        return func(*args)

    return SimpleNamespace(
        data={"lovelace": SimpleNamespace(resources=resources), "frontend_extra_module_url": extra},
        http=SimpleNamespace(app=SimpleNamespace(router=router), async_register_static_paths=register_static),
        config=SimpleNamespace(path=lambda *p: str(tmp_path.joinpath(*p))),
        async_add_executor_job=executor,
    ), extra


def test_register_update_remove(tmp_path):
    res = Resources([{"type": "module", "url": "/local/smart_heating/smart-heating-card.js?v=0.0.1"}])
    hass, extra = _hass(tmp_path, res)
    want = f"/local/smart_heating/smart-heating-card.js?v={VERSION}"
    asyncio.run(card.async_register_card(hass))
    assert [r["url"] for r in res.async_items()] == [want], "resource follows the installed version"
    assert extra.urls == {want}, "same URL as the resource: the browser loads it once"
    assert (tmp_path / "www" / "smart_heating" / card.NAME).exists()
    asyncio.run(card.async_register_card(hass))
    assert len(res.async_items()) == 1 and extra.urls == {want}
    asyncio.run(card.async_remove_card(hass))
    assert res.async_items() == [] and extra.urls == set()
    assert not (tmp_path / "www" / "smart_heating").exists()


def test_register_fallbacks(tmp_path):
    # /local not served yet (www created after HA started): the integration's own path.
    res = Resources()
    hass, extra = _hass(tmp_path, res, local=False)
    asyncio.run(card.async_register_card(hass))
    own = f"/smart_heating/smart-heating-card.js?v={VERSION}"
    assert [r["url"] for r in res.async_items()] == [own] and extra.urls == {own}
    # Resources in YAML: no collection to write to, the extra module still loads the card.
    hass, extra = _hass(tmp_path, SimpleNamespace())
    asyncio.run(card.async_register_card(hass))
    assert extra.urls == {f"/local/smart_heating/smart-heating-card.js?v={VERSION}"}
